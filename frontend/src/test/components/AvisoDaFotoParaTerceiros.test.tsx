import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { act } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const sessao = vi.hoisted(() => ({
  user: { id: "u-teste-1", role: "client", name: "Pessoa Teste" } as {
    id: string;
    role: string;
    name: string;
  } | null,
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: sessao.user }),
}));
vi.mock("../../services/userService", () => ({
  getExibicaoDaFoto: vi.fn(),
  setExibicaoDaFoto: vi.fn(),
}));

import { AvisoDaFotoParaTerceiros } from "../../components/layout/AvisoDaFotoParaTerceiros";
import { avisaQueAExibicaoMudou } from "../../lib/exibicaoDaFoto";
import * as userService from "../../services/userService";
import type { ExibicaoDaFoto } from "../../services/userService";

/**
 * O aviso de lançamento: não bloqueia, não autoriza ao fechar, e só aparece
 * quando há escolha a fazer. Versão e textos de TESTE.
 */

const DESLIGADA: ExibicaoDaFoto = {
  autorizada: false,
  disponivel: true,
  aviso: { versao: "TESTE-AVISO-01", rotulo: "TESTE — rótulo", explicacao: ["TESTE"] },
};

function montar(estado: ExibicaoDaFoto | Error = DESLIGADA, rota = "/dashboard") {
  if (estado instanceof Error) {
    vi.mocked(userService.getExibicaoDaFoto).mockRejectedValue(estado);
  } else {
    vi.mocked(userService.getExibicaoDaFoto).mockResolvedValue(estado);
  }
  const abrirChamado = vi.fn();
  const resultado = render(
    <MemoryRouter initialEntries={[rota]}>
      <AvisoDaFotoParaTerceiros />
      <Routes>
        <Route
          path="*"
          element={
            <button type="button" onClick={abrirChamado}>
              Abrir chamado
            </button>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
  return { ...resultado, abrirChamado };
}

const TITULO = "Novidade: sua foto para outras pessoas";

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  sessao.user = { id: "u-teste-1", role: "client", name: "Pessoa Teste" };
});

describe("AvisoDaFotoParaTerceiros", () => {
  it("explica a mudança, aponta para o perfil e não bloqueia a tela", async () => {
    const { abrirChamado } = montar();

    expect(await screen.findByText(TITULO)).toBeInTheDocument();
    expect(screen.getByText(/É opcional e começa desligado/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver a opção no meu perfil" })).toHaveAttribute(
      "href",
      "/profile#foto-para-outras-pessoas",
    );
    // Não é diálogo nem interruptor: nada a responder para seguir usando.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Abrir chamado" }));
    expect(abrirChamado).toHaveBeenCalledTimes(1);
  });

  it("fechar esconde o aviso e NÃO autoriza nada", async () => {
    const { unmount } = montar();
    await screen.findByText(TITULO);

    await userEvent.click(screen.getByRole("button", { name: "Fechar" }));

    expect(screen.queryByText(TITULO)).not.toBeInTheDocument();
    expect(userService.setExibicaoDaFoto).not.toHaveBeenCalled();

    unmount();
    montar();
    await waitFor(() => expect(userService.getExibicaoDaFoto).toHaveBeenCalledTimes(2));
    expect(screen.queryByText(TITULO)).not.toBeInTheDocument();
  });

  it("texto novo é novidade de novo; outra pessoa no mesmo navegador ainda vê", async () => {
    const { unmount } = montar();
    await userEvent.click(await screen.findByRole("button", { name: "Fechar" }));
    unmount();

    sessao.user = { id: "u-teste-2", role: "technician", name: "Outra" };
    const segundo = montar();
    expect(await screen.findByText(TITULO)).toBeInTheDocument();
    segundo.unmount();

    sessao.user = { id: "u-teste-1", role: "client", name: "Pessoa Teste" };
    montar({ ...DESLIGADA, aviso: { ...DESLIGADA.aviso!, versao: "TESTE-AVISO-02" } });
    expect(await screen.findByText(TITULO)).toBeInTheDocument();
  });

  it.each([
    ["quem já autorizou", { ...DESLIGADA, autorizada: true }],
    ["opção indisponível", { autorizada: false, disponivel: false, aviso: null }],
  ])("não aparece para %s", async (_, estado) => {
    montar(estado as ExibicaoDaFoto);
    await waitFor(() => expect(userService.getExibicaoDaFoto).toHaveBeenCalled());
    expect(screen.queryByText(TITULO)).not.toBeInTheDocument();
  });

  it("não aparece se a leitura falhar, e a tela segue funcionando", async () => {
    montar(new Error("rede"));
    await waitFor(() => expect(userService.getExibicaoDaFoto).toHaveBeenCalled());
    expect(screen.queryByText(TITULO)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Abrir chamado" })).toBeInTheDocument();
  });

  it("não aparece na página do perfil, onde a opção já está", async () => {
    montar(DESLIGADA, "/profile");
    await waitFor(() => expect(userService.getExibicaoDaFoto).toHaveBeenCalled());
    expect(screen.queryByText(TITULO)).not.toBeInTheDocument();
  });

  it("sai sozinho quando o perfil confirma a autorização", async () => {
    montar();
    await screen.findByText(TITULO);

    act(() => avisaQueAExibicaoMudou({ ...DESLIGADA, autorizada: true }));

    expect(screen.queryByText(TITULO)).not.toBeInTheDocument();
  });

  it("sem armazenamento local, fechar ainda funciona nesta visita", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("bloqueado");
    });
    try {
      montar();
      await userEvent.click(await screen.findByRole("button", { name: "Fechar" }));
      expect(screen.queryByText(TITULO)).not.toBeInTheDocument();
    } finally {
      setItem.mockRestore();
    }
  });
});
