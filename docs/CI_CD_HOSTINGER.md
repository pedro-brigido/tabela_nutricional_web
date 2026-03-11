# CI/CD Hostinger VPS (GitHub Actions + GHCR)

Este projeto usa CI/CD com foco em simplicidade e deploy rapido:

- CI em PR e `main`
- build/push de imagem Docker no GHCR
- deploy automatico no VPS por SSH
- backup + health check + rollback no release

## 1) Preparar o VPS (uma vez)

No VPS, garanta:

- Docker + Docker Compose instalados
- usuario de deploy com acesso ao docker (ou root)
- arquivo de ambiente em `/opt/terracota/.env`
- Caddy/reverse proxy apontando para o container `web` na rede `terracota_network`

Do seu ambiente local:

```bash
scp deploy/bootstrap_vps.sh <user>@<host>:/opt/terracota/bootstrap_vps.sh
scp .env <user>@<host>:/opt/terracota/.env
```

No VPS:

```bash
mkdir -p /opt/terracota
chmod +x /opt/terracota/bootstrap_vps.sh
/opt/terracota/bootstrap_vps.sh
```

## 2) Configurar branch protection (GitHub)

Em `Settings > Branches > main`:

- Require a pull request before merging
- Require status checks to pass before merging
- Restrict who can push to matching branches
- Do not allow bypassing the above settings

Checks recomendados:

- `Test Suite`
- `Docker Smoke Build`

## 3) Configurar environment de producao

Crie o environment `production` em `Settings > Environments`.

Segredos obrigatorios:

- `VPS_HOST`
- `VPS_PORT` (opcional, default 22)
- `VPS_USER` (opcional; se vazio, o workflow usa `root`)
- `VPS_SSH_KEY`
- `VPS_KNOWN_HOSTS`
- `GHCR_USERNAME`
- `GHCR_READ_TOKEN`

Notas:

- `VPS_KNOWN_HOSTS`: saida de `ssh-keyscan -H <vps_host>`.
- `GHCR_READ_TOKEN`: token com escopo minimo `read:packages`.

## 4) Comportamento do workflow

Arquivo: `.github/workflows/ci-cd.yml`

- Pull request para `main`:
  - roda testes
  - roda smoke build Docker
- Push em `main`:
  - roda testes e smoke build
  - builda imagem no GHCR
  - executa deploy no VPS com `deploy/release.sh`
- `workflow_dispatch`:
  - executa pipeline manualmente (build + deploy)

## 5) Release no VPS

Arquivo: `deploy/release.sh`

Fluxo do script:

1. valida compose e env
2. cria backup de `/opt/terracota/data`
3. faz pull e sobe nova imagem (`IMAGE_REF` por digest)
4. valida `/health`
5. em falha, rollback automatico para imagem anterior

Estado do ultimo release:

- `/opt/terracota/current-release.env`

Backups:

- `/opt/terracota/backups/data-<timestamp>.tar.gz`
- retencao padrao: 7 arquivos

## 6) Operacao manual (fallback)

Deploy manual de uma imagem especifica:

```bash
IMAGE_REF="ghcr.io/<owner>/<repo>@sha256:<digest>" /opt/terracota/release.sh
```

Ver status:

```bash
docker compose -f /opt/terracota/docker-compose.prod.yml --env-file /opt/terracota/.env ps
docker compose -f /opt/terracota/docker-compose.prod.yml --env-file /opt/terracota/.env logs web --tail 100
```
