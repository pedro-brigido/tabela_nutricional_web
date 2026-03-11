# Configurar login com Google (OAuth 2.0)

Este guia explica passo a passo como criar as credenciais no Google Cloud e configurar as variáveis de ambiente no projeto.

---

## 1. Criar ou escolher um projeto no Google Cloud

1. Acesse **[Google Cloud Console](https://console.cloud.google.com/)** e faça login com sua conta Google.
2. No topo da página, clique no **seletor de projetos** (ao lado de "Google Cloud").
3. Clique em **"Novo projeto"** (ou escolha um projeto existente).
4. Preencha:
   - **Nome do projeto:** por exemplo `Terracota Rotulagem` ou `tabela-nutricional-web`.
5. Clique em **"Criar"** e aguarde. Depois, selecione esse projeto no seletor.

---

## 2. Ativar a tela de consentimento OAuth (OAuth consent screen)

1. No menu lateral, vá em **"APIs e serviços"** → **"Tela de consentimento OAuth"** (ou **"OAuth consent screen"**).
2. Escolha o tipo de usuário:
   - **Externo** — qualquer pessoa com conta Google pode fazer login (recomendado para app público).
   - **Interno** — só contas da sua organização (Google Workspace).
3. Clique em **"Criar"**.
4. Preencha a **Página de consentimento**:
   - **Nome do app:** ex.: `Terracota Calculadora Nutricional`
   - **E-mail de suporte do usuário:** seu e-mail
   - **Domínios autorizados:** (opcional por enquanto; em produção use `rotulagem.terracotabpo.com`)
   - **Informações de contato do desenvolvedor:** seu e-mail
5. Clique em **"Salvar e continuar"**.
6. Na etapa **"Escopos"**, clique em **"Adicionar ou remover escopos"**, marque:
   - `openid`
   - `.../userinfo.email`
   - `.../userinfo.profile`
   Depois clique em **"Atualizar"** e **"Salvar e continuar"**.
7. Em **"Usuários de teste"** (se o app estiver em "Teste"): adicione e-mails que podem testar. Em produção, depois de publicar o app, não é obrigatório.
8. Clique em **"Voltar ao painel"**.

---

## 3. Criar credenciais OAuth (Client ID e Secret)

1. No menu lateral: **"APIs e serviços"** → **"Credenciais"**.
2. Clique em **"+ Criar credenciais"** → **"ID do cliente OAuth"**.
3. **Tipo de aplicativo:** escolha **"Aplicativo da Web"**.
4. **Nome:** ex. `Tabela Nutricional Web`.
5. **URIs de redirecionamento autorizados** — adicione **uma linha por URL** que receberá o retorno do Google após o login:

   **Desenvolvimento local:**
   ```text
   http://127.0.0.1:5000/auth/google/callback
   ```
   Se usar outra porta (ex.: 5001):
   ```text
   http://127.0.0.1:5001/auth/google/callback
   ```

   **Produção (exemplo):**
   ```text
   https://rotulagem.terracotabpo.com/auth/google/callback
   ```
   Se quiser aceitar também com `www`:
   ```text
   https://www.rotulagem.terracotabpo.com/auth/google/callback
   ```

6. Clique em **"Criar"**.
7. Na janela que abrir, você verá:
   - **ID do cliente** — algo como `123456789-xxxx.apps.googleusercontent.com`
   - **Segredo do cliente** — uma string (ex.: `GOCSPX-...`)
8. **Copie e guarde os dois** em local seguro. O segredo só é mostrado uma vez; se perder, será preciso gerar um novo.

---

## 4. Onde e como configurar as variáveis

O app lê as credenciais do **ambiente** (variáveis de ambiente). Nunca commite esses valores no Git.

### 4.1 Desenvolvimento local (terminal)

**Opção A — na hora de rodar:**

```bash
export GOOGLE_CLIENT_ID="seu-client-id.apps.googleusercontent.com"
export GOOGLE_CLIENT_SECRET="GOCSPX-seu-segredo"
uv run python app.py
```

**Opção B — arquivo `.env` na raiz do projeto (recomendado)**

1. Na raiz do projeto (`tabela_nutricional_web/`), crie um arquivo chamado `.env`.
2. O `.env` já está no `.gitignore`, então não será commitado.
3. Coloque as linhas (trocando pelos seus valores):

```env
SECRET_KEY=sua-chave-secreta-flask
GOOGLE_CLIENT_ID=seu-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-seu-segredo
```

4. O projeto já usa `python-dotenv`: se existir um arquivo `.env` na raiz do projeto, as variáveis são carregadas ao iniciar o app. Basta criar o `.env` e rodar `uv run python app.py`.

**Conteúdo típico do `.env` (exemplo):**

```env
SECRET_KEY=abc123def456...
GOOGLE_CLIENT_ID=123456789-xxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxx
```

### 4.2 Produção (VPS / Docker)

No servidor, **não** use arquivo `.env` commitado. Use um dos métodos abaixo.

**Docker Compose** — no `deploy/docker-compose.yml` ou em um arquivo `.env` no servidor (fora do Git):

```yaml
# no docker-compose.yml, na seção do serviço web:
environment:
  - SECRET_KEY=${SECRET_KEY}
  - GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
  - GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
  - DATA_DIR=/app/data
```

E no mesmo diretório do deploy, crie um `.env` (só no servidor):

```env
SECRET_KEY=sua-chave-longa-aleatoria
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

**Servidor sem Docker** — exporte no shell ou configure no systemd/supervisor:

```bash
export SECRET_KEY="..."
export GOOGLE_CLIENT_ID="..."
export GOOGLE_CLIENT_SECRET="..."
```

---

## 5. Resumo das URLs que o app usa

| Ambiente   | URL de callback que você deve cadastrar no Google |
|-----------|----------------------------------------------------|
| Local     | `http://127.0.0.1:5000/auth/google/callback`       |
| Produção  | `https://rotulagem.terracotabpo.com/auth/google/callback` |

O app inicia o login em: **`/auth/google`**  
O Google redireciona o usuário de volta para: **`/auth/google/callback`**

---

## 6. Testar

1. Configure as variáveis (`.env` ou `export`).
2. Inicie o app: `uv run python app.py`.
3. Acesse http://127.0.0.1:5000 (ou a porta que estiver usando).
4. Clique em **"Entrar"** e depois em **"Entrar com Google"**.
5. Você deve ser redirecionado para o Google, autorizar e voltar ao site logado.

Se aparecer erro de "redirect_uri_mismatch", confira se a URL de callback no Google Cloud está **exatamente** igual à que o app usa (incluindo `http` vs `https`, porta e path `/auth/google/callback`).

---

## 7. Gerar SECRET_KEY (Flask)

Para sessões e cookies, o Flask usa `SECRET_KEY`. Gere uma nova chave:

```bash
uv run python -c "import secrets; print(secrets.token_hex(32))"
```

Use o valor impresso como `SECRET_KEY` no `.env` ou nas variáveis de ambiente.
