import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../services/authService", () => ({
  forgotPasswordApi: vi.fn(),
}));

import ForgotPasswordPage from "../../pages/auth/ForgotPasswordPage";
import { forgotPasswordApi } from "../../services/authService";

const mockForgot = vi.mocked(forgotPasswordApi);

const EMAIL = "cliente@empresa.com";

/** Os três textos aprovados para a tela depois do pedido (RS-03). */
const TITULO = "Confira seu e-mail";
const MENSAGEM =
  "Se houver uma conta ativa associada ao e-mail informado, você receberá instruções para redefinir sua senha.";
const AJUDA =
  "Não recebeu? Verifique a pasta de spam e confirme que informou o e-mail utilizado no cadastro. Se precisar, entre em contato com o suporte.";

function renderiza() {
  render(
    <MemoryRouter initialEntries={["/esqueci-senha"]}>
      <Routes>
        <Route path="/esqueci-senha" element={<ForgotPasswordPage />} />
        <Route path="/login" element={<p>Tela de acesso</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function pede(email = EMAIL) {
  await userEvent.type(screen.getByLabelText("E-mail"), email);
  await userEvent.click(screen.getByRole("button", { name: "Enviar link de recuperação" }));
}

/** Erro no formato do axios: resposta com status, `detail` e cabeçalhos. */
function erroDaApi(status: number, detail?: string, headers: Record<string, string> = {}) {
  return { request: {}, response: { status, data: detail ? { detail } : {}, headers } };
}

describe("ForgotPasswordPage — depois do pedido (RS-03)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("no 200 mostra a comunicação condicional aprovada", async () => {
    mockForgot.mockResolvedValue("mensagem neutra do servidor");
    renderiza();

    await pede();

    expect(mockForgot).toHaveBeenCalledWith(EMAIL);
    expect(await screen.findByRole("heading", { name: TITULO })).toBeInTheDocument();
    expect(screen.getByText(MENSAGEM)).toBeInTheDocument();
    expect(screen.getByText(AJUDA)).toBeInTheDocument();
  });

  /**
   * O 200 é a mesma resposta para conta ativa, inativa, inexistente e para o
   * e-mail que não é o do cadastro — a tela não sabe qual foi o caso, então
   * não pode dizer que mandou. Era o que fazia "não gerou e-mail nenhum"
   * parecer falha de entrega.
   */
  it("no 200 não afirma envio, nem prazo fixo, nem repete o endereço", async () => {
    mockForgot.mockResolvedValue("ok");
    renderiza();

    await pede();
    await screen.findByText(MENSAGEM);

    const tela = document.body.textContent ?? "";
    expect(tela).not.toMatch(/enviamos/i);
    expect(tela).not.toMatch(/foi enviad/i);
    expect(tela).not.toMatch(/1 hora/i);
    expect(tela).not.toMatch(/em instantes/i);
    expect(tela).not.toContain(EMAIL);
  });

  it("a mensagem é informativa, não um alerta de sucesso nem de erro", async () => {
    mockForgot.mockResolvedValue("ok");
    renderiza();

    await pede();

    const aviso = (await screen.findByText(MENSAGEM)).closest("[role]");
    expect(aviso).toHaveAttribute("role", "status");
    expect(aviso?.className).toContain("tint-info");
    expect(aviso?.className).not.toContain("tint-success");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("'tentar com outro e-mail' devolve o formulário", async () => {
    mockForgot.mockResolvedValue("ok");
    renderiza();

    await pede();
    await userEvent.click(await screen.findByRole("button", { name: "Tentar com outro e-mail" }));

    expect(screen.getByRole("heading", { name: "Esqueci minha senha" })).toBeInTheDocument();
    expect(screen.getByLabelText("E-mail")).toBeInTheDocument();
    expect(screen.queryByText(MENSAGEM)).toBeNull();
  });
});

describe("ForgotPasswordPage — erros", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("429 com Retry-After diz quantos minutos esperar e mantém o formulário", async () => {
    mockForgot.mockRejectedValue(
      erroDaApi(429, "Muitas tentativas.", { "retry-after": "540" }),
    );
    renderiza();

    await pede();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Muitas tentativas. Aguarde 9 minutos e tente novamente.",
    );
    expect(screen.getByLabelText("E-mail")).toHaveValue(EMAIL);
    expect(screen.queryByText(MENSAGEM)).toBeNull();
  });

  it("503 mostra o aviso do servidor em vez de prometer o e-mail", async () => {
    const detalhe =
      "A recuperação de senha por e-mail ainda não está disponível. Fale com o administrador para redefinir sua senha.";
    mockForgot.mockRejectedValue(erroDaApi(503, detalhe));
    renderiza();

    await pede();

    expect(await screen.findByRole("alert")).toHaveTextContent(detalhe);
    expect(screen.queryByRole("heading", { name: TITULO })).toBeNull();
    expect(screen.queryByText(MENSAGEM)).toBeNull();
  });

  it("erro de rede avisa da conexão e não passa para a tela de confirmação", async () => {
    mockForgot.mockRejectedValue({ request: {} });
    renderiza();

    await pede();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível falar com o servidor. Verifique sua conexão e tente de novo.",
    );
    expect(screen.queryByText(MENSAGEM)).toBeNull();
  });

  it("erro sem motivo conhecido usa o texto da própria tela", async () => {
    mockForgot.mockRejectedValue(new Error("falhou"));
    renderiza();

    await pede();

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Não foi possível enviar o e-mail. Tente novamente.");
    expect(screen.queryByText(MENSAGEM)).toBeNull();
  });

  it("o alerta de erro some ao tentar de novo", async () => {
    mockForgot.mockRejectedValueOnce(erroDaApi(500));
    mockForgot.mockResolvedValueOnce("ok");
    renderiza();

    await pede();
    expect(await screen.findByRole("alert")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Enviar link de recuperação" }));

    expect(await screen.findByText(MENSAGEM)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
