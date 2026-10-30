import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useCarga } from "../../lib/useCarga";

/** Uma promessa que o caso resolve ou rejeita quando quiser. */
function adiada<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promessa = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promessa, resolve, reject };
}

/** Um erro no formato do axios, com o `detail` da API. */
function erroDaApi(status: number, detail: string) {
  return Object.assign(new Error("falhou"), {
    isAxiosError: true,
    response: { status, data: { detail } },
  });
}

describe("useCarga", () => {
  it("resposta atrasada do período anterior não sobrescreve o período atual", async () => {
    const antiga = adiada<string>();
    const nova = adiada<string>();
    const carregar = vi.fn()
      .mockReturnValueOnce(antiga.promessa)
      .mockReturnValueOnce(nova.promessa);

    const { result, rerender } = renderHook(
      ({ chave }) => useCarga(() => carregar(), chave),
      { initialProps: { chave: "setembro" } },
    );
    rerender({ chave: "outubro" });

    // A nova chega primeiro; a antiga, depois. Sem a guarda, a antiga
    // venceria por ter chegado por último.
    await act(async () => nova.resolve("dados de outubro"));
    await act(async () => antiga.resolve("dados de setembro"));

    expect(result.current.fase).toBe("pronto");
    expect(result.current.dados).toBe("dados de outubro");
  });

  it("falha antiga também é descartada: não pinta erro sobre o período novo", async () => {
    const antiga = adiada<string>();
    const carregar = vi.fn()
      .mockReturnValueOnce(antiga.promessa)
      .mockResolvedValueOnce("ok");

    const { result, rerender } = renderHook(
      ({ chave }) => useCarga(() => carregar(), chave),
      { initialProps: { chave: "a" } },
    );
    rerender({ chave: "b" });
    await waitFor(() => expect(result.current.fase).toBe("pronto"));
    await act(async () => antiga.reject(erroDaApi(500, "x")));

    expect(result.current.fase).toBe("pronto");
    expect(result.current.erro).toBeNull();
  });

  it("dado do período anterior some enquanto o novo carrega", async () => {
    const segunda = adiada<string>();
    const carregar = vi.fn()
      .mockResolvedValueOnce("antigo")
      .mockReturnValueOnce(segunda.promessa);

    const { result, rerender } = renderHook(
      ({ chave }) => useCarga(() => carregar(), chave),
      { initialProps: { chave: "a" } },
    );
    await waitFor(() => expect(result.current.dados).toBe("antigo"));

    rerender({ chave: "b" });
    expect(result.current.fase).toBe("carregando");
    expect(result.current.dados).toBeNull();
  });

  it("falha traz o texto da API e nenhum dado — nunca um valor inventado", async () => {
    const { result } = renderHook(() =>
      useCarga(() => Promise.reject(erroDaApi(422, "A data final não pode estar no futuro.")), "k"),
    );
    await waitFor(() => expect(result.current.fase).toBe("falha"));
    expect(result.current.erro).toBe("A data final não pode estar no futuro.");
    expect(result.current.dados).toBeNull();
  });

  it("sem resposta da API, usa a mensagem padrão de quem chama", async () => {
    const { result } = renderHook(() =>
      useCarga(() => Promise.reject(new Error("boom")), "k", "Não foi possível carregar X."),
    );
    await waitFor(() => expect(result.current.fase).toBe("falha"));
    expect(result.current.erro).toBe("Não foi possível carregar X.");
  });

  it("Tentar de novo pede outra vez e limpa o erro quando dá certo", async () => {
    const carregar = vi.fn()
      .mockRejectedValueOnce(erroDaApi(500, "Erro interno"))
      .mockResolvedValueOnce("recuperado");

    const { result } = renderHook(() => useCarga(() => carregar(), "k"));
    await waitFor(() => expect(result.current.fase).toBe("falha"));

    act(() => result.current.tentarDeNovo());
    await waitFor(() => expect(result.current.fase).toBe("pronto"));
    expect(result.current.erro).toBeNull();
    expect(result.current.dados).toBe("recuperado");
    expect(carregar).toHaveBeenCalledTimes(2);
  });

  it("carga desligada (null) não pede nada e não guarda dado", async () => {
    const carregar = vi.fn().mockResolvedValue("x");
    const { result, rerender } = renderHook(
      ({ ligado }) => useCarga(ligado ? () => carregar() : null, "k"),
      { initialProps: { ligado: true } },
    );
    await waitFor(() => expect(result.current.dados).toBe("x"));

    rerender({ ligado: false });
    expect(result.current.fase).toBe("ocioso");
    expect(result.current.dados).toBeNull();
    expect(carregar).toHaveBeenCalledTimes(1);
  });

  it("re-render com a mesma chave não pede de novo", async () => {
    const carregar = vi.fn().mockResolvedValue("x");
    const { result, rerender } = renderHook(() => useCarga(() => carregar(), "fixa"));
    await waitFor(() => expect(result.current.fase).toBe("pronto"));
    rerender();
    rerender();
    expect(carregar).toHaveBeenCalledTimes(1);
  });
});
