import { describe, it, expect } from "vitest";
import { resolveFileUrl } from "../../lib/fileUrl";

describe("resolveFileUrl", () => {
  it("aponta o caminho relativo para o host da API", () => {
    const url = resolveFileUrl("/api/v1/files/abc123", "https://api.helphs.com/api/v1");
    expect(url).toBe("https://api.helphs.com/api/v1/files/abc123");
  });

  it("funciona com a base terminando em barra", () => {
    const url = resolveFileUrl("/api/v1/files/abc123", "https://api.helphs.com/api/v1/");
    expect(url).toBe("https://api.helphs.com/api/v1/files/abc123");
  });

  it("mantém URL que já é absoluta", () => {
    const externa = "https://cdn.exemplo.com/foto.png";
    expect(resolveFileUrl(externa, "https://api.helphs.com/api/v1")).toBe(externa);
  });

  it("em desenvolvimento, com base relativa, devolve o caminho como está", () => {
    expect(resolveFileUrl("/api/v1/files/abc", "/api/v1")).toBe("/api/v1/files/abc");
  });

  it("devolve vazio ou nulo sem alteração", () => {
    expect(resolveFileUrl("", "https://api.helphs.com/api/v1")).toBe("");
    expect(resolveFileUrl(null, "https://api.helphs.com/api/v1")).toBeNull();
  });

  it("não duplica o prefixo quando o caminho não tem /api/v1", () => {
    const url = resolveFileUrl("/files/abc", "https://api.helphs.com/api/v1");
    expect(url).toBe("https://api.helphs.com/api/v1/files/abc");
  });
});
