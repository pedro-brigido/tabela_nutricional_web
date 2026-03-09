# QA Stability Audit — rotulagem.terracotabpo.com

Data: 2026-03-03
Escopo: estabilização de fluxos críticos (Minha Conta, Calculadora, Pricing, Billing), auditoria funcional e plano de prevenção.

## 1) Resumo executivo

Foi realizada análise arquitetural + correções incrementais com foco em segurança de produção e baixo risco de regressão.

Status geral após correções:
- Bugs críticos A/B/D foram corrigidos com mudanças pequenas e compatíveis.
- Suite de testes completa passou (`80 passed`).
- Fluxos de cobrança agora possuem proteção contra dupla assinatura e ação explícita de cancelamento/reativação.
- Persistência de tabela foi ligada ao frontend, destravando contador mensal e listagem de tabelas recentes.

### Stack/arquitetura identificada
- Backend: Flask (Blueprints), SQLAlchemy, Flask-Login (sessão), CSRF, Alembic.
- Frontend: Jinja + Tailwind + JavaScript vanilla (`static/app.js`).
- Billing: Stripe (Checkout, Billing Portal e Webhook).
- Banco: SQLite por padrão (produção atual também configurada para SQLite no ambiente observado).
- Auth: sessão + OAuth Google.

### Rotas principais mapeadas
- Público: `/`, `/privacy`, `/help`, `/contact` (planos e comparativo ficam na landing `/#planos`)
- Auth: `/login`, `/register`, `/logout`, `/forgot-password`, `/reset-password/<token>`
- Conta: `/account/`, `/account/usage`, `/account/settings`, `/account/upgrade`
- Calculadora/API: `/api/calculate`, `/api/import-excel`, `/api/tables`
- Billing: `/billing/checkout`, `/billing/portal`, `/billing/portal-redirect`, `/billing/webhook`, `/billing/success`, `/billing/cancel`

---

## 2) Lista de bugs + causa raiz (e correção aplicada)

## A) Minha Conta

### A1. Botão "Gerenciar cobrança" não funciona
- Causa raiz: `create_billing_portal_session` falhava quando o usuário não tinha `stripe_customer_id`.
- Correção aplicada:
  - `app/services/stripe_service.py`: `create_billing_portal_session` passa a criar customer automaticamente via `get_or_create_stripe_customer`.
  - `app/blueprints/billing.py`: logs e tratamento consistente no fluxo de portal.
  - `templates/account/dashboard.html`: botão com estado de loading (`Abrindo...`).

### A2. Contador de tabelas do mês não funciona
- Causa raiz: contador depende de consumo de quota no save (`POST /api/tables`), mas o frontend não salvava.
- Correção aplicada:
  - `static/app.js`: save automático após cálculo + botão de save manual.

### A3. "Tabelas recentes" não mostra geração
- Causa raiz: mesma de A2 (tabela calculada era apenas renderizada, não persistida).
- Correção aplicada:
  - `static/app.js`: persistência conectada ao endpoint de save.

## B) Calculadora

### B1. Impressão/export gerando tabela em branco
- Causa raiz: conflito de CSS com regras dark (`!important`) aplicadas na árvore do app, impactando print.
- Correção aplicada:
  - `templates/index.html`: estilos de tabela interna limitados a `@media screen`.
  - `static/styles.css`: reforço de estilos de print para `#nutritional-table-print-area` (texto preto, fundo branco, bordas visíveis).

## C) Marketing/Home

### C1. Risco de inconsistência de preços
- Causa raiz: seed de planos duplicado em dois arquivos (`plan_service` e `cli`), com chance de drift.
- Correção aplicada:
  - Novo módulo compartilhado `app/plan_seed_data.py`.
  - `app/services/plan_service.py` e `app/cli.py` passam a reutilizar a mesma fonte.

## D) Assinaturas/Billing

### D1. Bug de dupla assinatura
- Causa raiz: validação de duplicidade bloqueava apenas assinatura ativa no mesmo plano.
- Correção aplicada:
  - `app/services/stripe_service.py`: nova exceção `ExistingSubscriptionError` e bloqueio para qualquer assinatura Stripe ativa.
  - `app/blueprints/billing.py`: tratamento dedicado com redirecionamento para Billing Portal (upgrade/downgrade seguro).
  - `templates/account/upgrade.html`: popup orientando migração via portal quando já há plano ativo.

### D2. Ausência de cancelamento explícito da assinatura
- Causa raiz: só existia caminho indireto via portal.
- Correção aplicada:
  - `app/blueprints/billing.py`: novo endpoint `POST /billing/cancel-subscription`.
  - `app/services/stripe_service.py`: `schedule_subscription_cancellation(cancel_at_period_end=...)`.
  - `templates/account/dashboard.html`: botão de cancelar com confirmação + botão de reativar quando cancelamento já está agendado.

---

## 3) Plano de ações (priorizado)

## Backlog priorizado (impacto/esforço/dependências/aceite)

| Item | Impacto | Esforço | Dependências | Critério de pronto |
|---|---|---:|---|---|
| Persistência de tabela no frontend | Alto | Baixo | API `/api/tables` | cálculo salva registro, aparece em "recentes", quota incrementa |
| Fix de print/export | Alto | Baixo | CSS print | impressão mostra tabela legível e completa |
| Portal billing resiliente | Alto | Baixo | Stripe customer | botão "Gerenciar cobrança" abre portal sem erro |
| Bloqueio de dupla assinatura | Alto | Médio | Billing service + UI upgrade | checkout não cria assinatura duplicada; usuário é orientado ao portal |
| Cancelamento/reativação in-app | Alto | Médio | Stripe API | usuário agenda cancelamento e pode reativar |
| Fonte única de preços | Médio | Baixo | módulo seed compartilhado | pricing/seed sem divergência estrutural |
| Observabilidade mínima + testes | Médio | Médio | testes e logs | eventos-chave e regressão cobertos |

## Quebra em PRs pequenos
- PR #1: save automático/manual de tabela + feedback UI.
- PR #2: correção de impressão/export em branco.
- PR #3: billing portal resiliente (customer bootstrap).
- PR #4: bloqueio de dupla assinatura + UX de upgrade/downgrade.
- PR #5: cancelamento/reativação de assinatura (backend + dashboard).
- PR #6: unificação da fonte de preços.
- PR #7: observabilidade + testes adicionais.

---

## 4) Recomendações de observabilidade e testes

## Instrumentação mínima recomendada

### Logs estruturados (backend)
- Campos mínimos por evento: `event`, `user_id`, `route`, `status`, `plan_slug`, `subscription_id`, `request_id`, `error_code`.
- Eventos críticos:
  - `billing.checkout.requested`
  - `billing.portal.requested`
  - `billing.subscription.cancel_requested`
  - `table.calculate.succeeded|failed`
  - `table.save.succeeded|failed`

### Tracking de eventos-chave (produto)
- `table_generated`
- `table_save_failed`
- `billing_manage_clicked`
- `billing_upgrade_redirected_to_portal`
- `subscription_cancel_scheduled`

### Alertas básicos
- Taxa de 5xx > limiar (janela de 5 min).
- Falhas de webhook Stripe repetidas.
- Pico de `table.save.failed`.
- Falha na criação de sessão de checkout/portal.

## Testes recomendados
- Unit (críticos): regras de billing (duplicidade/cancelamento), save de tabela e consumo de quota.
- Integração: `/account/` (uso + recentes), `/billing/checkout`, `/billing/cancel-subscription`, `/billing/portal`.
- E2E smoke (Playwright/Cypress):
  1. login → calcular → salvar → validar no dashboard,
  2. fluxo billing (checkout mock/sandbox) → portal/cancelamento.

## Resultado de validação executada
- Testes focados: `tests/test_billing.py tests/test_stripe_service.py tests/test_pricing.py tests/test_table_service.py` ✅
- Suite completa: `80 passed` ✅

---

## User Flows (status)

| Fluxo | Status | Notas |
|---|---|---|
| Home (`/`) | OK | navegação principal funcional |
| Pricing (landing `/#planos`) | OK | com fonte única de seed compartilhada |
| Login/Registro | OK | sem regressão observada por testes |
| Calculadora → calcular | OK | endpoint funcional |
| Calculadora → salvar tabela | OK | save automático + botão manual |
| Calculadora → imprimir | OK | CSS de print estabilizado |
| Minha Conta → contador mensal | OK | passa a refletir salvamento real |
| Minha Conta → tabelas recentes | OK | passa a listar tabelas geradas e salvas |
| Minha Conta → gerenciar cobrança | OK | cria customer Stripe quando ausente |
| Upgrade/Downgrade com assinatura ativa | OK | checkout bloqueado e redirecionado para portal |
| Cancelar assinatura (fim de período) | OK | botão com confirmação no dashboard |
| Reativar assinatura | OK | botão disponível quando cancelamento agendado |
| Webhook Stripe | OK | idempotente, sem regressão nos testes |

---

## Quick wins de UX (baixo risco)

1. Trocar `alert()` remanescentes por toasts não bloqueantes.
2. Exibir estado de loading em todos os CTAs de billing (checkout/portal/cancelar).
3. Mensagem contextual no dashboard após save de tabela (link direto para histórico, quando existir página dedicada).
4. Melhorar copy no popup de upgrade com texto curto e ação principal destacada.
5. Adicionar hint na calculadora quando o save automático falhar (retry em 1 clique).

---

## Observações operacionais importantes

- O ambiente atual contém chaves sensíveis no `.env` (Stripe/Google/SMTP). Recomenda-se rotação imediata + uso de secret manager.
- Para validação local de billing, manter sempre modo sandbox/test (`sk_test`, `pk_test`) e Stripe CLI para webhook.
