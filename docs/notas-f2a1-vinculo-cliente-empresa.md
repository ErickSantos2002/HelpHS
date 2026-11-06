# F2-A1 — Vínculo de cliente a empresa: notas para integração

Notas exclusivas da F2-A1 (Sessão 4), para a Sessão 0 integrar em
`docs/decisoes-e-regras.md` e no `[Não publicado]` do `Changelog.md`. Nenhum
dos dois foi editado nesta entrega, porque outras sessões escrevem neles.

Base: `origin/main` `2201dcf` (F1-D1 já integrada). Branch
`fix/f2a1-vinculo-cliente-empresa`. Sem migration, sem mudança de model, de
schema nem de frontend.

## O que era

| Rota | Antes |
|---|---|
| `POST /groups/{g}/companies/{c}/clients` | sobrescrevia `users.company_id`: cliente de outra empresa era **transferido em silêncio** (201), sem 409 e sem rastro; aceitava cliente inativo ou anonimizado; nenhuma auditoria |
| `DELETE /groups/{g}/companies/{c}/clients/{id}` | desvinculava sem auditoria |
| `POST /groups/{g}/companies/from-suggestion` | conferia "cliente ativo e sem empresa" **sem trava**: duas confirmações simultâneas com o mesmo cliente passavam as duas e a segunda o transferia; sem auditoria da empresa criada nem dos vínculos |

`users.company_id` é a única autoridade sobre a empresa do cliente e já decide
escopo (a Helô recorta o histórico de chamados por ele) — por isso a
transferência silenciosa era o risco principal.

## Regra nova (texto proposto para `decisoes-e-regras.md`)

> **Vínculo de cliente a empresa.** Só administrador vincula ou desvincula.
>
> | Situação do cliente | Resposta |
> |---|---|
> | ativo, sem empresa | **201**, vincula e audita |
> | ativo, já na **mesma** empresa | **200**, nada muda, sem auditoria |
> | em **outra** empresa | **409** com o nome da empresa atual; não move |
> | inativo ou anonimizado | **409** — conferido **antes** da idempotência: conta parada não recebe nem a confirmação do vínculo que já existe |
> | inexistente ou não é cliente | **404** |
>
> Transferência entre empresas não existe como efeito colateral: corrige-se
> desvinculando e vinculando, duas ações auditadas. Se um dia houver
> transferência, é operação própria.
>
> Desvincular não filtra papel nem situação (é o único jeito de limpar a
> empresa de quem deixou de ser cliente ou foi desativado).
>
> A confirmação de sugestão (`from-suggestion`) recusa tudo (409) se algum
> cliente não estiver ativo e sem empresa — nada é gravado.
>
> **Auditoria**, na mesma transação da mudança: `action=assign`,
> `entity_type=user`, `entity_id` = cliente, autor em `user_id`,
> `old_data`/`new_data` = `{"company_id", "group_id"}` (ou
> `{"company_id": null}`). A empresa criada pela sugestão grava também
> `action=create`, `entity_type=company`, com nome, CNPJ e `group_id`; empresa
> reaproveitada não. Recusa **não** grava `audit_logs`, só aviso no log da
> aplicação (decisão D3 da F1-A). Operação idempotente (200) não audita.

O 409 é texto simples em `detail`, como na F1-D1 — o `toastApiError` do front
já o exibe; o front não precisou mudar.

## Concorrência

Ordem das travas, a mesma nas três rotas:

1. **ator** — `FOR KEY SHARE`;
2. **grupo ou empresa** — `FOR KEY SHARE` (na sugestão: grupo, depois a
   empresa reaproveitada pelo CNPJ, se houver);
3. **clientes** — `FOR UPDATE`, `ORDER BY id`, com `populate_existing`.

### Deadlock identificado e mitigação

O `INSERT` em `audit_logs` confere a FK `user_id` e, para isso, pega
`FOR KEY SHARE` na linha do **ator**. As alterações de conta da F1-A
(`_trava_para_alterar_conta`) travam **todos os admins** com `FOR UPDATE` e só
depois o alvo. Com a auditoria por último, o arranjo era:

- vínculo: segura o cliente (`FOR UPDATE`) → no INSERT da auditoria, espera o
  ator;
- alteração de conta do mesmo cliente: segura os admins (inclusive o ator) →
  espera o cliente.

Medido em PostgreSQL com SQL puro antes da escrita: `DeadlockDetectedError`.
Travando o ator **antes** do cliente, quem chega depois espera sem segurar nada
que a outra precise — as duas comitam. O teste
`test_alteracao_de_conta_com_os_admins_travados_nao_trava_em_circulo` cobre as
três rotas, e a mutação que tira a trava do ator em cada uma é derrubada.

### Resultado das corridas (PostgreSQL real)

| Corrida | Resultado |
|---|---|
| dois vínculos do mesmo cliente a empresas diferentes | um 201, o outro 409 |
| dois vínculos à mesma empresa | os dois ok (o segundo é o idempotente), **uma** auditoria |
| duas sugestões cruzadas (`[um, dois]` × `[dois, um]`) | uma ok, a outra 409, sem deadlock |
| vínculo × sugestão, nas duas ordens | um vence, o outro 409 |
| exclusão de empresa em curso × vínculo | vínculo **404** (era o 500 da FK, ponto de coordenação deixado pela F1-D1) |
| vínculo em curso × exclusão de empresa | exclusão 409 |
| exclusão de empresa com cliente × desvínculo | exclusão 409, desvínculo ok |
| exclusão de grupo em curso × sugestão | sugestão 404 |
| sugestão em curso × exclusão de grupo | exclusão 409 |
| exclusão da empresa reaproveitável em curso × sugestão | sugestão cria empresa nova, nada órfão |
| desativação ou anonimização em curso × vínculo | vínculo 409 |
| vínculo em curso × desativação | as duas ok (vínculo de quem era ativo naquele instante) |
| desativação em curso × sugestão | sugestão 409 |

A ordem das travas é conferida também nas instruções SQL que chegam ao banco
(`test_travas_saem_na_ordem_ator_grupo_ou_empresa_clientes`): o harness de
corrida não consegue intercalar duas aquisições dentro da mesma rota, e a
mutação "clientes travados um a um fora de ordem" só morreu com essa leitura.

Cliente não muda o próprio vínculo pelo `PATCH /users/me` (`company_id` no
corpo é ignorado, sem auditoria) — coberto com o cliente sem empresa e com
empresa.

## Testes

- `tests/test_groups.py` (SQLite): o antigo
  `test_vincular_move_de_uma_empresa_para_outra_sem_reclamar` virou
  `test_vincular_cliente_de_outra_empresa_recusa_sem_mover`; entraram os casos
  de 200, 409 por situação, auditoria do vínculo, do desvínculo e da
  sugestão. `audit_logs` entrou nas tabelas criadas, com `JSONB` compilado
  como `JSON` **só no dialeto SQLite** (`@compiles` no módulo).
- `tests/test_vinculo_cliente_empresa_postgres.py` (novo, 23 testes):
  corridas da tabela acima, deadlock nas três rotas, ordem das travas,
  `PATCH /users/me`.
- `tests/test_exclusao_grupos_empresas_postgres.py` (arquivo da F1-D1): **uma**
  asserção mudou. Em `test_vinculo_ou_nota_em_curso_impede_a_exclusao_da_empresa`,
  o caso `vincula_cliente` esperava `audit_logs == []`; agora espera
  exatamente `[(assign, "user")]` — a auditoria do vínculo que venceu. A
  igualdade estrita continua provando que a exclusão recusada **não** auditou;
  o caso da nota segue com `== []`.
- Mutação: 17 de 17 derrubadas (travas, ordem, idempotência, situação,
  transferência, auditoria das três rotas, filtros de 404).

## Fora do escopo (registrado, não implementado)

- **DAT-06 — CNPJ duplicado, medido:** duas confirmações de sugestão
  simultâneas com o **mesmo CNPJ** e clientes diferentes respondem ok as duas
  e criam **duas empresas**. Nada trava "o CNPJ" e `companies.cnpj` não é
  único. É decisão de integridade de empresa (nota no docstring da rota).
- `create_company` e as rotas de nota ainda respondem 500 na corrida com a
  exclusão da F1-D1 (frentes complementares).
- Anonimização mantém `company_id`.
- `scripts/funde_empresas_duplicadas.py` move clientes sem trava e sem
  auditoria.
- A Helô recorta o histórico pelo `company_id` **atual** do criador: a F2-A1
  não amplia o recorte (não há mais transferência silenciosa), mas um vínculo
  errado ainda amplia.
- Modal de vínculo: recarregar a lista ao receber 409 (melhoria opcional).
- F2-A2, F2-B, F2-C, F3.
