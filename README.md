# Terracota | Calculadora Nutricional

Calculadora nutricional em conformidade com a **RDC 429/2020** e **IN 75/2020** (ANVISA). Aplicação Flask com controle de acesso por planos (Free, Flow Start, Flow Pro, Flow Studio). Gerenciado com [uv](https://docs.astral.sh/uv/).

## Requisitos

- Python 3.10+
- [uv](https://docs.astral.sh/uv/installation/) (gerenciador de pacotes)

## Instalação

```bash
# Instalar uv (se ainda não tiver)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clonar/cd no projeto
cd tabela_nutricional_web

# Criar venv e instalar dependências
uv sync
```

## Como executar

A aplicação usa **application factory** e o entry point é `wsgi.py` (não existe mais `app.py`).

```bash
# Opção 1: Servidor de desenvolvimento (recomendado local)
# Requer FLASK_APP=wsgi:app no .env (já está em .env.example)
uv run flask run

# Opção 2: Via wsgi.py (inicia app com create_app, não depende de FLASK_APP)
uv run python wsgi.py

# Opção 3: Gunicorn (produção)
uv run gunicorn -c gunicorn.conf.py wsgi:app
```

Acesse [http://127.0.0.1:5000](http://127.0.0.1:5000) no navegador.

### Variáveis de ambiente

Copie `.env.example` para `.env` e ajuste conforme necessário.

| Variável | Descrição |
|----------|-----------|
| `FLASK_ENV` | `development`, `testing` ou `production` |
| `SECRET_KEY` | Chave para sessões (gere com `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `DATA_DIR` | Diretório para `app.db` e `subscribers.db` (padrão: `./data`) |
| `DATABASE_URL` | URI do banco (padrão: `sqlite:///{DATA_DIR}/app.db`) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Login com Google (opcional) |
| `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` | Stripe Checkout/Billing/Webhooks |
| `STRIPE_PRICE_ID_FLOW_START`, `STRIPE_PRICE_ID_FLOW_PRO`, `STRIPE_PRICE_ID_FLOW_STUDIO` | Price IDs Stripe para cada plano pago. Ver [Configuração do Stripe (passo a passo)](docs/STRIPE_SETUP.md) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, `EMAIL_FROM` | SMTP para e-mails transacionais |
| `NEWSLETTER_NOTIFY_EMAIL` | E-mail que recebe aviso de newsletter (padrão: `comercial@terracotabpo.com`) |
| `USE_RELOADER` | `1` para reload automático ao editar (apenas com `python wsgi.py`) |
| `FLASK_RUN_HOST` / `FLASK_RUN_PORT` | Host e porta (padrão: 127.0.0.1:5000) |

## Banco de dados e migrações

O schema é gerenciado pelo **Alembic** (Flask-Migrate).

```bash
# Aplicar migrações
uv run flask db upgrade

# Criar nova migração (após alterar models)
uv run flask db migrate -m "descrição"

# Comandos CLI úteis
uv run flask seed-plans              # Popular tabela de planos (Free, Flow Start, etc.)
uv run flask create-admin <email>    # Tornar usuário admin
uv run flask backfill-free-plan      # Atribuir plano Free a usuários sem assinatura
uv run flask anonymize-deleted       # Anonimizar contas soft-deleted há 30+ dias
uv run flask sync-stripe-prices      # Sincronizar STRIPE_PRICE_ID_* para a tabela de planos
```

## Estrutura do projeto

```
.
├── wsgi.py                # Entry point (create_app + gunicorn)
├── app/
│   ├── __init__.py        # create_app() — application factory
│   ├── config.py          # Config Dev/Test/Prod
│   ├── extensions.py      # db, login_manager, csrf, limiter, migrate
│   ├── decorators.py      # @require_entitlement, @require_quota, @require_role
│   ├── errors.py           # Handlers 400, 403, 404, 429, 500
│   ├── middleware.py       # Security headers, request logging
│   ├── cli.py             # Comandos Flask (seed-plans, create-admin, etc.)
│   ├── models/            # User, Plan, Subscription, UsageRecord, NutritionTable, AuditLog, SupportTicket
│   ├── services/          # plan_service, usage_service, table_service, auth_service, audit_service, email_service
│   └── blueprints/        # auth, main, calculator, account, admin, support
├── migrations/            # Alembic
├── src/tabela_nutricional/  # Cálculo ANVISA
├── static/
├── templates/             # base, auth/, main/, account/, admin/, support/, errors/
├── tests/
├── deploy/                # Docker e scripts
├── pyproject.toml
└── .env.example
```

## Planos e funcionalidades

| Plano | Tabelas/mês | Ingredientes/tabela | Recursos |
|-------|-------------|---------------------|----------|
| **Free** | 1 | 10 | Pulse Digest |
| **Flow Start** (R$ 39,90) | 3 | 25 | Pulse geral |
| **Flow Pro** (R$ 79,90) | 10 | 80 | Templates, PDF/PNG, histórico, Pulse Pro (5 temas + alertas) |
| **Flow Studio** (R$ 199,90) | Ilimitado | Ilimitado | Branding PDF, Pulse Advanced (15 temas + radar) |

Assinaturas podem ser atribuídas manualmente via admin e também via Stripe (Checkout + Billing Portal + Webhooks).

## Rotas principais

- **/** — Landing
- **/#como-funciona**, **/#beneficios**, **/#planos**, **/#faq**, **/#contato** — Navegação pública canônica na landing
- **/privacy** — Política de privacidade
- **/health** — Health check (inclui status do banco)
- **/login**, **/register**, **/logout** — Auth
- **/forgot-password**, **/reset-password/<token>** — Redefinição de senha
- **/verify-email/<token>** — Verificação de e-mail
- **/account** — Minha Conta (plano, consumo, configurações, upgrade)
- **POST /billing/checkout**, **POST /billing/portal**, **POST /billing/webhook** — Fluxos Stripe
- **/billing/success**, **/billing/cancel** — Páginas informativas pós-checkout
- **/help**, **/contact** — Redirects legados para a landing (`/#faq` e `/#contato`)
- **/admin/** — Painel admin (requer `is_admin`); usuários, planos, quotas, logs, tickets
- **POST /api/calculate** — Calcular tabela nutricional (requer login, respeita quota de ingredientes)
- **POST /api/import-excel** — Importar ingredientes de Excel
- **POST /api/tables**, **GET /api/tables**, **GET /api/tables/<id>**, **DELETE /api/tables/<id>** — CRUD de tabelas salvas (consome quota ao salvar)
- **POST /api/subscribe** — Newsletter

## Testes

```bash
uv sync --group dev
uv run pytest
```

Com cobertura:

```bash
uv run pytest --cov=app --cov-report=term-missing
```

## Stripe local (webhooks)

Para configurar cada variável Stripe passo a passo (chaves, webhook secret, Price IDs), veja [docs/STRIPE_SETUP.md](docs/STRIPE_SETUP.md).

1. Configure as variáveis `STRIPE_*` no `.env`.
2. Inicie a aplicação local.
3. Em outro terminal, rode:

```bash
stripe listen --forward-to localhost:5000/billing/webhook
```

4. Copie o `whsec_...` exibido pelo Stripe CLI para `STRIPE_WEBHOOK_SECRET`.

## Deploy com Docker

### Local/manual

Para subir localmente com Docker Compose (build local):

```bash
cd deploy
docker compose build
docker compose up -d
```

### Produção (CI/CD automático)

Produção usa este fluxo:

1. GitHub Actions roda testes e smoke build em cada PR para `main`.
2. Em push/merge para `main`, o workflow gera imagem imutável no GHCR.
3. O workflow conecta no VPS (Hostinger) por SSH e executa `deploy/release.sh`.
4. O script faz backup dos bancos SQLite, publica a nova imagem e valida `/health`.
5. Se `/health` falhar, ocorre rollback automático para a imagem anterior.

Arquivos principais:

- `.github/workflows/ci-cd.yml`
- `deploy/docker-compose.prod.yml`
- `deploy/release.sh`
- `deploy/bootstrap_vps.sh`

Pré-requisitos de produção:

1. Rodar bootstrap uma vez no VPS:
```bash
scp deploy/bootstrap_vps.sh <user>@<host>:/opt/terracota/bootstrap_vps.sh
ssh <user>@<host> "chmod +x /opt/terracota/bootstrap_vps.sh && /opt/terracota/bootstrap_vps.sh"
```
2. Subir o `.env` de produção para o VPS:
```bash
scp .env <user>@<host>:/opt/terracota/.env
```
3. Configurar os segredos do GitHub Environment `production`:
   - `VPS_HOST`
   - `VPS_PORT` (opcional; default `22`)
   - `VPS_USER`
   - `VPS_SSH_KEY`
   - `VPS_KNOWN_HOSTS`
   - `GHCR_USERNAME`
   - `GHCR_READ_TOKEN`

Consulte `docs/README_CONFIGURACAO_EXTERNA.md` para o passo a passo completo das configuracoes fora do codigo.
Consulte `docs/CI_CD_HOSTINGER.md` para o fluxo tecnico resumido do CI/CD.
Consulte `deploy/HOSTINGER_DNS_SETUP.md` para DNS no Hostinger.
