# Decisões e regras de negócio — HelpHS

Registro das regras que **não dá para deduzir lendo o código** e das decisões
tomadas junto ao cliente. Atualizado em 07/08/2026 (v1.4.0).

Para o histórico voltado ao usuário final, veja `frontend/src/data/changelog.ts`.
Para o detalhe de cada tabela, o `Documentação/Dicionario_Dados_HelpDesk_v1.docx`.

---

## SLA

**Jornada: segunda a sexta, 08:00–17:00 (9 horas úteis por dia).**

O valor vive em `backend/app/utils/sla.py` (`_WORK_START` / `_WORK_END`). Havia
divergência entre as fontes: o docstring do módulo e o Dicionário de Dados diziam
18:00, enquanto a constante virou 17:00 no commit `5954d3b`. O documento de
Requisitos (RN-013) sempre disse 08h–17h, e o cliente confirmou 9h/dia em
05/08/2026. Documentação e testes foram alinhados ao código.

Feriados não são modelados nesta versão — só fins de semana.

## Ciclo de encerramento do chamado

Os dois prazos abaixo são contados em **dias úteis** a partir do momento em que
o chamado foi **resolvido** — não do fechamento. Em dias corridos, quem
resolvesse na sexta à tarde daria ao cliente praticamente nenhum dia de
trabalho para se manifestar.

| Evento | Prazo | Configuração |
|---|---|---|
| Resolvido → Fechado, sozinho | 3 dias úteis | `TICKET_AUTO_CLOSE_BUSINESS_DAYS` |
| Cliente ainda pode reabrir | 5 dias úteis | `TICKET_REOPEN_BUSINESS_DAYS` |

A janela de reabertura é **maior** que a de fechamento de propósito: o chamado
fecha sozinho no 3º dia, mas o cliente continua podendo reabrir por mais dois.
Sem essa folga, o fechamento automático tiraria dele a única saída.

Definido com o cliente em 07/08/2026. Os requisitos originais previam 5 e 7
dias; nenhum dos dois estava implementado até então.

### O que acontece em cada status

**Resolvido** — SLA parado, chat bloqueado, convite para avaliar enviado. É a
janela em que o cliente ainda pode se manifestar.

**Fechado** — arquivamento. Chegar aqui pela rotina automática marca
`auto_closed = true` no chamado, e a tela avisa que o fechamento não foi
decisão de ninguém.

### Reabertura

Quem reabre precisa **escrever o motivo** (mínimo 5 caracteres). Ele vai para o
histórico e é o que o técnico lê para saber por onde retomar — a nota de
resolução anterior continua no chamado.

O chamado volta para **Em andamento** quando tem responsável, e para **Aberto**
quando não tem, para ser distribuído como um chamado novo.

O prazo de 5 dias vale para o **cliente**. Admin e técnico reabrem a qualquer
momento: quando o encerramento foi engano da própria equipe, um prazo vencido
só obrigaria a abrir chamado novo e perder o histórico.

Reabrir **recalcula o prazo de resolução** e limpa a marca de SLA violado. Sem
isso o chamado voltaria já vencido, com o cronômetro parado no dia em que foi
resolvido. A violação original continua registrada no histórico.

### Relação com o SLA

Os dois relógios **não se cruzam**: o SLA conta da abertura até a resolução, e
os prazos acima só começam depois disso. `check_breaches` ignora os status
terminais, então nada continua vencendo depois de resolvido, e o fechamento
automático apenas troca um status terminal por outro.

Dois pontos onde a separação precisou ser feita à mão:

- **Tempo médio de resolução** passou a contar até `resolved_at`, não até
  `closed_at`. Como o fechamento automático reescreve o `closed_at` três dias
  úteis depois, a métrica passaria a medir a demora do cliente em responder e
  não o trabalho da equipe — todo chamado fechado pela rotina apareceria com
  ~27 h a mais.
- **Reabrir zera o `sla_total_paused_ms`.** Esse acumulado existe para esticar o
  prazo do ciclo em que a pausa aconteceu; como a reabertura já dá um prazo novo
  contado a partir do momento, mantê-lo daria ao ciclo novo horas de bônus que
  ninguém esperou.

A marca de **primeira resposta vencida** sobrevive à reabertura de propósito:
ela se refere ao primeiro atendimento, que de fato aconteceu (ou atrasou) uma
vez só.

### Por que a rotina roda dentro da API

O projeto tem Celery configurado, mas **não existe worker nem beat no ambiente
de produção** — o `start.sh` sobe apenas o uvicorn. Uma tarefa agendada no
Celery nunca executaria.

A rotina roda como task do próprio processo da API
(`backend/app/services/ticket_lifecycle.py`), a cada
`TICKET_AUTO_CLOSE_INTERVAL_SECONDS` (padrão 1 h). Como o uvicorn sobe com
`--workers 2`, um **lock no Redis** garante que só um processo trabalha por
rodada; sem Redis a rodada é pulada, porque fechar o mesmo chamado duas vezes
duplicaria histórico e notificação. Definir o intervalo como `0` desliga a
rotina.

O fechamento automático fica no histórico **sem autor** (`user_id` nulo,
exibido como "Sistema"). Apontá-lo para um administrador qualquer registraria
uma ação que ninguém praticou.

## Pesquisa de satisfação (CSAT)

**Escala de 1 a 10.**

A coleta sempre foi 1–10, mas relatórios, gráficos e o filtro da API assumiam
1–5. O efeito colateral era grave: a distribuição do relatório ia de 1 a 5, então
**toda avaliação de 6 a 10 desaparecia do gráfico**. Unificado na v1.1.0.

A meta exibida no gráfico de tendência é 8.0 (era 4.0 na escala antiga).

### O convite é só no sininho

Disparado automaticamente quando o chamado entra em **Resolvido** — pelos dois
caminhos, "Concluir ticket" e "Alterar status". Passar para Fechado não dispara
nada: o convite já foi feito.

**Não sai e-mail** (`_IN_APP_ONLY` em `app/services/notifications.py`). A
avaliação é respondida no painel abaixo do chat, dentro do chamado; o e-mail
apenas pedia que a pessoa entrasse no sistema. Decidido em 07/08/2026.

Até então o caminho do "Alterar status" mandava **dois** e-mails — o da
notificação e outro escrito à mão logo abaixo.

Quem avalia é só **o cliente que abriu o chamado**, uma vez por chamado, sem
prazo para responder e sem poder alterar depois. Admin e técnico não veem o
painel.

### Duas perguntas, um envio

| Pergunta | Campo | Escala |
|---|---|---|
| Como você avalia o atendimento? | `rating` | 1 a 10 |
| O quanto você recomendaria nossa empresa? | `recommend_rating` | 1 a 10 |

As duas são **obrigatórias no formulário** — são dois cliques e o dado só serve
se vier completo. Na API a segunda é opcional, para não invalidar integrações
que enviem apenas a nota do atendimento.

`recommend_rating` é **nulo nas avaliações enviadas antes da pergunta existir**,
e continua assim: não há como recuperar a resposta de quem já avaliou. As médias
usam `AVG`, que ignora nulos — tratá-los como zero derrubaria o número sem
ninguém ter dado zero.

A média aparece no relatório, no card **Recomendação**, ao lado da Média CSAT.

> Não é o NPS de mercado. O NPS usa escala 0–10 e um cálculo próprio
> (% promotores − % detratores); aqui a escala é 1–10 e o que se mostra é a
> média simples, como foi pedido. Se um dia o número precisar ser comparável
> com o de fora, a escala precisa começar em 0.

## Permissões

### Entre técnicos — sem barreira

Qualquer técnico pode **atender, responder e concluir qualquer chamado**, mesmo
sem ser o responsável. Havia uma trava exigindo atribuição em três pontos
(concluir, chat REST e chat WebSocket), removida em 05/08/2026 a pedido do
cliente.

A trava não se sustentava: o mesmo técnico chegava a "Resolvido" pelo **Alterar
status**, que nunca exigiu atribuição. Bloqueava o caminho principal e deixava o
alternativo aberto.

> Se um dia isso virar problema de organização interna, o caminho do meio é a
> auto-atribuição: quem age num chamado sem responsável vira o responsável.

### Base de conhecimento

- **Admin e técnico** excluem qualquer comentário; cliente exclui só os próprios.
- **Cliente** vê a aba Base de Conhecimento dentro do próprio chamado. A API
  valida que ele só recebe sugestões de ticket que ele mesmo criou.
- O botão "Enviar ao cliente via chat" só aparece para a equipe.

## Base de conhecimento por produto

**Artigo sem nenhum produto vinculado vale para TODOS os produtos.**

Essa é a regra central. Ela existe para que artigos genéricos ("Como abrir um
chamado", "Política de garantia") não precisem apontar para um produto
arbitrário — e é o que manteve válidos, sem backfill, todos os artigos criados
antes da tabela `kb_article_products`.

No formulário isso aparece como a caixa **"Vale para todos os produtos"**. O
campo é obrigatório no sentido de que o técnico precisa decidir: ou marca a
caixa, ou escolhe pelo menos um produto.

### Como o artigo chega ao cliente no chamado

As sugestões buscam em camadas, da mais específica para a mais ampla, até
completar o limite (5 artigos):

| Ordem | Critério |
|---|---|
| 1 | produto do ticket **e** mesma categoria |
| 2 | produto do ticket, em qualquer categoria |
| 3 | mesma categoria, em qualquer produto (aqui entram os "todos os produtos") |
| 4 | palavra-chave do título do chamado |

Basta **produto OU categoria** casar. O produto vem do campo Produto do ticket;
se estiver vazio, do equipamento escolhido pelo cliente.

Na **listagem** da base (fora do chamado) não há restrição: todos veem a base
inteira, e produto e categoria são apenas filtros.

## Acesso: confirmação de e-mail e recuperação de senha

### O sistema se adapta ao SMTP

**Enquanto não houver SMTP configurado, o cadastro libera o acesso na hora**, como
antes. A confirmação só passa a ser exigida quando `SMTP_FROM_EMAIL` ou
`SMTP_USER` estiverem preenchidos (`Settings.requires_email_verification()`).

Isso existe para que o código possa ser publicado antes das credenciais de
e-mail: sem essa trava, o cliente criaria conta e ficaria esperando um link que
o sistema não tem como enviar. Ao preencher as credenciais, a regra passa a
valer sozinha — não precisa de novo deploy.

### Fluxo

Cadastro completo → conta criada bloqueada → e-mail com link → clique → conta
ativa → login → onboarding da empresa.

Quem tenta entrar antes de confirmar recebe **o motivo real** ("Confirme seu
e-mail...") e um botão para reenviar o link — não o genérico "e-mail ou senha
incorretos", que deixaria a pessoa tentando a senha à toa.

### Links

São JWT assinados, sem tabela e sem limpeza periódica:

| Link | Validade | Observação |
|---|---|---|
| Confirmação de cadastro | 24 h | `EMAIL_VERIFICATION_TOKEN_HOURS` |
| Redefinição de senha | 1 h | **uso único** |

O **uso único** funciona sem guardar estado: o token carrega uma impressão
digital da senha vigente, conferida contra a senha atual do usuário. Trocada a
senha, o link morre — inclusive o que acabou de ser usado. Sem isso, um link
esquecido na caixa de e-mail abriria a conta meses depois.

Cada token tem um tipo (`email_verify` ou `password_reset`) e não serve para
outra finalidade — um token de login também não vira link de arquivo.

### Por que as mensagens são vagas de propósito

"Esqueci a senha" e "reenviar confirmação" **sempre** respondem *"Se este e-mail
estiver cadastrado, você receberá..."*, mesmo quando o e-mail não existe.

Parece ruim para o usuário, mas responder "e-mail não encontrado" permitiria
que qualquer pessoa descobrisse quais e-mails têm conta no sistema, testando
endereços um a um.

Uma exceção deliberada: **redefinir a senha confirma o e-mail junto**. Quem
abriu o link provou ser dono da caixa.

## Cadastro do cliente

**CNPJ e CEP são obrigatórios** no onboarding e ao salvar os dados da empresa no
perfil. O CNPJ é validado pelos dois dígitos verificadores, tanto no frontend
(`frontend/src/lib/documents.ts`) quanto no backend (`OnboardingUpdate`) — a
regra não é contornável pela API.

As colunas seguem `nullable` no banco de propósito: **clientes cadastrados antes
da regra não são bloqueados**. Eles veem um aviso no perfil pedindo para
completar o cadastro.

## Respostas rápidas do chat

Lista **única para toda a equipe** — não há respostas por técnico. Admin e
técnico gerenciam em Gestão › Respostas Rápidas.

No chat, `/` abre o menu; continuar digitando filtra por atalho ou título,
ignorando acentos. Resposta inativa continua cadastrada mas some do menu.

Fora de escopo por ora: variáveis dinâmicas (`{{nome_do_cliente}}`), anexos e
categorias de resposta.

## Armazenamento de arquivos

**Anexos de chamado e fotos de perfil ficam em disco**, no caminho de
`UPLOAD_DIR` (padrão `/app/uploads`). Antes iam para MinIO/S3; a troca foi feita
em 05/08/2026 porque o ambiente de produção não tem serviço de storage e a
hospedagem oferece volume.

**No deploy, esse caminho precisa ser um volume.** Sem volume, o Docker descarta
o conteúdo a cada redeploy e todos os anexos somem. No EasyPanel:
serviço `helphs-api` › Armazenamento › **Adicionar Montagem de Volume**, com
`/app/uploads` como caminho no container.

O `Dockerfile` cria `/app/uploads` já pertencente ao `appuser` antes de trocar
de usuário. Isso é necessário: o container não roda como root, e um volume
montado sobre um diretório de root ficaria sem permissão de escrita.

### Como o arquivo chega ao navegador

Por **link temporário assinado**, não pela sessão do usuário — a foto de perfil e
a pré-visualização de anexo são carregadas pelo `<img src>`, que não envia
cabeçalho de autenticação.

1. A API devolve `/api/v1/files/<token>`, com validade de `FILE_URL_EXPIRES_SECONDS`
2. O frontend prefixa com o host da API (`resolveFileUrl`), porque em produção
   frontend e API ficam em domínios diferentes
3. O endpoint valida a assinatura e o tipo do token antes de servir o arquivo

O token é do tipo `file`: um token de login **não** serve para baixar arquivo, e
vice-versa. A key é validada contra path traversal — nenhum caminho sai de
`UPLOAD_DIR`.

### Por que quase tudo desce como download

Os arquivos vêm de upload de cliente. Servi-los inline no domínio da API é o
mesmo que deixar terceiros publicarem conteúdo naquela origem: um `.html` ou um
`.svg` com script rodaria **como se fosse do sistema** (XSS armazenado).

Por isso o endpoint `/files`:

- só exibe inline **png, jpeg, gif e webp** — o necessário para foto de perfil e
  pré-visualização de imagem;
- **SVG fica de fora de propósito**: é imagem, mas aceita `<script>` dentro;
- qualquer outro tipo vira `application/octet-stream` com
  `Content-Disposition: attachment`;
- toda resposta leva `X-Content-Type-Options: nosniff` e
  `Content-Security-Policy: default-src 'none'; sandbox`.

Hoje a allowlist de upload (`UPLOAD_ALLOWED_EXTENSIONS`) não aceita `.html` nem
`.svg`, mas ela é configurável por variável de ambiente — a proteção no download
existe para que mudar essa variável não abra um buraco.

Como o arquivo em disco tem nome interno (uuid), o backend acrescenta
`?filename=` na URL do anexo para o download sair com o nome original.

## LGPD

A anonimização de usuário existe no backend e foi **removida da interface de
propósito**. Manter o endpoint para uso futuro.

---

# Pendências conhecidas

Coisas que os documentos de Requisitos preveem e que **não estão implementadas**.
Nenhuma delas foi pedida pelo cliente até agora — estão aqui para não se
perderem.

### Celery continua sem worker

O `backend/app/worker/tasks.py` tem três tarefas de exemplo, nenhuma
implementada, e **nada as executa** — não há worker nem beat no EasyPanel. O
fechamento automático precisou ser resolvido por fora (ver "Ciclo de
encerramento do chamado").

Se um dia aparecer trabalho pesado o bastante para justificar, o caminho é
subir um serviço `celery -A app.worker.celery_app worker --beat` e mover a
rotina para lá.

### Antivírus (ClamAV) não está no ambiente

O upload de anexo passa por varredura antivírus antes de gravar
(`backend/app/services/antivirus.py`). Como o serviço **não existe no EasyPanel**,
o resultado da varredura vem como `unavailable` e o arquivo é aceito assim mesmo,
marcado como não escaneado (`virus_scanned = false` na tabela `attachments`).

Ou seja: **nenhum anexo enviado hoje é verificado contra vírus**. Nada trava, mas
arquivo malicioso enviado por um cliente entra sem checagem.

Decidido em 05/08/2026 manter assim por ora e revisar depois. Para ligar, basta
subir um serviço `clamav/clamav:latest` e apontar `CLAMAV_HOST`/`CLAMAV_PORT` —
o código já está pronto, não precisa de alteração.

### Cobertura de testes desigual

A suíte do backend está em ~80%, mas concentrada. Os pontos fracos são
`groups.py` (34%) e `chat.py` (53%) — nenhum deles tocado nas últimas rodadas.
