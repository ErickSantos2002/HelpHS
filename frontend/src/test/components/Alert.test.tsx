import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Alert } from "../../components/ui/Alert";
import { AA, contraste } from "../helpers/contraste";

/**
 * Aviso em bloco. Não tinha teste nenhum até a Fase 10 — a suíte inteira passava
 * com `success` pintado de `primary`, que é a variante dizendo a cor errada.
 */

const VARIANTES = ["info", "success", "warning", "danger"] as const;

describe("Alert — as tintas", () => {
  it.each(VARIANTES)("a variante %s usa o par medido da própria tinta", (v) => {
    const { container } = render(<Alert variant={v}>Mensagem</Alert>);
    const caixa = container.firstElementChild!;

    expect(caixa.className).toContain("bg-tint-" + v);
    expect(caixa.className).toContain(
      "text-on-tint-" + (v === "danger" ? "danger" : v),
    );
  });

  it("success NÃO usa o degrau de marca", () => {
    // Era `bg-primary/10 border-primary/30 text-primary`. Um aviso de sucesso
    // saía no mesmo degrau de um botão primário, indistinguível de "aqui há uma
    // ação".
    const { container } = render(<Alert variant="success">Salvo</Alert>);

    expect(container.firstElementChild!.className).not.toMatch(/primary/);
  });

  it("nenhuma variante pinta a tinta com opacidade", () => {
    // Regra (b) do D8-a: tinta é token medido, não cor com alfa. Eram
    // `bg-info/10`, `bg-warning/10`, `bg-danger/10`.
    for (const v of VARIANTES) {
      const { container, unmount } = render(<Alert variant={v}>x</Alert>);
      expect(container.firstElementChild!.className).not.toMatch(/bg-\w+\/\d/);
      unmount();
    }
  });

  it("o corpo não é rebaixado a 80% do contraste", () => {
    // Era `text-current/80`: herdava a cor da variante e cortava um quinto do
    // contraste de um par que fora medido a 100%.
    const { container } = render(<Alert variant="danger">Falhou</Alert>);

    expect(container.innerHTML).not.toContain("text-current/80");
  });

  it("nenhum degrau cravado da rampa sobrou", () => {
    for (const v of VARIANTES) {
      const { container, unmount } = render(<Alert variant={v}>x</Alert>);
      expect(container.innerHTML).not.toMatch(/text-(info|warning|danger|success)-\d00/);
      unmount();
    }
  });
});

describe("Alert — o papel depende da variante", () => {
  it("só danger interrompe", () => {
    // A primeira versão daqui punha `warning` em `alert` também. A emenda E12
    // fixou o contrário para os dois repositórios: aviso de atenção quase nunca
    // é urgente a ponto de justificar cortar a fala do leitor de tela, e quando
    // for, a tela usa `danger`.
    render(<Alert variant="danger">Mensagem</Alert>);

    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it.each([
    ["info", "status"],
    ["success", "status"],
    ["warning", "status"],
  ] as const)("%s espera a pausa: role=%s", (v, papel) => {
    // `role="alert"` é região viva ASSERTIVA: interrompe o que o leitor de tela
    // estiver dizendo. Para um erro é o certo; para um "salvo com sucesso" é
    // atropelar a leitura com uma informação que podia esperar.
    render(<Alert variant={v}>Mensagem</Alert>);

    expect(screen.getByRole(papel)).toBeInTheDocument();
  });

  it.each(["info", "success", "warning"] as const)(
    "%s não se anuncia como alerta",
    (v) => {
      render(<Alert variant={v}>Mensagem</Alert>);

      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    },
  );

  it("live=false tira o papel de região viva", () => {
    // Para o aviso que JÁ ESTÁ na tela quando a página carrega. Região viva
    // anuncia MUDANÇA; conteúdo que sempre esteve ali não mudou, e anunciá-lo
    // faz o leitor lê-lo fora de ordem — antes do conteúdo que lhe dá contexto.
    render(
      <Alert variant="danger" live={false}>
        Esta empresa está inativa.
      </Alert>,
    );

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByText("Esta empresa está inativa.")).toBeInTheDocument();
  });

  it("live é ligado por padrão", () => {
    render(<Alert variant="danger">Falhou</Alert>);

    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});

describe("Alert — o botão de fechar", () => {
  it("é do tipo button, e não submete o formulário que o contém", async () => {
    // Sem `type="button"` o padrão do HTML dentro de `<form>` é `submit`:
    // fechar o aviso enviaria o formulário.
    const aoEnviar = vi.fn((e: React.FormEvent) => e.preventDefault());
    render(
      <form onSubmit={aoEnviar}>
        <Alert variant="danger" onDismiss={vi.fn()}>
          Falhou
        </Alert>
      </form>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Fechar" }));

    expect(aoEnviar).not.toHaveBeenCalled();
  });

  it("chama onDismiss", async () => {
    const aoFechar = vi.fn();
    render(<Alert onDismiss={aoFechar}>Mensagem</Alert>);

    await userEvent.click(screen.getByRole("button", { name: "Fechar" }));

    expect(aoFechar).toHaveBeenCalledTimes(1);
  });

  it("tem anel de foco no degrau de ação", () => {
    render(<Alert onDismiss={vi.fn()}>Mensagem</Alert>);

    expect(screen.getByRole("button", { name: "Fechar" }).className).toContain(
      "focus-visible:ring-action",
    );
  });

  it("não usa branco cravado no realce", () => {
    // Era `hover:bg-white/10` — a família da E1. O véu neutro precisa inverter
    // com o tema.
    render(<Alert onDismiss={vi.fn()}>Mensagem</Alert>);

    expect(screen.getByRole("button", { name: "Fechar" }).className).not.toContain(
      "bg-white",
    );
  });

  it("sem onDismiss não existe botão", () => {
    render(<Alert>Mensagem</Alert>);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("Alert — contraste", () => {
  it.each(["claro", "escuro"] as const)(
    "as quatro tintas passam o piso de texto, tema %s",
    (tema) => {
      for (const v of VARIANTES) {
        expect(
          contraste("--tint-" + v, "--on-tint-" + v, tema),
        ).toBeGreaterThanOrEqual(AA);
      }
    },
  );
});
