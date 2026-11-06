# F1-D1 — Exclusão de grupo e de empresa: notas para integração

Notas exclusivas da F1-D1 (Sessão 3), para a Sessão 0 integrar em
`docs/decisoes-e-regras.md` e no `[Não publicado]` do `Changelog.md`. Nenhum
dos dois foi editado nesta entrega, porque outras sessões escrevem neles.

Base: `origin/main` `6e9a55d`. Branch `fix/f1d1-exclusoes-grupos-empresas`.
Sem migration, sem mudança de model.

## O que era

| Rota | Antes |
|---|---|
| `DELETE /groups/{id}` | admin **e técnico**; apagava as empresas e as notas do grupo e de cada empresa (FK `companies.group_id` CASCADE + `delete-orphan` no ORM) e soltava os clientes (`users.company_id` SET NULL). 204, sem contagem, sem auditoria, sem teste |
| `DELETE /groups/{id}/companies/{id}` | admin e técnico; apagava as notas e soltava os clientes, em silêncio. O próprio teste chamava de "o comportamento que ninguém escolheu" |

Reproduzido em PostgreSQL descartável antes da correção
(`test_exclusao_grupos_empresas_postgres.py` contra `6e9a55d`, 21 falhas):

- técnico excluía grupo e empresa (204);
- grupo com empresas, clientes e notas saía inteiro (204);
- **corrida**: empresa ou nota criada (escrita, ainda não comitada) enquanto o
  grupo era excluído era apagada pela cascata logo depois do commit dela — a
  própria criação estourava em `Could not refresh instance` (500) e o dado
  sumia; vínculo de cliente em curso era solto em silêncio (`['ok', 'ok']`);
- duas exclusões simultâneas do mesmo grupo respondiam 204 as duas.

## Regra nova (texto proposto para `decisoes-e-regras.md`)

> **Exclusão de grupo e de empresa.** Só administrador exclui grupo ou empresa;
> técnico recebe 403. Só sai o que está vazio:
>
> - **grupo** com empresa, cliente vinculado a uma empresa dele, nota do grupo
>   ou nota de empresa dele → **409**;
> - **empresa** com cliente vinculado (de qualquer situação, inclusive
>   inativo) ou nota → **409**.
>
> O 409 diz **quantos** de cada coisa bloqueiam, nunca **quem**: nenhum nome
> nem e-mail de cliente no corpo nem no log. Não existe exclusão em cascata
> com confirmação. Para excluir, esvazia-se antes (desvincular clientes, mover
> ou excluir empresas e notas).
>
> A exclusão bem-sucedida grava `audit_logs` (`action=delete`,
> `entity_type=group|company`, `entity_id`, autor em `user_id`, data em
> `created_at`) com o retrato em `old_data`: nome, e — para empresa — CNPJ e
> `group_id`, mais as contagens (todas zero, provando que estava vazia).
> Recusa **não** grava `audit_logs`, só um aviso no log da aplicação com ids e
> contagens (mesma decisão D3 da F1-A).
>
> As FKs continuam CASCADE/SET NULL; a recusa vem antes delas. Trocar o
> `ondelete` é mudança de model, fora da F1-D1.

### Concorrência

A exclusão trava a linha mãe com `FOR UPDATE` antes de contar. Toda escrita
que cria um filho (empresa, nota, vínculo de cliente) passa pela checagem de
FK, que pega `FOR KEY SHARE` na linha mãe — e `FOR UPDATE` é o modo que
conflita com ele (`FOR NO KEY UPDATE` **não** conflita; a mutação que troca
um pelo outro foi morta pelos testes). Com isso:

| Quem escreveu primeiro | Resultado |
|---|---|
| a criação/vínculo (não comitado) | a exclusão espera o commit dele, conta e recusa: **409**; nada se perde |
| a exclusão (grupo/empresa vazio) | a criação/vínculo espera; a exclusão comita; a escrita do filho falha na FK e **não grava nada** |
| duas exclusões do mesmo alvo | uma 204, a outra 404 (relê sob a trava e não acha a linha) |

`IntegrityError` no commit da exclusão vira 409 com rollback inteiro (a
exclusão e a auditoria são uma transação só).

## ⚠️ Ponto de coordenação com a Sessão 4 (não implementado)

Na segunda linha da tabela acima, a **outra** rota — `create_company`,
`create_group_note`, `assign_client`, `create_company_note` — recebe
`IntegrityError` e hoje responde **500**. A integridade está garantida (nada
órfão, nada gravado), mas a resposta HTTP não. Consertar exige mexer nessas
rotas, que são da Sessão 4, então ficou fora da F1-D1.

Proposta para quem for dono delas (duas opções, a primeira é a recomendada):

1. ler a linha mãe com `FOR KEY SHARE` (`with_for_update(read=True,
   key_share=True)`) no `_get_group_or_404`/`_get_company_or_404` dessas rotas:
   a leitura espera a exclusão terminar e, se ela comitou, não acha a linha →
   **404** limpo, antes de qualquer escrita;
2. ou capturar `IntegrityError` no commit delas e responder 404/409.

Os testes `test_exclusao_do_grupo_em_curso_faz_a_criacao_falhar_sem_gravar` e
`test_exclusao_da_empresa_em_curso_faz_o_vinculo_falhar_sem_gravar` já aceitam
`404` além de `IntegrityError`: quando a Sessão 4 aplicar a opção 1, eles
continuam verdes e basta apertar a asserção para só `404`.

### Rotas que ainda podem responder 500 ao concorrer com uma exclusão

Mecanismo comum: a rota lê a linha mãe **sem trava** (`_get_group_or_404` /
`_get_company_or_404`), vê a linha porque a exclusão ainda não comitou, e só
esbarra na FK ao escrever. Não há handler global de `IntegrityError`
(`core/exceptions.py`, `main.py`), então vira 500.

| Rota | Escrita que esbarra | Situação |
|---|---|---|
| `POST /groups/{id}/companies` (`create_company`) | INSERT em `companies` | **Reproduzido** (teste PostgreSQL, ordem "exclusão primeiro": a criação levanta `IntegrityError` e não grava) |
| `POST /groups/{id}/notes` (`create_group_note`) | INSERT em `group_notes` | **Reproduzido** (idem) |
| `POST /groups/{g}/companies/{c}/clients` (`assign_client`) | UPDATE `users.company_id` | **Reproduzido** (idem) |
| `POST /groups/{g}/companies/{c}/notes` (`create_company_note`) | INSERT em `company_notes` | **Reproduzido** (idem) |
| `POST /groups/{id}/companies/from-suggestion` | INSERT em `companies` (flush) e UPDATE `users.company_id` | **Hipótese**, mesmo mecanismo; sem teste |
| `PATCH .../clients/{id}/notes`, `DELETE .../clients/{id}` | não mudam coluna de FK para valor novo | não afetadas (a checagem de FK no UPDATE só roda quando a coluna muda para valor não nulo) |

"Reproduzido" quer dizer: os testes aceitam `IntegrityError` ou 404 e
passaram, e a rota não tem trava que pudesse produzir 404 — então o valor
observado foi `IntegrityError`. O 500 pela API é a consequência dele sem
handler; não foi medido por HTTP.

Nenhuma dessas correções pertence à F1-D1. Distribuição preliminar definida
pela Sessão 0 (04/11/2026), sujeita a refinamento quando as frentes voltarem:

| Rota | Frente |
|---|---|
| `assign_client`, `create_company_from_suggestion` | F2-A1 |
| `create_company` | subentrega futura da F2 |
| `create_group_note`, `create_company_note` | correção complementar futura da F1-D |

### Ordem das travas e a F2-A1

Hoje cada exclusão pega **uma** trava (`FOR UPDATE` no grupo, ou na empresa),
então não há ordem entre travas da F1-D1 que possa formar ciclo. Para a F2-A1
continuar sem deadlock:

- toda rota que travar mais de uma linha deve seguir a hierarquia **grupo →
  empresa → usuário**, em todas as rotas;
- se a F2-A1 fizer `delete_company` travar também o grupo, a trava do grupo
  vem **antes** da empresa (a mesma ordem de `delete_group` com as empresas);
- `FOR KEY SHARE` na leitura da mãe (opção 1) não conflita com outra
  `FOR KEY SHARE` nem com UPDATE de campos comuns (`FOR NO KEY UPDATE`): só
  espera a exclusão. Custo baixo para as rotas de criação;
- a F3 (`equipments.company_id`) precisa entrar na contagem de
  `_dependentes_da_empresa` e do grupo, e a FK nova precisa ser NO ACTION ou
  RESTRICT — com CASCADE ou SET NULL a recusa continua valendo, mas a próxima
  rota que escrever no equipamento repete o mesmo 500.

## Dependências do frontend (fora da reserva da F1-D1)

`frontend/src/pages/groups/GroupsPage.tsx`, na `main` de `6e9a55d`:

- os modais de confirmação dizem que o grupo "será removido com as empresas e
  as notas que carrega" e que a empresa sai "com os clientes vinculados" — o
  texto passa a ser falso;
- `handleDeleteCompany` não tem `catch`: o 409 da empresa não vira toast (o
  de grupo vira, por `toastApiError`);
- os botões de excluir aparecem para técnico, que agora recebe 403.

Sugestão: PR de front pequeno, depois do deploy do backend (o front antigo
continua funcionando com o backend novo — só mostra o texto errado e, na
empresa, nenhum aviso).

### Proposta para esse PR (não implementada)

| Item | Hoje | Proposta |
|---|---|---|
| Texto do modal de grupo | "será removido com as empresas e as notas que carrega" | "Só é possível excluir um grupo sem empresas e sem notas. Esta ação não pode ser desfeita." |
| Texto do modal de empresa | "será removida do grupo com os clientes vinculados" | "Só é possível excluir uma empresa sem clientes vinculados e sem notas. Esta ação não pode ser desfeita." |
| 409 do grupo | `toastApiError` já mostra o `detail` | manter; fechar o modal e manter o grupo na lista |
| 409 da empresa | sem `catch` (rejeição não tratada) | `catch` com `toastApiError(err, "Erro ao excluir empresa.")`, sem tirar a empresa da lista nem decrementar `company_count` |
| 403 | só toast genérico, se houver `catch` | mesmo `toastApiError` (o `detail` do 403 já é texto) |
| Botões "Excluir" para técnico | visíveis | esconder quando o papel não é admin (o backend continua sendo a garantia) |
| Contagem antes de abrir o modal | — | opcional: se `company_count`/`client_count`/`note_count` da tela já forem > 0, desabilitar o botão com dica, evitando a ida ao servidor |

Testes do PR: Vitest de `GroupsPage` cobrindo os dois textos, o 409 de empresa
sem remoção da lista, e a ausência do botão para técnico.

## Testes

- Novo: `backend/tests/test_exclusao_grupos_empresas_postgres.py` (28 casos,
  banco próprio no PostgreSQL): autorização, 409 com contagens e sem dado
  pessoal, nada perdido na recusa, auditoria no sucesso e só nele, corridas
  nos dois sentidos para criar empresa, nota de grupo, vincular cliente e nota
  de empresa, duas exclusões simultâneas, exclusão de empresa × do grupo dela,
  falha de integridade e falha genérica no commit sem exclusão parcial.
- Atualizados em `backend/tests/test_groups.py`: os dois testes que **fixavam**
  o comportamento antigo (204 soltando clientes e apagando notas) passaram a
  afirmar o 409 e a preservação; o da sugestão que reaparece usa agora o
  `DELETE .../clients/{id}` para soltar o cliente, já que excluir a empresa com
  cliente não passa mais.
- Mutação: 19 mutantes em `groups.py`, 19 mortos (trava ausente, `FOR NO KEY
  UPDATE`, papel, cada contagem, `any`→`all`, auditoria e seu retrato, autor,
  CNPJ, rede de `IntegrityError`, `delete` fora da rede).

## Texto proposto para o `[Não publicado]` do `Changelog.md`

> - Excluir grupo ou empresa agora é só para administrador, e só quando
>   estiver vazio. Grupo com empresas, clientes ou notas, e empresa com
>   clientes vinculados ou notas, não são mais apagados junto: a exclusão é
>   recusada e diz quantos itens precisam sair antes. Cada exclusão fica
>   registrada na auditoria.

(Exige texto de tela alinhado — ver "Dependências do frontend".)

## Decisão a confirmar

- **CNPJ na auditoria.** Entrou em `old_data` da empresa por ser dado da
  empresa e o que identifica qual saiu. Se a Sessão 0 entender que CNPJ de MEI
  é dado pessoal a evitar, sai uma linha (e a asserção correspondente).
