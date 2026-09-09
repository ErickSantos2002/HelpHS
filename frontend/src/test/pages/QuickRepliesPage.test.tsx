import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));
vi.mock("../../services/quickReplyService", () => ({
  createQuickReply: vi.fn(),
  deleteQuickReply: vi.fn(),
  listQuickReplies: vi.fn(),
  updateQuickReply: vi.fn(),
}));

import QuickRepliesPage from "../../pages/settings/QuickRepliesPage";
import * as quickReplyService from "../../services/quickReplyService";
import type { QuickReply } from "../../services/quickReplyService";
import { AA, contraste } from "../helpers/contraste";

/**
 * As respostas rápidas, e o que a Fase 16 mexeu aqui.
 *
 * **26** classes de paleta crua, **2** `<svg>` num par de componentes locais
 * (`IconEdit` e `IconTrash`, idênticos ao `edit` e ao `trash` do pacote) e
 * **um** par que a catraca de contraste cobrava — o selo "Inativa", que no
 * escuro pintava `dark:text-slate-500` sobre `dark:bg-surface-elevated`:
 * **2,85:1**. O prefixo `dark:` é o detalhe que importa: no claro o mesmo selo
 * passava, e quem olhasse um tema só daria a tela por conforme.
 *
 * Os casos de conteúdo não olham classe — o happy-dom não aplica CSS, e um
 * caso que afirmasse a classe passaria com a regra morta. Eles prendem o que a
 * tela **promete**: o estado dito em palavra, o nome acessível dos dois botões
 * de ícone (que agora são só desenho), e os dois vazios que dizem coisas
 * diferentes.
 */
const FONTE = readFileSync(
  resolve(process.cwd(), "src/pages/settings/QuickRepliesPage.tsx"),
  "utf-8",
);
const CODIGO = FONTE.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");

function resposta(over: Partial<QuickReply> = {}): QuickReply {
  return {
    id: "q1",
    shortcut: "bomdia",
    title: "Saudação inicial",
    content: "Bom dia! Sou da equipe de suporte da H&S.",
    is_active: true,
    created_by: "u1",
    created_at: "2026-09-01T10:00:00Z",
    updated_at: "2026-09-01T10:00:00Z",
    ...over,
  };
}

const ATIVA = resposta();
const INATIVA = resposta({
  id: "q2",
  shortcut: "ferias",
  title: "Aviso de férias",
  content: "Estamos em recesso até dia 10.",
  is_active: false,
});

function comLista(items: QuickReply[] = [ATIVA, INATIVA]) {
  vi.mocked(quickReplyService.listQuickReplies).mockResolvedValue(items);
}

describe("QuickRepliesPage — o que a tela promete", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    comLista();
  });

  it("mostra o atalho e o título de cada resposta", async () => {
    render(<QuickRepliesPage />);
    expect(await screen.findByText("/bomdia")).toBeTruthy();
    expect(screen.getByText("Saudação inicial")).toBeTruthy();
    expect(screen.getByText("/ferias")).toBeTruthy();
  });

  it("diz o estado em PALAVRA, não só na cor do selo", async () => {
    // 1.4.1: o selo era verde para ativa e cinza para inativa, e no escuro o
    // cinza reprovava. A palavra é o que informa sem depender de nenhum dos
    // dois.
    render(<QuickRepliesPage />);
    expect(await screen.findByText("Ativa")).toBeTruthy();
    expect(screen.getByText("Inativa")).toBeTruthy();
  });

  it("os dois botões de ícone têm nome acessível com o atalho dentro", async () => {
    // Eles não têm texto: eram dois `<svg>` locais e agora são dois `Icon`,
    // que o pacote marca com `aria-hidden`. Sem o `aria-label` o botão seria
    // anunciado como "botão" e nada mais.
    render(<QuickRepliesPage />);
    expect(await screen.findByRole("button", { name: "Editar bomdia" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Excluir bomdia" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Editar ferias" })).toBeTruthy();
  });

  it("a busca filtra por atalho", async () => {
    render(<QuickRepliesPage />);
    await screen.findByText("/bomdia");
    await userEvent.type(
      screen.getByPlaceholderText(/Buscar por atalho/),
      "feri",
    );
    expect(screen.getByText("/ferias")).toBeTruthy();
    expect(screen.queryByText("/bomdia")).toBeNull();
  });

  it("os dois vazios dizem coisas diferentes", async () => {
    comLista([]);
    const { unmount } = render(<QuickRepliesPage />);
    expect(
      await screen.findByText("Nenhuma resposta rápida cadastrada ainda."),
    ).toBeTruthy();
    unmount();

    comLista([ATIVA]);
    render(<QuickRepliesPage />);
    await screen.findByText("/bomdia");
    await userEvent.type(
      screen.getByPlaceholderText(/Buscar por atalho/),
      "zzzz",
    );
    expect(
      screen.getByText("Nenhuma resposta encontrada para esta busca."),
    ).toBeTruthy();
  });

  it("excluir pergunta antes, e só então chama o serviço", async () => {
    vi.mocked(quickReplyService.deleteQuickReply).mockResolvedValue(undefined);
    render(<QuickRepliesPage />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Excluir bomdia" }),
    );

    const dialogo = await screen.findByRole("dialog", {
      name: "Excluir resposta rápida",
    });
    expect(quickReplyService.deleteQuickReply).not.toHaveBeenCalled();

    await userEvent.click(
      within(dialogo).getByRole("button", { name: "Excluir" }),
    );
    await waitFor(() =>
      expect(quickReplyService.deleteQuickReply).toHaveBeenCalledWith("q1"),
    );
    await waitFor(() => expect(screen.queryByText("/bomdia")).toBeNull());
  });

  it("avisa quando a lista não carrega", async () => {
    vi.mocked(quickReplyService.listQuickReplies).mockRejectedValue(new Error("boom"));
    render(<QuickRepliesPage />);
    expect(
      await screen.findByText("Não foi possível carregar as respostas rápidas."),
    ).toBeTruthy();
  });
});

describe("QuickRepliesPage — o que a Fase 16 tirou daqui", () => {
  it("não sobrou `<svg>` solto nem componente local de ícone", () => {
    expect(CODIGO).not.toContain("<svg");
    expect(CODIGO).not.toMatch(/function Icon(Edit|Trash)/);
  });

  it("não sobrou classe da paleta crua", () => {
    expect(CODIGO).not.toMatch(
      /\b(?:[a-z-]+:)*(?:bg|text|border|fill|stroke|divide|ring)-(?:slate|gray|zinc|red|orange|amber|emerald|sky|blue|indigo|violet|rose)-\d/,
    );
  });

  it("a rampa semântica não é mais cor de texto", () => {
    // `text-danger-400` no asterisco de obrigatório era a §3.2 em miniatura.
    expect(CODIGO).not.toMatch(/\btext-(danger|success|warning|info)(-\d+)?\b/);
  });
});

describe("QuickRepliesPage — o selo de estado, medido nos tokens", () => {
  it.each([
    ["Ativa", "--tint-success", "--on-tint-success"],
    ["Inativa", "--tint-neutral", "--on-tint-neutral"],
  ] as const)("o selo %s aprova em AA nos dois temas", (_rotulo, tinta, par) => {
    for (const tema of ["claro", "escuro"] as const) {
      expect(contraste(tinta, par, tema), tema).toBeGreaterThanOrEqual(AA);
    }
  });

  it("o par antigo do selo Inativa reprovava no escuro", () => {
    // `dark:bg-surface-elevated` + `dark:text-slate-500` — 2,85:1. O
    // `--text-faint` é o degrau mais próximo do slate-500 que o pacote tem, e
    // ele reprova sobre a mesma superfície: é a razão de o selo ter par
    // próprio.
    expect(contraste("--surface-elevated", "--text-faint", "escuro")).toBeLessThan(AA);
  });
});
