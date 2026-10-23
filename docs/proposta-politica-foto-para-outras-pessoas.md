# PROPOSTA — Política de Privacidade: foto de perfil para outras pessoas

**Documento INTERNO. Não é política, não é texto publicado e não é servido ao
usuário.** Mora em `docs/` pelo mesmo motivo de
`proposta-politica-gravacao-de-chamadas.md`: o frontend importa só
`src/content/politica-privacidade.md` e `src/content/termos-de-uso.md`, e
qualquer rebuild publicaria um texto colocado ali. Este arquivo não entra no
bundle.

Preparado em 21/10/2026 para a Fase 3B (branch
`feat/avatar-participantes-chamados`, sem commit). **Nada aqui está aprovado.**
A Política publicada (PGS-TI-031, Revisão 00, vigência 05/10/2026) não foi
alterada.

## O que continua pendente — e não é decisão técnica

1. **Redação final e revisão documental** deste texto, e se ele entra numa
   Revisão 01 da PGS-TI-031.
2. **Novo aceite geral ou não.** A seção 15 diz que inclusão de novo
   destinatário pede novo aceite. A autorização implementada é específica e
   opcional; se isso dispensa o re-aceite da Política inteira é decisão do
   responsável.
3. **Base legal das fotos da equipe** (técnicos e administradores) exibidas a
   clientes. A implementação trata todos os papéis igual — exibição só com a
   autorização individual —, mas a base legal declarada para funcionários
   (consentimento, legítimo interesse ou outra) não foi escolhida.
4. **Prazo de guarda dos registros** de autorização e revogação. A tabela
   `avatar_visibility_events` não tem limpeza automática e nenhum prazo foi
   escolhido.
5. **Texto final da opção no perfil.** O texto em uso é minuta
   (`MINUTA-2026-10-21`, em `backend/app/services/exibicao_da_foto.py`,
   marcada `aprovado=False`). Em produção só um texto marcado como aprovado no
   catálogo autoriza: configurar o nome da minuta em
   `AVATAR_AVISO_EXIBICAO_VERSAO` deixa a opção indisponível. Nenhuma
   autorização de produção pode ser registrada contra a minuta.
6. **A autorização depois da anonimização.** A anonimização não zera a
   escolha nem os eventos (que guardam o IP). Se uma conta anonimizada for
   reativada e enviar foto nova, a escolha antiga volta a valer. Se isso deve
   mudar é decisão de ciclo de vida, fora desta implementação.

## Como a implementação funciona (para a redação refletir o que é verdade)

- **Ninguém aparece para outras pessoas sem autorizar.** Vale para contas
  existentes e novas, de clientes, técnicos e administradores. Ter foto, ter
  aceitado a Política ou enviar uma foto nova não autoriza.
- **Só o titular autoriza ou revoga**, no próprio perfil. Nenhum
  administrador muda a escolha de outra pessoa.
- **Quem vê, com autorização** (dentro de um chamado que a pessoa já pode ver):
  - a foto do **cliente**: a equipe de atendimento, nos chamados que ele abriu
    (bloco "Solicitante") e junto das mensagens que ele envia neles;
  - a foto do **técnico ou administrador**: a equipe, nos chamados; o cliente,
    nos chamados em que ele é o responsável; e, na conversa, a equipe e o
    cliente que abriu o chamado, junto das mensagens que ele envia;
  - **outro cliente nunca** vê a foto de um cliente, com ou sem autorização.
- **A própria pessoa** vê a própria foto sempre (perfil, topo da tela e o
  bloco do próprio chamado), com ou sem autorização. Na conversa, sem
  autorização, a mensagem sai sem foto para todos, ela incluída.
- **Recusar ou não responder** mantém as iniciais. Nada no atendimento muda.
- **Revogar** vale para as telas abertas depois. Não apaga a foto do perfil.
  Revogar exige estar logado, como qualquer opção do perfil: conta desativada
  não entra no sistema.
- **Conta desativada ou anonimizada** não tem a foto exibida a ninguém além
  dela mesma, com ou sem autorização. Isso não é uma revogação: a escolha
  fica guardada, nada é registrado em nome da pessoa, e reativar a conta volta
  a respeitar a escolha que estava gravada.
- **Fotos já enviadas** não foram apagadas e não precisam ser reenviadas.
- **Limites que o texto precisa dizer:** um link já entregue a uma tela aberta
  pode continuar exibindo a foto até expirar, o navegador pode manter a imagem
  em cache, e uma imagem já vista, salva ou capturada por outra pessoa não
  desaparece com a revogação.
- **Registro:** cada autorização e revogação é guardada com data e hora, a
  versão do texto apresentado, a origem ("alteração própria") e o IP. A foto,
  o arquivo e os links não são guardados nesse registro. Excluir a conta
  desvincula o registro da conta, mas data, versão e IP permanecem; anonimizar
  não altera o registro.

## Redação proposta

### Seção 6 — linha "Imagem de perfil"

> | Imagem de perfil | Fotografia de perfil, quando o usuário optar por enviá-la. O envio é facultativo e a ausência da foto não limita o uso da plataforma. A exibição da foto a outros participantes dos atendimentos depende de autorização específica do usuário, concedida e revogada no próprio perfil. | Enviada voluntariamente pelo usuário. |

E uma linha nova:

> | Registro da autorização de exibição da foto | Data e hora de cada autorização e revogação, a versão do texto apresentado e o endereço IP. | Registrado automaticamente quando o usuário altera a escolha no perfil. |

### Seção 8 — substituir a linha da imagem de perfil

> | Identificar visualmente o usuário na plataforma: para o próprio usuário, sempre que houver foto; e, **somente com a sua autorização específica**, para os participantes dos atendimentos — a foto do cliente para a equipe de atendimento, nos chamados que ele abriu; a foto do técnico ou administrador para a equipe e para o cliente dos chamados em que é o responsável ou em que enviou mensagens. A foto de um cliente nunca é exibida a outro cliente. | Imagem de perfil. | Consentimento específico (art. 7º, I), revogável a qualquer tempo no perfil. **[Base legal para fotos de técnicos e administradores: decisão pendente do responsável pela Política.]** |

E uma linha para o registro:

> | Comprovar a autorização e a revogação da exibição da foto. | Registro da autorização de exibição da foto. | Exercício regular de direitos (art. 7º, VI). **[A confirmar pelo responsável.]** |

### Seção 12 — compartilhamento

Não há destinatário EXTERNO novo: a foto não sai da plataforma. Sugere-se uma
frase depois da tabela, para não deixar dúvida:

> A exibição da imagem de perfil a outros usuários da plataforma, nos
> atendimentos de que participam, depende de autorização específica do titular
> e é descrita na seção 8.

### Seção 13 — retenção

Linha da imagem de perfil, mantida, com o acréscimo:

> | Imagem de perfil | Enquanto a conta estiver ativa, ou até que o usuário a remova. A exibição a outras pessoas cessa com a revogação da autorização, sem apagar a imagem. | Consentimento do titular, revogável a qualquer tempo. |

Linha nova:

> | Registro da autorização de exibição da foto | **[Prazo a definir pelo responsável pela Política.]** | Comprovação da escolha do titular. |

### Texto sobre a revogação (seção 8 ou 16)

> O usuário pode revogar a autorização de exibição da foto a qualquer tempo, no
> próprio perfil, sem prejuízo do atendimento. A revogação vale para as telas
> abertas a partir de então. Imagens já exibidas podem permanecer
> temporariamente em telas abertas ou na memória do navegador de quem as
> visualizou, e a Health & Safety não tem como recolher cópias eventualmente
> salvas ou capturadas por terceiros.

### Fotos existentes

> As fotos enviadas antes desta revisão não são exibidas a outras pessoas até
> que o próprio usuário autorize. Elas não foram apagadas e não precisam ser
> enviadas novamente.

## O que NÃO foi feito

- A Política publicada não foi alterada.
- Nenhum aceite, autorização ou registro foi criado para usuários reais.
- Nenhum e-mail de aviso foi enviado; o aviso de lançamento é só dentro da
  plataforma e não bloqueia o uso.
