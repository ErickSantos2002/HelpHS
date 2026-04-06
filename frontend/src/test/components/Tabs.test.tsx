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
