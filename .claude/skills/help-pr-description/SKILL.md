---
name: help-pr-description
description: Gera descrição de Pull Request do HelpHS a partir do diff ou dos commits do branch, destacando migrations automáticas, variáveis de ambiente e a ordem de subida dos serviços no EasyPanel. Nunca abre o PR.
---

# Skill: PR Description — HelpHS

## Objetivo

Gerar descrição clara e padronizada de PR, com contexto suficiente para
revisar com confiança e **subir na ordem certa**.

## Contexto que muda a descrição

- **Monorepo**: um PR pode tocar `frontend/` e `backend/` juntos — é o normal
  quando o contrato muda, e a descrição deve tratar os dois lados como uma
  entrega só
- O CI roda no PR (`ci.yml`, branches `main` e `develop`): ruff, black,
  pytest com cobertura ≥ 80%, eslint, `tsc -b`, Vitest, build. **E2E e k6
  não rodam** — se a mudança depende deles, o "como testar" precisa cobrir
- Migrations Alembic **rodam sozinhas no boot** do container — merge + deploy
  aplica o schema; isso nunca é nota de rodapé
- Deploy é **manual via EasyPanel**, front e back em serviços separados
- `VITE_*` muda só com **rebuild** da imagem do front

## O que pedir se não for fornecido

- `git log main..HEAD --oneline` ou o diff
- Contexto: bug, feature, refactor, segurança?
- Há migration? Muda contrato da API?

## Estrutura gerada

```markdown
## O que foi feito
[O que muda, do ponto de vista de quem usa o sistema]

## Por que foi feito
[Motivação: bug reportado, requisito (RN-xxx), decisão técnica, achado de segurança]

## Como testar
- [ ] Passo 1
- [ ] Comportamento esperado: ...
- [ ] O que o CI não cobre e foi testado à mão: e2e / fluxo manual

## Impacto
- [ ] Breaking change no contrato da API (front acompanhou no mesmo PR?)
- [ ] Migration Alembic — revision: `xxx` (roda sozinha no deploy; backup antes)
- [ ] Variável de ambiente nova — qual, e onde configurar no EasyPanel
- [ ] Mudou `VITE_*` — exige rebuild da imagem do front
- [ ] Altera autenticação/token (ver ordem de subida)

## Ordem de subida
1. [ex.: backup do banco]
2. [ex.: subir o serviço do back — migration roda no boot]
3. [ex.: rebuild + subir o serviço do front]

## Checklist
- [ ] CI verde (inclui cobertura ≥ 80% no back e o Vitest do front)
- [ ] E2E rodado se o fluxo mudou (manual — fora do CI)
- [ ] Migration testada com upgrade → downgrade → upgrade
- [ ] Variáveis novas documentadas no `.env.example`
- [ ] Changelog (`src/data/changelog.ts`) atualizado, se é entrega visível
```

## Regras

- Título no padrão de commit do projeto: `tipo: descrição em português`
  (sem escopo)
- Não listar arquivos como descrição — explicar o impacto
- **Migration sempre em destaque**, com o nome da revision e o lembrete de que
  ela aplica sozinha no deploy
- Mudança de autenticação exige a seção "Ordem de subida" explicando por que
  o front vem antes (sessão de quem está logado)
- Adaptar o detalhe ao tamanho: PR pequeno não precisa de todas as seções

## Observações

- **Nunca abrir o PR automaticamente**
- Diff acima de ~500 linhas: sugerir dividir antes
- Aproveitar o contexto da sessão para decisões já discutidas
- Ver [[help-deploy-check]] para o checklist completo de subida
