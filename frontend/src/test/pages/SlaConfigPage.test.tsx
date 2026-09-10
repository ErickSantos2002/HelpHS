import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../services/slaService", () => ({
  getSLAConfigs: vi.fn(),
  updateSLAConfig: vi.fn(),
}));

import SlaConfigPage from "../../pages/sla/SlaConfigPage";
import * as slaService from "../../services/slaService";
import type { SLAConfig } from "../../services/slaService";

/**
 * O que esta tela tinha, e que estes casos prendem.
 *
 * **Três mapas locais de prioridade** — `LEVEL_LABEL`, `LEVEL_STYLE` e
 * `LEVEL_ORDER` — e o primeiro deles falava MASCULINO: "Crítico", "Alto",
 * "Médio", "Baixo", contra o feminino que a emenda E17 fixou. Duas telas do
 * mesmo sistema diziam palavras diferentes para o mesmo dado, e nenhum teste
 * segurava nenhuma das duas.
 *
 * Por isso os casos daqui olham para o **texto que a pessoa lê** e para o
 * **nome acessível do controle**, e não para classe nem para estrutura: classe
 * não é medida em ambiente de teste (o DOM virtual não aplica CSS nenhum), e
 * estrutura muda a cada refatoração sem que a promessa mude.
 */

function config(level: string, over: Partial<SLAConfig> = {}): SLAConfig {
  return {
    id: `sla-${level}`,
    level,
    response_time_hours: 4,
    resolve_time_hours: 24,
    warning_threshold: 80,
    is_active: true,
    created_at: "2026-01-01T12:00:00Z",
    updated_at: "2026-01-01T12:00:00Z",
    ...over,
  } as SLAConfig;
}

/**
 * De propósito FORA de ordem, e fora da ordem alfabética também: se a tela
 * deixar de ordenar, o que aparece é esta sequência, e não a certa por acaso.
 */
const DO_SERVIDOR = [
  config("medium", { response_time_hours: 8, resolve_time_hours: 48 }),
  config("low", { response_time_hours: 24, resolve_time_hours: 72 }),
  config("critical", { response_time_hours: 1, resolve_time_hours: 4 }),
  config("high", { response_time_hours: 6, resolve_time_hours: 28 }),
];

async function montar(configs: SLAConfig[] = DO_SERVIDOR) {
  vi.mocked(slaService.getSLAConfigs).mockResolvedValue(configs);
  render(<SlaConfigPage />);
  await waitFor(() =>
    expect(screen.getByText("Níveis de SLA")).toBeInTheDocument(),
  );
}

/** Os rótulos de prioridade, na ordem em que a tela os desenha. */
function rotulosNaTela(extras: string[] = []) {
  const nomes = ["Crítica", "Alta", "Média", "Baixa", ...extras];
  return screen
    .getAllByText(new RegExp(`^(${nomes.join("|")})$`))
    .map((el) => el.textContent);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("SlaConfigPage", () => {
  it("a prioridade fala a língua do módulo, no feminino", async () => {
    // O mapa local dizia "Crítico/Alto/Médio/Baixo". A troca é de TEXTO
    // VISÍVEL: quem usa a tela vê palavra diferente depois desta fase.
    await montar();

    for (const rotulo of ["Crítica", "Alta", "Média", "Baixa"]) {
      expect(screen.getByText(rotulo)).toBeInTheDocument();
    }
    for (const antigo of ["Crítico", "Alto", "Médio", "Baixo"]) {
      expect(screen.queryByText(antigo)).not.toBeInTheDocument();
    }
  });

  it("a ordem é a do módulo, e não a que o servidor mandou", async () => {
    await montar();
    expect(rotulosNaTela()).toEqual(["Crítica", "Alta", "Média", "Baixa"]);
  });

  it("prioridade que o front não conhece não derruba a tela, e vai para o fim", async () => {
    // O dado vem da REDE. Um nível novo no backend não pode nem quebrar a
    // renderização nem — pior — aparecer no TOPO como se fosse o mais urgente,
    // que é o que `indexOf` devolvendo -1 faria.
    await montar([config("blocker"), ...DO_SERVIDOR]);

    expect(rotulosNaTela(["blocker"])).toEqual([
      "Crítica",
      "Alta",
      "Média",
      "Baixa",
      "blocker",
    ]);
  });

  it("cada botão de editar diz qual prioridade edita", async () => {
    // São quatro botões só de ícone, e o `Icon` do pacote é `aria-hidden`.
    // Sem a prioridade dentro do nome, o leitor de tela anuncia "Editar"
    // quatro vezes e a pessoa não tem como escolher a linha.
    await montar();

    for (const rotulo of ["Crítica", "Alta", "Média", "Baixa"]) {
      expect(
        screen.getByRole("button", {
          name: `Editar SLA da prioridade ${rotulo}`,
        }),
      ).toBeInTheDocument();
    }
  });

  it("editar abre o modal da linha escolhida", async () => {
    await montar();

    await userEvent.click(
      screen.getByRole("button", { name: "Editar SLA da prioridade Alta" }),
    );

    expect(
      screen.getByRole("dialog", { name: "Editar SLA — Alta" }),
    ).toBeInTheDocument();
  });

  it("salvar manda o valor novo e a linha passa a mostrá-lo", async () => {
    await montar();
    vi.mocked(slaService.updateSLAConfig).mockResolvedValue(
      config("high", { response_time_hours: 9, resolve_time_hours: 28 }),
    );

    await userEvent.click(
      screen.getByRole("button", { name: "Editar SLA da prioridade Alta" }),
    );

    const dialogo = screen.getByRole("dialog", { name: "Editar SLA — Alta" });
    const resposta = within(dialogo).getByLabelText(/Resposta \(horas úteis\)/);
    await userEvent.clear(resposta);
    await userEvent.type(resposta, "9");
    await userEvent.click(within(dialogo).getByRole("button", { name: "Salvar" }));

    await waitFor(() =>
      expect(slaService.updateSLAConfig).toHaveBeenCalledWith(
        "sla-high",
        expect.objectContaining({ response_time_hours: 9 }),
      ),
    );
    await waitFor(() => expect(screen.getByText("9h")).toBeInTheDocument());
  });

  it("as horas viram dias quando passam de um dia", async () => {
    // "28h" não é o que alguém escreve num contrato de SLA; "1d 4h" é.
    await montar();

    expect(screen.getByText("4h")).toBeInTheDocument(); // crítica, resolução
    expect(screen.getByText("1d 4h")).toBeInTheDocument(); // alta, resolução
    expect(screen.getByText("2d")).toBeInTheDocument(); // média, resolução
    expect(screen.getByText("3d")).toBeInTheDocument(); // baixa, resolução
  });

  it("falha ao carregar vira aviso, e o aviso interrompe", async () => {
    // `danger` é a única variante do `Alert` que fica em `role="alert"` —
    // região viva assertiva. Não conseguir carregar a configuração de SLA é
    // exatamente o caso que justifica cortar a fala do leitor de tela.
    vi.mocked(slaService.getSLAConfigs).mockRejectedValue(new Error("500"));
    render(<SlaConfigPage />);

    const aviso = await screen.findByRole("alert");
    expect(aviso).toHaveTextContent(
      "Não foi possível carregar as configurações de SLA.",
    );
  });
});
