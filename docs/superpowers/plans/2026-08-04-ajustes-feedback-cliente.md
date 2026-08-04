# Ajustes do feedback do cliente — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aplicar as sete frentes de ajuste levantadas na rodada de testes do cliente sobre a v1.0.0 do HelpHS.

**Architecture:** As frentes são independentes e tocam camadas diferentes (permissão na KB, UI da agenda, textos, tratamento de erro, novo CRUD de respostas rápidas, validação de onboarding, escala do CSAT). Cada tarefa é entregável sozinha, com commit próprio. Só a Frente 5 mexe no banco (nova tabela + migration Alembic).

**Tech Stack:** FastAPI 3.12 + SQLAlchemy 2.0 async + Alembic + pytest (DB e Redis mockados); React 19 + Vite + TypeScript + Tailwind + Vitest + Playwright.

**Spec:** `docs/superpowers/specs/2026-08-04-ajustes-feedback-cliente-design.md`

**Branch:** `ajustes/feedback-cliente-v1.0.0`

---

## Task 0: Preparar o ambiente de teste do backend

O frontend já tem `node_modules`. O backend não tem venv nem dependências instaladas, e sem isso nenhuma mudança de Python pode ser verificada.

**Files:** nenhum arquivo versionado é alterado.

- [ ] **Step 1: Criar o venv e instalar as dependências**

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r backend\requirements-dev.txt
```

- [ ] **Step 2: Rodar a suíte atual para confirmar o baseline**

Run: `backend\.venv\Scripts\python.exe -m pytest --no-cov -q` (a partir de `backend/`)
Expected: todos os testes passando. Anotar o número de testes — é o baseline das próximas tarefas.

`--no-cov` desliga o `--cov-fail-under=80` do `pyproject.toml`, que faz a suíte falhar quando se roda um subconjunto de testes.

- [ ] **Step 3: Confirmar o baseline do frontend**

Run (em `frontend/`): `npm test`, depois `npm run lint`
Expected: ambos verdes. Se algo já estiver quebrado antes das mudanças, registrar antes de seguir.

- [ ] **Step 4: Adicionar o venv ao .gitignore se ainda não estiver coberto**

Verificar se `.gitignore` cobre `.venv/`. Se não cobrir, adicionar a linha `backend/.venv/` e commitar junto da Task 1.

---

## Task 1: Frente 3 — varredura ortográfica

**Files:**
- Modify: `frontend/src/lib/utils.ts`
- Modify: `frontend/src/pages/reports/ReportsPage.tsx:478,745,749`
- Modify: `frontend/src/pages/kb/KBArticlePage.tsx:394`
- Modify: demais arquivos com erros encontrados na varredura
- Test: `frontend/src/test/lib/plural.test.ts` (criar)

- [ ] **Step 1: Escrever o teste do helper de plural**

Criar `frontend/src/test/lib/plural.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { plural } from "../../lib/utils";

describe("plural", () => {
  it("usa o singular para 1", () => {
    expect(plural(1, "violação", "violações")).toBe("violação");
  });

  it("usa o plural para 0", () => {
    expect(plural(0, "violação", "violações")).toBe("violações");
  });

  it("usa o plural para mais de 1", () => {
    expect(plural(3, "avaliação", "avaliações")).toBe("avaliações");
  });
});
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run (em `frontend/`): `npx vitest run src/test/lib/plural.test.ts`
Expected: FAIL — `plural` não é exportado de `lib/utils`.

- [ ] **Step 3: Implementar o helper**

Acrescentar ao final de `frontend/src/lib/utils.ts`:

```ts
/**
 * Escolhe entre singular e plural. Evita o erro de concatenar terminação
 * (`violação` + `ões` = `violaçãoões`).
 */
export function plural(n: number, singular: string, pluralForm: string): string {
  return n === 1 ? singular : pluralForm;
}
```

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `npx vitest run src/test/lib/plural.test.ts`
Expected: PASS (3 testes).

- [ ] **Step 5: Corrigir as quatro pluralizações quebradas**

`frontend/src/pages/reports/ReportsPage.tsx:478` — importar `plural` de `../../lib/utils` e trocar:

```tsx
sub={`${totalCsat} ${plural(totalCsat, "avaliação", "avaliações")}`}
```

Linha 745:

```tsx
sub={`${data.sla_breached} ${plural(data.sla_breached, "violação", "violações")}`}
```

Linha 749:

```tsx
sub={data.csat_count > 0
  ? `${data.csat_count} ${plural(data.csat_count, "avaliação", "avaliações")}`
  : "sem avaliações"} />
```

`frontend/src/pages/kb/KBArticlePage.tsx:394`:

```tsx
{article.view_count} {plural(article.view_count, "visualização", "visualizações")}
```

- [ ] **Step 6: Varrer o restante dos textos visíveis**

Ler os textos em português de `frontend/src/pages/`, `frontend/src/components/`, e as mensagens de `backend/app/` (routers, `services/email.py`, `services/notifications.py`). Procurar:

- acentuação faltando ou sobrando (`usuario`, `voce`, `sera`, `codigo`, `numero`, `atribuido`, `tecnico`)
- crase e concordância (`a partir`, `às`, `há/a`)
- pluralização concatenada, no padrão dos erros acima
- termos inconsistentes para a mesma coisa (ex.: "chamado" vs "ticket") — anotar, mas só padronizar se for erro claro

Comando útil para o primeiro passe:

```powershell
# Palavras comuns sem acento em strings de UI
Select-String -Path frontend\src\**\*.tsx -Pattern '"[^"]*\b(usuario|tecnico|voce|nao|sao|esta|codigo|numero|atribuido|conteudo|periodo|relatorio)\b[^"]*"'
```

Registrar cada correção (arquivo, antes, depois) numa lista para entregar ao usuário.

- [ ] **Step 7: Verificar**

Run (em `frontend/`): `npm test`, `npm run lint`, `npm run build`
Expected: os três verdes. `npm run build` pega qualquer import de `plural` faltando.

- [ ] **Step 8: Commit (pedir confirmação ao usuário antes)**

```bash
git add frontend/src
git commit -m "fix: corrige erros de ortografia e pluralizacao nos textos da interface"
```

---

## Task 2: Frente 7 — unificar a escala CSAT em 1–10

A avaliação é coletada de 1 a 10, mas relatórios, gráficos e filtros assumem 1 a 5. Notas de 6 a 10 somem do gráfico de distribuição.

**Files:**
- Modify: `backend/app/routers/dashboard.py:307`
- Modify: `backend/app/routers/surveys.py:148`
- Modify: `backend/app/models/models.py:634` (comentário)
- Modify: `frontend/src/pages/reports/ReportsPage.tsx:75,477,567,572,748`
- Modify: `frontend/src/pages/dashboard/AdminDashboard.tsx:384`
- Modify: `frontend/src/pages/dashboard/TechnicianDashboard.tsx:318`
- Test: `backend/tests/test_dashboard.py`, `backend/tests/test_surveys.py`

- [ ] **Step 1: Escrever o teste da distribuição 1–10**

Em `backend/tests/test_dashboard.py`, seguir o padrão de mock já usado no arquivo e acrescentar um teste que verifica que a distribuição devolvida tem 10 faixas e inclui uma avaliação de nota 8:

```python
async def test_csat_distribution_cobre_notas_de_1_a_10(...):
    # mock: uma avaliação com rating=8
    ...
    data = response.json()["csat_distribution"]
    assert len(data) == 10
    assert [d["rating"] for d in data] == list(range(1, 11))
    assert next(d for d in data if d["rating"] == 8)["count"] == 1
```

Ler os mocks existentes no arquivo antes de escrever — o teste precisa usar o mesmo estilo de `MagicMock`/`AsyncMock` já presente.

- [ ] **Step 2: Rodar o teste e ver falhar**

Run (em `backend/`): `.venv\Scripts\python.exe -m pytest tests/test_dashboard.py -k csat_distribution --no-cov -v`
Expected: FAIL — só 5 faixas, nota 8 ausente.

- [ ] **Step 3: Corrigir o backend**

`backend/app/routers/dashboard.py:307`:

```python
    csat_distribution = [
        CSATDistributionItem(rating=i, count=counts_by_rating.get(i, 0)) for i in range(1, 11)
    ]
```

`backend/app/routers/surveys.py:148`:

```python
    rating: int | None = Query(default=None, ge=1, le=10),
```

`backend/app/models/models.py:634` — comentário passa de `# 1 a 5` para `# 1 a 10`.

Conferir também os rótulos de exportação CSV e PDF em `dashboard.py` (por volta das linhas 687-692 e 775-780): onde houver menção a escala, deixar coerente com 1–10.

- [ ] **Step 4: Rodar os testes do backend**

Run: `.venv\Scripts\python.exe -m pytest tests/test_dashboard.py tests/test_surveys.py --no-cov -v`
Expected: PASS, incluindo o teste novo.

- [ ] **Step 5: Corrigir o frontend**

`frontend/src/pages/reports/ReportsPage.tsx:75` — 10 cores, do vermelho ao verde:

```tsx
const CSAT_COLORS = [
  "#dc2626", "#ef4444", "#f97316", "#fb923c", "#eab308",
  "#facc15", "#a3e635", "#84cc16", "#4ade80", "#22c55e",
];
```

Linha 477 e 748 — `/ 5` vira `/ 10`:

```tsx
value={data.csat_average ? `${data.csat_average} / 10` : "—"}
```

Linha 567 — título do gráfico: `"Distribuição CSAT (1–10)"`.

Linha 572 — o `tickFormatter` usa `★ ${v}`, que sugere estrelas de 1 a 5. Trocar por `String(v)`, já que a coleta é por nota numérica.

Linha 480 — o `Delta` multiplica a média por 10 para comparar (`csat_average * 10`). Com a escala explícita em 1–10 isso continua válido como normalização percentual; manter, mas conferir se o número exibido faz sentido no card.

`frontend/src/pages/dashboard/AdminDashboard.tsx:384`:

```tsx
value={avgRating === "—" ? "—" : `${avgRating} / 10`}
```

`frontend/src/pages/dashboard/TechnicianDashboard.tsx:318` — mesmo ajuste no card "Meu CSAT"; ler o trecho antes de editar para casar com a formatação local.

- [ ] **Step 6: Verificar o frontend**

Run (em `frontend/`): `npm test`, `npm run build`
Expected: verdes.

- [ ] **Step 7: Commit (pedir confirmação ao usuário antes)**

```bash
git add backend/app backend/tests frontend/src
git commit -m "fix: unifica a escala do CSAT em 1-10 em relatorios, graficos e filtros"
```

---

## Task 3: Frente 1 — técnico exclui comentários da KB

**Files:**
- Modify: `backend/app/routers/kb.py:475-493`
- Modify: `frontend/src/pages/kb/KBArticlePage.tsx` (visibilidade do botão excluir)
- Test: `backend/tests/test_kb.py`

- [ ] **Step 1: Escrever o teste da permissão**

Em `backend/tests/test_kb.py`, seguindo os mocks já existentes no arquivo, dois testes:

```python
async def test_tecnico_pode_excluir_comentario_de_cliente(...):
    # actor = technician, comment.author_id = outro usuário
    assert response.status_code == 204


async def test_cliente_nao_pode_excluir_comentario_de_outro(...):
    # actor = client, comment.author_id = outro usuário
    assert response.status_code == 403
    assert "permissão" in response.json()["detail"]
```

- [ ] **Step 2: Rodar e ver falhar**

Run (em `backend/`): `.venv\Scripts\python.exe -m pytest tests/test_kb.py -k excluir_comentario --no-cov -v`
Expected: o primeiro teste falha com 403.

- [ ] **Step 3: Alterar a regra**

`backend/app/routers/kb.py`, dentro de `delete_comment`:

```python
    is_privileged = actor.role in (UserRole.admin, UserRole.technician)
    is_own = comment.author_id == actor.id
    if not is_privileged and not is_own:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você só pode excluir os seus próprios comentários.",
        )
```

Atualizar também a docstring da função e o cabeçalho de permissões no topo do arquivo, se houver menção à regra antiga.

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv\Scripts\python.exe -m pytest tests/test_kb.py --no-cov -v`
Expected: PASS.

- [ ] **Step 5: Liberar o botão no frontend**

Em `frontend/src/pages/kb/KBArticlePage.tsx`, localizar a condição que hoje mostra o botão de excluir comentário (procurar por `role === "admin"` perto do bloco de comentários) e ampliar para incluir técnico:

```tsx
const canModerateComments = user?.role === "admin" || user?.role === "technician";
// ...
{(canModerateComments || comment.author_id === user?.id) && (
  /* botão de excluir */
)}
```

Ler o trecho antes de editar — o nome da variável de usuário e a estrutura do bloco precisam casar com o que já existe no arquivo.

- [ ] **Step 6: Verificar**

Run (em `frontend/`): `npm run build`
Expected: build limpo.

- [ ] **Step 7: Commit (pedir confirmação ao usuário antes)**

```bash
git add backend/app/routers/kb.py backend/tests/test_kb.py frontend/src/pages/kb/KBArticlePage.tsx
git commit -m "feat: permite que tecnico exclua comentarios na base de conhecimento"
```

---

## Task 4: Frente 2 — paleta de 15 cores na agenda

**Files:**
- Modify: `frontend/src/pages/calendar/CalendarPage.tsx:25-30,192-205,616-624`

- [ ] **Step 1: Definir a paleta**

Logo abaixo de `EVENT_TYPE_COLORS` em `frontend/src/pages/calendar/CalendarPage.tsx`:

```tsx
/** Cores disponíveis para eventos — as 5 primeiras são as cores padrão dos tipos. */
const EVENT_COLOR_PALETTE: { value: string; label: string }[] = [
  { value: "#6366f1", label: "Índigo" },
  { value: "#3b82f6", label: "Azul" },
  { value: "#10b981", label: "Verde" },
  { value: "#f59e0b", label: "Âmbar" },
  { value: "#ef4444", label: "Vermelho" },
  { value: "#8b5cf6", label: "Violeta" },
  { value: "#0ea5e9", label: "Azul-céu" },
  { value: "#06b6d4", label: "Ciano" },
  { value: "#14b8a6", label: "Turquesa" },
  { value: "#84cc16", label: "Lima" },
  { value: "#eab308", label: "Amarelo" },
  { value: "#f97316", label: "Laranja" },
  { value: "#ec4899", label: "Rosa" },
  { value: "#a855f7", label: "Púrpura" },
  { value: "#64748b", label: "Cinza" },
];
```

- [ ] **Step 2: Trocar o seletor de cor pela grade**

Substituir o bloco do campo "Cor" (por volta das linhas 192-205, que hoje tem `<input type="color">` e o texto com o código hex):

```tsx
<div className="space-y-1.5">
  <label className="text-xs font-medium text-slate-400">Cor</label>
  <div className="grid grid-cols-5 gap-2">
    {EVENT_COLOR_PALETTE.map((c) => (
      <button
        key={c.value}
        type="button"
        aria-label={c.label}
        aria-pressed={color === c.value}
        title={c.label}
        onClick={() => { setColor(c.value); setColorOverride(true); }}
        className={cn(
          "h-8 w-full rounded-md border transition-all cursor-pointer",
          color === c.value
            ? "border-white ring-2 ring-primary ring-offset-2 ring-offset-background-surface"
            : "border-transparent hover:scale-105",
        )}
        style={{ backgroundColor: c.value }}
      />
    ))}
  </div>
</div>
```

Se `cn` ainda não estiver importado no arquivo, importar de `../../lib/utils`.

- [ ] **Step 3: Remover a legenda do rodapé**

Apagar o bloco `{/* Legend */}` (por volta das linhas 616-624), inclusive a `<div>` que o envolve.

- [ ] **Step 4: Verificar visualmente**

Run (em `frontend/`): `npm run dev` e abrir `/agenda` como admin.
Conferir: a grade 5×3 aparece no modal "Novo evento"; clicar seleciona com anel; trocar o tipo do evento ainda muda a cor sugerida enquanto nenhuma cor foi escolhida à mão; a legenda sumiu do rodapé; salvar cria o evento com a cor certa.

- [ ] **Step 5: Verificar build e testes**

Run: `npm run build`, `npm test`
Expected: verdes.

- [ ] **Step 6: Commit (pedir confirmação ao usuário antes)**

```bash
git add frontend/src/pages/calendar/CalendarPage.tsx
git commit -m "feat: substitui seletor de cor livre por paleta fixa na agenda e remove a legenda"
```

---

## Task 5: Frente 6 — CNPJ e CEP obrigatórios no cadastro do cliente

**Files:**
- Create: `frontend/src/lib/documents.ts` (validação de CNPJ e CEP)
- Create: `frontend/src/test/lib/documents.test.ts`
- Modify: `frontend/src/pages/onboarding/OnboardingPage.tsx`
- Modify: `frontend/src/pages/profile/ProfilePage.tsx` (aviso para cadastro incompleto)
- Modify: `backend/app/schemas/user.py:69-75`
- Test: `backend/tests/test_users.py`

- [ ] **Step 1: Escrever o teste da validação de CNPJ**

Criar `frontend/src/test/lib/documents.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { isValidCnpj, isValidCep } from "../../lib/documents";

describe("isValidCnpj", () => {
  it("aceita um CNPJ válido com máscara", () => {
    expect(isValidCnpj("08.857.492/0001-48")).toBe(true);
  });

  it("aceita um CNPJ válido sem máscara", () => {
    expect(isValidCnpj("08857492000148")).toBe(true);
  });

  it("rejeita dígito verificador errado", () => {
    expect(isValidCnpj("08857492000149")).toBe(false);
  });

  it("rejeita todos os dígitos iguais", () => {
    expect(isValidCnpj("11111111111111")).toBe(false);
  });

  it("rejeita quantidade de dígitos errada", () => {
    expect(isValidCnpj("123")).toBe(false);
  });
});

describe("isValidCep", () => {
  it("aceita CEP com e sem máscara", () => {
    expect(isValidCep("50070-000")).toBe(true);
    expect(isValidCep("50070000")).toBe(true);
  });

  it("rejeita CEP incompleto", () => {
    expect(isValidCep("5007")).toBe(false);
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run (em `frontend/`): `npx vitest run src/test/lib/documents.test.ts`
Expected: FAIL — módulo não existe.

- [ ] **Step 3: Implementar as validações**

Criar `frontend/src/lib/documents.ts`:

```ts
/** Validação de documentos brasileiros usados no cadastro de cliente. */

export function onlyDigits(value: string): string {
  return value.replace(/\D/g, "");
}

/** Valida CNPJ pelos dois dígitos verificadores (aceita com ou sem máscara). */
export function isValidCnpj(value: string): boolean {
  const digits = onlyDigits(value);
  if (digits.length !== 14) return false;
  if (/^(\d)\1{13}$/.test(digits)) return false;

  const calcCheckDigit = (length: number): number => {
    let weight = length - 7;
    let sum = 0;
    for (let i = 0; i < length; i++) {
      sum += Number(digits[i]) * weight;
      weight -= 1;
      if (weight < 2) weight = 9;
    }
    const rest = sum % 11;
    return rest < 2 ? 0 : 11 - rest;
  };

  return (
    calcCheckDigit(12) === Number(digits[12]) &&
    calcCheckDigit(13) === Number(digits[13])
  );
}

/** Valida CEP: exatamente 8 dígitos (aceita com ou sem máscara). */
export function isValidCep(value: string): boolean {
  return onlyDigits(value).length === 8;
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `npx vitest run src/test/lib/documents.test.ts`
Expected: PASS (7 testes).

- [ ] **Step 5: Tornar os campos obrigatórios no onboarding**

Em `frontend/src/pages/onboarding/OnboardingPage.tsx`:

- Marcar os labels de CNPJ e CEP como obrigatórios (mesmo padrão visual dos demais campos obrigatórios da tela).
- Antes de enviar, validar com `isValidCnpj` e `isValidCep`, exibindo a mensagem no campo:
  - CNPJ vazio → "Informe o CNPJ da empresa."
  - CNPJ inválido → "CNPJ inválido. Confira os números digitados."
  - CEP vazio → "Informe o CEP da empresa."
  - CEP inválido → "CEP inválido. Deve ter 8 dígitos."
- O botão de concluir fica desabilitado enquanto qualquer um dos dois estiver vazio.
- A busca automática por CNPJ/CEP que já existe continua igual; falha na consulta externa não bloqueia o preenchimento manual.

Ler o arquivo inteiro antes de editar: ele tem estado próprio (`cnpj`, `cep`, `error`) e handlers de `onBlur` que já fazem lookup.

- [ ] **Step 6: Exigir no backend**

`backend/app/schemas/user.py`, em `OnboardingUpdate`:

```python
class OnboardingUpdate(AppBaseModel):
    company_name: str = Field(..., min_length=1, max_length=255)
    cnpj: str = Field(..., max_length=18)
    company_cep: str = Field(..., max_length=9)
    company_address: str | None = Field(default=None, max_length=255)
    company_city: str | None = Field(default=None, max_length=100)
    company_state: str | None = Field(default=None, max_length=2)

    @field_validator("cnpj")
    @classmethod
    def cnpj_must_have_14_digits(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v)
        if len(digits) != 14:
            raise ValueError("CNPJ deve conter 14 dígitos.")
        return digits

    @field_validator("company_cep")
    @classmethod
    def cep_must_have_8_digits(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v)
        if len(digits) != 8:
            raise ValueError("CEP deve conter 8 dígitos.")
        return digits
```

Importar `re` e `field_validator` no topo do arquivo se ainda não estiverem lá.

- [ ] **Step 7: Teste do backend**

Em `backend/tests/test_users.py`, no estilo dos testes existentes:

```python
async def test_onboarding_sem_cnpj_retorna_422(...):
    # body sem a chave "cnpj"
    assert response.status_code == 422


async def test_onboarding_com_cnpj_curto_retorna_422(...):
    # body com cnpj="123"
    assert response.status_code == 422
```

Run: `.venv\Scripts\python.exe -m pytest tests/test_users.py --no-cov -v`
Expected: PASS. Se algum teste antigo enviava onboarding sem CNPJ/CEP, atualizá-lo para o novo contrato.

- [ ] **Step 8: Aviso no perfil para cadastro incompleto**

Em `frontend/src/pages/profile/ProfilePage.tsx`, quando `profile.cnpj` ou `profile.company_cep` estiverem vazios e o usuário for cliente, mostrar um `Alert` acima dos dados da empresa:

```tsx
{user?.role === "client" && (!profile.cnpj || !profile.company_cep) && (
  <Alert variant="warning">
    Complete o cadastro da sua empresa: CNPJ e CEP são obrigatórios.
  </Alert>
)}
```

Conferir a API do componente `Alert` em `frontend/src/components/ui/Alert.tsx` antes de usar (nome das props e variantes disponíveis). O salvamento do perfil aplica as mesmas validações de formato quando o campo for preenchido, mas não bloqueia quem deixar em branco.

- [ ] **Step 9: Verificar**

Run (em `frontend/`): `npm test`, `npm run lint`, `npm run build`
Run (em `backend/`): `.venv\Scripts\python.exe -m pytest --no-cov -q`
Expected: todos verdes.

- [ ] **Step 10: Commit (pedir confirmação ao usuário antes)**

```bash
git add frontend/src backend/app/schemas/user.py backend/tests/test_users.py
git commit -m "feat: torna CNPJ e CEP obrigatorios no cadastro do cliente"
```

---

## Task 6: Frente 4 — mensagens de erro descritivas

Três partes: robustez do handler no frontend, mensagens explicativas no backend, e a causa raiz do erro de reatribuição.

**Files:**
- Modify: `frontend/src/lib/apiError.ts`
- Create: `frontend/src/test/lib/apiError.test.ts`
- Modify: `backend/app/routers/tickets.py` (mensagens + validações do `assign_ticket`)
- Modify: outros routers com `detail` genérico
- Modify: `frontend/src/pages/tickets/TicketDetailPage.tsx:794` e demais toasts de erro
- Test: `backend/tests/test_tickets.py`

- [ ] **Step 1: Teste do handler de erro**

Criar `frontend/src/test/lib/apiError.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { getApiError, getApiErrorParts } from "../../lib/apiError";

describe("getApiError", () => {
  it("usa o detail em string", () => {
    const err = { response: { status: 403, data: { detail: "Motivo específico." } } };
    expect(getApiError(err)).toBe("Motivo específico.");
  });

  it("extrai a mensagem de erro de validação do FastAPI", () => {
    const err = {
      response: {
        status: 422,
        data: { detail: [{ loc: ["body", "cnpj"], msg: "CNPJ deve conter 14 dígitos.", type: "value_error" }] },
      },
    };
    expect(getApiError(err)).toContain("CNPJ deve conter 14 dígitos.");
  });

  it("avisa quando não houve resposta do servidor", () => {
    const err = { request: {}, message: "Network Error" };
    expect(getApiError(err)).toContain("conexão");
  });

  it("usa mensagem padrão para 500 sem detail", () => {
    const err = { response: { status: 500, data: {} } };
    expect(getApiError(err)).toContain("servidor");
  });
});

describe("getApiErrorParts", () => {
  it("separa título e descrição", () => {
    const err = { response: { status: 403, data: { detail: "Apenas o técnico responsável pode alterar." } } };
    const { title, description } = getApiErrorParts(err, "Não foi possível atribuir o ticket.");
    expect(title).toBe("Não foi possível atribuir o ticket.");
    expect(description).toBe("Apenas o técnico responsável pode alterar.");
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run (em `frontend/`): `npx vitest run src/test/lib/apiError.test.ts`
Expected: FAIL — `getApiErrorParts` não existe e os casos novos não são tratados.

- [ ] **Step 3: Reescrever `apiError.ts`**

```ts
import type { AxiosError } from "axios";

interface ValidationItem { loc?: (string | number)[]; msg?: string }

const STATUS_FALLBACKS: Record<number, string> = {
  400: "Os dados enviados não são válidos. Revise o formulário e tente de novo.",
  401: "Sua sessão expirou. Entre novamente para continuar.",
  403: "Você não tem permissão para realizar esta ação.",
  404: "O item que você tentou acessar não foi encontrado. Ele pode ter sido excluído.",
  409: "Esta ação conflita com o estado atual do registro. Atualize a página e tente de novo.",
  413: "O arquivo enviado é grande demais.",
  422: "Alguns campos não foram preenchidos corretamente.",
  429: "Muitas tentativas em pouco tempo. Aguarde alguns instantes.",
  500: "Erro interno no servidor. Tente novamente em instantes.",
  502: "O servidor está indisponível no momento. Tente novamente em instantes.",
  503: "O servidor está indisponível no momento. Tente novamente em instantes.",
};

/** Traduções de mensagens técnicas que ainda chegam em inglês do backend. */
const TRANSLATIONS: Record<string, string> = {
  "Ticket not found": "Ticket não encontrado. Ele pode ter sido excluído.",
  "Access denied": "Você não tem permissão para realizar esta ação.",
  "Assignee not found": "O técnico selecionado não existe mais no sistema.",
  "User not found": "Usuário não encontrado.",
  "Comment not found": "Comentário não encontrado.",
  "Email already registered": "Este e-mail já está cadastrado.",
  "Invalid credentials": "E-mail ou senha incorretos.",
  "Only admins can change roles": "Apenas administradores podem alterar o tipo de usuário.",
};

function describeError(err: unknown): string | null {
  const axiosErr = err as AxiosError<{ detail?: string | ValidationItem[] }>;

  // Sem resposta: rede caiu, servidor fora do ar ou timeout
  if (axiosErr?.request && !axiosErr?.response) {
    return "Não foi possível falar com o servidor. Verifique sua conexão e tente de novo.";
  }

  const detail = axiosErr?.response?.data?.detail;

  if (typeof detail === "string" && detail.trim()) {
    return TRANSLATIONS[detail] ?? detail;
  }

  // Erro de validação do FastAPI: detail vem como lista de objetos
  if (Array.isArray(detail) && detail.length > 0) {
    const messages = detail
      .map((item) => item?.msg)
      .filter((msg): msg is string => Boolean(msg));
    if (messages.length > 0) return messages.join(" ");
  }

  const status = axiosErr?.response?.status;
  if (status && STATUS_FALLBACKS[status]) return STATUS_FALLBACKS[status];

  return null;
}

/** Mensagem única, legível, para o erro da API. */
export function getApiError(err: unknown, fallback = "Ocorreu um erro inesperado."): string {
  return describeError(err) ?? fallback;
}

/**
 * Título curto + descrição do motivo, para toasts com duas linhas.
 * O título é o texto da ação que falhou; a descrição explica o porquê.
 */
export function getApiErrorParts(
  err: unknown,
  fallback = "Ocorreu um erro inesperado.",
): { title: string; description?: string } {
  const description = describeError(err);
  return description ? { title: fallback, description } : { title: fallback };
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `npx vitest run src/test/lib/apiError.test.ts`
Expected: PASS.

- [ ] **Step 5: Reproduzir o erro de reatribuição antes de corrigir**

Antes de mudar `assign_ticket`, confirmar a causa. Ler `backend/app/routers/tickets.py:653-699` e verificar cada hipótese:

1. atribuir a um usuário com papel `client` — hoje não há validação de papel;
2. atribuir em ticket `closed`/`cancelled` — hoje não há bloqueio, e `_auto_transition` pode se comportar de forma inesperada;
3. falha em `notify` (Redis/e-mail indisponível) subindo 500 sem `detail`.

Escrever um teste que reproduza o caso confirmado em `backend/tests/test_tickets.py` e vê-lo falhar. Não corrigir por palpite — se nenhuma hipótese se confirmar, investigar o log real antes de seguir (usar a skill superpowers:systematic-debugging).

- [ ] **Step 6: Corrigir `assign_ticket` com mensagens explicativas**

Depois do `get_or_404`, dentro de `assign_ticket`:

```python
    if ticket.status in (TicketStatus.closed, TicketStatus.cancelled):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Este ticket está {'fechado' if ticket.status == TicketStatus.closed else 'cancelado'} "
                "e não pode ser reatribuído. Reabra o ticket antes de atribuí-lo a outro técnico."
            ),
        )
```

E na resolução do novo responsável:

```python
        if not new_assignee_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="O técnico selecionado não existe mais no sistema.",
            )
        if new_assignee_user.role not in (UserRole.admin, UserRole.technician):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Tickets só podem ser atribuídos a técnicos ou administradores.",
            )
        if new_assignee_user.status != UserStatus.active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Este usuário está inativo e não pode receber tickets.",
            )
```

Importar `UserStatus` no topo do arquivo se necessário.

- [ ] **Step 7: Rodar os testes de ticket**

Run (em `backend/`): `.venv\Scripts\python.exe -m pytest tests/test_tickets.py --no-cov -v`
Expected: PASS, incluindo o teste de reprodução do Step 5.

- [ ] **Step 8: Substituir os `detail` genéricos nos demais routers**

Varrer `backend/app/routers/*.py` procurando `detail="` com texto em inglês ou genérico demais e trocar por mensagem em português que diga o motivo. Manter curto e sem jargão. Exemplos do padrão desejado:

| Antes | Depois |
|---|---|
| `"Access denied"` | `"Você não tem permissão para acessar este ticket."` |
| `"Ticket not found"` | `"Ticket não encontrado. Ele pode ter sido excluído."` |
| `"Tag name already exists"` | `"Já existe uma etiqueta com esse nome."` |

Ao mudar uma mensagem, rodar os testes daquele router — vários asserts checam o texto do `detail`.

- [ ] **Step 9: Usar título + descrição nos toasts principais**

Em `frontend/src/pages/tickets/TicketDetailPage.tsx:794` e nos demais `toast.error(getApiError(...))` de ações críticas (atribuir, mudar status, resolver, upload):

```tsx
const { title, description } = getApiErrorParts(err, "Não foi possível atribuir o ticket.");
toast.error(title, { description });
```

- [ ] **Step 10: Verificar**

Run (em `frontend/`): `npm test`, `npm run lint`, `npm run build`
Run (em `backend/`): `.venv\Scripts\python.exe -m pytest --no-cov -q`
Expected: todos verdes.

- [ ] **Step 11: Commit (pedir confirmação ao usuário antes)**

```bash
git add frontend/src backend/app backend/tests
git commit -m "feat: mensagens de erro explicativas e correcao da validacao de reatribuicao"
```

---

## Task 7: Frente 5 — respostas rápidas no chat (backend)

**Files:**
- Modify: `backend/app/models/models.py` (model `QuickReply`)
- Create: `backend/alembic/versions/o5j6k7l8m9n0_add_quick_replies.py`
- Create: `backend/app/schemas/quick_reply.py`
- Create: `backend/app/routers/quick_replies.py`
- Modify: `backend/app/main.py` (registrar o router)
- Test: `backend/tests/test_quick_replies.py` (criar)

- [ ] **Step 1: Escrever os testes do CRUD**

Criar `backend/tests/test_quick_replies.py` seguindo o estilo de `tests/test_kb.py` (DB e Redis mockados). Casos:

```python
async def test_tecnico_lista_respostas_rapidas(...):
    assert response.status_code == 200

async def test_cliente_nao_acessa_respostas_rapidas(...):
    assert response.status_code == 403

async def test_criar_resposta_rapida(...):
    assert response.status_code == 201
    assert response.json()["shortcut"] == "bomdia"

async def test_atalho_duplicado_retorna_409(...):
    assert response.status_code == 409
    assert "atalho" in response.json()["detail"].lower()

async def test_excluir_resposta_rapida(...):
    assert response.status_code == 204
```

- [ ] **Step 2: Rodar e ver falhar**

Run (em `backend/`): `.venv\Scripts\python.exe -m pytest tests/test_quick_replies.py --no-cov -v`
Expected: FAIL — rotas não existem (404).

- [ ] **Step 3: Criar o model**

Em `backend/app/models/models.py`, após o model `Tag`:

```python
class QuickReply(Base):
    """Mensagens prontas usadas pelos técnicos no chat dos tickets"""

    __tablename__ = "quick_replies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shortcut: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 4: Criar os schemas**

Criar `backend/app/schemas/quick_reply.py`:

```python
import re
import uuid
from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.base import AppBaseModel

_SHORTCUT_RE = re.compile(r"^[a-z0-9_-]+$")


class QuickReplyCreate(AppBaseModel):
    shortcut: str = Field(..., min_length=2, max_length=50)
    title: str = Field(..., min_length=1, max_length=120)
    content: str = Field(..., min_length=1, max_length=4000)
    is_active: bool = True

    @field_validator("shortcut")
    @classmethod
    def shortcut_format(cls, v: str) -> str:
        normalized = v.strip().lower().lstrip("/")
        if not _SHORTCUT_RE.match(normalized):
            raise ValueError(
                "O atalho deve conter apenas letras minúsculas, números, hífen ou underline."
            )
        return normalized


class QuickReplyUpdate(AppBaseModel):
    shortcut: str | None = Field(default=None, min_length=2, max_length=50)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    content: str | None = Field(default=None, min_length=1, max_length=4000)
    is_active: bool | None = None

    @field_validator("shortcut")
    @classmethod
    def shortcut_format(cls, v: str | None) -> str | None:
        if v is None:
            return None
        normalized = v.strip().lower().lstrip("/")
        if not _SHORTCUT_RE.match(normalized):
            raise ValueError(
                "O atalho deve conter apenas letras minúsculas, números, hífen ou underline."
            )
        return normalized


class QuickReplyResponse(AppBaseModel):
    id: uuid.UUID
    shortcut: str
    title: str
    content: str
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class QuickReplyListResponse(AppBaseModel):
    items: list[QuickReplyResponse]
    total: int
```

Conferir em `backend/app/schemas/base.py` se `AppBaseModel` já traz `from_attributes` — os demais schemas do projeto dependem disso para o `model_validate`.

- [ ] **Step 5: Criar o router**

Criar `backend/app/routers/quick_replies.py` seguindo `tags.py`:

```python
"""
CRUD de respostas rápidas usadas no chat dos tickets.

Permissões:
  GET    /quick-replies       — admin | technician
  POST   /quick-replies       — admin | technician
  PATCH  /quick-replies/{id}  — admin | technician
  DELETE /quick-replies/{id}  — admin | technician
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import authorize
from app.models.models import QuickReply, User, UserRole
from app.schemas.quick_reply import (
    QuickReplyCreate,
    QuickReplyListResponse,
    QuickReplyResponse,
    QuickReplyUpdate,
)

router = APIRouter(tags=["Quick Replies"])

_STAFF = authorize(UserRole.admin, UserRole.technician)


@router.get("/quick-replies", response_model=QuickReplyListResponse)
async def list_quick_replies(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(_STAFF)],
) -> QuickReplyListResponse:
    rows = await db.execute(select(QuickReply).order_by(QuickReply.shortcut))
    items = rows.scalars().all()
    return QuickReplyListResponse(
        items=[QuickReplyResponse.model_validate(q) for q in items], total=len(items)
    )


@router.post(
    "/quick-replies", response_model=QuickReplyResponse, status_code=status.HTTP_201_CREATED
)
async def create_quick_reply(
    body: QuickReplyCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(_STAFF)],
) -> QuickReplyResponse:
    existing = await db.execute(select(QuickReply).where(QuickReply.shortcut == body.shortcut))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe uma resposta rápida com o atalho /{body.shortcut}.",
        )

    reply = QuickReply(
        id=uuid.uuid4(),
        shortcut=body.shortcut,
        title=body.title,
        content=body.content,
        is_active=body.is_active,
        created_by=actor.id,
    )
    db.add(reply)
    await db.commit()
    await db.refresh(reply)
    return QuickReplyResponse.model_validate(reply)


@router.patch("/quick-replies/{reply_id}", response_model=QuickReplyResponse)
async def update_quick_reply(
    reply_id: uuid.UUID,
    body: QuickReplyUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(_STAFF)],
) -> QuickReplyResponse:
    result = await db.execute(select(QuickReply).where(QuickReply.id == reply_id))
    reply = result.scalar_one_or_none()
    if not reply:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resposta rápida não encontrada."
        )

    if body.shortcut is not None and body.shortcut != reply.shortcut:
        conflict = await db.execute(
            select(QuickReply).where(QuickReply.shortcut == body.shortcut, QuickReply.id != reply_id)
        )
        if conflict.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Já existe uma resposta rápida com o atalho /{body.shortcut}.",
            )
        reply.shortcut = body.shortcut

    if body.title is not None:
        reply.title = body.title
    if body.content is not None:
        reply.content = body.content
    if body.is_active is not None:
        reply.is_active = body.is_active

    reply.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(reply)
    return QuickReplyResponse.model_validate(reply)


@router.delete("/quick-replies/{reply_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quick_reply(
    reply_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(_STAFF)],
) -> None:
    result = await db.execute(select(QuickReply).where(QuickReply.id == reply_id))
    reply = result.scalar_one_or_none()
    if not reply:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resposta rápida não encontrada."
        )

    await db.delete(reply)
    await db.commit()
```

- [ ] **Step 6: Registrar o router**

Em `backend/app/main.py`, adicionar `quick_replies` ao import de `app.routers` e a linha:

```python
app.include_router(quick_replies.router, prefix=settings.api_prefix)
```

- [ ] **Step 7: Rodar os testes e ver passar**

Run: `.venv\Scripts\python.exe -m pytest tests/test_quick_replies.py --no-cov -v`
Expected: PASS.

- [ ] **Step 8: Criar a migration**

Criar `backend/alembic/versions/o5j6k7l8m9n0_add_quick_replies.py`, seguindo o formato de `n4i5j6k7l8m9_add_calendar_events.py` (ler esse arquivo antes para copiar o estilo de `revision`/`down_revision`):

```python
"""add quick_replies

Revision ID: o5j6k7l8m9n0
Revises: n4i5j6k7l8m9
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "o5j6k7l8m9n0"
down_revision = "n4i5j6k7l8m9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quick_replies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("shortcut", sa.String(50), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_quick_replies_shortcut", "quick_replies", ["shortcut"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_quick_replies_shortcut", table_name="quick_replies")
    op.drop_table("quick_replies")
```

Confirmar que `down_revision` aponta para a última migration existente de fato.

- [ ] **Step 9: Commit (pedir confirmação ao usuário antes)**

```bash
git add backend/app backend/alembic backend/tests/test_quick_replies.py
git commit -m "feat: API de respostas rapidas para o chat de tickets"
```

---

## Task 8: Frente 5 — respostas rápidas no chat e página de gestão (frontend)

**Files:**
- Create: `frontend/src/services/quickReplyService.ts`
- Create: `frontend/src/components/chat/QuickReplyPicker.tsx`
- Modify: `frontend/src/components/chat/ChatPanel.tsx`
- Create: `frontend/src/pages/settings/QuickRepliesPage.tsx`
- Modify: `frontend/src/App.tsx` (rota)
- Modify: `frontend/src/components/layout/Sidebar.tsx` (item de menu)
- Test: `frontend/src/test/services/quickReplyService.test.ts` (criar)

- [ ] **Step 1: Teste do serviço**

Criar `frontend/src/test/services/quickReplyService.test.ts` no mesmo formato de `src/test/services/tagService`-equivalentes já existentes (ver `src/test/services/kbService.test.ts` para o padrão de mock do axios). Casos: listar, criar, atualizar e excluir chamam a URL certa com o método certo.

- [ ] **Step 2: Rodar e ver falhar**

Run (em `frontend/`): `npx vitest run src/test/services/quickReplyService.test.ts`
Expected: FAIL — módulo não existe.

- [ ] **Step 3: Criar o serviço**

Criar `frontend/src/services/quickReplyService.ts`:

```ts
import { api } from "./api";

export interface QuickReply {
  id: string;
  shortcut: string;
  title: string;
  content: string;
  is_active: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface QuickReplyPayload {
  shortcut: string;
  title: string;
  content: string;
  is_active?: boolean;
}

export async function listQuickReplies(): Promise<QuickReply[]> {
  const { data } = await api.get<{ items: QuickReply[]; total: number }>("/quick-replies");
  return data.items;
}

export async function createQuickReply(payload: QuickReplyPayload): Promise<QuickReply> {
  const { data } = await api.post<QuickReply>("/quick-replies", payload);
  return data;
}

export async function updateQuickReply(
  id: string,
  payload: Partial<QuickReplyPayload>,
): Promise<QuickReply> {
  const { data } = await api.patch<QuickReply>(`/quick-replies/${id}`, payload);
  return data;
}

export async function deleteQuickReply(id: string): Promise<void> {
  await api.delete(`/quick-replies/${id}`);
}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `npx vitest run src/test/services/quickReplyService.test.ts`
Expected: PASS.

- [ ] **Step 5: Criar o componente do seletor**

Criar `frontend/src/components/chat/QuickReplyPicker.tsx` — painel que aparece acima do input, controlado pelo `ChatPanel`:

```tsx
import { useEffect, useRef } from "react";
import { cn } from "../../lib/utils";
import type { QuickReply } from "../../services/quickReplyService";

interface QuickReplyPickerProps {
  replies: QuickReply[];
  activeIndex: number;
  onSelect: (reply: QuickReply) => void;
  onHover: (index: number) => void;
}

export function QuickReplyPicker({
  replies,
  activeIndex,
  onSelect,
  onHover,
}: QuickReplyPickerProps) {
  const listRef = useRef<HTMLDivElement>(null);

  // Mantém o item ativo visível ao navegar pelo teclado
  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-index="${activeIndex}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  if (replies.length === 0) return null;

  return (
    <div
      ref={listRef}
      role="listbox"
      aria-label="Respostas rápidas"
      className="absolute bottom-full left-0 right-0 mb-2 max-h-64 overflow-y-auto rounded-xl border border-border bg-background-surface shadow-lg z-30"
    >
      <p className="px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        Respostas rápidas
      </p>
      {replies.map((reply, index) => (
        <button
          key={reply.id}
          type="button"
          role="option"
          aria-selected={index === activeIndex}
          data-index={index}
          onMouseEnter={() => onHover(index)}
          onClick={() => onSelect(reply)}
          className={cn(
            "w-full px-3 py-2 text-left transition-colors",
            index === activeIndex ? "bg-primary/10" : "hover:bg-background-elevated",
          )}
        >
          <span className="block text-sm font-medium text-slate-100">
            /{reply.shortcut}
          </span>
          <span className="block text-xs text-slate-400 line-clamp-2">{reply.content}</span>
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 6: Integrar no ChatPanel**

Em `frontend/src/components/chat/ChatPanel.tsx`:

1. Carregar as respostas ativas ao montar, apenas para admin e técnico:

```tsx
const [quickReplies, setQuickReplies] = useState<QuickReply[]>([]);
const isStaff = user?.role === "admin" || user?.role === "technician";

useEffect(() => {
  if (!isStaff) return;
  listQuickReplies()
    .then((items) => setQuickReplies(items.filter((r) => r.is_active)))
    .catch(() => setQuickReplies([]));
}, [isStaff]);
```

2. Derivar a lista filtrada e a visibilidade do painel a partir do texto digitado:

```tsx
const quickReplyQuery = isStaff && input.startsWith("/") ? input.slice(1).toLowerCase() : null;
const filteredReplies =
  quickReplyQuery === null
    ? []
    : quickReplies.filter(
        (r) =>
          r.shortcut.toLowerCase().includes(quickReplyQuery) ||
          r.title.toLowerCase().includes(quickReplyQuery),
      );
const pickerOpen = quickReplyQuery !== null && filteredReplies.length > 0;
```

3. Estado `activeReply` (índice) resetado para 0 sempre que `input` mudar.

4. Em `handleKeyDown`, tratar o painel **antes** da lógica de envio, para que `Enter` selecione em vez de mandar mensagem:

```tsx
if (pickerOpen) {
  if (e.key === "ArrowDown") {
    e.preventDefault();
    setActiveReply((i) => (i + 1) % filteredReplies.length);
    return;
  }
  if (e.key === "ArrowUp") {
    e.preventDefault();
    setActiveReply((i) => (i - 1 + filteredReplies.length) % filteredReplies.length);
    return;
  }
  if (e.key === "Enter" || e.key === "Tab") {
    e.preventDefault();
    applyQuickReply(filteredReplies[activeReply]);
    return;
  }
  if (e.key === "Escape") {
    e.preventDefault();
    setInput("");
    return;
  }
}
```

5. Função de aplicar:

```tsx
function applyQuickReply(reply: QuickReply) {
  setInput(reply.content);
  setActiveReply(0);
  inputRef.current?.focus();
}
```

6. Renderizar `<QuickReplyPicker />` dentro do container do input, que precisa ter `className="relative"` para o posicionamento absoluto do painel funcionar.

Ler o arquivo inteiro antes de editar: `handleKeyDown` e a área do input já existem e têm outras responsabilidades (sugestão de IA, melhorar texto, resumo).

- [ ] **Step 7: Criar a página de gestão**

Criar `frontend/src/pages/settings/QuickRepliesPage.tsx` seguindo o padrão visual de `frontend/src/pages/settings/SettingsPage.tsx` (a página de Etiquetas): cabeçalho com título e botão "Nova resposta", tabela com atalho, título, prévia do conteúdo e status, modal de criar/editar e confirmação de exclusão. Usar os componentes de `frontend/src/components/ui` (`Table`, `Modal`, `Button`, `Input`, `Textarea`, `Badge`) e `toast` do `sonner` para o feedback, com `getApiErrorParts` no erro.

Campos do formulário: atalho (obrigatório, minúsculo, sem `/` e sem espaço), título (obrigatório), conteúdo (obrigatório, textarea), ativo (checkbox).

- [ ] **Step 8: Registrar a rota**

Em `frontend/src/App.tsx`:

```tsx
const QuickRepliesPage = lazy(() => import("./pages/settings/QuickRepliesPage"));
```

E dentro do bloco `<RoleGuard roles={["admin", "technician"]}>` que já cobre `/users`, `/products`, `/etiquetas` e `/grupos`:

```tsx
<Route path="/respostas-rapidas" element={<QuickRepliesPage />} />
```

- [ ] **Step 9: Adicionar ao menu**

Em `frontend/src/components/layout/Sidebar.tsx`, no grupo "Gestão" do `NAV_GROUPS`:

```tsx
{ label: "Respostas Rápidas", path: "/respostas-rapidas", icon: <IconChat />, roles: ["admin", "technician"] },
```

Criar o ícone `IconChat` junto dos demais ícones do arquivo, no mesmo formato (svg 24×24, `strokeWidth={1.75}`, `className="w-5 h-5 shrink-0"`):

```tsx
function IconChat() {
  return (
    <svg className="w-5 h-5 shrink-0" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.86 9.86 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
    </svg>
  );
}
```

- [ ] **Step 10: Testar manualmente ponta a ponta**

Run (em `frontend/`): `npm run dev`, com o backend rodando.

Conferir:
1. "Respostas Rápidas" aparece no menu para admin e técnico, e **não** aparece para cliente;
2. criar, editar e excluir funcionam, e atalho duplicado mostra a mensagem de conflito;
3. no chat de um ticket, digitar `/` abre o painel; continuar digitando filtra; ↑/↓ navegam; Enter insere o texto sem enviar a mensagem; Esc fecha;
4. logado como cliente, digitar `/` no chat não abre nada.

- [ ] **Step 11: Verificar**

Run: `npm test`, `npm run lint`, `npm run build`
Expected: todos verdes.

- [ ] **Step 12: Commit (pedir confirmação ao usuário antes)**

```bash
git add frontend/src
git commit -m "feat: respostas rapidas no chat com atalho / e pagina de gestao"
```

---

## Task 9: Fechamento do pacote

- [ ] **Step 1: Atualizar o changelog**

Em `frontend/src/data/changelog.ts`, subir `APP_VERSION` para `"v1.1.0"` e adicionar a entrada no topo do array `CHANGELOG`, com a data do dia e uma linha por frente entregue, usando os tipos `novidade`, `melhoria` e `corrigido` já existentes.

- [ ] **Step 2: Rodar a verificação completa**

Run (em `frontend/`): `npm test`, `npm run lint`, `npm run build`
Run (em `backend/`): `.venv\Scripts\python.exe -m pytest -q` (agora **com** cobertura, para confirmar o mínimo de 80%)
Expected: todos verdes. Se a cobertura cair abaixo de 80%, escrever os testes que faltam no código novo.

- [ ] **Step 3: Entregar o resumo ao usuário**

Listar: o que foi feito por frente, a lista das correções de ortografia, e o que ficou de fora (variáveis dinâmicas nas respostas rápidas, anexos, respostas pessoais por técnico).

- [ ] **Step 4: Commit e merge (pedir confirmação ao usuário antes)**

Perguntar ao usuário se quer o merge de `ajustes/feedback-cliente-v1.0.0` na `main` ou se prefere abrir PR.

**Atenção:** a Frente 5 cria uma tabela nova. Antes do deploy, rodar `alembic upgrade head` no ambiente de produção.
