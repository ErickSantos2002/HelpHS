import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../components/ui/Tabs";

function TabsFixture({ defaultTab = "a" }: { defaultTab?: string }) {
  const [tab, setTab] = [defaultTab, () => {}];
  return (
    <Tabs value={tab} onChange={setTab}>
      <TabsList>
        <TabsTrigger value="a">Aba A</TabsTrigger>
        <TabsTrigger value="b">Aba B</TabsTrigger>
      </TabsList>
      <TabsContent value="a">Conteúdo A</TabsContent>
      <TabsContent value="b">Conteúdo B</TabsContent>
    </Tabs>
  );
}

describe("Tabs", () => {
  it("renders trigger buttons", () => {
    render(<TabsFixture />);
    expect(screen.getByRole("tab", { name: "Aba A" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Aba B" })).toBeInTheDocument();
  });

  it("shows active tab content", () => {
    render(<TabsFixture defaultTab="a" />);
    expect(screen.getByText("Conteúdo A")).toBeInTheDocument();
    expect(screen.queryByText("Conteúdo B")).not.toBeInTheDocument();
  });

  it("active trigger has aria-selected=true", () => {
    render(<TabsFixture defaultTab="a" />);
    expect(screen.getByRole("tab", { name: "Aba A" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("tab", { name: "Aba B" })).toHaveAttribute(
      "aria-selected",
      "false",
    );
  });

  it("calls onChange when a trigger is clicked", async () => {
    let current = "a";
    render(
      <Tabs
        value={current}
        onChange={(v) => {
          current = v;
        }}
      >
        <TabsList>
          <TabsTrigger value="a">Aba A</TabsTrigger>
          <TabsTrigger value="b">Aba B</TabsTrigger>
        </TabsList>
        <TabsContent value="a">Conteúdo A</TabsContent>
        <TabsContent value="b">Conteúdo B</TabsContent>
      </Tabs>,
    );

    await userEvent.click(screen.getByRole("tab", { name: "Aba B" }));
    expect(current).toBe("b");
  });

  it("throws if TabsTrigger is used outside Tabs", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<TabsTrigger value="x">X</TabsTrigger>)).toThrow();
    spy.mockRestore();
  });
});

describe("Tabs — Fase 10: o contrato que os papéis prometiam", () => {
  function Abas() {
    const [ativa, setAtiva] = useState("um");
    return (
      <Tabs value={ativa} onChange={setAtiva}>
        <TabsList>
          <TabsTrigger value="um">Um</TabsTrigger>
          <TabsTrigger value="dois">Dois</TabsTrigger>
          <TabsTrigger value="tres">Três</TabsTrigger>
        </TabsList>
        <TabsContent value="um">Conteúdo um</TabsContent>
        <TabsContent value="dois">Conteúdo dois</TabsContent>
        <TabsContent value="tres">Conteúdo três</TabsContent>
      </Tabs>
    );
  }

  it("a seta para a direita anda, e dá a volta no fim", async () => {
    // O padrão WAI-ARIA de abas navega com ←/→. Antes o `Tab` percorria aba por
    // aba, que é o comportamento de um grupo de botões — não de abas.
    render(<Abas />);
    screen.getByRole("tab", { name: "Um" }).focus();

    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Dois" })).toHaveFocus();

    await userEvent.keyboard("{ArrowRight}{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Um" })).toHaveFocus();
  });

  it("a seta para a esquerda dá a volta no começo", async () => {
    render(<Abas />);
    screen.getByRole("tab", { name: "Um" }).focus();

    await userEvent.keyboard("{ArrowLeft}");

    expect(screen.getByRole("tab", { name: "Três" })).toHaveFocus();
  });

  it("Home e End vão às pontas", async () => {
    render(<Abas />);
    screen.getByRole("tab", { name: "Um" }).focus();

    await userEvent.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "Três" })).toHaveFocus();

    await userEvent.keyboard("{Home}");
    expect(screen.getByRole("tab", { name: "Um" })).toHaveFocus();
  });

  it("andar com a seta também troca a aba", async () => {
    // No padrão de seleção automática, mover o foco seleciona. O contrário
    // obrigaria a pessoa a apertar Enter depois de cada seta.
    render(<Abas />);
    screen.getByRole("tab", { name: "Um" }).focus();

    await userEvent.keyboard("{ArrowRight}");

    expect(screen.getByText("Conteúdo dois")).toBeInTheDocument();
  });

  it("só a aba ativa é tabulável", async () => {
    // Tabulação móvel. Sem isso, uma tela com cinco abas gasta cinco paradas de
    // teclado antes de chegar ao conteúdo.
    render(<Abas />);

    expect(screen.getByRole("tab", { name: "Um" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("tab", { name: "Dois" })).toHaveAttribute("tabindex", "-1");
    expect(screen.getByRole("tab", { name: "Três" })).toHaveAttribute("tabindex", "-1");
  });

  it("a aba diz qual painel controla, e o painel diz de qual aba veio", () => {
    // A aba declarava `role="tab"` e não dizia o que controlava.
    render(<Abas />);

    const aba = screen.getByRole("tab", { name: "Um" });
    const painel = screen.getByRole("tabpanel");

    expect(aba.getAttribute("aria-controls")).toBe(painel.id);
    expect(painel.getAttribute("aria-labelledby")).toBe(aba.id);
  });

  it("o painel entra na tabulação", () => {
    // É para onde o `Tab` leva depois da lista. Um painel sem elemento focável
    // ficaria inalcançável por teclado.
    render(<Abas />);

    expect(screen.getByRole("tabpanel")).toHaveAttribute("tabindex", "0");
  });

  it("o gatilho é type=button, e não submete o formulário", async () => {
    // Aqui não há portal para salvar, ao contrário do Modal: o gatilho é
    // descendente do form de verdade.
    const aoEnviar = vi.fn((e: React.FormEvent) => e.preventDefault());
    render(
      <form onSubmit={aoEnviar}>
        <Abas />
      </form>,
    );

    await userEvent.click(screen.getByRole("tab", { name: "Dois" }));

    expect(aoEnviar).not.toHaveBeenCalled();
  });

  it("não sobra cor cravada nem alias de fundo", () => {
    const { container } = render(<Abas />);

    expect(container.innerHTML).not.toMatch(/slate-\d/);
    expect(container.innerHTML).not.toMatch(/background-surface|background-elevated/);
  });

  it("o gatilho tem anel de foco no degrau de ação", () => {
    render(<Abas />);

    expect(screen.getByRole("tab", { name: "Um" }).className).toContain(
      "focus-visible:ring-action",
    );
  });
});
