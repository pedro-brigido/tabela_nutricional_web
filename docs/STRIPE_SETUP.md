# Configuração do Stripe (passo a passo)

Este guia explica como obter e configurar cada variável de ambiente do Stripe usada pela aplicação. As variáveis estão listadas em [`.env.example`](../.env.example) na seção **Stripe (Checkout + Billing + Webhooks)**.

**Pré-requisito:** ter uma conta no [Stripe](https://dashboard.stripe.com/register) (use o modo **Test** para desenvolvimento).

---

## 1. Chaves da API (Secret e Publishable)

### 1.1 Obter as chaves

1. Acesse o [Stripe Dashboard](https://dashboard.stripe.com/).
2. No canto superior direito, confira se está em **Modo de teste** (toggle "Test mode" ativado). Para produção, desative depois de validar.
3. Vá em **Developers** → **API keys**.
4. Você verá:
   - **Publishable key** (começa com `pk_test_...` ou `pk_live_...`) — pode ser usada no front-end.
   - **Secret key** (clique em "Reveal" para ver; começa com `sk_test_...` ou `sk_live_...`) — **nunca** exponha no front-end.

### 1.2 Configurar no `.env`

No seu arquivo `.env` (cópia do `.env.example`):

```env
# Chave secreta (backend apenas)
STRIPE_SECRET_KEY=sk_test_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Chave pública (opcional no backend; útil se algum template precisar)
STRIPE_PUBLISHABLE_KEY=pk_test_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Segurança:** não commite o `.env`. O `STRIPE_SECRET_KEY` dá acesso total à sua conta Stripe.

---

## 2. Webhook Signing Secret

O webhook signing secret é usado para **validar** que os eventos POST em `/billing/webhook` vêm mesmo do Stripe.

### 2.1 Desenvolvimento local (Stripe CLI)

O secret gerado pelo `stripe listen` é **temporário e exclusivo** para aquela sessão local. Ele **não** funciona em produção.

1. Instale o [Stripe CLI](https://stripe.com/docs/stripe-cli):
   - **macOS:** `brew install stripe/stripe-cli/stripe`
   - **Linux (automático):**
     ```bash
     sudo ./deploy/install_stripe_cli.sh
     ```
   - **Linux (manual):** baixe em [Stripe CLI Releases](https://github.com/stripe/stripe-cli/releases) (`stripe_*_linux_x86_64.tar.gz`), extraia e mova para `/usr/local/bin/`.
   - **Windows:** `scoop install stripe` ou baixe de [Releases](https://github.com/stripe/stripe-cli/releases).
2. Faça login: `stripe login`.
3. Em um terminal, rode:
   ```bash
   stripe listen --forward-to localhost:5000/billing/webhook
   ```
4. O CLI exibirá algo como: `Ready. Your webhook signing secret is whsec_xxxxxxxxxxxxxxxxxxxxxxxx`.
5. Copie esse valor e coloque no `.env`:
   ```env
   STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxxxxxxxxx
   ```
6. Mantenha o `stripe listen` rodando enquanto testa checkout/webhooks localmente.

### 2.2 Produção — Automático (recomendado)

O script `deploy/setup_stripe.sh` e o comando Flask `setup-stripe-webhook` criam o endpoint via API e gravam o signing secret no `.env` automaticamente:

```bash
# Opção A: script completo (instala CLI + cria endpoint + atualiza .env)
sudo ./deploy/setup_stripe.sh --url https://rotulagem.terracotabpo.com/billing/webhook

# Opção B: apenas o Flask CLI (se Python/Docker já estiver disponível)
flask setup-stripe-webhook https://rotulagem.terracotabpo.com/billing/webhook --update-env

# Opção C: via Docker (container rodando)
docker compose -f deploy/docker-compose.yml exec web \
  flask setup-stripe-webhook https://rotulagem.terracotabpo.com/billing/webhook --update-env
```

> **Por que dois secrets diferentes?**  O `whsec_...` do `stripe listen` local é efêmero — gerado a cada sessão do CLI. O `whsec_...` de produção é permanente, vinculado ao endpoint registrado na Stripe. **Nunca reutilize** o secret local em produção.

### 2.3 Produção — Manual (Dashboard)

Se preferir configurar pelo Dashboard:

1. No Stripe Dashboard, vá em **Developers** → **Webhooks**.
2. Clique em **Add endpoint**.
3. **Endpoint URL:** `https://seu-dominio.com/billing/webhook`.
4. Em **Events to send**, selecione (mínimo necessário):
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
5. Salve. Na página do endpoint, clique em **Reveal** em **Signing secret**.
6. Copie o valor (`whsec_...`) e use no `.env` do servidor:
   ```env
   STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxxxxxxxxx
   ```

---

## 3. Price IDs (planos pagos)

A aplicação mapeia os planos internos (Flow Start, Flow Pro, Flow Studio) para **Prices** do Stripe. Cada plano pago precisa de um **Price ID** (ex.: `price_xxxxxxxxxxxx`).

### 3.1 Criar produtos e preços no Stripe

1. No Dashboard, vá em **Product catalog** → **Products** → **Add product**.
2. Crie **três produtos** (um por plano pago), por exemplo:

| Nome do produto (Stripe) | Preço (recorrente) | ID que você vai usar |
|--------------------------|--------------------|------------------------|
| Terracota Flow Start     | R$ 39,90 / mês     | Flow Start             |
| Terracota Flow Pro      | R$ 79,90 / mês     | Flow Pro               |
| Terracota Flow Studio   | R$ 199,90 / mês    | Flow Studio            |

3. Para cada produto:
   - **Pricing:** escolha **Recurring**, intervalo **Monthly**.
   - Moeda: **BRL** (ou a que você usar).
   - Após salvar, o Stripe cria um **Price**; na lista de preços do produto, copie o **Price ID** (começa com `price_...`).

### 3.2 Configurar no `.env`

Coloque cada Price ID na variável correspondente:

```env
STRIPE_PRICE_ID_FLOW_START=price_xxxxxxxxxxxx
STRIPE_PRICE_ID_FLOW_PRO=price_xxxxxxxxxxxx
STRIPE_PRICE_ID_FLOW_STUDIO=price_xxxxxxxxxxxx
```

A aplicação usa esses IDs ao criar a sessão de Checkout e ao interpretar webhooks (para saber qual plano interno ativar).

### 3.3 Sincronizar com a tabela de planos (opcional)

Depois de configurar as variáveis, rode no servidor (ou localmente com o mesmo `.env`):

```bash
uv run flask sync-stripe-prices
```

Isso atualiza o campo `stripe_price_id` dos planos na base de dados (flow_start, flow_pro, flow_studio) com os valores das variáveis de ambiente. O comando `flask seed-plans` também pode preencher esses campos se as variáveis estiverem definidas.

---

## 4. Resumo das variáveis no `.env`

| Variável | Onde obter | Exemplo |
|----------|------------|---------|
| `STRIPE_SECRET_KEY` | Dashboard → Developers → API keys (Reveal secret key) | `sk_test_...` |
| `STRIPE_PUBLISHABLE_KEY` | Dashboard → Developers → API keys | `pk_test_...` |
| `STRIPE_WEBHOOK_SECRET` | Local: `stripe listen --forward-to ...`; Produção: Dashboard → Webhooks → endpoint → Signing secret | `whsec_...` |
| `STRIPE_PRICE_ID_FLOW_START` | Dashboard → Products → preço mensal do plano Start | `price_...` |
| `STRIPE_PRICE_ID_FLOW_PRO` | Dashboard → Products → preço mensal do plano Pro | `price_...` |
| `STRIPE_PRICE_ID_FLOW_STUDIO` | Dashboard → Products → preço mensal do plano Studio | `price_...` |

---

## 5. Verificar se está ativo

- Se **todas** as variáveis Stripe estiverem preenchidas (em especial `STRIPE_SECRET_KEY` e `STRIPE_WEBHOOK_SECRET`), a aplicação considera o Stripe habilitado:
  - Os CTAs de assinatura na página de planos e em "Minha Conta" passam a abrir o Stripe Checkout.
  - O botão "Gerenciar cobrança" no dashboard da conta abre o Stripe Customer Portal.
- Se alguma chave ou o webhook secret estiver faltando, essas rotas retornam 404 e a interface mostra os links de "Fale conosco" no lugar do checkout.

Para testar o fluxo completo em desenvolvimento: rode a app, rode `stripe listen --forward-to localhost:5000/billing/webhook`, use o `STRIPE_WEBHOOK_SECRET` exibido pelo CLI no `.env` e faça um pagamento de teste no Checkout.

---

## 6. Deploy automatizado (VPS + Docker)

Para configurar o Stripe num servidor de produção sem passos manuais:

```bash
# 1. Preencha STRIPE_SECRET_KEY e STRIPE_PRICE_ID_* no .env do servidor

# 2. Rode o setup completo (instala CLI + cria webhook + grava secret)
sudo ./deploy/setup_stripe.sh --url https://rotulagem.terracotabpo.com/billing/webhook

# 3. Reinicie a aplicação para carregar as novas variáveis
docker compose -f deploy/docker-compose.yml restart
```

### Scripts disponíveis

| Script | Descrição |
|--------|----------|
| `deploy/install_stripe_cli.sh` | Instala o Stripe CLI via apt no host Linux |
| `deploy/setup_stripe.sh` | Setup completo: CLI + webhook endpoint + .env |
| `flask setup-stripe-webhook URL` | Cria endpoint via Stripe API (Flask CLI) |
| `flask sync-stripe-prices` | Sincroniza Price IDs do .env para o banco |
