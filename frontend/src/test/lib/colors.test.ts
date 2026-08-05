import { describe, it, expect } from "vitest";
import { readableTextColor } from "../../lib/colors";

describe("readableTextColor", () => {
  it("usa texto claro sobre cores escuras", () => {
    expect(readableTextColor("#1e293b")).toBe("#ffffff");
    expect(readableTextColor("#6366f1")).toBe("#ffffff");
    expect(readableTextColor("#dc2626")).toBe("#ffffff");
  });

  it("usa texto escuro sobre cores claras", () => {
    expect(readableTextColor("#ffffff")).toBe("#0f172a");
    expect(readableTextColor("#eab308")).toBe("#0f172a");
    expect(readableTextColor("#facc15")).toBe("#0f172a");
  });

  it("aceita hex sem cerquilha", () => {
    expect(readableTextColor("ffffff")).toBe("#0f172a");
  });

  it("aceita hex de 3 dígitos", () => {
    expect(readableTextColor("#fff")).toBe("#0f172a");
    expect(readableTextColor("#000")).toBe("#ffffff");
  });

  it("cai no texto claro quando o valor é inválido", () => {
    expect(readableTextColor("não é cor")).toBe("#ffffff");
    expect(readableTextColor("")).toBe("#ffffff");
  });
});
