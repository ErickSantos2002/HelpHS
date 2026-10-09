/**
 * A cor dos gráficos, numa fonte só.
 *
 * Existia espalhada por três arquivos — `AdminDashboard`, `TechnicianDashboard`
 * e `ReportsPage` —, cada um com o seu `theme === "dark" ? A : B` escrito à mão
 * e nenhum concordando com os outros. Este módulo não é conveniência: é o que
 * faz o gráfico deixar de ler o tema.
 *
 * ── Por que o `theme` some ────────────────────────────────────────────
 *
 * O padrão anterior lia `useTheme()` e escolhia o hexadecimal no JavaScript. Um
 * token faz isso sozinho no CSS: `var(--surface)` já é branco no claro e
 * `#132238` no escuro. Ler o tema em JS para escolher a cor é reimplementar o
 * seletor `.dark` — com o agravante de que a versão em JS não acompanha a
 * paleta quando ela muda.
 *
 * ── Os tokens do cromo resolvem para hexadecimal LITERAL ──────────────
 *
 * Isto importa, e é a razão de a tentativa anterior ter quebrado o gráfico: as
 * tintas de interface (`--tint-*`) são `color-mix()`, e o Recharts as escreve em
 * atributo de SVG. Os cinco daqui — `--surface`, `--border-color`,
 * `--border-muted`, `--text-muted`, `--text-heading` — e os sete `--chart-*` e
 * quatro `--fill-*` descem por cadeia de `var()` até hexadecimal cravado. Nenhum
 * passa por `color-mix()`.
 *
 * ── O eixo reprovava, nos dois temas ──────────────────────────────────
 *
 * Medido contra as três superfícies, pior caso:
 *
 *   claro   eixo hoje `#94a3b8` (slate-400)   2,45 / 2,56 / 2,34
 *   escuro  eixo hoje `#475569` (slate-600)   2,30 / 2,11 / 1,79
 *
 * O piso de forma é 3:1, e o `stroke` do `XAxis` do Recharts pinta **também o
 * texto das marcas** — então o piso que vale ali é o de texto, 4,5:1. O eixo
 * reprovava os dois, nos dois temas, e não aparecia em nenhuma catraca porque
 * era variável de JavaScript, não classe do Tailwind.
 *
 * O substituto é `--text-muted`: 7,24 / 7,58 / 6,92 no claro e 6,78 / 6,23 /
 * 5,29 no escuro. **Isto escurece o eixo nas duas telas** — é mudança visível, e
 * é conserto de defeito, não preferência.
 *
 * A grade é outro caso, e a regra é a que o @chamadoshs registrou: cor é higiene
 * ou acessibilidade conforme **quem carrega a informação**. Linha de grade não
 * carrega — quem diz o valor é a marca do eixo. Então ela aponta para
 * `--border-muted`, que tem exatamente o valor de hoje nos dois temas, e o
 * gráfico não muda de aparência por causa dela.
 */

/**
 * Eixo, grade e dica.
 *
 * Cinco entradas, e cada uma é o token do papel que o elemento tem — não o
 * token cujo valor por acaso bate com o hexadecimal que estava lá.
 */
export const CROMO = {
  /** Linha do eixo **e o texto das marcas**: o Recharts pinta os dois com este. */
  eixo: "var(--text-muted)",
  /** Linha de grade. Mesmo valor de hoje nos dois temas — higiene, não conserto. */
  grade: "var(--border-muted)",
  /** Fundo da dica. Exato nos dois temas. */
  dicaFundo: "var(--surface)",
  /** Borda da dica. Exata no claro; um degrau mais clara no escuro. */
  dicaBorda: "var(--border-color)",
  /** Texto da dica. Exato nos dois temas. */
  dicaTexto: "var(--text-heading)",
} as const;

/** O `contentStyle` da dica do Recharts. */
export const ESTILO_DICA = {
  backgroundColor: CROMO.dicaFundo,
  border: `1px solid ${CROMO.dicaBorda}`,
  borderRadius: "8px",
  color: CROMO.dicaTexto,
  fontSize: "12px",
} as const;

/**
 * O `wrapperStyle` da dica.
 *
 * `outline: none` porque o Recharts põe um contorno de foco no envoltório que
 * não corresponde a nenhum elemento focável.
 */
export const ENVOLTORIO_DICA = {
  backgroundColor: CROMO.dicaFundo,
  border: `1px solid ${CROMO.dicaBorda}`,
  borderRadius: "8px",
  outline: "none",
} as const;

/**
 * Os sete slots de série, na ordem da paleta.
 *
 * São **categóricos**: a cor não significa nada, só separa. Quem quiser dizer
 * "cancelado" põe legenda — é a regra da E18, e ela vale para qualquer série,
 * não só status.
 */
export const SLOTS_DE_SERIE = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--chart-6)",
  "var(--chart-7)",
] as const;

/**
 * O slot de uma série categórica pela posição, ciclando depois do sétimo.
 *
 * Ciclar é a resposta menos ruim, e ela é ruim: da oitava série em diante duas
 * pintam igual. A E16-b mediu que o tema claro comporta **sete** matizes com
 * 3:1 nas três superfícies e ΔE ≥ 20 entre todos os pares — não há oitava para
 * inventar. Gráfico com mais de sete categorias precisa agrupar a cauda em
 * "outros", e isso é decisão de tela.
 *
 * Índice negativo ou fracionário recua para o primeiro slot em vez de devolver
 * `undefined` — série sem cor some do gráfico sem erro.
 */
export function slotCategorico(indice: number): string {
  if (!Number.isInteger(indice) || indice < 0) return SLOTS_DE_SERIE[0];
  return SLOTS_DE_SERIE[indice % SLOTS_DE_SERIE.length];
}

/**
 * A cor de uma série temporal quando ela é a **única** medida do gráfico.
 *
 * Regra do operador: série temporal da mesma natureza usa uma cor só quando for
 * a mesma medida. Hoje são cinco gráficos da mesma natureza — chamados por dia —
 * em quatro cores diferentes, e a diferença não significa nada.
 *
 * Gráfico temporal com **mais de uma** medida não usa isto: são séries
 * distintas, e cada uma pega o seu `slotCategorico`.
 */
export const COR_SERIE_TEMPORAL = SLOTS_DE_SERIE[0];

/**
 * As três faixas da escala de satisfação, decididas pelo operador em 08/09/2026.
 *
 * `1–4` insatisfeito, `5–7` neutro, `8–10` satisfeito. Saiu a rampa de dez cores
 * cravadas, que falhava a separação **por construção**: degraus vizinhos são
 * próximos de propósito, e o eixo vermelho-verde é justamente o que colapsa em
 * protanopia e deuteranopia — dez notas viravam duas manchas.
 *
 * A cor sozinha continua não bastando (1.4.1), e o que resolve é o operador ter
 * exigido **o número sempre no rótulo**: a nota é o portador redundante. Sem
 * ele, três faixas seriam a mesma falha da rampa, só com menos passos.
 */
export const FAIXAS_CSAT = [
  { de: 1, ate: 4, preenchimento: "var(--fill-danger)" },
  { de: 5, ate: 7, preenchimento: "var(--fill-warning)" },
  { de: 8, ate: 10, preenchimento: "var(--fill-success)" },
] as const;

/**
 * O preenchimento da barra de uma nota de satisfação.
 *
 * Nota fora de 1–10 recua para o neutro em vez de pegar a faixa da ponta: o
 * dado vem da rede, e uma escala que mudasse para 0–10 no backend pintaria o
 * zero de vermelho como se fosse nota 1 — afirmação que ninguém fez.
 */
export function preenchimentoCsat(nota: number): string {
  const faixa = FAIXAS_CSAT.find((f) => nota >= f.de && nota <= f.ate);
  return faixa?.preenchimento ?? "var(--border-control)";
}
