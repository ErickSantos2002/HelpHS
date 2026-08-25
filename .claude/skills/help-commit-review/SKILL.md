---
name: help-commit-review
description: Revisa um commit do HelpHS antes de finalizar — conventional commits sem escopo em português, coesão do diff, arquivos indevidos e sincronia entre model, migration e front. Usar antes de git commit ou push.
---

# Skill: Commit Review — HelpHS

## Objetivo

Revisar um commit antes de ser finalizado: mensagem clara, escopo coeso,
nenhum arquivo indevido, e os dois lados do monorepo consistentes.

## Convenção do projeto

**Conventional commits sem escopo, com descrição em português.** Exemplos
reais do histórico:

```
feat: varios equipamentos por chamado (v1.6.0)
fix: anexos escolhidos na abertura do chamado eram descartados
fix: build do frontend quebrado por typecheck que nao checava nada
docs: changelog da v1.3.0
test: recupera a suite do backend (37 falhas -> 0)
ci: devolve o pipeline ao verde (ruff + cobertura de 80%)
```

Regras derivadas do histórico:

- **Tipos em uso**: `feat`, `fix`, `docs`, `test`, `ci`, `merge`
- **Sem escopo** — diferente do ChamadosHS, aqui a convenção é
  `tipo: descrição`, não `tipo(escopo):`. Não sugerir escopo
- Descrição em **português, minúscula, sem ponto final**, descrevendo
  **o efeito**, não o arquivo mexido
- Release ganha o número da versão no fim: `(v1.6.0)`
- O `.pre-commit-config.yaml` traz **commitizen** no `commit-msg`, mas os
  hooks **não estão instalados** na máquina atual (`pre-commit install`
  ativa) — não confiar que o hook barra; validar o formato na revisão

> ⚠️ Não sugerir imperativo em inglês ("Add", "Fix", "Update") — contraria a
> convenção adotada.

## O que analisar

### 1. Mensagem

- Segue `tipo: descrição em português`?
- Diz o efeito para quem usa o sistema, e não "mexi no arquivo X"?
- Subject com no máximo ~72 caracteres
- Mudança de regra de negócio (RN-xxx) tem corpo explicando o **porquê**?

Apontar: mensagem vaga ("ajustes", "wip"), tipo errado (`feat` para correção).

### 2. Escopo das mudanças

- O commit faz **uma coisa só**?
- Arquivo indevido no staged: `.env`, `keys/`, `*.pem`, `dist/`,
  `node_modules/`, `__pycache__/`, `logs/`, `uploads/`
- `console.log` / `print()` de debug esquecido
- O diff é proporcional ao que a mensagem descreve?

### 3. Coerência estrutural (monorepo)

- **Mudou `app/models/models.py`?** A revision Alembic correspondente está no
  mesmo commit? Model sem migration explode em runtime, depois do deploy
  (ver `help-migration-check`)
- **Mudou schema Pydantic?** O service e os tipos do front
  (`frontend/src/services/`, `src/types/`) mudaram **no mesmo commit**? A
  vantagem do monorepo é o contrato fechar atômico — usar isso
- **Endpoint novo?** Tem `Depends(get_current_user)`/`authorize(...)` e filtro
  de escopo do `client`? Não há trava que pegue depois
- Código novo no backend veio com teste? O gate de 80% do CI cobra
- Se é release: `frontend/src/data/changelog.ts` e `APP_VERSION`
  acompanharam? (ver `help-changelog-update`)

### 4. Hooks

O `.pre-commit-config.yaml` define ruff (com `--fix`), black, prettier e
checagens gerais — **quando instalados** (`pre-commit install`; na máquina
atual não estão, então nada roda no commit e a formatação é manual). Com
hooks ativos, se o hook alterou arquivo, o diff staged pode ter ficado para
trás.
**Nunca sugerir `--no-verify`** para contornar hook falhando: entender e
corrigir.

## Formato da resposta

```
✅ Mensagem: aprovada — feat: reabertura de chamado pelo cliente
📦 Escopo: coeso — ciclo de reabertura apenas
🔍 Arquivos: ⚠️ keys/private.pem aparece no staged — remover JÁ e trocar as chaves
🗄️  Migration: model alterado com revision no mesmo commit ✅
🔗 Contrato: schema mudou e ticketService.ts acompanhou ✅
💬 Sugestão: feat: cliente reabre chamado em ate 5 dias uteis
```

## Observações

- **Nunca executar o commit** — a decisão é do usuário
- Se o commit tiver múltiplas responsabilidades, sugerir como dividir
- Chave privada ou `.env` commitados não é só "remover do staged": se já
  entrou em commit anterior, o segredo está no histórico — trocar o segredo
- Tom objetivo: agilizar, não bloquear
