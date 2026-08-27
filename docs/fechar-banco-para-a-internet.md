# Fechar o banco para a internet, sem fechar o desenvolvimento

**Para: Erick.** Descoberto em 27/08/2026, verificado de fora.

## O que foi encontrado

O PostgreSQL de produção atende na internet pública. Mandando só o handshake
mínimo do protocolo — sem credencial, sem consulta — o servidor responde:

```
$ 62.72.11.28:8888
← b'R\x00\x00\x00\x17\x00\x00\x00\nSCRAM-SHA-256\x00\x00'
```

Qualquer pessoa alcança a porta e recebe o desafio de autenticação. **A senha é
a única coisa entre o banco inteiro e o mundo** — não há rede privada nem
allowlist de IP na frente.

**Não é urgência de largar tudo.** O SCRAM-SHA-256 é autenticação forte e não há
indício algum de problema. Isto é *exposição*, não invasão em curso. É motivo
para não seguir assim por inércia.

Foi encontrado por acaso: usei o IP do servidor para responder outra pergunta e
sondei as portas vizinhas. O diagnóstico de segurança de agosto passou por
autenticação inteira e nunca perguntou *"de onde dá para alcançar o banco?"*.

## O que NÃO pode acontecer

Fechar a porta e deixar a equipe sem acesso. O `.env` de desenvolvimento aponta
para o banco de produção, e isso é uma escolha consciente enquanto não existir um
banco de desenvolvimento separado. **O que precisa sair é o acesso da internet,
não o acesso de vocês.**

## Caminho recomendado: túnel SSH

O SSH já está aberto no servidor, atualizado (`OpenSSH_9.6p1 Ubuntu`, verificado
no banner) e usa chave em vez de senha — credencial mais forte que a do banco.

### 1. No servidor: parar de publicar a 8888

No EasyPanel, no serviço do PostgreSQL, remover a publicação da porta 8888.
O banco continua alcançável de dentro da rede do Docker, que é de onde a API
fala com ele — **a aplicação não sente nada**.

Confirmar depois, de fora:

```bash
python -c "
import socket
try:
    socket.create_connection(('62.72.11.28', 8888), timeout=8).close()
    print('AINDA ABERTA')
except Exception as e:
    print('fechada:', e)
"
```

### 2. Em cada máquina de desenvolvimento: o túnel

Adicionar ao `~/.ssh/config`:

```
Host helphs
    HostName 62.72.11.28
    User <o usuário de vocês>
    LocalForward 8888 localhost:8888
    ServerAliveInterval 30
```

A partir daí, `ssh helphs` abre a sessão **e** o túnel junto. Com ele de pé, o
banco responde em `localhost:8888` como se fosse local.

### 3. No `.env` de cada máquina: uma troca só

```diff
- DATABASE_URL=postgresql+asyncpg://administrador:SENHA@62.72.11.28:8888/helpdesk_db
+ DATABASE_URL=postgresql+asyncpg://administrador:SENHA@localhost:8888/helpdesk_db
```

**Nada mais muda.** Mesmas ferramentas, mesmo DBeaver, mesmos scripts, mesma
senha. O que muda é o caminho até a porta.

## Alternativa: allowlist de IP

A 8888 continua publicada, mas o firewall do painel só aceita os IPs de vocês.
Não muda nada no `.env`.

O problema é prático: **IP residencial costuma ser dinâmico**. Ele rotaciona, o
acesso cai justamente quando alguém precisa, e a tentação vira reabrir para todo
mundo "por enquanto" — que é como a porta ficou aberta em primeiro lugar.

Vale se os IPs forem fixos.

## Terceira opção: decidir não fazer agora

Defensável no curto prazo, pelos motivos do começo. Se for a escolha, que fique
**registrada como decisão**, não como esquecimento — é a diferença que importa
quando alguém reencontrar isto em seis meses.

## Uma coisa distinta, da mesma raiz

O `.env` local apontar para **produção** significa que qualquer script rodado sem
atenção numa máquina de desenvolvimento escreve no banco real. Isso independe da
porta e continua valendo com o túnel.

Não é proposta de mudança — enquanto não houver um banco de desenvolvimento, a
conveniência tem razão de ser. Só merece estar escrito ao lado, porque as duas
coisas nascem da mesma decisão.
