---
name: help-changelog-update
description: Atualiza o changelog do HelpHS, que vive dentro do app em frontend/src/data/changelog.ts e é exibido ao usuário final. Usar ao fechar um conjunto de entregas ou preparar uma versão. Nunca sobrescreve versão já publicada.
---

# Skill: Changelog Update — HelpHS

## Objetivo

Manter o changelog do produto a partir dos commits do período. Aqui **não há
`CHANGELOG.md`**: o changelog é dado da aplicação, em
`frontend/src/data/changelog.ts`, e **aparece dentro do sistema para o
cliente final** — o cuidado com o texto é de produto, não de repositório.

## Como funciona

```ts
export const APP_VERSION = "v1.6.0";

export const CHANGELOG: ChangelogVersion[] = [
  {
    version: "v1.6.0",
    date: "10/08/2026",
    entries: [
      { type: "novidade", text: "Um chamado pode cobrir vários aparelhos: ..." },
      { type: "melhoria", text: "A busca encontra o chamado pelo número de série ..." },
      { type: "corrigido", text: "O chat ficava espremido quando ..." },
    ],
  },
  ...
];
```

- Tipos possíveis: **`novidade` | `melhoria` | `corrigido`** (enum
  `EntryType` no próprio arquivo — não inventar categoria)
- Data em `DD/MM/AAAA`
- Versão nova entra **no topo** do array, e `APP_VERSION` acompanha
- O commit do changelog segue o padrão do histórico:
  `docs: changelog da v1.X.0`

Não há tags git nem `[Não publicado]` — a fonte para montar uma versão é o
log desde o commit do changelog anterior:

```bash
git log --oneline <commit-do-changelog-anterior>..HEAD
```

## Mapeamento commit → tipo

| Commit | Tipo |
|---|---|
| `feat:` que adiciona capacidade | `novidade` |
| `feat:`/`fix:` que melhora algo existente sem ser conserto de defeito | `melhoria` |
| `fix:` de defeito que o usuário sentia | `corrigido` |
| `docs:`, `ci:`, `test:`, refactor interno | normalmente **não entra** — o cliente não vê |

Mudança puramente interna (migration, cobertura, pipeline) só entra se tiver
efeito perceptível ("o sistema ficou mais rápido ao...").

## Regras de escrita

O leitor é o **cliente da Health & Safety** dentro do sistema, não um dev:

- Falar de chamados, aparelhos, prazos — nunca de endpoint, schema, migration
- Exemplo real do arquivo, para calibrar o tom:
  > "Reabrir chamado: se o problema voltar, o cliente reabre o chamado em até
  > 5 dias úteis, sem perder o histórico."
- Ser específico: "correção de bug" não diz nada — qual defeito, qual impacto
- Frase completa, em português, terminada em ponto (padrão do arquivo)
- Agrupar mudanças relacionadas numa entrada só

## Observações

- **Nunca sobrescrever versão já publicada** — versão nova no topo, as
  anteriores ficam intactas
- **Perguntar o número da versão** antes de criar (o projeto usa minor bump:
  v1.4.0 → v1.5.0 → v1.6.0)
- `APP_VERSION` e a primeira entrada do array têm que bater — o app exibe os dois
- O arquivo é TypeScript: rodar `npx tsc --noEmit` (ou confiar no CI) depois
  de editar — vírgula errada aqui quebra o build do front
- Ver [[help-commit-review]]: se é commit de release, changelog e versão
  andam juntos
