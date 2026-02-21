#!/bin/bash
# =============================================================================
# Tabela Nutricional Web - Script de Deploy para VPS
# =============================================================================
# Este script automatiza o deploy em um VPS (Hostinger, DigitalOcean, etc.)
# Requisitos: Ubuntu 20.04+ ou Debian 11+, Docker e Docker Compose instalados
# =============================================================================

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}  Tabela Nutricional Web - Deploy VPS${NC}"
echo -e "${BLUE}======================================${NC}"
echo ""

# Verificar se está rodando como root ou com sudo
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Este script precisa ser executado como root ou com sudo${NC}"
    echo "Execute: sudo $0"
    exit 1
fi

# Detectar diretório do script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# =============================================================================
# PASSO 0: Verificações Preliminares
# =============================================================================
echo -e "${YELLOW}Passo 0: Verificações preliminares...${NC}"

# Verificar Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker não encontrado. Instale Docker primeiro.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker instalado${NC}"

# Verificar Docker Compose
if ! docker compose version &> /dev/null; then
    echo -e "${RED}✗ Docker Compose não encontrado. Instale Docker Compose primeiro.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose instalado${NC}"

echo ""

# =============================================================================
# PASSO 1: Criar rede Docker compartilhada (se não existir)
# =============================================================================
echo -e "${YELLOW}Passo 1: Verificando rede Docker compartilhada...${NC}"

if ! docker network ls | grep -q "terracota_network"; then
    echo "Criando rede Docker compartilhada 'terracota_network'..."
    docker network create terracota_network
    echo -e "${GREEN}✓ Rede 'terracota_network' criada${NC}"
else
    echo -e "${GREEN}✓ Rede 'terracota_network' já existe${NC}"
fi

echo ""

# =============================================================================
# PASSO 2: Build e Start dos containers
# =============================================================================
echo -e "${YELLOW}Passo 2: Iniciando containers...${NC}"

# Parar containers existentes se houver
echo "Parando containers existentes..."
docker compose down 2>/dev/null || true

# Build das imagens
echo ""
echo "Building Docker image (isso pode levar alguns minutos)..."
docker compose build

# Limpeza após build
echo ""
echo "Limpando recursos Docker após build..."
docker image prune -f 2>/dev/null || true

# Iniciar containers
echo ""
echo "Iniciando containers..."
docker compose up -d

echo ""

# =============================================================================
# PASSO 3: Verificar health
# =============================================================================
echo -e "${YELLOW}Passo 3: Verificando saúde dos serviços...${NC}"

# Aguardar inicialização
echo "Aguardando serviços iniciarem..."
sleep 10

# Verificar containers
echo ""
docker compose ps

# Verificar health do web
echo ""
echo "Verificando endpoint /health..."
for i in {1..5}; do
    if docker compose exec -T web python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Servidor web respondendo${NC}"
        break
    fi
    if [ $i -eq 5 ]; then
        echo -e "${RED}✗ Servidor web não respondeu. Verifique os logs: docker compose logs web${NC}"
        echo -e "${YELLOW}  Tentando verificar logs do container...${NC}"
        docker compose logs web --tail 50
    else
        echo "Tentativa $i/5..."
        sleep 5
    fi
done

echo ""

# =============================================================================
# FINALIZAÇÃO
# =============================================================================
echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}  Deploy Concluído!${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""

VPS_IP="72.61.24.232"
echo -e "Acesse: ${BLUE}https://rotulagem.terracotabpo.com${NC}"
echo -e "ou: ${BLUE}https://www.rotulagem.terracotabpo.com${NC}"
echo ""
echo -e "${YELLOW}Próximos passos:${NC}"
echo "1. Configure DNS na Hostinger:"
echo "   - Acesse: https://hpanel.hostinger.com"
echo "   - Vá em: Domínios > terracotabpo.com > Zona DNS"
echo "   - Adicione registro A para 'rotulagem':"
echo "     * Tipo: A"
echo "     * Nome: rotulagem"
echo "     * Aponta para: $VPS_IP"
echo "     * TTL: 14400"
echo "   - Adicione registro A para 'www.rotulagem':"
echo "     * Tipo: A"
echo "     * Nome: www.rotulagem"
echo "     * Aponta para: $VPS_IP"
echo "     * TTL: 14400"
echo "2. Aguarde propagação do DNS (5-30 minutos)"
echo "3. O certificado SSL será gerado automaticamente pelo Caddy"
echo ""
echo -e "${BLUE}Para mais detalhes, consulte: deploy/HOSTINGER_DNS_SETUP.md${NC}"

echo ""
echo -e "${YELLOW}Comandos úteis:${NC}"
echo "  docker compose logs -f        # Ver logs em tempo real"
echo "  docker compose logs web       # Ver logs do servidor web"
echo "  docker compose ps             # Ver status dos containers"
echo "  docker compose restart        # Reiniciar todos os serviços"
echo "  docker compose down           # Parar todos os serviços"
echo ""
