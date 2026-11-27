import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../services/productService", () => ({ getProducts: vi.fn() }));
vi.mock("../../services/equipmentService", () => ({ getMyEquipment: vi.fn() }));
vi.mock("../../services/attachmentService", () => ({ uploadAttachments: vi.fn() }));
vi.mock("../../services/ticketService", () => ({
  createTicket: vi.fn(),
  getTicket: vi.fn(),
  updateTicket: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { toast } from "sonner";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import TicketFormPage from "../../pages/tickets/TicketFormPage";
import { getMyEquipment } from "../../services/equipmentService";
import { getProducts } from "../../services/productService";
import { createTicket, getTicket, updateTicket } from "../../services/ticketService";

/**
 * INC-01 — o que acontece quando a API recusa o chamado.
 *
 * Em 27/11/2026 um cliente escolheu "Outro", a API respondeu 422 apontando o
 * campo `category`, e a tela mostrou "Erro ao salvar o chamado. Tente
 * novamente." — o `catch` jogava fora o status e o motivo. Tentar de novo dava
 * o mesmo erro, para sempre, e nem o cliente nem o suporte sabiam por quê.
 *
 * O que estes casos prendem:
 *
 *   - o 422 diz QUAL campo recusou, no alerta e no próprio campo;
 *   - 500, rede e erro desconhecido têm mensagem segura, sem detalhe interno;
 *   - o que a pessoa preencheu continua lá para ela corrigir;
 *   - o aviso velho some quando ela avança de novo, e o do campo some quando
 *     ela corrige o campo;
 *   - o alerta é o único aviso — nada de toast repetindo a mesma falha;
 *   - um clique duplo não abre dois chamados, e nada é reenviado sozinho.
 */

const PHOEBUS = { id: "p2", name: "Phoebus", description: null, version: null, is_active: true };

const TITULO = "CONFIGURAR";
const DESCRICAO = "configurar leitor de crachas EXTERNO  na identificação RFDI";

/** A frase que a pessoa lê quando a API recusa a categoria. */
const CATEGORIA_INDISPONIVEL =
  "A categoria selecionada não está disponível. Selecione uma das categorias válidas.";

/** O 422 exatamente como `backend/app/core/exceptions.py` o monta para um enum. */
function erro422(
  field = "category",
  message = "Valor inválido. Opções: 'hardware', 'software', 'network', 'access', 'email', 'security' or 'general'",
) {
  return { response: { status: 422, data: { detail: [{ field, message }] } } };
}

function montar(rota = "/tickets/new") {
  render(
    <MemoryRouter initialEntries={[rota]}>
      <Routes>
        <Route path="/tickets/new" element={<TicketFormPage />} />
        <Route path="/tickets/:id/edit" element={<TicketFormPage />} />
        <Route path="/tickets/:id" element={<p>detalhe do chamado</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function preencherERevisar(categoria = "Geral") {
  montar();
  await waitFor(() => expect(screen.getByLabelText("Título *")).toBeInTheDocument());
  fireEvent.change(screen.getByLabelText("Título *"), { target: { value: TITULO } });
  fireEvent.change(screen.getByLabelText("Descrição *"), { target: { value: DESCRICAO } });
  fireEvent.click(screen.getByRole("radio", { name: categoria }));
  fireEvent.click(screen.getByRole("button", { name: "Revisar e enviar" }));
  await screen.findByRole("button", { name: "Confirmar e enviar" });
}

async function confirmar() {
  fireEvent.click(screen.getByRole("button", { name: "Confirmar e enviar" }));
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getProducts).mockResolvedValue({ items: [PHOEBUS], total: 1 } as never);
  vi.mocked(getMyEquipment).mockResolvedValue([] as never);
});

describe("TicketFormPage — a criação que dá certo", () => {
  it("abrir chamado em 'Geral' manda `general` e vai para o chamado criado", async () => {
    vi.mocked(createTicket).mockResolvedValue({ id: "t9" } as never);
    await preencherERevisar("Geral");
    await confirmar();

    expect(await screen.findByText("detalhe do chamado")).toBeInTheDocument();
    expect(createTicket).toHaveBeenCalledTimes(1);
    expect(createTicket).toHaveBeenCalledWith(
      expect.objectContaining({ title: TITULO, description: DESCRICAO, category: "general" }),
    );
  });

  it("clique duplo em 'Confirmar e enviar' abre UM chamado", async () => {
    let resolver: (v: unknown) => void = () => {};
    vi.mocked(createTicket).mockReturnValue(new Promise((r) => (resolver = r)) as never);
    await preencherERevisar();

    const botao = screen.getByRole("button", { name: "Confirmar e enviar" });
    fireEvent.click(botao);
    fireEvent.click(botao);
    fireEvent.click(botao);

    await act(async () => resolver({ id: "t9" }));
    expect(await screen.findByText("detalhe do chamado")).toBeInTheDocument();
    expect(createTicket).toHaveBeenCalledTimes(1);
  });
});

describe("TicketFormPage — quando a API recusa (INC-01)", () => {
  it("422 em `category` diz o campo no alerta e no próprio campo", async () => {
    vi.mocked(createTicket).mockRejectedValue(erro422());
    await preencherERevisar();
    await confirmar();

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Não foi possível salvar o chamado.");
    expect(alerta).toHaveTextContent("Categoria");
    expect(alerta).not.toHaveTextContent("Erro ao salvar o chamado. Tente novamente.");

    // O campo fica marcado inválido, com a frase da pessoa ao lado.
    const grupo = screen.getByRole("group", { name: "Categoria" });
    expect(screen.getByText(CATEGORIA_INDISPONIVEL)).toBeInTheDocument();
    expect(within(grupo).getAllByRole("radio")[0]).toHaveAttribute("aria-invalid", "true");
  });

  it("a recusa da categoria fala português, e não a lista crua do enum", async () => {
    // O backend responde "Valor inválido. Opções: 'hardware', … or 'general'":
    // útil para quem lê a API, ilegível para quem abre o chamado.
    vi.mocked(createTicket).mockRejectedValue(erro422());
    await preencherERevisar();
    await confirmar();
    await screen.findByRole("alert");

    expect(screen.queryByText(/Opções:|'hardware'|or 'general'|Input should be/)).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("'general'");
    expect(screen.getByText(CATEGORIA_INDISPONIVEL)).toBeInTheDocument();
  });

  it("os outros campos mantêm o motivo do servidor, que é útil", async () => {
    vi.mocked(createTicket).mockRejectedValue(
      erro422("description", "A descrição deve ter pelo menos 10 caracteres."),
    );
    await preencherERevisar();
    await confirmar();

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Revise o campo: Descrição.");
    expect(screen.getByText("A descrição deve ter pelo menos 10 caracteres.")).toBeInTheDocument();
  });

  it("o que a pessoa preencheu continua lá para corrigir", async () => {
    vi.mocked(createTicket).mockRejectedValue(erro422());
    await preencherERevisar();
    await confirmar();
    await screen.findByRole("alert");

    // Volta ao formulário, com os valores intactos.
    expect(screen.getByText("Formulário")).toHaveAttribute("aria-current", "step");
    expect(screen.getByLabelText("Título *")).toHaveValue(TITULO);
    expect(screen.getByLabelText("Descrição *")).toHaveValue(DESCRICAO);
    expect(screen.getByRole("radio", { name: "Geral" })).toBeChecked();
  });

  it("corrigir o campo apaga o aviso dele, e avançar apaga o alerta velho", async () => {
    vi.mocked(createTicket).mockRejectedValue(erro422());
    await preencherERevisar();
    await confirmar();
    await screen.findByRole("alert");

    expect(screen.getByText(CATEGORIA_INDISPONIVEL)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Hardware" }));
    await waitFor(() => expect(screen.queryByText(CATEGORIA_INDISPONIVEL)).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Revisar e enviar" }));
    await screen.findByRole("button", { name: "Confirmar e enviar" });
    // Na revisão, o aviso da tentativa anterior não fica fingindo ser atual.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("422 de campo que a tela não tem cai no motivo do servidor, sem inventar campo", async () => {
    vi.mocked(createTicket).mockRejectedValue(erro422("campo", "Requisição inválida."));
    await preencherERevisar();
    await confirmar();

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Não foi possível salvar o chamado. Requisição inválida.");
  });

  it("500 dá mensagem segura, e nada do corpo cru", async () => {
    vi.mocked(createTicket).mockRejectedValue({
      response: { status: 500, data: "Internal Server Error" },
    });
    await preencherERevisar();
    await confirmar();

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent(
      "Não foi possível salvar o chamado. Erro interno no servidor. Tente novamente em instantes.",
    );
    expect(alerta).not.toHaveTextContent("Internal Server Error");
  });

  it("traceback vazado no `detail` não chega à tela", async () => {
    vi.mocked(createTicket).mockRejectedValue({
      response: {
        status: 500,
        data: {
          detail:
            'Traceback (most recent call last): sqlalchemy.exc.DBAPIError: SELECT * FROM tickets WHERE category = $1',
        },
      },
    });
    await preencherERevisar();
    await confirmar();

    const alerta = await screen.findByRole("alert");
    expect(alerta).not.toHaveTextContent(/Traceback|SELECT|sqlalchemy/);
    expect(alerta).toHaveTextContent("Erro interno no servidor");
  });

  it("sem conexão diz que o servidor não respondeu", async () => {
    vi.mocked(createTicket).mockRejectedValue({ request: {}, message: "Network Error" });
    await preencherERevisar();
    await confirmar();

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Não foi possível falar com o servidor");
  });

  it("erro que não é da API mantém a mensagem genérica de antes", async () => {
    vi.mocked(createTicket).mockRejectedValue(new TypeError("x is undefined"));
    await preencherERevisar();
    await confirmar();

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Erro ao salvar o chamado. Tente novamente.");
    expect(alerta).not.toHaveTextContent("x is undefined");
  });

  it("401 que o interceptor não salvou diz que a sessão expirou", async () => {
    // O refresh e o redirecionamento são do interceptor (services/api.ts), que
    // esta mudança não toca; aqui só o texto do que sobra para a tela.
    vi.mocked(createTicket).mockRejectedValue({ response: { status: 401, data: {} } });
    await preencherERevisar();
    await confirmar();

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Sua sessão expirou");
  });

  it("a falha aparece UMA vez: no alerta, sem toast repetindo", async () => {
    vi.mocked(createTicket).mockRejectedValue(erro422());
    await preencherERevisar();
    await confirmar();
    await screen.findByRole("alert");

    expect(toast.error).not.toHaveBeenCalled();
    expect(screen.getAllByRole("alert")).toHaveLength(1);
  });

  it("nada é reenviado sozinho depois da falha", async () => {
    vi.mocked(createTicket).mockRejectedValue(erro422());
    await preencherERevisar();
    await confirmar();
    await screen.findByRole("alert");

    await new Promise((r) => setTimeout(r, 50));
    expect(createTicket).toHaveBeenCalledTimes(1);
  });

  it("a edição recebe o mesmo tratamento", async () => {
    vi.mocked(getTicket).mockResolvedValue({
      id: "t1",
      protocol: "HS-2026-0042",
      title: "Chamado existente",
      category: "hardware",
      product_id: null,
      equipments: [],
    } as never);
    vi.mocked(updateTicket).mockRejectedValue(erro422("title", "Título muito longo."));
    montar("/tickets/t1/edit");
    await waitFor(() => expect(screen.getByLabelText("Título *")).toHaveValue("Chamado existente"));
    fireEvent.change(screen.getByLabelText("Descrição *"), { target: { value: "Descrição nova do chamado." } });
    fireEvent.click(screen.getByRole("button", { name: "Revisar e enviar" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirmar e enviar" }));

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Título");
    expect(screen.getByText("Título muito longo.")).toBeInTheDocument();
    expect(screen.getByLabelText("Título *")).toHaveValue("Chamado existente");
  });
});

/**
 * Nenhum detalhe interno chega à tela (revisão da Fase 4).
 *
 * O backend de hoje não manda nada disto — o 500 dele é texto puro, e o 422 só
 * traz mensagem traduzida. Estes casos existem porque o alerta passou a mostrar
 * o motivo da API, e um vazamento futuro (handler novo, proxy, ORM) não pode
 * virar texto na frente do cliente. O que se espera em cada um é a frase do
 * status, ou a genérica, e nunca o pedaço técnico.
 */
describe("TicketFormPage — nenhum detalhe interno chega à tela", () => {
  const casos: Array<[string, number, unknown, RegExp]> = [
    ["SQL sem a palavra Traceback", 500,
      { detail: "(sqlalchemy.exc.ProgrammingError) SELECT id FROM tickets WHERE category = 'other'" },
      /SELECT|sqlalchemy|tickets WHERE/],
    ["quadro de pilha Python", 500,
      { detail: 'File "/app/app/routers/tickets.py", line 680, in list_tickets' },
      /routers|line 680|\.py/],
    ["nome de exceção do driver", 500,
      { detail: "asyncpg.exceptions.InvalidTextRepresentationError: invalid input value for enum" },
      /asyncpg|InvalidText|enum/],
    ["URL de conexão com senha", 500,
      { detail: "could not connect to postgresql://helphs:segredo@10.0.0.5:5432/helphs" },
      /postgresql|segredo|10\.0\.0\.5/],
    ["HTML cru do proxy dentro do detail", 502,
      { detail: "<html><head><title>502 Bad Gateway</title></head><body>nginx</body></html>" },
      /<html|nginx|Bad Gateway/],
    ["traceback dentro de um item do 422", 422,
      { detail: [{ field: "campo", message: "Traceback (most recent call last): KeyError" }] },
      /Traceback|KeyError/],
    ["SQL dentro de um item do 422 de campo da tela", 422,
      { detail: [{ field: "product_id", message: "UPDATE tickets SET product_id = NULL WHERE id = 1" }] },
      /UPDATE|SET product_id/],
  ];

  it.each(casos)("%s", async (_nome, status, data, proibido) => {
    vi.mocked(createTicket).mockRejectedValue({ response: { status, data } });
    await preencherERevisar();
    await confirmar();

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Não foi possível salvar o chamado");
    expect(document.body).not.toHaveTextContent(proibido);
  });

  it.each([
    ["corpo em texto puro", "Internal Server Error"],
    ["corpo nulo", null],
    ["detail de tipo inesperado", { detail: 42 }],
    ["página HTML no lugar do JSON", "<!DOCTYPE html><html><body>erro</body></html>"],
  ])("corpo inesperado (%s) dá a frase do status", async (_nome, data) => {
    vi.mocked(createTicket).mockRejectedValue({ response: { status: 500, data } });
    await preencherERevisar();
    await confirmar();

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Erro interno no servidor. Tente novamente em instantes.");
    expect(alerta).not.toHaveTextContent(/DOCTYPE|<html|Internal Server Error|42/);
  });

  it("campo com nome de propriedade do Object não vira rótulo de função", async () => {
    vi.mocked(createTicket).mockRejectedValue(erro422("constructor", "Valor inválido."));
    await preencherERevisar();
    await confirmar();

    const alerta = await screen.findByRole("alert");
    expect(alerta).not.toHaveTextContent(/function|native code|Revise o campo/);
    expect(alerta).toHaveTextContent("Não foi possível salvar o chamado. Valor inválido.");
  });

  it("mensagem legítima do backend continua aparecendo inteira", async () => {
    // Recusa de negócio, em português, com número e aspas: nada disso é técnico.
    const motivo = "Este chamado já foi encerrado e não aceita alterações. Abra um novo chamado.";
    vi.mocked(createTicket).mockRejectedValue({ response: { status: 409, data: { detail: motivo } } });
    await preencherERevisar();
    await confirmar();

    expect(await screen.findByRole("alert")).toHaveTextContent(`Não foi possível salvar o chamado. ${motivo}`);
  });

  it("403 de segundo fator exigido mostra o motivo, sem enfraquecer nada", async () => {
    // A exigência de MFA é do backend e do interceptor; a tela só não pode
    // engolir nem deformar o motivo.
    const motivo = "Ative a verificação em duas etapas para continuar.";
    vi.mocked(createTicket).mockRejectedValue({ response: { status: 403, data: { detail: motivo } } });
    await preencherERevisar();
    await confirmar();

    expect(await screen.findByRole("alert")).toHaveTextContent(motivo);
    expect(createTicket).toHaveBeenCalledTimes(1);
  });

  it("depois de um 500, o que a pessoa preencheu continua no formulário", async () => {
    vi.mocked(createTicket).mockRejectedValue({ response: { status: 500, data: "Internal Server Error" } });
    await preencherERevisar("Geral");
    await confirmar();
    await screen.findByRole("alert");

    expect(screen.getByLabelText("Título *")).toHaveValue(TITULO);
    expect(screen.getByLabelText("Descrição *")).toHaveValue(DESCRICAO);
    expect(screen.getByRole("radio", { name: "Geral" })).toBeChecked();
  });
});
