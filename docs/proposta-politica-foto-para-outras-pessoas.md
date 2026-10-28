# PROPOSTA — Política de Privacidade: foto de perfil para outras pessoas

**Documento INTERNO. Não é política, não é texto publicado e não é servido ao
usuário.** Mora em `docs/` pelo mesmo motivo de
`proposta-politica-gravacao-de-chamadas.md`: o frontend importa só
`src/content/politica-privacidade.md` e `src/content/termos-de-uso.md`, e
qualquer rebuild publicaria um texto colocado ali. Este arquivo não entra no
bundle.

Preparado em 21/10/2026 para a Fase 3B (PR #94, em rascunho), revisto em
26/10/2026 com as decisões de comportamento e em 28/10/2026 com a Decisão 2 e
as recomendações candidatas das Decisões 3 e 4. **Nada aqui está aprovado.** A
Política publicada (PGS-TI-031, Revisão 00, vigência 05/10/2026) não foi
alterada.

A candidata completa da Revisão 01 está em
[`candidata-pgs-ti-031-revisao-01.md`](candidata-pgs-ti-031-revisao-01.md).

## Estado das decisões

### Decisão 2 — novo aceite geral: DEFINIDA (27/10/2026)

- Haverá novo aceite geral da Revisão 01.
- O aceite é condição obrigatória de uso, e o backend faz o enforcement.
- `criado_por_terceiro` não vale como aceite do titular.
- Clientes, técnicos e administradores aceitam.
- Aviso prévio mínimo de 15 dias.
- A implementação técnica já existe na `main` (PR #97), mas está inativa:
  `LGPD_EXIGE_REACEITE=false`.
- **Isso não significa que a Revisão 01 esteja aprovada ou publicada.**

O aceite geral **nunca** liga a autorização da foto, nem o revogar a desliga:
são registros separados, com testes próprios
(`test_aceite_da_politica_e_upload_nao_ativam_a_escolha` e
`test_revogar_o_aceite_da_politica_nao_revoga_a_autorizacao_da_foto`).

### Decisão 1 — Revisão 01: CANDIDATA PRONTA, pendente de aprovação formal

- O texto candidato completo está no arquivo citado acima.
- A elaboração e o versionamento formais cabem à Qualidade / SGI, e a
  aprovação, à Diretoria.
- A Revisão 00 foi elaborada por Gustavo Oliveira e aprovada por Nicholson
  Pimentel em 25/09/2026. **Isso não equivale à aprovação da Revisão 01.**
- Data de aprovação, vigência e aprovação efetiva seguem pendentes.

### Decisão 3 — foto de técnicos e administradores: RECOMENDAÇÃO CANDIDATA

Registrada como recomendação, **não como aprovação jurídica nem parecer
jurídico definitivo**:

> A exibição da foto de técnicos e administradores aos clientes continua
> dependendo de autorização específica, opcional e individual do próprio
> titular.

Fundamento candidato para a Política:

- consentimento específico do titular para a exibição da imagem a outros
  participantes dos atendimentos;
- separado do aceite geral da PGS-TI-031: o aceite geral da Política **não** é
  usado como consentimento da foto;
- revogável no próprio perfil;
- sem autorização, aparecem as iniciais, e isso não limita o trabalho nem o
  acesso;
- administrador não pode autorizar por outra pessoa.

Na candidata (seção 8), a linha leva a marca: "Base legal candidata:
consentimento específico — sujeita à aprovação formal da Revisão 01."

### Decisão 4 — guarda dos registros: RECOMENDAÇÃO DE GOVERNANÇA CANDIDATA

Prazo proposto para `avatar_visibility_events`:

> **5 anos** contados do evento mais recente de autorização ou revogação, ou do
> encerramento ou da anonimização da conta, o que ocorrer por último.

Após o prazo:

- eliminar ou anonimizar o registro de forma que não permaneça identificável;
- ressalvar a conservação necessária por obrigação legal ou regulatória,
  exercício regular de direitos, investigação ou litígio, quando aplicável.

⚠️ **O código atual NÃO executa expurgo automático** desses registros (nem de
nenhum outro: seção 13.1 da Política). O prazo não é cumprido hoje.

- A rotina de expurgo é **requisito futuro**, a ser implantada antes de a
  regra entrar em vigor de fato.
- Ela **não** será implementada no PR #94 sem autorização posterior.

Na candidata (seção 13), o prazo aparece como: "5 anos — proposta candidata,
pendente de aprovação formal e de mecanismo técnico de expurgo."

## O comportamento decidido (para a redação refletir o que é verdade)

- **Desligado por padrão**, para contas existentes e novas, de clientes,
  técnicos e administradores. Ter foto, aceitar a Política ou enviar uma foto
  nova não autoriza.
- **Separado do envio da foto e opcional.** Recusar não limita nada no uso do
  HelpHS.
- **Só o titular** autoriza ou revoga, no próprio perfil. Nenhum administrador
  muda a escolha de outra pessoa.
- **Produção só aceita texto aprovado.** Ambientes de teste (staging) podem
  usar a minuta para exercitar o fluxo; isso não gera autorização em produção,
  que tem outro banco e recusa minuta, texto de teste e versão inexistente.
- **Registro:** cada autorização e revogação é guardada com data e hora, a
  versão do texto apresentado, a origem ("alteração própria") e o IP. A foto, o
  arquivo e os links não entram nesse registro.

## A. Aviso final candidato

**Identificador candidato:** `FOTO-PARTICIPANTES-2026-01`.

- Este texto **ainda não está no catálogo** (`backend/app/services/exibicao_da_foto.py`).
  Entra lá só depois da aprovação formal, com este nome e `aprovado=True`.
- A minuta atual (`MINUTA-2026-10-21`, `aprovado=False`) não é editada no
  lugar, porque o nome da versão é o que os registros gravam. Em produção,
  ninguém autoriza enquanto não houver texto aprovado.

**Rótulo:**

> Permitir que minha foto de perfil apareça para outros participantes dos
> atendimentos.

**Para o cliente:**

> Se você permitir, a equipe de atendimento (técnicos e administradores) verá
> a sua foto nos chamados que você abriu e junto das mensagens que você enviar
> neles. Outros clientes nunca veem a sua foto.

**Para o técnico ou administrador:**

> Se você permitir, a sua foto aparece para a equipe nos chamados; para o
> cliente, nos chamados em que você é o responsável; e, nas conversas, junto
> das mensagens que você enviar — para a equipe e para o cliente que abriu o
> chamado.

**Para todos (vem depois do parágrafo do papel):**

> - É opcional e separado do aceite da Política de Privacidade: aceitar a
>   Política não liga a sua foto.
> - Enquanto você não permitir, as outras pessoas veem só as suas iniciais —
>   mesmo que você já tenha uma foto no perfil. Você continua abrindo chamados
>   e conversando normalmente.
> - Não é preciso enviar a foto de novo. A permissão vale para a foto que
>   estiver no seu perfil a cada momento: se você trocar a foto, a nova aparece
>   no lugar; se remover, aparecem as iniciais.
> - Você pode desligar quando quiser, aqui no perfil. A partir daí, as telas
>   abertas depois mostram as suas iniciais. Uma tela que outra pessoa já tinha
>   aberto pode continuar mostrando a foto por algum tempo, e uma imagem que já
>   foi carregada ou copiada não some por causa disso.
> - Desligar não apaga a sua foto: ela continua no seu perfil, para você.

## B. Quem vê a foto, com autorização

Sempre dentro de um chamado que a pessoa já pode ver:

- **Foto do cliente:** a equipe de atendimento, nos chamados que ele abriu
  (bloco "Solicitante") e junto das mensagens que ele envia neles.
- **Foto do técnico ou administrador:** a equipe, nos chamados; o cliente, nos
  chamados em que ele é o responsável; e, na conversa, a equipe e o cliente
  que abriu o chamado, junto das mensagens que ele envia.
- **Outro cliente nunca** vê a foto de um cliente, com ou sem autorização.
- **A própria pessoa** vê a própria foto sempre (perfil, topo da tela e o
  bloco do próprio chamado). Na conversa, sem autorização, a mensagem sai sem
  foto para todos, ela incluída.

## C. Fotos já existentes

> As fotos enviadas antes desta revisão não são exibidas a outras pessoas até
> que o próprio usuário autorize. Elas não foram apagadas e não precisam ser
> enviadas novamente: a decisão é feita no perfil.

## D. Revogação

> O usuário pode revogar a autorização a qualquer tempo, no próprio perfil,
> sem prejuízo do atendimento. A partir da revogação, as novas telas deixam de
> exibir a foto. Um link já entregue a uma tela aberta pode continuar exibindo
> a imagem até expirar, por tempo limitado; o navegador de quem a viu pode
> mantê-la em cache; e cópias salvas ou capturadas por outras pessoas não
> podem ser apagadas retroativamente.

Nota técnica, fora do texto: o link da foto de outra pessoa usa o prazo dos
arquivos (`file_url_expires_seconds`), que no código tem padrão de 3600 s. O
valor de produção não foi medido; por isso o texto diz "por tempo limitado".

## E. Conta inativa

> Enquanto a conta estiver inativa, a foto não é exibida a outras pessoas. A
> escolha do usuário fica guardada e volta a valer se a conta for reativada.
> Isso não é uma revogação e nada é registrado em nome do usuário.

## F. Anonimização

> Quando a conta é anonimizada, a foto é apagada e a autorização deixa de
> valer. Se a conta voltar a ser usada, a foto só volta a aparecer para outras
> pessoas com uma nova autorização do titular.

Sobre os registros, para a seção de retenção:

> Os registros de autorização e revogação não são apagados quando a conta é
> anonimizada ou excluída. Na exclusão, o registro deixa de apontar para a
> conta, mas data, versão do texto e endereço IP permanecem. Prazo de guarda:
> **5 anos — proposta candidata (Decisão 4), pendente de aprovação formal e de
> mecanismo técnico de expurgo.**

## Onde cada parte entrou na candidata da Revisão 01

- **Cabeçalho, seção 1 e Tabela de Revisão:** Revisão 01, vigência
  **[A DEFINIR]**, linha 01 com data e aprovação **[PENDENTE]**.
- **Seção 6:** a linha "Imagem de perfil" remete à autorização, e há linha nova
  para o registro da autorização.
- **Seção 8:** a finalidade da imagem é separada em duas linhas — exibição ao
  próprio usuário, que mantém a base da Revisão 00, e exibição a outros
  participantes, com a base legal candidata da Decisão 3. A linha do registro
  da autorização fica com a base **[A DEFINIR]**.
- **Seção 8.1, nova:** A (próprio usuário), B (outros participantes, por
  papel, com revogação, conta inativa e anonimização) e C (registro).
- **Seção 12:** linha para os outros participantes dos atendimentos, dentro da
  plataforma, sem destinatário externo.
- **Seção 13:** a imagem de perfil é apagada na anonimização, e há linha nova
  com o prazo candidato da Decisão 4. A seção 13.1 diz que esses registros
  também não são expurgados hoje.
- **Seção 15:** a Decisão 2 (novo aceite obrigatório para os três papéis,
  depois da comunicação da seção 20; o aceite pela equipe não vale) e a
  separação entre o aceite e a autorização da foto.
- **Seção 16:** revogação da autorização direto no perfil.
- **Sem mudança:** seções 2 a 5, 7, 9 a 11, 14 e 17 a 22. A seção 20 já
  prevê o aviso prévio de 15 dias.

## Consistência com a `main` (PR #97)

A candidata foi conferida contra o que a `main` já faz:

- o novo aceite vale para os três papéis;
- `criado_por_terceiro` não satisfaz;
- o backend bloqueia só pela Política (428 e 4428); os Termos não têm
  enforcement no backend, e a candidata não muda os Termos;
- o aceite da Política não autoriza a foto.

## O que ainda depende de aprovação formal

- O texto da Revisão 01 inteiro: elaboração pela Qualidade / SGI e aprovação
  pela Diretoria.
- A base legal candidata da Decisão 3 e a base do registro da autorização,
  que ainda está **[A DEFINIR]**.
- O prazo candidato da Decisão 4, além do mecanismo técnico de expurgo.
- O texto final e o identificador do aviso (`FOTO-PARTICIPANTES-2026-01`).
- As datas de comunicação e de vigência.
- Na fase operacional, e só nela, `LGPD_REVISAO_POLITICA=01` e as demais
  etapas de ativação do PR #97.

## O que NÃO foi feito

- A Política publicada não foi alterada.
- Nenhum texto foi aprovado. A minuta segue com `aprovado=False`, e o aviso
  candidato não entrou no catálogo.
- Nenhuma flag, revisão configurada, versão ou release mudou.
- Nenhum aceite, autorização ou registro foi criado para usuários reais.
- Nenhum e-mail de aviso foi enviado; o aviso de lançamento é só dentro da
  plataforma e não bloqueia o uso.
- Nenhuma rotina de expurgo foi implementada.
