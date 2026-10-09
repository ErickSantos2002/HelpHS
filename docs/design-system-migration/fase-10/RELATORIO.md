# Fase 10 — Feedback e navegação — HelpHS

Relatório no formato da seção 32. **Fase fechada.**

## 1. Componentes

| Componente | Commit | O que mudou |
|---|---|---|
| `AppToaster` | `8da7494` | **novo** — a configuração do sonner sai do `AppLayout` |
| `Alert` | `a87381b` | as tintas medidas, e o papel passa a depender da variante |
| `Modal` | `0bfaf01` | devolve o foco a quem o abriu |
| `Tabs` | `0ec9acd` | setas, tabulação móvel e o painel que faltava |

**`Tooltip` não existe no HelpHS.** A §7.1 o lista porque o ChamadosHS o tem;
aqui não há arquivo nem uso, e nada foi criado só para preencher a linha.

## 2. O padrão da fase: papel declarado, contrato não entregue

Três dos quatro componentes **declaravam um papel de widget e não entregavam o
que ele promete**. É a continuação direta do que a Fase 9 encontrou, e o gêmeo
não-visual dela.

| Onde | O papel dizia | E não havia |
|---|---|---|
| `Tabs` | `role="tablist"` + `role="tab"` | setas, tabulação móvel, `role="tabpanel"`, `aria-controls` |
| `Alert` | `role="alert"` nas **quatro** variantes | distinção entre interromper e esperar |
| `Modal` | armadilha de foco na entrada | devolução do foco na saída |

O do `Alert` é o mais sutil: `role="alert"` é região viva **assertiva** — ela
interrompe o que o leitor de tela estiver dizendo. Para um erro é o certo. Para
um "salvo com sucesso" é atropelar a leitura da pessoa com uma informação que
podia esperar a próxima pausa. `info` e `success` passaram a `status`.

Declarar o papel e não honrá-lo **é pior que não declarar**: faz um leitor de
tela anunciar "aba 2 de 4" e a pessoa esperar as setas que nunca respondem.

## 3. Cor: dois vícios distintos

**A paleta crua da biblioteca.** O `richColors` do sonner pinta o fundo do toast
com a paleta **própria dele**, fora do sistema de tokens e sem contraste medido.
Saiu; a cor do tipo foi para o ícone, onde informa sem virar decoração.

**A cor cheia da rampa como "a cor do tipo".** É o palpite óbvio, e reprova.
Medido contra `--toast-bg` nos dois temas, piso de 3:1:

| Token | claro | escuro | |
|---|---:|---:|---|
| `--on-tint-success` | 7,68 | 7,72 | ✅ |
| `--on-tint-danger` | 6,47 | 7,82 | ✅ |
| `--on-tint-warning` | 7,09 | 8,89 | ✅ |
| `--action` (info) | 5,29 | 5,52 | ✅ |
| `--color-warning-500` | **2,15** | 6,91 | ❌ claro |
| `--color-success-500` | **2,54** | 5,85 | ❌ claro |
| `--action-success` | 5,48 | **2,71** | ❌ escuro |

O `--action-success` reprova no escuro pela mesma razão que o `Input` não usa
`--action-danger`: **o bloco `.dark` não os redefine**. Escolher por analogia
teria errado nos dois sentidos.

E o `Alert` tinha um terceiro caso: `success` pintado com **`primary`**. Não é
ajuste de tom — é a variante dizendo a cor errada, saindo no mesmo degrau de um
botão primário.

## 4. O quinto componente só-escuro

`Tabs` era escrito **só para o tema claro não existir**: `text-slate-100`,
`text-slate-400`, sem um único `dark:`. Com `FormDropdown`, `SearchSelect`,
`Table` e `Pagination`, são **cinco** componentes de `ui/` com o mesmo vício.

A suspeita registrada na Fase 9 se confirmou, e o inventário agora está fechado:
**todo componente de `ui/` foi lido nesta migração**, e nenhum outro tem o vício.

## 5. Um bug que não era de acessibilidade nem de cor

O botão de fechar do `Alert` e o gatilho do `Tabs` **não tinham `type="button"`**.
Dentro de `<form>` o padrão do HTML é `submit`: fechar o aviso ou trocar de aba
enviava o formulário. Os testes confirmam que acontecia.

O `Modal` também não tinha, **e ali não acontecia** — ele vai para um portal em
`document.body`, então o botão nunca é descendente do `<form>` no DOM. Escrevi o
contrário no comentário e num teste, e **a mutação me desmentiu**: o teste
passava com o atributo removido. O atributo ficou; a afirmação foi corrigida.

## 6. A galeria de componentes

`3983e33`. É a exigência do Checkpoint 2, e a resposta ao caso que a comprou: na
Fase 7 a medição de **tokens** do `Badge` deu zero reprovações e o componente
renderizado tinha sete em quarenta e duas.

Entrada própria do Vite, sem roteador nem backend. O spec visita nos dois temas,
lê o estilo **computado**, compõe o fundo efetivo empilhando camadas
translúcidas e cobra 4,5:1 para texto e 3:1 para gráfico.

**Ela caiu em três armadilhas antes de servir**, e cada uma foi pega por uma
guarda diferente — nenhuma por leitura:

1. **Media 28 de 85 elementos e passava verde.** O Chromium devolve
   `color(srgb …)` para cor vinda de `color-mix()`, que é como o D1 mapeia os
   tokens. O parser só entendia `rgb()`. Pegou o **piso de cobertura**.
2. **Acusou quatro reprovações que não existiam.** O Playwright reusa o servidor
   de desenvolvimento, e havia um subido antes das mudanças no
   `tailwind.config.js`. Entrou um **canário** que exige regra CSS para seis
   classes de token.
3. **O primeiro controle não controlava.** `bg-surface text-slate-300` não
   reprova: no claro o espelho do D5 o reescreve para slate-700. Trocado por
   `bg-action text-white`, que reprova em **2,69:1 no escuro** e aprova em
   **5,32:1 no claro** — e a galeria acusa no tema certo.

A segunda é a mais perigosa das três: **se eu tivesse "consertado" aquelas
quatro, teria quebrado código que funciona.**

## 7. Prova

| | |
|---|---|
| Testes novos | 49 (`AppToaster` 14, `Alert` 20, `Modal` 5, `Tabs` 10) |
| Mutações | 24 aplicadas, **24 acusadas** — três só depois de corrigir teste ou alvo |
| Galeria | 2 execuções (claro e escuro), **85 elementos medidos**, zero reprovações |
| Suíte | **678 passando**, 57 arquivos |
| Tipos | `tsc -b` limpo — e ele pegou um erro que o `--noEmit` deixava passar |
| Catraca | **49**, linha de base 49, em dia |

## 8. Pendências que a fase abre

1. **O `Alert.jsx` do pacote usa `role="alert"` nas quatro variantes.**
   Registrada como candidata a emenda: a correção pertence à origem, mas emenda
   não se escreve sem autorização.
2. **O `SearchSelect.jsx` do pacote tem `<label>` sem `htmlFor`** e `<button>`
   sem `id` — o rótulo é texto que não rotula nada. Ficou de fora da E11 por
   estar fora do escopo autorizado, e tem uma escolha real dentro: `htmlFor` num
   botão é válido mas passa o clique para o gatilho; `aria-labelledby` dá o nome
   sem mexer no clique.
3. **O modo linear da armadilha 12 nunca foi exercitado** por código real — o
   HelpHS não tem template com mais de 64 combinações. Tem caso de prova, e é só
   isso que o segura.
