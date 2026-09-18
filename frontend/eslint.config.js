import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'coverage'] },
  {
    // Os `.mjs` — varredura de contraste, sonda de captura, ponte D5 — não
    // casavam com NENHUM bloco deste arquivo: os dois de baixo pedem `.ts`/
    // `.tsx`. O ESLint processava cada um com **zero regras** e saía com
    // código 0.
    //
    // Isso é pior que não rodar: `npx eslint script.mjs` dizia "limpo", e a
    // frase entrou em relatório e em mensagem de commit como se fosse prova.
    // Conferido por mutação — um arquivo com `var x = x`, constante não usada
    // e atribuição dentro de `if` passava igual.
    //
    // Ao ligar a regra, os arquivos deram **zero problema**: a régua estava
    // vazia e não escondia nada. Mas "não escondia nada" só se soube depois de
    // medir, e é essa a diferença que este bloco compra.
    // ── E os globais são os DOIS, o que também só se soube medindo ──────
    //
    // A primeira versão deste bloco declarava só `globals.node`, e a regra
    // acusou 13 `no-undef`: `window`, `document` e `getComputedStyle`. Nenhum é
    // erro — eles estão **dentro de `page.evaluate()`**, que o Playwright
    // executa no navegador. Um mesmo arquivo tem código dos dois lados, e
    // declarar só um faz a régua nova nascer gritando no lugar errado.
    extends: [js.configs.recommended],
    files: ['**/*.mjs'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: { ...globals.node, ...globals.browser },
    },
  },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],
    },
  },
  {
    // Arquivos que rodam em Node (usam process.env), não no browser
    files: ['e2e/**/*.ts', 'playwright.config.ts', 'vite.config.ts'],
    languageOptions: {
      globals: globals.node,
    },
  },
)
