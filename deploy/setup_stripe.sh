#!/bin/bash
# =============================================================================
# Stripe - Setup automatizado para produção (VPS + Docker)
# =============================================================================
# Este script configura TODO o Stripe necessário para produção:
#
#   1. Instala o Stripe CLI no host (opcional, útil para debug)
#   2. Cria o webhook endpoint no Stripe via API
#   3. Grava o STRIPE_WEBHOOK_SECRET no .env automaticamente
#
# Uso:
#   sudo ./deploy/setup_stripe.sh
#   sudo ./deploy/setup_stripe.sh --skip-cli   # Pula instalação do CLI
#   sudo ./deploy/setup_stripe.sh --help
#
# Pré-requisitos:
#   - STRIPE_SECRET_KEY já configurado no .env
#   - STRIPE_PRICE_ID_* já configurados no .env
#   - Python (ou Docker) disponível para rodar o Flask CLI
# =============================================================================

set -euo pipefail

# --------------- cores ---------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[info]${NC}  $*"; }
ok()    { echo -e "${GREEN}[ok]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC}  $*"; }
fail()  { echo -e "${RED}[erro]${NC}  $*"; exit 1; }

# --------------- defaults ---------------
SKIP_CLI=false
WEBHOOK_URL=""
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${PROJECT_DIR}/.env"
DEPLOY_DIR="${PROJECT_DIR}/deploy"

# --------------- usage ---------------
usage() {
    echo "Uso: sudo $0 [opções]"
    echo ""
    echo "Opções:"
    echo "  --url URL         URL do webhook (ex: https://rotulagem.terracotabpo.com/billing/webhook)"
    echo "  --skip-cli        Não instalar o Stripe CLI no host"
    echo "  --help            Mostra esta ajuda"
    echo ""
    echo "Exemplo:"
    echo "  sudo $0 --url https://rotulagem.terracotabpo.com/billing/webhook"
    exit 0
}

# --------------- parse args ---------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-cli)   SKIP_CLI=true; shift ;;
        --url)        WEBHOOK_URL="$2"; shift 2 ;;
        --help|-h)    usage ;;
        *)            fail "Argumento desconhecido: $1. Use --help." ;;
    esac
done

# --------------- checks ---------------
if [ "$(id -u)" -ne 0 ]; then
    fail "Execute como root ou com sudo: sudo $0"
fi

echo ""
echo -e "${BLUE}===========================================${NC}"
echo -e "${BLUE}  Stripe - Setup Automático (Produção)${NC}"
echo -e "${BLUE}===========================================${NC}"
echo ""

# 1. Verify .env exists and has STRIPE_SECRET_KEY
if [ ! -f "$ENV_FILE" ]; then
    fail ".env não encontrado em ${ENV_FILE}. Crie a partir do .env.example primeiro."
fi

STRIPE_SECRET_KEY=$(grep -E '^STRIPE_SECRET_KEY=' "$ENV_FILE" | cut -d'=' -f2- | tr -d '[:space:]')
if [ -z "$STRIPE_SECRET_KEY" ] || [ "$STRIPE_SECRET_KEY" = "sk_test_..." ]; then
    fail "STRIPE_SECRET_KEY não configurada no .env. Configure antes de rodar este script."
fi
ok "STRIPE_SECRET_KEY encontrada no .env"

# Check price IDs
MISSING_PRICES=0
for PRICE_VAR in STRIPE_PRICE_ID_FLOW_START STRIPE_PRICE_ID_FLOW_PRO STRIPE_PRICE_ID_FLOW_STUDIO; do
    PRICE_VAL=$(grep -E "^${PRICE_VAR}=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '[:space:]')
    if [ -z "$PRICE_VAL" ] || [ "$PRICE_VAL" = "price_..." ]; then
        warn "${PRICE_VAR} não configurado (placeholder ou vazio)"
        MISSING_PRICES=$((MISSING_PRICES + 1))
    else
        ok "${PRICE_VAR} = ${PRICE_VAL}"
    fi
done

if [ "$MISSING_PRICES" -gt 0 ]; then
    warn "${MISSING_PRICES} price ID(s) ainda com placeholder. Configure no .env após criar os produtos no Stripe Dashboard."
fi

echo ""

# ===========================================================================
# 2. Install Stripe CLI (optional)
# ===========================================================================
if [ "$SKIP_CLI" = false ]; then
    info "Passo 1: Instalando Stripe CLI no host..."
    if command -v stripe &>/dev/null; then
        STRIPE_VER=$(stripe version 2>/dev/null || stripe --version 2>/dev/null || echo "?")
        ok "Stripe CLI já instalado (${STRIPE_VER})"
    else
        if [ -x "${DEPLOY_DIR}/install_stripe_cli.sh" ]; then
            bash "${DEPLOY_DIR}/install_stripe_cli.sh"
        else
            warn "Script install_stripe_cli.sh não encontrado — instalando inline..."
            apt-get update -qq
            apt-get install -y --no-install-recommends curl gnupg > /dev/null 2>&1
            curl -fsSL https://packages.stripe.dev/api/security/keypair/stripe-cli-gpg/public \
                | gpg --dearmor -o /usr/share/keyrings/stripe-archive-keyring.gpg 2>/dev/null
            echo "deb [signed-by=/usr/share/keyrings/stripe-archive-keyring.gpg] https://packages.stripe.dev/stripe-cli-debian-local stable main" \
                > /etc/apt/sources.list.d/stripe.list
            apt-get update -qq
            apt-get install -y stripe
            ok "Stripe CLI instalado"
        fi
    fi
    echo ""
else
    info "Passo 1: Instalação do Stripe CLI pulada (--skip-cli)"
    echo ""
fi

# ===========================================================================
# 3. Create webhook endpoint via Flask CLI (inside Docker or host)
# ===========================================================================
info "Passo 2: Criando webhook endpoint no Stripe..."

# Ask for URL if not provided
if [ -z "$WEBHOOK_URL" ]; then
    echo ""
    echo -e "${YELLOW}Informe a URL pública do webhook (ex: https://rotulagem.terracotabpo.com/billing/webhook):${NC}"
    read -r WEBHOOK_URL
fi

if [ -z "$WEBHOOK_URL" ]; then
    fail "URL do webhook é obrigatória."
fi

# Validate URL format
if [[ ! "$WEBHOOK_URL" =~ ^https:// ]]; then
    warn "URL não começa com https:// — Stripe exige HTTPS em produção."
fi

echo ""
info "URL do webhook: ${WEBHOOK_URL}"
echo ""

# Try via Docker first (if container is running), else try local Flask CLI
WEBHOOK_CREATED=false

if docker compose -f "${DEPLOY_DIR}/docker-compose.yml" ps --status running 2>/dev/null | grep -q "tabela_nutricional_web"; then
    info "Container Docker ativo — rodando Flask CLI via Docker..."
    docker compose -f "${DEPLOY_DIR}/docker-compose.yml" exec -T web \
        flask setup-stripe-webhook "$WEBHOOK_URL" --update-env && WEBHOOK_CREATED=true
elif command -v flask &>/dev/null; then
    info "Rodando Flask CLI localmente..."
    cd "$PROJECT_DIR"
    flask setup-stripe-webhook "$WEBHOOK_URL" --update-env && WEBHOOK_CREATED=true
elif command -v python3 &>/dev/null; then
    info "Rodando via python -m flask..."
    cd "$PROJECT_DIR"
    python3 -m flask setup-stripe-webhook "$WEBHOOK_URL" --update-env && WEBHOOK_CREATED=true
else
    fail "Nenhum método disponível para rodar Flask CLI (Docker, flask, python3). Instale Python ou inicie o container."
fi

echo ""

if [ "$WEBHOOK_CREATED" = true ]; then
    ok "Webhook endpoint configurado!"
else
    warn "Não foi possível criar o endpoint automaticamente."
    echo ""
    echo -e "${YELLOW}Alternativa manual:${NC}"
    echo "  1. Acesse: https://dashboard.stripe.com/webhooks"
    echo "  2. Add endpoint → URL: ${WEBHOOK_URL}"
    echo "  3. Selecione eventos:"
    echo "     - checkout.session.completed"
    echo "     - customer.subscription.created"
    echo "     - customer.subscription.updated"
    echo "     - customer.subscription.deleted"
    echo "     - invoice.payment_succeeded"
    echo "     - invoice.payment_failed"
    echo "  4. Copie o Signing secret (whsec_...) para .env como STRIPE_WEBHOOK_SECRET"
fi

# ===========================================================================
# 4. Verify final state
# ===========================================================================
echo ""
info "Passo 3: Verificação final do .env..."

WEBHOOK_SECRET=$(grep -E '^STRIPE_WEBHOOK_SECRET=' "$ENV_FILE" | cut -d'=' -f2- | tr -d '[:space:]')
if [ -n "$WEBHOOK_SECRET" ] && [ "$WEBHOOK_SECRET" != "whsec_..." ]; then
    ok "STRIPE_WEBHOOK_SECRET configurado ✓"
else
    warn "STRIPE_WEBHOOK_SECRET ainda com placeholder. Configure manualmente."
fi

echo ""
echo -e "${GREEN}===========================================${NC}"
echo -e "${GREEN}  Setup Stripe concluído!${NC}"
echo -e "${GREEN}===========================================${NC}"
echo ""
echo -e "${YELLOW}Checklist:${NC}"
echo "  [$([ -n "$STRIPE_SECRET_KEY" ] && echo 'x' || echo ' ')] STRIPE_SECRET_KEY"
echo "  [$([ -n "$WEBHOOK_SECRET" ] && [ "$WEBHOOK_SECRET" != "whsec_..." ] && echo 'x' || echo ' ')] STRIPE_WEBHOOK_SECRET"
for PRICE_VAR in STRIPE_PRICE_ID_FLOW_START STRIPE_PRICE_ID_FLOW_PRO STRIPE_PRICE_ID_FLOW_STUDIO; do
    PRICE_VAL=$(grep -E "^${PRICE_VAR}=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2- | tr -d '[:space:]')
    echo "  [$([ -n "$PRICE_VAL" ] && [ "$PRICE_VAL" != "price_..." ] && echo 'x' || echo ' ')] ${PRICE_VAR}"
done
echo ""
echo -e "${YELLOW}Próximos passos:${NC}"
echo "  1. Se faltam price IDs, crie produtos no Stripe Dashboard:"
echo "     https://dashboard.stripe.com/products"
echo "  2. Reinicie a aplicação para carregar as novas variáveis:"
echo "     docker compose -f deploy/docker-compose.yml restart"
echo "  3. Teste o webhook (Stripe CLI no host):"
echo "     stripe trigger checkout.session.completed"
echo ""
echo -e "  Docs completos: ${BLUE}docs/STRIPE_SETUP.md${NC}"
echo ""
