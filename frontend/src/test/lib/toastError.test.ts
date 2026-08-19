import { describe, it, expect, vi, beforeEach } from "vitest";
import { toastApiError } from "../../lib/toastError";
import { toast } from "sonner";

// É o caminho de erro usado pela aplicação inteira: cada ação que falha passa
// por aqui antes de virar toast. O sonner é mockado porque o que está sob
// teste é a montagem título/descrição, não a renderização.
vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
  },
}));

const mockToastError = vi.mocked(toast.error);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("toastApiError", () => {
  it("mostra o título da ação e o motivo do servidor como descrição", () => {
    const err = {
      response: { status: 409, data: { detail: "Este número de série já está em uso." } },
    };

    toastApiError(err, "Não foi possível cadastrar o equipamento.");

    expect(mockToastError).toHaveBeenCalledWith(
      "Não foi possível cadastrar o equipamento.",
      { description: "Este número de série já está em uso." },
    );
  });

  it("sem motivo conhecido, mostra só o título — sem descrição vazia", () => {
    // Passar `{ description: undefined }` renderiza diferente de não passar
    // nada; o contrato é omitir o objeto de opções por inteiro.
    toastApiError(new Error("estado inesperado"), "Não foi possível salvar.");

    expect(mockToastError).toHaveBeenCalledWith("Não foi possível salvar.", undefined);
  });
});
