# Configuração de DNS no Hostinger para rotulagem.terracotabpo.com

Este guia detalha como configurar os registros DNS no Hostinger para que o subdomínio `rotulagem.terracotabpo.com` e `www.rotulagem.terracotabpo.com` apontem para o VPS onde a aplicação está hospedada.

## Informações Importantes

- **VPS IP**: `72.61.24.232`
- **Domínio principal**: `terracotabpo.com`
- **Subdomínio**: `rotulagem.terracotabpo.com`
- **Subdomínio com www**: `www.rotulagem.terracotabpo.com`

## Passo a Passo

### 1. Acessar o hPanel da Hostinger

1. Acesse: https://hpanel.hostinger.com
2. Faça login com suas credenciais
3. Você será redirecionado para o painel principal

### 2. Navegar até a Zona DNS

1. No menu lateral esquerdo, localize a seção **"Domínios"**
2. Clique em **"Domínios"** ou **"Gerenciar Domínios"**
3. Encontre o domínio **`terracotabpo.com`** na lista
4. Clique no domínio ou no botão **"Gerenciar"** ao lado dele
5. Procure pela aba ou seção **"Zona DNS"** ou **"DNS Zone"**
6. Clique nela para ver os registros DNS atuais

### 3. Adicionar Registro A para rotulagem.terracotabpo.com

1. Na página da Zona DNS, procure por um botão **"Adicionar Registro"**, **"Add Record"**, **"Novo Registro"** ou similar
2. Clique nele para abrir o formulário de novo registro
3. Preencha os campos da seguinte forma:
   - **Tipo**: Selecione **"A"** no dropdown
   - **Nome** ou **Host**: Digite `rotulagem` (sem o domínio completo)
   - **Aponta para** ou **Points to** ou **Value**: Digite `72.61.24.232`
   - **TTL**: Deixe o padrão (geralmente `14400` ou `3600`) ou selecione `14400` (4 horas)
4. Clique em **"Salvar"**, **"Adicionar"** ou **"Save"**

### 4. Adicionar Registro A para www.rotulagem.terracotabpo.com

1. Novamente, clique em **"Adicionar Registro"** ou **"Add Record"**
2. Preencha os campos:
   - **Tipo**: Selecione **"A"**
   - **Nome** ou **Host**: Digite `www.rotulagem` (sem o domínio completo)
   - **Aponta para** ou **Points to** ou **Value**: Digite `72.61.24.232`
   - **TTL**: Deixe o padrão ou selecione `14400`
3. Clique em **"Salvar"** ou **"Adicionar"**

### 5. Verificar os Registros Criados

Após adicionar os registros, você deve ver na lista da Zona DNS:

```
Tipo    Nome              Valor           TTL
A       rotulagem         72.61.24.232    14400
A       www.rotulagem     72.61.24.232    14400
```

## Propagação DNS

Após configurar os registros DNS:

1. **Tempo de propagação**: Geralmente leva entre **5 a 30 minutos**, mas pode levar até **24-48 horas** em casos raros
2. **Verificar propagação**: Você pode verificar se o DNS já propagou usando ferramentas online:
   - https://www.whatsmydns.net/#A/rotulagem.terracotabpo.com
   - https://dnschecker.org/#A/rotulagem.terracotabpo.com
3. **Teste local**: No terminal, você pode testar:
   ```bash
   dig rotulagem.terracotabpo.com
   # ou
   nslookup rotulagem.terracotabpo.com
   ```

## SSL/HTTPS Automático

O **Caddy** (reverse proxy) configurado no VPS irá:
- Detectar automaticamente quando o DNS está propagado
- Solicitar certificado SSL gratuito da Let's Encrypt
- Configurar HTTPS automaticamente
- Renovar o certificado automaticamente quando necessário

**Não é necessário** configurar SSL manualmente no Hostinger. O Caddy cuida de tudo automaticamente.

## Troubleshooting

### O DNS não está propagando

1. Verifique se os registros foram salvos corretamente no hPanel
2. Aguarde mais tempo (até 48 horas em casos extremos)
3. Limpe o cache DNS do seu computador:
   - Windows: `ipconfig /flushdns`
   - Linux/Mac: `sudo dscacheutil -flushcache` ou `sudo systemd-resolve --flush-caches`
4. Verifique se não há outros registros conflitantes (CNAME, etc.)

### O site não carrega após propagação DNS

1. Verifique se o container Docker está rodando:
   ```bash
   docker ps | grep tabela_nutricional_web
   ```
2. Verifique os logs do Caddy:
   ```bash
   docker logs web_monitor_caddy
   ```
3. Verifique se o firewall do VPS permite tráfego nas portas 80 e 443:
   ```bash
   sudo ufw status
   ```

### Erro de certificado SSL

1. Aguarde alguns minutos após a propagação DNS - o Caddy precisa de tempo para obter o certificado
2. Verifique os logs do Caddy para erros:
   ```bash
   docker logs web_monitor_caddy
   ```
3. Reinicie o container do Caddy:
   ```bash
   docker restart web_monitor_caddy
   ```

## Estrutura Final Esperada

Após a configuração completa, você terá:

- ✅ DNS configurado no Hostinger
- ✅ DNS propagado globalmente
- ✅ Aplicação rodando no VPS (porta 5000 interna)
- ✅ Caddy fazendo reverse proxy (portas 80/443 externas)
- ✅ HTTPS automático via Let's Encrypt
- ✅ Acesso via: https://rotulagem.terracotabpo.com
- ✅ Acesso via: https://www.rotulagem.terracotabpo.com

## Notas Importantes

- **Não crie registros CNAME** para esses subdomínios - use apenas registros A
- **Não configure SSL no Hostinger** - o Caddy cuida disso automaticamente
- O **TTL** pode ser ajustado, mas valores menores (ex: 300) aumentam a carga no servidor DNS
- Mantenha o **IP do VPS atualizado** se você mudar de servidor no futuro

## Suporte

Se encontrar problemas:
1. Verifique os logs: `docker compose logs` (no diretório do projeto)
2. Verifique a conectividade: `curl -I http://72.61.24.232` (deve retornar resposta do Caddy)
3. Verifique o DNS: Use as ferramentas de verificação mencionadas acima
