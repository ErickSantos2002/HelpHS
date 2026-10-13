import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../services/attachmentService", async (importOriginal) => {
  // `tipoDePrevia` é regra pura e fica a de verdade; só a rede é falsa.
  const real = await importOriginal<typeof import("../../services/attachmentService")>();
  return { ...real, getAttachmentUrl: vi.fn(), downloadAttachment: vi.fn() };
});
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { toast } from "sonner";

import { AttachmentPreviewModal } from "../../components/tickets/AttachmentPreviewModal";
import {
  downloadAttachment,
  getAttachmentUrl,
  type Attachment,
} from "../../services/attachmentService";

function anexo(over: Partial<Attachment> = {}): Attachment {
  return {
    id: "a1",
    ticket_id: "t1",
    uploaded_by: "u9",
    uploaded_by_name: "Bruno Lima",
    uploaded_by_role: "technician",
    original_name: "foto.png",
    mime_type: "image/png",
    size_bytes: 2048,
    virus_scanned: true,
    virus_clean: true,
    created_at: "2026-10-09T17:03:00.000Z",
    ...over,
  };
}

/** O erro no formato que o axios entrega. */
function erroHttp(status: number) {
  return Object.assign(new Error(String(status)), { response: { status, data: {} } });
}

async function abre(a: Attachment | null, onClose = vi.fn()) {
  render(<AttachmentPreviewModal anexo={a} onClose={onClose} />);
  await act(async () => {});
  return onClose;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getAttachmentUrl).mockResolvedValue("/api/v1/files/tok?filename=x");
});

describe("AttachmentPreviewModal", () => {
  it("fechado quando não há anexo", async () => {
    await abre(null);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(getAttachmentUrl).not.toHaveBeenCalled();
  });

  it("mostra nome, autor, perfil e data/hora — a mesma linha da aba Anexos", async () => {
    await abre(anexo());
    expect(screen.getByRole("dialog", { name: "foto.png" })).toBeInTheDocument();
    expect(
      screen.getByText(/^Enviado por Bruno Lima \(Técnico\) · 09\/10\/2026/),
    ).toBeInTheDocument();
  });

  it("repete o selo de não verificado dentro do modal", async () => {
    await abre(anexo({ virus_scanned: false, virus_clean: false }));
    expect(screen.getByText("não verificado")).toBeInTheDocument();
  });

  it("imagem: pede o link ao backend e mostra no próprio modal", async () => {
    await abre(anexo());
    expect(getAttachmentUrl).toHaveBeenCalledWith("a1");
    const img = await screen.findByRole("img", { name: "foto.png" });
    expect(img).toHaveAttribute("src", "/api/v1/files/tok?filename=x");
  });

  it("enquanto o link não chega, diz que está carregando", async () => {
    vi.mocked(getAttachmentUrl).mockReturnValue(new Promise(() => {}));
    await abre(anexo());
    expect(screen.getByText("Carregando o anexo…")).toBeInTheDocument();
  });

  it("PDF abre num quadro dentro do modal", async () => {
    await abre(anexo({ original_name: "laudo.pdf", mime_type: "application/pdf" }));
    const quadro = await screen.findByTitle("Visualização de laudo.pdf");
    expect(quadro.tagName).toBe("IFRAME");
    expect(quadro).toHaveAttribute("src", "/api/v1/files/tok?filename=x");
  });

  it("formato sem prévia: não pede link nenhum e oferece só o download", async () => {
    await abre(anexo({ original_name: "planilha.xlsx" }));
    expect(getAttachmentUrl).not.toHaveBeenCalled();
    expect(screen.getByText(/não tem visualização no navegador/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Baixar planilha.xlsx" })).toBeEnabled();
  });

  it("anexo removido (404): diz que não está mais disponível e não oferece baixar", async () => {
    vi.mocked(getAttachmentUrl).mockRejectedValue(erroHttp(404));
    await abre(anexo());
    expect(await screen.findByText(/não está mais disponível/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Tentar de novo" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Baixar foto.png" })).toBeDisabled();
  });

  it("outra falha: oferece tentar de novo, e tentar pede um link novo", async () => {
    vi.mocked(getAttachmentUrl).mockRejectedValueOnce(erroHttp(500));
    await abre(anexo());
    expect(await screen.findByText("Não foi possível carregar o anexo.")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    });
    expect(getAttachmentUrl).toHaveBeenCalledTimes(2);
    expect(await screen.findByRole("img", { name: "foto.png" })).toBeInTheDocument();
  });

  it("a imagem que não carrega (arquivo sumido do disco, link vencido) vira aviso", async () => {
    await abre(anexo());
    fireEvent.error(await screen.findByRole("img", { name: "foto.png" }));
    expect(screen.getByText(/não pôde ser exibido/)).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "foto.png" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tentar de novo" })).toBeInTheDocument();
  });

  it("Baixar usa o mesmo download autorizado da lista", async () => {
    vi.mocked(downloadAttachment).mockResolvedValue();
    await abre(anexo());
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Baixar foto.png" }));
    });
    expect(downloadAttachment).toHaveBeenCalledWith("a1");
  });

  it("falha no download aparece como aviso, sem fechar o modal", async () => {
    vi.mocked(downloadAttachment).mockRejectedValue(erroHttp(500));
    await abre(anexo());
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Baixar foto.png" }));
    });
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("fecha pelo botão Fechar e pelo Escape", async () => {
    const onClose = await abre(anexo());
    fireEvent.click(screen.getByRole("button", { name: "Fechar" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("trocar de anexo descarta o link do anterior", async () => {
    const onClose = vi.fn();
    const { rerender } = render(<AttachmentPreviewModal anexo={anexo()} onClose={onClose} />);
    await screen.findByRole("img", { name: "foto.png" });

    vi.mocked(getAttachmentUrl).mockResolvedValue("/api/v1/files/outro?filename=y");
    rerender(
      <AttachmentPreviewModal anexo={anexo({ id: "a2", original_name: "outra.png" })} onClose={onClose} />,
    );
    const img = await screen.findByRole("img", { name: "outra.png" });
    expect(img).toHaveAttribute("src", "/api/v1/files/outro?filename=y");
    expect(getAttachmentUrl).toHaveBeenLastCalledWith("a2");
  });
});
