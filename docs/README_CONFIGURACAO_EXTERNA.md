# README - Configuracao externa do CI/CD

Este guia cobre apenas o que precisa ser configurado fora do codigo para colocar o CI/CD em funcionamento no GitHub + GHCR + VPS Hostinger.

Objetivo final:

- abrir PR para `main`
- CI rodar automaticamente
- merge em `main` publicar a imagem no GHCR
- GitHub Actions conectar no VPS e fazer o deploy automatico

## 1. Pre-requisitos

Voce precisa ter:

- acesso admin ao repositorio no GitHub
- acesso SSH ao VPS
- Docker e Docker Compose funcionando no VPS
- dominio/subdominio ja apontando para o VPS, se o site ja estiver publico
- arquivo `.env` de producao pronto

## 2. Preparar o VPS

Conecte no VPS:

```bash
ssh seu_usuario@seu_host
```

Crie a pasta base do deploy:

```bash
sudo mkdir -p /opt/terracota
sudo chown -R $USER:$USER /opt/terracota
```

Garanta que Docker e Compose estao instalados:

```bash
docker --version
docker compose version
```

Se a rede compartilhada do Caddy ainda nao existir:

```bash
docker network create terracota_network
```

## 3. Subir os arquivos iniciais para o VPS

Do seu computador local, envie o bootstrap e o `.env` de producao:

```bash
scp deploy/bootstrap_vps.sh seu_usuario@seu_host:/opt/terracota/bootstrap_vps.sh
scp .env seu_usuario@seu_host:/opt/terracota/.env
```

Depois rode o bootstrap no VPS:

```bash
ssh seu_usuario@seu_host "chmod +x /opt/terracota/bootstrap_vps.sh && /opt/terracota/bootstrap_vps.sh"
```

Ao final, estes caminhos devem existir:

- `/opt/terracota/.env`
- `/opt/terracota/backups`

## 4. Criar a chave SSH do deploy

Na sua maquina local, gere uma chave dedicada para o GitHub Actions:

```bash
ssh-keygen -t ed25519 -C "github-actions-terracota" -f ~/.ssh/terracota_actions
```

Isso gera:

- chave privada: `~/.ssh/terracota_actions`
- chave publica: `~/.ssh/terracota_actions.pub`

Adicione a chave publica no VPS em `~/.ssh/authorized_keys` do usuario que fara deploy:

```bash
cat ~/.ssh/terracota_actions.pub
```

Copie a saida e acrescente no arquivo:

```bash
ssh seu_usuario@seu_host
mkdir -p ~/.ssh
chmod 700 ~/.ssh
nano ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Teste a conexao:

```bash
ssh -i ~/.ssh/terracota_actions seu_usuario@seu_host
```

## 5. Gerar o `known_hosts`

Na sua maquina local:

```bash
ssh-keyscan -H seu_host
```

Guarde a saida completa. Ela sera usada no segredo `VPS_KNOWN_HOSTS` do GitHub.

## 6. Criar o token de leitura do GHCR

No GitHub, crie um token apenas para o VPS puxar imagens privadas:

1. Acesse `GitHub > Settings > Developer settings > Personal access tokens`
2. Crie um token com escopo minimo `read:packages`
3. Guarde o valor do token

Esse token sera usado no segredo `GHCR_READ_TOKEN`.

Use como `GHCR_USERNAME` o seu usuario do GitHub dono do pacote.

## 7. Configurar o environment `production` no GitHub

No repositorio:

1. Abra `Settings > Environments`
2. Crie o environment `production`
3. Adicione estes secrets:

- `VPS_HOST`: host ou IP do VPS
- `VPS_PORT`: porta SSH, normalmente `22`
- `VPS_USER`: usuario do VPS que executara o deploy; se omitir, o workflow usa `root`
- `VPS_SSH_KEY`: conteudo completo da chave privada `~/.ssh/terracota_actions`
- `VPS_KNOWN_HOSTS`: saida do `ssh-keyscan -H seu_host`
- `GHCR_USERNAME`: seu usuario GitHub
- `GHCR_READ_TOKEN`: token com `read:packages`

Observacao:

- nao coloque aspas
- mantenha o `.env` da aplicacao apenas no VPS, nao no GitHub

## 8. Ajustar branch protection da `main`

No repositorio:

1. Abra `Settings > Branches`
2. Adicione ou edite a regra da branch `main`
3. Ative:

- `Require a pull request before merging`
- `Require status checks to pass before merging`
- `Restrict who can push to matching branches`
- `Do not allow bypassing the above settings`

Depois que o workflow aparecer pela primeira vez, marque como obrigatorios:

- `Test Suite`
- `Docker Smoke Build`

## 9. Validar o pacote no GHCR

No primeiro push para `main`, o workflow vai publicar a imagem em:

```text
ghcr.io/<owner>/<repo>
```

Para este projeto:

```text
ghcr.io/pedro-brigido/tabela_nutricional_web
```

Confirme no GitHub em:

`Profile/Organization > Packages`

## 10. Fazer o primeiro deploy

Com tudo configurado:

1. faça push de uma branch
2. abra PR para `main`
3. espere `Test Suite` e `Docker Smoke Build` ficarem verdes
4. faça merge em `main`

O workflow vai:

- rebuildar e publicar a imagem
- copiar `deploy/docker-compose.prod.yml` e `deploy/release.sh` para `/opt/terracota`
- executar o deploy remoto

## 11. Verificar se o deploy funcionou

No GitHub Actions:

- abra a execucao do workflow
- verifique se `Deploy Production (Hostinger VPS)` terminou com sucesso

No VPS:

```bash
docker compose -f /opt/terracota/docker-compose.prod.yml --env-file /opt/terracota/.env ps
docker compose -f /opt/terracota/docker-compose.prod.yml --env-file /opt/terracota/.env logs web --tail 100
cat /opt/terracota/current-release.env
```

Teste o healthcheck:

```bash
curl -I http://127.0.0.1:5000/health
```

Se o app estiver atras de Caddy/Nginx, teste tambem pela URL publica.

## 12. Como funciona o rollback

Se a nova release falhar no `/health`, o script:

1. detecta a falha
2. pega o `IMAGE_REF` anterior em `/opt/terracota/current-release.env`
3. sobe novamente a imagem anterior

Os backups do SQLite ficam em:

```text
/opt/terracota/backups
```

O banco ativo fica no volume Docker:

```text
tabela-nutricional_tabela_data
```

## 13. Checklist final

Antes de considerar pronto, confirme:

- VPS acessivel por SSH com a chave dedicada
- `/opt/terracota/.env` presente
- `terracota_network` existente
- environment `production` criado no GitHub
- todos os secrets preenchidos
- branch protection ativa em `main`
- GHCR package criado no primeiro deploy
- workflow concluindo sem erro

## 14. Troubleshooting rapido

Erro de SSH no GitHub Actions:

- confira `VPS_HOST`, `VPS_PORT`, `VPS_USER`
- confira se `VPS_SSH_KEY` e `VPS_KNOWN_HOSTS` estao corretos
- confirme que a chave publica esta em `authorized_keys`

Erro ao puxar imagem do GHCR:

- confira `GHCR_USERNAME`
- confira `GHCR_READ_TOKEN`
- confirme que o token tem `read:packages`

Erro de deploy/healthcheck:

- veja logs do container `web`
- confira se `/opt/terracota/.env` esta completo
- confira se o Caddy continua usando a rede `terracota_network`

## 15. Arquivos relacionados

- `README.md`
- `docs/CI_CD_HOSTINGER.md`
- `.github/workflows/ci-cd.yml`
- `deploy/docker-compose.prod.yml`
- `deploy/release.sh`
