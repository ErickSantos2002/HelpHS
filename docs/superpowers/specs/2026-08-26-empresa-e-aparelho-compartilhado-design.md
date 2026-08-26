# Empresa e aparelho compartilhado — desenho

**Data:** 26/08/2026
**Status:** decisões do cliente colhidas; aguarda o diagnóstico em produção
**Antecede:** Helô Fase 1 (o "desligar por CNPJ" depende da empresa existir de verdade)
**Continua:** [duas fontes de verdade de empresa](2026-08-24-duas-fontes-de-verdade-empresa.md)

---

## O problema, em duas metades que parecem uma

O relato foi um só — "não quero duplicar CNPJ nem número de série" — mas são
dois defeitos diferentes, e tratá-los como o mesmo levaria a corrigir o lado
errado.

**CNPJ repetido entre clientes não é defeito.** Dois funcionários da mesma
empresa vão digitar o mesmo CNPJ, e devem mesmo. O que falta é o sistema saber
que são a mesma empresa: cada um fica com um `users.cnpj` solto e nada os liga.
Quem não pode duplicar é a `Company` — e `companies.cnpj` não tem `UNIQUE`
nenhum hoje (`models.py:162`).

**Série repetida duplica de verdade.** A unicidade é por dono
(`uq_equipments_owner_serial`), então duas pessoas cadastrando o mesmo aparelho
criam **duas linhas**, cada uma se achando dona. Não existe "o aparelho" no
banco; existem cópias que não se conhecem.

E há um motivo delicado por trás do escopo atual, que precisa sobreviver a
qualquer mudança: a unicidade global de série foi **removida** porque o
`409 "número de série já cadastrado"` era um oráculo — contava ao cliente que
outra empresa tinha aquele aparelho, e qualquer cliente podia varrer seriais
para mapear o parque alheio.

---

## Decisões do cliente — 26/08/2026

| # | Pergunta | Decisão |
|---|---|---|
| 1 | A série é única no mundo ou pode repetir? | Chave **`(produto, série)`** — repetir entre produtos diferentes é aceitável |
| 2 | Quem é o dono quando dois cadastram o mesmo aparelho? | **Os dois são usuários** do aparelho; a tela mostra quem cadastrou |
| 3 | Colegas do mesmo CNPJ veem os chamados uns dos outros? | **Veem na listagem, não abrem** — o detalhe continua sendo só do autor |

A decisão 1 é melhor do que parece: ela dissolve a objeção que travava o
assunto. O código afirma que "fabricantes repetem séries entre lotes e linhas";
com a chave composta, isso deixa de ser conflito — dois produtos podem repetir o
número à vontade, e dois aparelhos do mesmo produto nunca colidem.

### O ajuste na decisão 2

O cliente cadastra aparelho sozinho (`POST /equipment/my`). Se anexar-se a um
aparelho já existente desse direito de editar, quem souber ou acertar um serial
poderia renomear, mudar a localização ou desativar o registro de um aparelho
**de outra empresa** — adulteração de dado alheio, não vazamento de leitura.

Regra adotada, mais estreita que a resposta literal: **todos veem, todos usam o
aparelho para abrir chamado, a tela mostra quem cadastrou — mas editar fica com
quem cadastrou e com o staff.** Afrouxar depois é fácil; apertar depois de ter
soltado é conversa desagradável com quem já se acostumou.

### O que a decisão 3 realmente protege

Se a linha da listagem mostra título e status, bloquear o clique não esconde
quase nada — esconde a descrição, os anexos e a conversa. Está registrado aqui
para não virar surpresa: a listagem **é** a divulgação; o bloqueio do detalhe é
o que sobra dela.

---

## O desenho

### A. A empresa vira o ponto de encontro

- `companies.cnpj` ganha `UNIQUE` sobre o valor normalizado (14 dígitos crus).
- O cadastro procura antes de criar: achou o CNPJ, vincula à empresa existente;
  não achou, cria. Dois clientes com o mesmo CNPJ caem na mesma `Company`.

**O vínculo automático não concede escopo por si.** O CNPJ é autodeclarado e o
servidor só confere que soma 14 dígitos — quem valida dígito verificador é o
front, que é o cliente. Eleger esse campo como autoridade de acesso é deixar o
cliente escolher em que empresa entra. Como a decisão 3 liga visibilidade à
empresa, o vínculo criado por CNPJ nasce **pendente** e vale para relatório;
quem o confirma para efeito de visibilidade é um admin. É a mesma conclusão do
levantamento de 24/08, agora com consequência prática.

### B. O aparelho vira entidade única

- Índice `UNIQUE (product_id, serial_number)` no lugar de
  `(owner_id, serial_number)`.
- Tabela de associação `equipment_users` — `owner_id` sozinho é um campo só e
  não comporta várias pessoas. Guarda quem se anexou, quando, e quem foi o
  primeiro (o "cadastrante").
- `POST /equipment/my` com série já existente **não recusa e não avisa**:
  anexa a pessoa ao aparelho existente e responde `201`, igual ao primeiro
  cadastro. O oráculo morre porque as duas respostas são indistinguíveis — mesmo
  raciocínio do `404` de chamado alheio (`ensure_ticket_visible`).
- Editar o equipamento: cadastrante + staff. Ver e usar: todos os anexados.

### C. Duas recusas para duas relações

O detalhe do chamado passa a distinguir de quem é o chamado:

| Relação | Resposta | Por quê |
|---|---|---|
| Colega da mesma empresa | `403` "chamado de outro usuário da sua empresa" | A listagem já contou que existe; `404` seria mentira sobre algo visível na tela |
| Fora da empresa | `404` | Mantém intacta a correção de enumeração de `7371bc7` |

A listagem do cliente passa a trazer os chamados da empresa com campos
reduzidos — protocolo, título, status, autor e data. Sem descrição, sem anexos,
sem chat.

### D. As duas telas de staff

Saem quase de graça depois de A e B, e **só para admin e técnico**:

- **Da empresa** → as pessoas (`users.company_id`) e os aparelhos (associação).
- **Do aparelho** → quem já abriu chamado com ele e sob qual CNPJ
  (`ticket_equipments` + autor).

---

## O risco que dita a ordem

Índice único **falha na criação** se o banco já tiver duplicata — e migration
que falha, aqui, é API que não sobe: o `start.sh` roda `alembic upgrade head` a
cada boot do container. Os dois índices deste desenho são exatamente do tipo que
pode falhar, e o caso que os faz falhar é o que motivou a rodada: gente com o
mesmo CNPJ, aparelho cadastrado duas vezes.

Por isso existe `backend/scripts/diagnostico_empresa_aparelho.py` — somente
leitura, sem `--aplicar`. Ele responde, contra o banco real, quantas duplicatas
existem em cada frente. Com o número na mão, cada migration ou nasce trivial ou
nasce com a fusão embutida, e não descobre isso derrubando a produção.

O `normaliza_cnpj.py`, escrito em 24/08, **ainda não foi rodado em produção**.
Ele é pré-requisito de A: sem os dígitos normalizados dos dois lados, o `UNIQUE`
pega `11.222.333/0001-81` e `11222333000181` como valores diferentes.

---

## Ordem

1. `diagnostico_empresa_aparelho.py` em produção — dry-run por natureza.
2. `normaliza_cnpj.py --aplicar`, se o diagnóstico mostrar pontuação pendente.
3. Fusão das duplicatas que o diagnóstico apontar (à mão, com decisão humana:
   fundir aparelho de dois donos é o caso legítimo; duas linhas do mesmo dono é
   cadastro repetido).
4. Migrations: `UNIQUE(cnpj)`, `UNIQUE(product_id, serial_number)`,
   `equipment_users`.
5. Vínculo por CNPJ no cadastro; anexação silenciosa no `/equipment/my`.
6. Visibilidade entre colegas — as duas recusas e a listagem reduzida.
7. Telas de staff.

Depois disso, a Helô Fase 1 nasce já com o "desligar por CNPJ" completo, em vez
de ganhar um remendo sobre um campo em que ninguém confia.
