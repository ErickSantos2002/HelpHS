# PROPOSTA - Politica de Privacidade: gravacao de chamadas

**Documento INTERNO. Nao e politica, nao e texto publicado, e nao e servido ao
usuario.** Vive em `docs/` de proposito: o frontend importa exatamente dois
markdown, `src/content/politica-privacidade.md` e `src/content/termos-de-uso.md`
-- medido, e nada de `docs/` entra no bundle. Um rebuild do front nao publica
este arquivo.

## Por que a proposta mora aqui, e nao no arquivo publico

A redacao abaixo foi escrita para entrar na PGS-TI-031, e chegou a ser inserida
no arquivo publico com um aviso de "TEXTO EM PROPOSTA - NAO VIGENTE". Essa
abordagem foi **revertida em 09/10/2026, a pedido do Rickelme**, e o motivo dele
e melhor que o aviso:

`frontend/src/content/politica-privacidade.md` e importado com `?raw` por
`PoliticaPrivacidadePage.tsx` e renderizado na pagina publica. Qualquer rebuild
do frontend publicaria o texto -- aviso e tudo. Um banner de "nao vigente" numa
pagina de politica e, na melhor das hipoteses, confuso para o titular; e depender
de ninguem reconstruir o front e depender de disciplina, nao de desenho.

Entao o arquivo publico voltou a ser **byte a byte identico a `main`**, e a
proposta espera aqui.

## O que ainda falta para isto virar politica

Nada neste arquivo esta aprovado. Em particular, continuam **indefinidos**: base
legal, prazo de retencao do audio, prazo da transcricao e o enquadramento
juridico do provedor de telefonia.

Quando houver aprovacao, o caminho e: o Setor de Qualidade/SGI incorpora o texto,
incrementa a revisao, define a vigencia e preenche a Tabela de Revisao e
Aprovacao; a Diretoria aprova (secao 19 da propria politica). Depois disso, pelas
secoes 15 e 20, a publicacao exige **comunicacao previa de 15 dias** e **novo
aceite** do titular -- e ai sim o conteudo entra em
`frontend/src/content/politica-privacidade.md`, junto com o bump de
`LGPD_REVISAO_POLITICA`.

As duas coisas andam juntas: o texto vem do bundle do front e o numero da revisao
vem do ambiente do backend. Publicar um sem o outro grava aceite de uma revisao
contra um texto diferente -- ver "Fases 2D.1 e 2D.2" em `decisoes-e-regras.md`.

---

## A redacao proposta

O que segue e o diff que havia sido aplicado ao arquivo publico, preservado na
integra: quatro linhas de tabela (secoes 6, 8, 12 e 13), um paragrafo na secao 7
sobre o canal de voz, e a secao 23 completa. A numeracao citada e a da
PGS-TI-031.

~~~markdown
> ⚠️ **TEXTO EM PROPOSTA — NÃO VIGENTE.** O conteúdo sobre **gravação de
> chamadas de atendimento** é minuta técnica submetida à aprovação
> institucional, e **não** integra a revisão 00 em vigência. Alcança a linha
> de gravação na seção 6, a finalidade na seção 8, o parágrafo do canal de voz
> na seção 7, o provedor de telefonia na seção 12, o prazo na seção 13 e a
> **seção 23** inteira.
>
> Enquanto este aviso existir: a **base legal não está definida**, o **prazo de
> retenção não está aprovado**, o **enquadramento jurídico do provedor de
> telefonia não está formalizado**, e o número de revisão, a data de vigência e
> a Tabela de Revisão e Aprovação **seguem intocados de propósito** — versionar
> é do Setor de Qualidade/SGI e aprovar é da Diretoria (seção 19).
>
> Publicar este texto exige, pelas próprias seções 15 e 20: nova revisão,
> **comunicação prévia de 15 dias** e **novo aceite** do titular. Este aviso sai
> no mesmo ato em que a revisão for aprovada.

| Gravação de atendimento telefônico | Gravação em áudio da ligação realizada pela equipe de atendimento no contexto de um chamado, contendo as falas dos dois participantes, e a transcrição dessa gravação, quando o recurso for implantado. | Gerada pelo provedor de telefonia no momento da ligação. Ver seção 23. |
A recomendação acima pressupõe que o usuário possa revisar o conteúdo antes de enviá-lo, o que não ocorre no atendimento por telefone: a ligação é registrada tal como falada, e o usuário pode mencionar espontaneamente informações que, conforme o conteúdo, envolvam dados pessoais de terceiros ou dados pessoais sensíveis. Não se presume que toda gravação contenha dados sensíveis; presume-se que ela **possa** contê-los, e por isso as gravações e as respectivas transcrições recebem proteção reforçada, com acesso restrito, registro de auditoria próprio e as condições descritas na seção 23.

| Registrar o atendimento telefônico, assegurar a continuidade do suporte, permitir auditoria operacional, apurar divergências e melhorar a qualidade do atendimento. | Gravação de atendimento telefônico. | Ver seção 23. Base legal aplicável em validação pelo Encarregado; recurso não disponível aos usuários nesta revisão. |
| Provedor de telefonia e comunicação | Número de telefone do destinatário da ligação e, quando a gravação estiver habilitada no ramal utilizado, o áudio da chamada. | Realizar e encaminhar as ligações de atendimento e disponibilizar a respectiva gravação. Ver seção 23. |
| Gravação de atendimento telefônico e respectiva transcrição | Prazo específico **em definição**, menor que o do conteúdo dos chamados; ver seção 23.7. | Minimização: a gravação é o registro mais sensível do atendimento e não deve ser conservada pelo mesmo prazo do texto. |
## 23. Gravação de Chamadas de Atendimento

### 23.1. Estado atual

A plataforma HelpHS permite que a equipe de atendimento inicie uma ligação telefônica a partir de um chamado. Essa ligação é realizada por provedor de telefonia contratado e, no ramal utilizado em produção, a **gravação do áudio está habilitada na plataforma do provedor**, que registra as falas dos dois participantes.

Hoje a plataforma HelpHS **não** transfere, **não** armazena, **não** reproduz e **não** transcreve essas gravações: o áudio permanece exclusivamente na plataforma do provedor de telefonia, e nenhum usuário da plataforma — cliente ou integrante da equipe — tem acesso a ele pela interface do HelpHS.

As condições descritas nas subseções seguintes aplicam-se ao tratamento das gravações e serão observadas quando e se o recurso for implantado, na forma da subseção 23.8.

### 23.2. Finalidade

As gravações de atendimento telefônico destinam-se exclusivamente a:

- registrar o atendimento prestado;
- assegurar a continuidade do suporte, quando o atendimento envolver mais de um contato ou mais de um atendente;
- permitir auditoria operacional do atendimento;
- apurar divergências sobre o que foi informado ou acordado durante a ligação;
- aferir e melhorar a qualidade do atendimento.

As gravações **não** são utilizadas para publicidade, para formação de perfil comportamental, para análise comercial, para prospecção nem para treinamento de modelos de inteligência artificial de terceiros.

### 23.3. Aviso ao titular

O titular será informado, antes do início ou no início da ligação, de que o atendimento poderá ser gravado, com indicação da finalidade e remissão a esta política.

O texto operacional proposto para esse aviso é:

> "Esta ligação poderá ser gravada para fins de registro do atendimento, segurança e qualidade do suporte. Consulte nossa Política de Privacidade para mais informações."

A redação final do aviso e a forma de apresentá-lo serão definidas antes da ativação do recurso.

### 23.4. Acesso às gravações e às transcrições

O acesso é restrito à equipe de atendimento da Health & Safety, pelo critério do menor privilégio, e observa a regra de visibilidade do chamado:

| Perfil | Acesso à gravação | Acesso à transcrição |
|---|---|---|
| Administrador | Conforme a regra de visibilidade do chamado. | Conforme a regra de visibilidade do chamado. |
| Técnico de atendimento | Apenas nos chamados que o próprio perfil pode visualizar. | Apenas nos chamados que o próprio perfil pode visualizar. |
| Cliente | Não disponível. | Não disponível. |

Gravação e transcrição são tratadas como recursos **distintos** para fins de autorização e de registro de auditoria: a autorização para uma não implica autorização para a outra, e cada acesso é registrado separadamente.

O titular que desejar obter a gravação de um atendimento do qual participou exerce o direito de acesso previsto na seção 16, por meio dos canais da seção 22, com verificação de identidade — fluxo administrativo distinto da consulta operacional descrita no quadro acima.

### 23.5. Download

Na primeira versão do recurso **não haverá download** de gravação na interface da plataforma: o acesso autorizado se dará por reprodução controlada dentro do próprio HelpHS.

A plataforma não entrega ao navegador do usuário o endereço da gravação na plataforma do provedor, e esse endereço não é divulgado a nenhum usuário.

### 23.6. Provedor de telefonia

A realização das ligações e a geração da gravação dependem de provedor de telefonia e comunicação contratado pela Health & Safety, que trata o número de telefone do destinatário e, quando a gravação está habilitada, o áudio da chamada, exclusivamente para executar o serviço contratado.

O provedor está sujeito às obrigações de confidencialidade e de segurança aplicáveis aos fornecedores que tratam dados em nome da Health & Safety, nos termos da seção 14, e à avaliação de segurança de fornecedores ali prevista. As condições contratuais específicas aplicáveis à gravação — notadamente retenção, eliminação e eventuais subcontratados — são objeto de verificação formal antes da ativação do recurso, na forma da subseção 23.8.

### 23.7. Retenção e eliminação

A gravação de atendimento telefônico é o registro mais sensível do atendimento e, por isso, **não deve ser conservada pelo mesmo prazo do conteúdo textual do chamado**. O prazo específico será definido e aprovado antes da ativação do recurso, e será menor que o prazo previsto para o conteúdo dos chamados no quadro da seção 13. A transcrição poderá observar prazo próprio, distinto do prazo do áudio.

A eliminação ao término do prazo depende da rotina automática de expurgo referida na subseção 13.2. Enquanto essa rotina não estiver implantada, o recurso de gravação não será disponibilizado aos usuários com prazo de retenção anunciado que a plataforma não tenha meios de cumprir.

A eliminação da gravação remove o conteúdo armazenado. O registro de auditoria do ato de eliminação é conservado com os metadados mínimos necessários à rastreabilidade — quem eliminou, quando e a qual chamado o registro se referia — e não contém o endereço da gravação nem o seu conteúdo.

A anonimização ou a eliminação de dados do usuário na plataforma HelpHS não produz, por si, a eliminação da gravação na plataforma do provedor de telefonia. O procedimento de eliminação junto ao provedor é objeto da verificação prevista na subseção 23.8.

### 23.8. Condições para a ativação

O recurso de gravação acessível pela plataforma — transferência, armazenamento, reprodução e eventual transcrição — somente será disponibilizado após o cumprimento cumulativo das seguintes condições:

- definição e aprovação da base legal aplicável pelo Encarregado;
- aprovação da redação final do aviso ao titular e da sua forma de apresentação;
- definição e aprovação dos prazos de retenção da gravação e da transcrição;
- verificação formal das condições contratuais do provedor de telefonia quanto a retenção, eliminação e eventuais subcontratados;
- publicação de revisão desta política contemplando o tratamento, com a comunicação prévia e o novo aceite previstos nas seções 15 e 20;
- implantação dos controles técnicos de acesso, de auditoria e de eliminação descritos nesta seção.

Até que todas essas condições estejam cumpridas, permanece válido o estado descrito na subseção 23.1.
~~~

---

## Procedencia

Extraido de `frontend/src/content/politica-privacidade.md` no commit `78363e3`,
antes da reversao. Nada foi reescrito na transposicao: sao as 104 linhas
acrescentadas, na ordem em que estavam.
