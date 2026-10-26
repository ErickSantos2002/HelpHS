# PROPOSTA — Política de Privacidade: foto de perfil para outras pessoas

**Documento INTERNO. Não é política, não é texto publicado e não é servido ao
usuário.** Mora em `docs/` pelo mesmo motivo de
`proposta-politica-gravacao-de-chamadas.md`: o frontend importa só
`src/content/politica-privacidade.md` e `src/content/termos-de-uso.md`, e
qualquer rebuild publicaria um texto colocado ali. Este arquivo não entra no
bundle.

Preparado em 21/10/2026 para a Fase 3B (PR #94, em rascunho) e revisto em
26/10/2026 com as decisões de comportamento já tomadas. **Nada aqui está
aprovado.** A Política publicada (PGS-TI-031, Revisão 00, vigência 05/10/2026)
não foi alterada.

## Para decidir — quatro pontos que não são técnicos

O comportamento do sistema já está decidido (abaixo). Estes quatro pontos
continuam com o responsável pela Política, e o código não escolhe nenhum
deles:

1. **Redação jurídica final** deste texto, e se ele entra numa Revisão 01 da
   PGS-TI-031.
2. **Novo aceite geral ou não.** A seção 15 da Política diz que a inclusão de
   novo destinatário pede novo aceite. A autorização implementada é específica,
   opcional e começa desligada; se isso dispensa o re-aceite da Política
   inteira é decisão do responsável. O aceite geral **nunca** liga a
   autorização da foto, com ou sem nova revisão.
3. **Base legal para as fotos da equipe** (técnicos e administradores)
   exibidas a clientes. O sistema trata todos os papéis igual — exibição só
   com a autorização individual —, mas a base legal declarada para
   funcionários não foi escolhida.
4. **Prazo de guarda dos registros** de autorização e revogação
   (`avatar_visibility_events`). Não há limpeza automática nem prazo no
   código.

Depois da decisão, o texto aprovado da opção entra no catálogo
(`backend/app/services/exibicao_da_foto.py`) com um **nome de versão novo** e
`aprovado=True`. A minuta atual (`MINUTA-2026-10-21`, `aprovado=False`) não é
editada no lugar: o nome é o que os registros gravam.

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

## Pacote proposto para aprovação

### A. Texto da opção no perfil

Rótulo (base sugerida em 26/10/2026):

> Permitir que minha foto de perfil apareça para outros participantes dos
> atendimentos nos quais essa visualização é permitida.

Complemento comum:

> Essa escolha é opcional e pode ser alterada a qualquer momento. Se você não
> autorizar, serão exibidas apenas suas iniciais.

Complemento por papel — necessário porque quem vê é diferente para cliente e
para equipe (item B):

- **Cliente:** "A equipe de atendimento (técnicos e administradores) verá a sua
  foto nos chamados que você abriu e junto das mensagens que você enviar
  neles. Outros clientes nunca veem a sua foto."
- **Técnico ou administrador:** "A sua foto aparece para a equipe nos
  chamados; para o cliente, nos chamados em que você é o responsável; e, nas
  conversas, junto das mensagens que você enviar — para a equipe e para o
  cliente que abriu o chamado."

Avisos que a tela já mostra hoje e que o texto aprovado deve manter (itens D a
F tratam do resto):

> A permissão vale para a foto que estiver no seu perfil a cada momento: se
> você trocar a foto, a nova aparece no lugar; se remover, aparecem as
> iniciais. Desligar não apaga a sua foto: ela continua no seu perfil, para
> você.

### B. Quem vê a foto, com autorização

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

### C. Fotos já existentes

> As fotos enviadas antes desta revisão não são exibidas a outras pessoas até
> que o próprio usuário autorize. Elas não foram apagadas e não precisam ser
> enviadas novamente: a decisão é feita no perfil.

### D. Revogação

> O usuário pode revogar a autorização a qualquer tempo, no próprio perfil,
> sem prejuízo do atendimento. A partir da revogação, as novas telas deixam de
> exibir a foto. Um link já entregue a uma tela aberta pode continuar exibindo
> a imagem até expirar (até uma hora), o navegador de quem a viu pode
> mantê-la em cache, e cópias salvas ou capturadas por outras pessoas não
> podem ser apagadas retroativamente.

### E. Conta inativa

> Enquanto a conta estiver inativa, a foto não é exibida a outras pessoas. A
> escolha do usuário fica guardada e volta a valer se a conta for reativada.
> Isso não é uma revogação e nada é registrado em nome do usuário.

### F. Anonimização

> Quando a conta é anonimizada, a foto é apagada e a autorização deixa de
> valer. Se a conta voltar a ser usada, a foto só volta a aparecer para outras
> pessoas com uma nova autorização do titular.

Sobre os registros, para a seção de retenção:

> Os registros de autorização e revogação não são apagados quando a conta é
> anonimizada ou excluída. Na exclusão, o registro deixa de apontar para a
> conta, mas data, versão do texto e endereço IP permanecem. O prazo de guarda
> desses registros é: **[a definir pelo responsável pela Política]**.

## Onde cada parte entraria na Política (sugestão de encaixe)

Marcadores **[...]** são decisões pendentes; nada aqui afirma base legal ou
exigência legal como fato.

- **Seção 6, linha "Imagem de perfil":** acrescentar "A exibição da foto a
  outros participantes dos atendimentos depende de autorização específica do
  usuário, concedida e revogada no próprio perfil." E uma linha nova para o
  registro da autorização (data e hora, versão do texto, IP; registrado quando
  o usuário altera a escolha).
- **Seção 8, finalidade:** identificar visualmente o usuário — para ele mesmo,
  sempre; para os participantes dos atendimentos, só com a autorização (item
  B). Base legal: **[proposta: consentimento específico, revogável no perfil —
  a confirmar; para técnicos e administradores, decisão pendente (ponto 3)]**.
  Registro da autorização: finalidade de comprovar a escolha; base legal
  **[a confirmar]**.
- **Seção 12, compartilhamento:** não há destinatário externo novo; uma frase
  remetendo à seção 8 evita dúvida.
- **Seção 13, retenção:** imagem de perfil enquanto a conta existir ou até o
  usuário removê-la (apagada na anonimização); registro da autorização
  **[prazo a definir — ponto 4]**.
- **Seção 16 ou 8, revogação:** item D.

## O que NÃO foi feito

- A Política publicada não foi alterada.
- Nenhum texto foi aprovado; a minuta segue `aprovado=False`.
- Nenhum aceite, autorização ou registro foi criado para usuários reais.
- Nenhum e-mail de aviso foi enviado; o aviso de lançamento é só dentro da
  plataforma e não bloqueia o uso.
