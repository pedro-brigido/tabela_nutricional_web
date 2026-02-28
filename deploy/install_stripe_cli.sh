#!/bin/bash
# =============================================================================
# Stripe CLI - Instalação automatizada para Linux (VPS / Docker host)
# =============================================================================
# Baseado em: https://docs.stripe.com/stripe-cli/install?install-method=linux
#
# Uso:
#   sudo ./install_stripe_cli.sh              # Instala ou atualiza o Stripe CLI
#   sudo ./install_stripe_cli.sh --uninstall  # Remove o Stripe CLI
#
# Após instalar:
#   stripe login                              # Autenticar com sua conta Stripe
#   stripe listen --forward-to localhost:5000/billing/webhook
# =============================================================================

set -euo pipefail

# --------------- cores ---------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# --------------- helpers ---------------
info()    { echo -e "${BLUE}[info]${NC}  $*"; }
ok()      { echo -e "${GREEN}[ok]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[warn]${NC}  $*"; }
fail()    { echo -e "${RED}[erro]${NC}  $*"; exit 1; }

need_root() {
    if [ "$(id -u)" -ne 0 ]; then
        fail "Execute como root ou com sudo: sudo $0 $*"
    fi
}

# --------------- uninstall ---------------
uninstall_stripe_cli() {
    need_root
    info "Removendo Stripe CLI..."

    apt-get remove -y stripe 2>/dev/null && ok "Pacote 'stripe' removido" \
        || warn "Pacote 'stripe' não estava instalado via apt"

    # Remove repo e chave
    rm -f /etc/apt/sources.list.d/stripe.list
    rm -f /usr/share/keyrings/stripe-archive-keyring.gpg
    apt-get update -qq

    ok "Stripe CLI desinstalado com sucesso"
    exit 0
}

# --------------- install ---------------
install_stripe_cli() {
    need_root

    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  Stripe CLI - Instalação Linux (apt)${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""

    # 1. Dependências básicas
    info "Instalando dependências (curl, gnupg)..."
    apt-get update -qq
    apt-get install -y --no-install-recommends curl gnupg > /dev/null 2>&1
    ok "Dependências instaladas"

    # 2. Adicionar chave GPG do repositório Stripe
    info "Adicionando chave GPG do Stripe..."
    curl -fsSL https://packages.stripe.dev/api/security/keypair/stripe-cli-gpg/public \
        | gpg --dearmor -o /usr/share/keyrings/stripe-archive-keyring.gpg 2>/dev/null
    ok "Chave GPG adicionada em /usr/share/keyrings/stripe-archive-keyring.gpg"

    # 3. Adicionar repositório apt
    info "Configurando repositório apt do Stripe..."
    echo "deb [signed-by=/usr/share/keyrings/stripe-archive-keyring.gpg] https://packages.stripe.dev/stripe-cli-debian-local stable main" \
        > /etc/apt/sources.list.d/stripe.list
    ok "Repositório adicionado em /etc/apt/sources.list.d/stripe.list"

    # 4. Instalar (ou atualizar)
    info "Instalando Stripe CLI via apt..."
    apt-get update -qq
    apt-get install -y stripe
    ok "Stripe CLI instalado"

    # 5. Verificar
    echo ""
    if command -v stripe &>/dev/null; then
        STRIPE_VERSION=$(stripe version 2>/dev/null || stripe --version 2>/dev/null || echo "desconhecida")
        ok "stripe encontrado no PATH — versão: ${STRIPE_VERSION}"
    else
        fail "Instalação concluída mas o binário 'stripe' não foi encontrado no PATH"
    fi

    # 6. Resumo pós-instalação
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Instalação concluída!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${YELLOW}Próximos passos:${NC}"
    echo ""
    echo "  1. Autenticar com sua conta Stripe:"
    echo "       stripe login"
    echo ""
    echo "  2. Encaminhar webhooks para a aplicação local:"
    echo "       stripe listen --forward-to localhost:5000/billing/webhook"
    echo ""
    echo "  3. Copie o webhook signing secret (whsec_...) exibido pelo CLI"
    echo "     e atualize no .env:"
    echo "       STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxx"
    echo ""
    echo "  4. Para encaminhar webhooks ao container Docker:"
    echo "       stripe listen --forward-to http://localhost:5000/billing/webhook"
    echo "     (certifique-se de que a porta 5000 esteja exposta no docker-compose)"
    echo ""
    echo -e "  Docs completos: ${BLUE}docs/STRIPE_SETUP.md${NC}"
    echo ""
}

# --------------- main ---------------
case "${1:-}" in
    --uninstall|-u)
        uninstall_stripe_cli
        ;;
    --help|-h)
        echo "Uso: sudo $0 [--uninstall | --help]"
        echo ""
        echo "  (sem args)    Instala ou atualiza o Stripe CLI"
        echo "  --uninstall   Remove o Stripe CLI e o repositório apt"
        echo "  --help        Mostra esta ajuda"
        exit 0
        ;;
    *)
        install_stripe_cli
        ;;
esac
