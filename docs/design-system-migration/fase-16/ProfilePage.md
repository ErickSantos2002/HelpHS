# §29 — `pages/profile/ProfilePage.tsx`

A pior tela do sistema na catraca de contraste: **8 linhas da varredura** em dois
pares diferentes, e mais **5 ocorrências** da chave das cores cheias. Sem
gráfico nenhum — o problema aqui não era cor de série, era o degrau de ação e o
formulário.

809 linhas antes, 875 depois. O arquivo cresceu porque o que saiu era denso e o
porquê ficou escrito.

---

## O que a tela tinha

| o que | quantos |
|---|---:|
| classes da paleta crua (todas `slate-*` e `green-*`) | **74** |
| par `bg-primary` + `text-white` (3,83:1) | **3** lugares |
| par `bg-danger` + `text-white` (3,76:1) | **1** lugar |
| cor cheia semântica como cor de TEXTO | **5** (`text-info`, `text-danger` ×3, `hover:text-danger`) |
| `<svg>` solto | **3** |
| hexadecimal cravado | **0** |
| mapas locais indexados pela mesma chave | **2** (`ROLE_LABEL` + `ROLE_BADGE`) |
| constante de classe de campo (`INPUT_CLS`) | **1**, usada em **14** campos |
| `<label>` sem `htmlFor` | **10** |
| campo que só se entendia pelo `placeholder` | **2** (senha do desligamento do MFA, código do autenticador) |
| casca de cartão desenhada à mão | **2** receitas (`SectionCard` e o cartão de identidade) |

Os dois defeitos que nenhuma ferramenta desta migração acha, e que estavam aqui:

**Os dez `<label>` não tinham `htmlFor`.** Visualmente o rótulo ficava logo
acima do campo; para um leitor de tela **não existia relação nenhuma** entre os
dois. A pessoa ouvia "campo de edição, em branco" dez vezes seguidas e tinha de
adivinhar qual era qual pela ordem. Não é cor, não é contraste, e a varredura
passaria batido.

**Dois campos diziam o que eram só pelo `placeholder`** — o texto que some
exatamente quando a pessoa começa a digitar, e que nunca chega a quem não vê a
tela. É o item fixo do `CHECKLIST-29.md`.

---

## O que passou a usar

| módulo / primitivo | onde | quantos |
|---|---|---:|
| `Input` | os 14 campos, em 12 chamadas | 12 |
| `Button` | os pares Cancelar/Salvar e as ações do segundo fator | 7 |
| `Alert` | erro de formulário (4), erro de foto, aviso de cadastro incompleto, confirmação da troca de senha | 7 |
| `Card` | o cartão de identidade e a casca do `SectionCard` | 2 |
| `Badge` | o selo do papel | 1 |
| `Icon` (E21) | `camera` e `lock` | 2 |

### Os três `<svg>`, e como cada um casou

Os três eram `viewBox="0 0 24 24"` com `fill="none"` e `stroke="currentColor"` —
mesma família do `Icon`, conferido **antes** de trocar. E os três casaram
**pelo traçado, caractere a caractere**:

| desenho | virou | observação |
|---|---|---|
| cadeado da seção Segurança | `lock` | `w-4.5` = `size={18}` |
| máquina fotográfica do avatar | `camera` | traçado múltiplo, entrou no pacote pela **E21**; `w-3.5` = `size={14}` |
| "certo" da confirmação de senha | `check` | **não virou `Icon`**: o `Alert` de sucesso já desenha esse mesmo traçado, então o ícone sumiu junto com o parágrafo verde |

Nenhum ícone novo foi preciso.

### O degrau de ação, que é o motivo da tela estar na catraca

Os quatro botões cheios (`Ativar`, `Confirmar`, `Salvar`, `Desativar`)
escreviam `bg-primary text-white` e `bg-danger text-white`. São **3,83:1** e
**3,76:1**, e nos dois temas — o degrau 500 é absoluto e não inverte. O
`Button` resolve pelos pares que a E2 criou: `--action` com `--text-on-primary`
(branco no claro, navy no escuro) e `--action-danger` com `--text-on-danger`.

### As cinco cores cheias como texto

| onde | era | virou |
|---|---|---|
| selo do papel `technician` | `bg-info/10 text-info` | `Badge variant="info"` — tinta e par da tinta |
| `ErrorMsg` (4 usos) | `text-danger bg-danger/10` | `Alert variant="danger"` |
| erro do envio de foto | `text-danger bg-danger/10` | `Alert variant="danger"` |
| "Desativar" do segundo fator | `text-danger hover:text-danger/80` | `text-on-tint-danger hover:bg-tint-danger` |

### Os dois pontos coloridos

O ponto do segundo fator ativo e o ponto do estado da conta eram `bg-green-500`
e `bg-slate-400`. Passaram a `bg-fill-success` e `bg-borda-control`, que é a
mesma receita do selo do `ProductsPage`: a **E19** mediu `--color-success-500`
em **2,54:1** como preenchimento no tema claro, abaixo do piso de 3:1 da WCAG
1.4.11, e `--border-control` é o único neutro que inverte por tema.

**Nenhum dos dois informa sozinho** — o texto ao lado ("Ativa.", "Ativo") é
quem carrega o estado, e há caso de teste que morre se ele sair.

### O retrato

`bg-primary/15` com `text-primary` por cima é exatamente o par que a emenda
**E8** mediu em **2,77:1**: o degrau de marca como cor de TEXTO sobre a própria
tinta. Virou `bg-tint-primary` + `text-on-tint-primary` — a tinta pelo token, e
**sem** modificador de opacidade, porque ela já carrega 15% (regra (a) do D8-a).

---

## O que resta à mão — a contagem

**Contar, não julgar**: um número maior que zero significa que alguém tem de
olhar, não que há trabalho pendente.

| o que | quantos | observação |
|---|---:|---|
| `<svg>` solto | **0** | a única ocorrência de `<svg` no arquivo é texto de comentário |
| classe de paleta crua | **0** | as 5 ocorrências restantes são texto de comentário, documentando o que saiu |
| `text-white` | **0** | a ocorrência restante é comentário |
| hexadecimal em código | **0** | não havia |
| cor cheia semântica como texto | **0** | era 5 |
| linhas da varredura de contraste | **0** | eram 8 |
| `theme` lido em JavaScript | **0** | não havia |
| mapas locais | **1** | `PAPEL` — ver abaixo |
| controles à mão | **3** | ver abaixo |

**O mapa que ficou.** `PAPEL` funde as duas tabelas antigas numa entrada só, e
o que ele guarda agora é rótulo e **variante de `Badge`**, não classe. Ele
continua local porque `lib/` está fora do escopo desta tela — e ele é fonte
única **faltando**, não fonte única a inventar aqui. Relatado.

**Os três controles à mão:**

1. **`SectionAction`** (4 usos: dois "Editar", "Alterar senha", "Desativar") —
   é ação de texto na mesma linha do título da seção. O `Button` traz borda,
   altura e preenchimento de botão, e usá-lo mudaria a altura do cabeçalho de
   quatro cartões — leiaute, não sistema de design. O que a migração trocou foi
   a cor: `text-primary` é o degrau de MARCA e dá **3,66:1** sobre `--bg-base`;
   `--text-link` existe para isto e dá 5,05:1 no claro e 6,47:1 no escuro;
2. **o botão "Alterar foto"** — 28px redondo sobre a borda do retrato, com o
   `Icon` dentro. Não há primitivo para isso;
3. **o `<input type="file">` escondido** — o `FileUpload` é zona de arrastar e
   soltar para vários arquivos, e aqui é um seletor de **uma** imagem disparado
   por um botão. Ver "o que NÃO foi feito".

---

## O que NÃO foi feito, e por quê

- **O primitivo `Avatar` no retrato.** Ele para em **48px** (`lg`) e a tela usa
  **80px**. O `cn()` deste projeto é concatenação simples, não `tailwind-merge`:
  mandar `w-20` por `className` deixaria `w-12 w-20` na mesma classe e quem
  vencesse sairia da ordem do CSS gerado, não do código. Além do tamanho, o
  `Avatar` não tem anel, véu de carregando nem o botão de trocar a foto. Fica
  desenhado aqui, com a cor corrigida. Relatado como falta do primitivo.
- **O `FileUpload` no seletor de foto.** Ele resolve outro problema — vários
  arquivos, arrastar e soltar, validação de extensão e tamanho. Trocar mudaria
  a interface inteira do bloco. Relatado.
- **`--overlay` no véu de carregando do retrato.** O token existe no
  `colors.css` (`rgb(0 0 0 / 0.6)`) e **não está mapeado no
  `tailwind.config.js`**, que está fora do escopo desta tela. Ficou
  `bg-black/40`, que é o que o `ui/Modal.tsx` também faz (`bg-black/60`) pelo
  mesmo motivo. É acréscimo de uma linha no config, para quem for consolidar.
- **`lib/papel.ts`.** As mesmas três linhas de rótulo de papel existem em
  `ProfilePage`, `Topbar` e `UsersPage` — e dentro do `UsersPage` mais duas
  vezes, em `ROLE_OPTIONS` e `FILTER_ROLE_OPTIONS`. São **cinco cópias**. Criar
  o módulo é escrever em `lib/`, que o contrato proíbe. Relatado.
- **Traduzir o estado da conta.** Quando `profile.status` não é `"active"`, a
  tela mostra o valor cru do backend — a pessoa lê "inactive" ou "anonymized".
  O `UsersPage` tem um `STATUS_LABEL` com os três; módulo não existe. Consertar
  muda o que o usuário lê, e isso é decisão do operador. Relatado.
- **O desvio F1 (foco em `ring` e não em `outline`).** Os 14 campos passaram a
  herdar o foco do primitivo `Input`; alinhar ao `outline` do pacote é mudança
  em `components/ui/`, fora do escopo.

---

## Testes

`src/test/pages/ProfilePage.test.tsx`, **11 casos**, todos validados por
mutação. Nenhum caso olha classe: o happy-dom não aplica CSS, e um mutante de
classe sobrevive por um motivo que não tem nada a ver com o que o caso mede.

**Doze mutações, todas no ELEMENTO**, e o que cada uma matou:

| mutação | caso que morreu |
|---|---|
| tira o `label` dos três campos do perfil | cada campo é alcançável pelo próprio rótulo |
| `"Administrador"` vira `"Admin"` no `PAPEL` | o selo do papel diz o cargo por extenso |
| apaga o `aria-label="Alterar foto"` | o botão de foto tem nome, e não só um desenho |
| apaga o `<p>` do estado da conta | o estado é dito em texto, não só na cor do ponto |
| a seção Empresa deixa de ser condicional | a seção Empresa é só de cliente |
| o aviso de cadastro incompleto volta a ser região viva | o aviso não interrompe a leitura |
| o segundo fator deixa de ser condicional | o segundo fator só existe para o staff |
| `iniciar` já chama `activateMfaApi` | mostra a chave e NÃO liga nada antes do código |
| o `label` do código vira `placeholder` | mostra a chave e NÃO liga nada antes do código |
| o `label` da senha do desligamento vira `placeholder` | desligar pede a senha por um campo com rótulo |
| some a regra de tamanho mínimo da senha | senha curta é recusada, e não vai para a rede |
| a confirmação volta a ser `<p>` verde | a troca bem-sucedida é ANUNCIADA |

A mutação achou **um ponto cego real**, e nele o defeito era do teste, não da
tela: três casos do segundo fator usavam `getByRole`, e o status do MFA chega
**depois** do perfil — a seção aparece num segundo quadro. Passavam por sorte de
temporização e falhavam sob mutação por um motivo alheio ao que mediam.
Viraram `findByRole`. E o caso do cliente, que afirma uma **ausência**, deixou
de confiar num `queryBy` (que não distingue "não existe" de "ainda não chegou")
e passou a medir o que a tela não pergunta ao servidor:
`getMfaStatusApi` não é chamado.

---

## Verificação

| conferência | resultado |
|---|---|
| `npx vitest run src/test/pages/ProfilePage.test.tsx` | 11 passaram (3 execuções seguidas, estável) |
| `npx tsc --noEmit -p tsconfig.app.json` | sem erro |
| `npx eslint` nos dois arquivos | limpo |
| `varredura-contraste.mjs` \| `grep ProfilePage` | **nenhuma linha** (eram 8) |
| cores cheias semânticas como texto | **0** (eram 5) |
| classes de paleta crua em código | **0** (eram 74) |
| `<svg>` solto | **0** (eram 3) |
