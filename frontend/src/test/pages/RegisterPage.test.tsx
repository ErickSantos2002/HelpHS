import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import RegisterPage from "../../pages/auth/RegisterPage";

/**
 * A caixa de aceite do cadastro nomeia dois documentos. Até 25/09 só a
 * política tinha página: "termos de uso" era texto solto, porque os Termos
 * não existiam. Estes casos prendem que a pessoa consegue abrir os DOIS antes
 * de declarar que leu — e sem perder o que já digitou.
 */
describe("RegisterPage — os documentos da caixa de aceite", () => {
  function monta() {
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>,
    );
  }

  it.each([
    ["termos de uso", "/termos"],
    ["política de privacidade", "/privacidade"],
  ])("o link \"%s\" abre %s em nova aba", (nome, destino) => {
    monta();
    const link = screen.getByRole("link", { name: nome });
    expect(link.getAttribute("href")).toBe(destino);
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("clicar no link dos termos não marca a caixa de aceite", async () => {
    // O link vive dentro do <label> da caixa: sem conter o clique, abrir o
    // documento contaria como aceitá-lo.
    monta();
    const caixa = screen.getByRole("checkbox");
    const link = screen.getByRole("link", { name: "termos de uso" });
    link.addEventListener("click", (e) => e.preventDefault());

    await userEvent.click(link);

    expect(caixa).not.toBeChecked();
  });
});
