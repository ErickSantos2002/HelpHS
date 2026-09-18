# Justificativa de SLA violado na tela de chamado

Data: 11/09/2026. Autor: Rickelme David.

## O problema, medido

O backend exige `sla_breach_justification` para resolver chamado fora do
prazo (`105878d`, PR #4): `POST /tickets/{id}/resolve` e `PATCH
/tickets/{id}/status` para `resolved` devolvem **422** sem ela. O commit dizia
"só backend, o modal do front vem depois", e o front nunca ganhou o campo.

Em 11/09 isso está em produção: o banco está no head `c9x0y1z2a3b4`, a API
responde 401 em `/api/v1/library`, e o front no ar (10/09 15:04) não tem o
campo em nenhum dos 65 arquivos do bundle. Quem tenta concluir um chamado
vencido vê um toast de 4 s com o nome técnico do campo, o modal fica aberto
sem ter onde escrever, e cada tentativa devolve o mesmo 422.

## A decisão: pedir o motivo quando o servidor tem certeza

1. **Marca de violação ligada** (`sla_response_breach` ou
   `sla_resolve_breach`): o campo "Motivo do atraso" aparece de saída e é
   obrigatório. O servidor sempre respeita a marca ligada
   (`violacao_ao_resolver`, `backend/app/utils/sla.py`).
2. **Marca desligada**: o front envia sem justificativa. Se voltar o 422 da
   justificativa, o campo aparece no próprio modal, com um aviso dizendo qual
   prazo passou, o foco vai para ele, e o toast não é mostrado. A segunda
   tentativa leva o texto.

Vale para os dois caminhos que resolvem: o modal "Concluir ticket" e o modal
"Alterar status" quando o novo status é Resolvido.

## Alternativas recusadas

| Alternativa | Por que não |
|---|---|
| Prever a violação pela data no front | O front não recebe `sla_total_paused_ms`, então o cálculo dele acha vencido o que o servidor não acha. O relatório de SLA violado filtra pela **presença** da justificativa (`routers/dashboard.py`): um falso positivo põe no relatório um chamado que não violou nada |
| Campo sempre visível, opcional | Mesmo defeito: justificativa escrita sem violação é gravada e entra no relatório |
| Backend expor o veredito na resposta do chamado | É o conserto mais exato, mas exige deploy do back para tirar do ar um defeito que é só de tela. Fica registrado como melhoria; o 422 continua sendo a rede, porque o prazo pode vencer com o modal aberto |

## Detalhes que ficam decididos

- **Texto.** Rótulo "Motivo do atraso *", limite de 2000 caracteres (o do
  backend) com `maxLength`, dica "Fica registrada no histórico do chamado.
  Escreva como se o cliente fosse ler. Até 2.000 caracteres." A API do
  histórico devolve a justificativa ao cliente dono do chamado, mesmo sem a
  tela dele mostrar. A dica não promete o relatório de SLA violado, porque
  nenhuma tela o mostra (ver "Fora deste trabalho").
- **Aviso.** "Este chamado passou do prazo (o de resolução), e o motivo do
  atraso é obrigatório." O prazo sai do próprio 422 ou das marcas. Pelas
  marcas a lista pode ser **parcial** — elas só se recalculam em escrita, e o
  backend pode cobrar um prazo a mais —, mas o que ela diz é verdade.
- **Acessibilidade.** O aviso entra no `aria-describedby` do campo, somado à
  dica. No caminho do 422 o foco vai direto para o campo, e região viva
  inserida já preenchida não tem anúncio garantido. O `Alert` só é região viva
  quando o aviso chega (422, ou Resolvido escolhido no Alterar status); aberto
  já com ele, é conteúdo (emenda E12).
- **Nada sobra de um pedido para o outro.** O Cancelar limpa o motivo e o
  veredito do 422, como já faziam o X, o Esc e o fundo. Trocar de chamado na
  mesma tela (a rota não tem `key`) zera os dois. E só vai no corpo a
  justificativa que está exigida na tela.
- **Fechar trava com a resposta a caminho.** O X, o Esc e o fundo não fecham
  enquanto a requisição corre, e o destino do Alterar status fica travado:
  sem isso, um 422 que chegasse com o modal fechado sumiria sem toast e sem
  campo.
- **Comentário do Alterar status.** Com o campo de justificativa à vista, o
  placeholder do comentário deixa de dizer "motivo": dois campos de motivo
  lado a lado induziam a escrever a justificativa no lugar errado, e o
  comentário o cliente vê no histórico dele.
- **Reconhecer o 422.** Status 422 com `detail` em texto contendo
  `sla_breach_justification`. O 422 de validação (texto acima do limite) vem
  em lista, não é pedido de justificativa e segue para o toast. Um teste do
  front lê `backend/app/routers/tickets.py` e reprova se a recusa deixar de ser
  422, de citar o campo ou de dizer qual prazo passou; outro confere o limite
  contra `schemas/ticket.py`.
- **Payload.** A justificativa só vai no corpo quando existe e está exigida;
  sem ela, o corpo fica idêntico ao de hoje.
- **Histórico.** A entrada `sla_breach_justification` passa a ter nome legível
  e a mostrar o texto, com quebra de palavra longa. Antes aparecia o nome cru
  do campo e o texto sumia.

## Riscos que ficam, registrados

- **Marca velha na tela depois de reabertura em outra sessão.** A reabertura
  zera `sla_resolve_breach` e não avisa pelo WebSocket; a tela só troca o
  status. Se o técnico conclui nessa aba sem recarregar, o campo é pedido e o
  backend grava o texto sem haver violação. Consertar é recarregar o chamado
  ao receber `status_update`.
- **A guarda "só envia o que está exigido na tela" não tem mutante que a
  mate sozinha.** Ela é a terceira camada: com o Cancelar limpando, o reset
  por chamado e a trava no fechamento, não sobra caminho em que ela seja a
  única a agir. Fica como rede para um caminho novo que deixe estado sujo.

## Fora deste trabalho

- A tela de relatórios não mostra `sla_justifications`, que o backend já manda.
- O export CSV é um `<a href download>` sem token, e o endpoint exige Bearer:
  pela leitura do código, responde 401. Não medido.
- O front não oferece `awaiting_client` ↔ `awaiting_technical`, que o backend
  permite.

## Testes

Primeiro vermelhos, depois o código, e cada guarda validada por mutação.

- **Lib:** reconhecimento do 422 e das marcas, e a frase do aviso.
- **Contrato:** lendo `tickets.py` (status, campo e prazos da recusa) e
  `schemas/ticket.py` (o limite).
- **Service:** o corpo com e sem justificativa, nos dois endpoints.
- **Os dois modais:** marca ligada; 422 revelando o campo, com foco e
  descrição acessível; erro de outro tipo seguindo no toast; texto que não
  vai de carona para outro status; Cancelar descartando o motivo; troca de
  chamado zerando o campo; fechar travado com a resposta a caminho.
- **Histórico:** a entrada com nome legível e o texto.
