# Terracota | Calculadora Nutricional

Calculadora nutricional em conformidade com a **RDC 429/2020** e **IN 75/2020** (ANVISA). Projeto Python com aplicação Flask. Gerenciado com [uv](https://docs.astral.sh/uv/).

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

```bash
# Opção 1: uv run (recomendado, usa o ambiente gerenciado pelo uv)
uv run python app.py

# Opção 2: Script auxiliar
./run.sh

# Opção 3: Python do venv diretamente
.venv/bin/python app.py
```

Acesse [http://127.0.0.1:5000](http://127.0.0.1:5000) no navegador.

### Variáveis de ambiente opcionais

- `SECRET_KEY` — Chave para sessões Flask (gere com `python -c "import secrets; print(secrets.token_hex(32))"`)
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — Para login com Google (opcional)
- `USE_RELOADER=1` — Habilita reload automático ao editar código
- `FLASK_RUN_HOST` / `FLASK_RUN_PORT` — Host e porta (padrão: 127.0.0.1:5000)

## Estrutura do projeto

```
.
├── app.py                 # Aplicação Flask (rotas, API, auth)
├── auth.py                # Blueprint de autenticação (login, registro, OAuth)
├── models.py              # Modelo User (SQLAlchemy)
├── pyproject.toml         # Dependências e config (uv)
├── uv.lock                # Lock file para instalação reproduzível
├── src/
│   └── tabela_nutricional/   # Pacote de cálculo ANVISA
├── static/
├── templates/
├── tests/
├── deploy/                # Docker e scripts de deploy
└── legacy/                # Implementação antiga em JavaScript
```

## API

- **POST /api/calculate** — Recebe `{ product, ingredients }` e retorna dados nutricionais (requer login).
- **POST /api/import-excel** — Recebe arquivo `.xlsx` e retorna lista de ingredientes (requer login).
- **POST /api/subscribe** — Cadastro de e-mail para newsletter.

## Testes

```bash
uv sync --group dev
uv run pytest
```

## Deploy com Docker

```bash
cd deploy
docker compose build
docker compose up -d
```

Consulte `deploy/HOSTINGER_DNS_SETUP.md` para configurar DNS no Hostinger.
