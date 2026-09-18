import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FileUpload } from "../../components/ui/FileUpload";

const ACEITOS = [".pdf", ".png", ".txt"];

/**
 * Arquivo de teste com tamanho **declarado**, não alocado.
 *
 * `new File([new Uint8Array(25 * 1024 * 1024)], …)` alocaria 25 MB por caso e
 * estoura a pilha no jsdom. O componente só lê `f.size`, então declarar basta —
 * e o teste passa a medir a regra, não a memória.
 */
function arquivo(nome: string, mb = 1): File {
  const f = new File(["x"], nome, { type: "application/pdf" });
  Object.defineProperty(f, "size", { value: Math.round(mb * 1024 * 1024) });
  return f;
}

/** Solta arquivos na zona, que é o caminho que ignora o `accept` do input. */
function soltar(container: HTMLElement, ...files: File[]) {
  const zona = container.firstElementChild!.firstElementChild!;
  const evento = new Event("drop", { bubbles: true });
  Object.defineProperty(evento, "dataTransfer", { value: { files } });
  zona.dispatchEvent(evento);
}

function montar(props: Partial<Parameters<typeof FileUpload>[0]> = {}) {
  const onChange = vi.fn();
  const utils = render(
    <FileUpload
      files={[]}
      onChange={onChange}
      accept={ACEITOS}
      maxFiles={10}
      maxSizeMb={25}
      {...props}
    />,
  );
  return { onChange, ...utils };
}

describe("FileUpload", () => {
  it("anuncia o limite de arquivos e de tamanho", () => {
    montar();
    expect(screen.getByText(/Máx 10 arquivos · 25 MB cada/)).toBeInTheDocument();
  });

  it("o accept do input espelha as extensões, sem inventar formato", () => {
    const { container } = montar();
    const input = container.querySelector('input[type="file"]');
    expect(input).toHaveAttribute("accept", ".pdf,.png,.txt");
    expect(input).toHaveAttribute("multiple");
  });

  // ── As regras de validação, que espelham o backend ────────────────────

  it("recusa extensão fora da lista, e diz qual arquivo", async () => {
    // Pelo caminho do ARRASTAR, que é onde isto pode acontecer de verdade: o
    // `accept` do input filtra no seletor do sistema, mas soltar um arquivo na
    // zona passa por cima dele. Testar pelo input mediria o navegador, não a
    // regra — o `userEvent.upload` também respeita o `accept` e o arquivo
    // sequer chegaria ao componente.
    const { onChange, container } = montar();
    soltar(container, arquivo("planilha.exe"));
    // `findBy` e não `getBy`: o `drop` é despachado fora do `act`, então a
    // mensagem só existe depois que o React repinta.
    expect(
      await screen.findByText(/Tipo não permitido: planilha\.exe/),
    ).toBeInTheDocument();
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("recusa arquivo acima do limite, e diz o limite", async () => {
    const { onChange, container } = montar({ maxSizeMb: 1 });
    soltar(container, arquivo("grande.pdf", 2));
    expect(
      await screen.findByText(/Arquivo muito grande \(máx 1 MB\): grande\.pdf/),
    ).toBeInTheDocument();
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("não duplica o mesmo arquivo — mesmo nome e mesmo tamanho", async () => {
    const jaEscolhido = arquivo("laudo.pdf");
    const { onChange } = montar({ files: [jaEscolhido] });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, arquivo("laudo.pdf"));
    expect(onChange).toHaveBeenCalledWith([jaEscolhido]);
  });

  it("corta no limite de arquivos em vez de estourar", async () => {
    const cheio = Array.from({ length: 10 }, (_, i) => arquivo(`f${i}.pdf`));
    const { onChange } = montar({ files: cheio, maxFiles: 10 });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, arquivo("extra.pdf"));
    expect(onChange.mock.calls[0][0]).toHaveLength(10);
  });

  it("limpa o valor do input, para o mesmo arquivo poder ser escolhido de novo", async () => {
    montar();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, arquivo("laudo.pdf"));
    // Sem isto, escolher o mesmo arquivo duas vezes seguidas não dispara
    // `change` — o valor não mudou, e a segunda tentativa some em silêncio.
    expect(input.value).toBe("");
  });

  // ── Arrastar e soltar, que já existia e continua ──────────────────────

  it("aceita arquivo solto na zona", () => {
    const { onChange, container } = montar();
    const solto = arquivo("solto.pdf");
    soltar(container, solto);
    expect(onChange).toHaveBeenCalledWith([solto]);
  });

  it("desabilitado não aceita nada, nem por arrastar", () => {
    const { onChange, container } = montar({ disabled: true });
    soltar(container, arquivo("solto.pdf"));
    expect(onChange).not.toHaveBeenCalled();
  });

  // ── A lista do que foi escolhido ──────────────────────────────────────

  it("lista o escolhido com nome e tamanho, e deixa remover", async () => {
    const a = arquivo("laudo.pdf", 2.5);
    const { onChange } = montar({ files: [a] });
    expect(screen.getByText("laudo.pdf")).toBeInTheDocument();
    expect(screen.getByText("2.5 MB")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Remover laudo.pdf" }));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("não usa cor cravada", () => {
    const { container } = montar({ files: [arquivo("x.pdf")] });
    expect(container.innerHTML).not.toMatch(/slate-\d/);
    expect(container.innerHTML).not.toMatch(/text-primary\b/);
  });
});
