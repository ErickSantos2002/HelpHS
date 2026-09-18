import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const navegar = vi.fn();
const sair = vi.fn();
const concluirOnboarding = vi.fn();

vi.mock("react-router-dom", () => ({ useNavigate: () => navegar }));
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ logout: sair, markOnboardingComplete: concluirOnboarding }),
}));
vi.mock("../../services/userService", () => ({ completeOnboarding: vi.fn() }));
vi.mock("../../services/equipmentService", () => ({
  createMyEquipment: vi.fn(),
  getMyEquipment: vi.fn(),
  lookupCnpj: vi.fn(),
  lookupCep: vi.fn(),
}));
vi.mock("../../services/api", () => ({ api: { get: vi.fn() } }));

import OnboardingPage from "../../pages/onboarding/OnboardingPage";
import * as equipmentService from "../../services/equipmentService";
import * as userService from "../../services/userService";
import { api } from "../../services/api";
import { AA, contraste } from "../helpers/contraste";

/**
 * O passo a passo de primeiro acesso, e o que a Fase 16 mexeu aqui.
 *
 * **28** classes de paleta crua, **zero** `<svg>` — e as **três** bolas do
 * indicador de passo concentravam os três pares que a catraca cobrava:
 *
 * | bola | par antigo | contraste |
 * |---|---|---|
 * | passo cumprido | `bg-primary` + `text-white` | 3,83:1 |
 * | passo futuro (claro) | `bg-surface-elevated` + `text-slate-500` | 4,34:1 |
 * | passo futuro (escuro) | idem | 2,85:1 |
 *
 * Nenhum dos três é observável em happy-dom, que não aplica CSS. Por isso os
 * casos de conteúdo prendem outra coisa: que o passo corrente continua dito em
 * **texto** ("Passo 1 de 3 — Empresa"), porque a bola colorida sozinha não
 * satisfaz 1.4.1, e que o asterisco de obrigatório — que era um `<span>`
 * vermelho sem ligação nenhuma com o campo — continua legível depois de ter
 * virado parte do rótulo.
 */
const FONTE = readFileSync(
  resolve(process.cwd(), "src/pages/onboarding/OnboardingPage.tsx"),
  "utf-8",
);
const CODIGO = FONTE.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");

/** Um CNPJ com dígitos verificadores válidos — o mesmo do teste de `documents`. */
const CNPJ_VALIDO = "08857492000148";

async function preencherEmpresa(cnpj = CNPJ_VALIDO) {
  await userEvent.type(screen.getByPlaceholderText("00.000.000/0000-00"), cnpj);
  await userEvent.type(
    screen.getByPlaceholderText("Razão social ou nome fantasia"),
    "Construtora Alfa",
  );
  await userEvent.type(screen.getByPlaceholderText("00000-000"), "50000000");
}

describe("OnboardingPage — o passo corrente", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(equipmentService.getMyEquipment).mockResolvedValue([]);
    vi.mocked(api.get).mockResolvedValue({ data: { items: [] } } as never);
  });

  it("diz em TEXTO qual passo é, e não só na cor da bola", () => {
    // 1.4.1: as três bolas se distinguem por cor e por preenchimento. A linha
    // de rodapé é o que informa quem não lê nenhum dos dois.
    render(<OnboardingPage />);
    expect(screen.getByText("Passo 1 de 3 — Empresa")).toBeTruthy();
  });

  it("o rodapé acompanha o avanço", async () => {
    vi.mocked(userService.completeOnboarding).mockResolvedValue({} as never);
    render(<OnboardingPage />);
    await preencherEmpresa();
    await userEvent.click(screen.getByRole("button", { name: "Continuar" }));
    expect(
      await screen.findByText("Passo 2 de 3 — Equipamentos"),
    ).toBeTruthy();
  });
});

describe("OnboardingPage — o passo da empresa", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(equipmentService.getMyEquipment).mockResolvedValue([]);
    vi.mocked(api.get).mockResolvedValue({ data: { items: [] } } as never);
  });

  it("marca CNPJ e CEP como obrigatórios no próprio rótulo", () => {
    // O asterisco era um `<span className="text-danger-400">` — vermelho
    // pintado como cor de texto, e um elemento sem ligação nenhuma com o
    // campo. Ele passou para dentro do rótulo.
    render(<OnboardingPage />);
    expect(screen.getByText("CNPJ *")).toBeTruthy();
    expect(screen.getByText("CEP *")).toBeTruthy();
  });

  it("recusa CNPJ com dígito verificador errado, e diz por quê", async () => {
    render(<OnboardingPage />);
    await preencherEmpresa("08857492000149");
    await userEvent.click(screen.getByRole("button", { name: "Continuar" }));
    expect(
      await screen.findByText("CNPJ inválido. Confira os números digitados."),
    ).toBeTruthy();
    expect(userService.completeOnboarding).not.toHaveBeenCalled();
  });

  it("recusa CNPJ em branco, e diz qual campo falta", async () => {
    // O campo "Nome da empresa" é um `Input` com `required`, então o navegador
    // barra o envio antes de o `handleSubmit` rodar — a mensagem
    // "Nome da empresa é obrigatório." é ramo morto hoje. Quem chega ao guarda
    // de JavaScript é o CNPJ, que não tem `required`.
    render(<OnboardingPage />);
    await userEvent.type(
      screen.getByPlaceholderText("Razão social ou nome fantasia"),
      "Construtora Alfa",
    );
    await userEvent.click(screen.getByRole("button", { name: "Continuar" }));
    expect(
      await screen.findByText("Informe o CNPJ da empresa."),
    ).toBeTruthy();
    expect(userService.completeOnboarding).not.toHaveBeenCalled();
  });

  it("envia o CNPJ e o CEP sem máscara", async () => {
    vi.mocked(userService.completeOnboarding).mockResolvedValue({} as never);
    render(<OnboardingPage />);
    await preencherEmpresa();
    await userEvent.click(screen.getByRole("button", { name: "Continuar" }));
    await waitFor(() =>
      expect(userService.completeOnboarding).toHaveBeenCalledWith(
        expect.objectContaining({ cnpj: CNPJ_VALIDO, company_cep: "50000000" }),
      ),
    );
  });

  it("a consulta de CNPJ preenche o nome sozinha", async () => {
    vi.mocked(equipmentService.lookupCnpj).mockResolvedValue({
      trade_name: "Alfa Engenharia",
      company_name: "Construtora Alfa LTDA",
      city: "Recife",
      state: "PE",
    } as never);
    render(<OnboardingPage />);
    const campo = screen.getByPlaceholderText("00.000.000/0000-00");
    await userEvent.type(campo, CNPJ_VALIDO);
    await userEvent.tab();
    await waitFor(() =>
      expect(
        (screen.getByPlaceholderText("Razão social ou nome fantasia") as HTMLInputElement)
          .value,
      ).toBe("Alfa Engenharia"),
    );
  });

  it("quando o CNPJ não é achado, avisa em vez de travar", async () => {
    vi.mocked(equipmentService.lookupCnpj).mockRejectedValue(new Error("404"));
    render(<OnboardingPage />);
    await userEvent.type(screen.getByPlaceholderText("00.000.000/0000-00"), CNPJ_VALIDO);
    await userEvent.tab();
    expect(
      await screen.findByText("CNPJ não encontrado. Preencha os dados manualmente."),
    ).toBeTruthy();
  });
});

describe("OnboardingPage — o passo dos equipamentos", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(userService.completeOnboarding).mockResolvedValue({} as never);
  });

  async function irParaEquipamentos() {
    render(<OnboardingPage />);
    await preencherEmpresa();
    await userEvent.click(screen.getByRole("button", { name: "Continuar" }));
    return screen.findByText("Seus equipamentos");
  }

  it("sem produto cadastrado, o botão diz que dá para pular", async () => {
    vi.mocked(equipmentService.getMyEquipment).mockResolvedValue([]);
    vi.mocked(api.get).mockResolvedValue({ data: { items: [] } } as never);
    await irParaEquipamentos();
    expect(
      await screen.findByRole("button", { name: "Pular por agora" }),
    ).toBeTruthy();
    expect(
      screen.getByText(/Nenhum produto cadastrado ainda/),
    ).toBeTruthy();
  });

  it("com equipamento já cadastrado, o botão passa a dizer Continuar", async () => {
    vi.mocked(equipmentService.getMyEquipment).mockResolvedValue([
      { id: "e1", name: "Phoebus-PE", serial_number: "SN-1", location: "Sala 201" },
    ] as never);
    vi.mocked(api.get).mockResolvedValue({ data: { items: [] } } as never);
    await irParaEquipamentos();
    expect(await screen.findByText("Phoebus-PE")).toBeTruthy();
    expect(screen.getByText("Adicionados (1)")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Continuar" })).toBeTruthy();
  });

  it("o último passo conclui o onboarding e leva ao primeiro chamado", async () => {
    vi.mocked(equipmentService.getMyEquipment).mockResolvedValue([]);
    vi.mocked(api.get).mockResolvedValue({ data: { items: [] } } as never);
    await irParaEquipamentos();
    await userEvent.click(
      await screen.findByRole("button", { name: "Pular por agora" }),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Abrir primeiro chamado" }),
    );
    expect(concluirOnboarding).toHaveBeenCalledTimes(1);
    expect(navegar).toHaveBeenCalledWith("/tickets/new");
  });
});

/**
 * Rótulo ligado ao campo.
 *
 * Os quatro rótulos desta tela eram `<label>` sem `htmlFor` sobre `<input>`
 * sem `id`: ficavam um em cima do outro na tela e não tinham relação nenhuma
 * na árvore de acessibilidade. Quem usa leitor de tela ouvia "edição, em
 * branco" e nada mais; quem clica no rótulo não focava o campo.
 *
 * `getByLabelText` consulta exatamente essa relação — é a consulta que falha
 * com o rótulo solto e passa com ele ligado, sem olhar classe nenhuma.
 */
describe("OnboardingPage — cada campo é alcançável pelo próprio rótulo", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(equipmentService.getMyEquipment).mockResolvedValue([]);
    vi.mocked(api.get).mockResolvedValue({ data: { items: [] } } as never);
  });

  it.each([
    "CNPJ *",
    "Nome da empresa",
    "CEP *",
    "Endereço",
    "Cidade",
    "Estado (UF)",
  ])("o passo da empresa liga o rótulo %s ao seu campo", (rotulo) => {
    render(<OnboardingPage />);
    const campo = screen.getByLabelText(rotulo);
    expect(campo.tagName, rotulo).toBe("INPUT");
  });

  it("o seletor de produto do passo 2 também", async () => {
    vi.mocked(userService.completeOnboarding).mockResolvedValue({} as never);
    vi.mocked(api.get).mockResolvedValue({
      data: { items: [{ id: "p1", name: "Detector", version: "2.1", is_active: true }] },
    } as never);
    render(<OnboardingPage />);
    await preencherEmpresa();
    await userEvent.click(screen.getByRole("button", { name: "Continuar" }));

    const seletor = await screen.findByLabelText("Produto");
    expect(seletor.tagName).toBe("SELECT");
    // O rótulo do produto é montado pelo `Select` a partir de nome + versão.
    expect(screen.getByRole("option", { name: "Detector (2.1)" })).toBeTruthy();
  });

  it("clicar no rótulo foca o campo — que é o que o `htmlFor` compra", async () => {
    render(<OnboardingPage />);
    // Consulta pelo texto do rótulo, não pelo campo: se o `htmlFor` sumir, o
    // clique deixa de mover o foco e este caso cai.
    await userEvent.click(screen.getByText("CNPJ *"));
    expect(screen.getByLabelText("CNPJ *")).toHaveFocus();
  });
});

describe("OnboardingPage — o que a Fase 16 tirou daqui", () => {
  it("não sobrou classe da paleta crua", () => {
    expect(CODIGO).not.toMatch(
      /\b(?:[a-z-]+:)*(?:bg|text|border|fill|stroke|divide|ring)-(?:slate|gray|zinc|red|orange|amber|emerald|sky|blue|indigo|violet|rose)-\d/,
    );
  });

  it("o par errado do degrau de ação sumiu do indicador de passo", () => {
    expect(CODIGO).not.toMatch(/\btext-white\b/);
    expect(CODIGO).toContain("bg-action text-on-primary");
  });

  it("a rampa semântica não é mais cor de texto", () => {
    expect(CODIGO).not.toMatch(/\btext-(danger|success|warning|info)(-\d+)?\b/);
  });
});

describe("OnboardingPage — o indicador de passo, medido nos tokens", () => {
  it("o passo cumprido aprova em AA nos dois temas", () => {
    for (const tema of ["claro", "escuro"] as const) {
      expect(contraste("--action", "--text-on-primary", tema), tema)
        .toBeGreaterThanOrEqual(AA);
    }
  });

  it("o par antigo — o degrau de marca com branco — reprovava", () => {
    for (const tema of ["claro", "escuro"] as const) {
      expect(contraste("--color-primary-500", "--color-white", tema), tema)
        .toBeLessThan(AA);
    }
  });

  it("o passo futuro aprova sobre a superfície elevada, nos dois temas", () => {
    for (const tema of ["claro", "escuro"] as const) {
      expect(
        contraste("--surface-elevated", "--text-muted", tema, "--bg-base"),
        tema,
      ).toBeGreaterThanOrEqual(AA);
    }
  });
});
