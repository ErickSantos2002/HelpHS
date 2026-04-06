import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Badge, PriorityBadge, StatusBadge } from "../../components/ui/Badge";

describe("Badge", () => {
  it("renders text", () => {
    render(<Badge>Aberto</Badge>);
    expect(screen.getByText("Aberto")).toBeInTheDocument();
  });
});

describe("StatusBadge", () => {
  it("renders label for open status", () => {
    render(<StatusBadge status="open" />);
    expect(screen.getByText("Aberto")).toBeInTheDocument();
  });

  it("renders label for in_progress status", () => {
    render(<StatusBadge status="in_progress" />);
    expect(screen.getByText("Em andamento")).toBeInTheDocument();
  });

  it("renders label for resolved status", () => {
    render(<StatusBadge status="resolved" />);
    expect(screen.getByText("Resolvido")).toBeInTheDocument();
  });

  it("renders label for closed status", () => {
    render(<StatusBadge status="closed" />);
    expect(screen.getByText("Fechado")).toBeInTheDocument();
  });

  it("renders label for cancelled status", () => {
    render(<StatusBadge status="cancelled" />);
    expect(screen.getByText("Cancelado")).toBeInTheDocument();
  });
});

describe("PriorityBadge", () => {
  it("renders label for critical priority", () => {
    render(<PriorityBadge priority="critical" />);
    expect(screen.getByText("Crítico")).toBeInTheDocument();
  });

  it("renders label for high priority", () => {
    render(<PriorityBadge priority="high" />);
    expect(screen.getByText("Alto")).toBeInTheDocument();
  });

  it("renders label for medium priority", () => {
    render(<PriorityBadge priority="medium" />);
    expect(screen.getByText("Médio")).toBeInTheDocument();
  });

  it("renders label for low priority", () => {
    render(<PriorityBadge priority="low" />);
    expect(screen.getByText("Baixo")).toBeInTheDocument();
  });
});
