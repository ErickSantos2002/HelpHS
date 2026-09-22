import { fireEvent, screen, within } from "@testing-library/react";

/**
 * Os três gestos que um `SelectMenu` aceita, para os testes de página.
 *
 * O `<select>` nativo era manipulado por `userEvent.selectOptions` e por
 * `fireEvent.change` — os dois falam com o elemento nativo, e nenhum dos dois
 * funciona num painel suspenso. Aqui o gesto é o do usuário: abrir e clicar.
 *
 * Por que `fireEvent` e não `userEvent`: os casos de página já usam os dois, e
 * um deles (`TechnicianDashboard.test.tsx`) registra por escrito que trocou
 * para `fireEvent` por causa da carga da máquina. `fireEvent.click` basta
 * porque a opção reage a `onClick`.
 *
 * O painel vive num portal em `document.body`, então a busca é sempre pelo
 * `screen` — `within(campo)` não o alcança, e era assim que os casos liam as
 * `<option>` do nativo.
 */

/** O campo é o gatilho: mesmo papel do `<select>`, `role="combobox"`. */
export function campoDeMenu(nome: string | RegExp): HTMLElement {
  return screen.getByRole("combobox", { name: nome });
}

export function abrirMenu(campo: HTMLElement): HTMLElement {
  if (campo.getAttribute("aria-expanded") !== "true") fireEvent.click(campo);
  return screen.getByRole("listbox");
}

/** Os rótulos da lista, na ordem — o que `getAllByRole("option")` lia antes. */
export function opcoesDoMenu(campo: HTMLElement): string[] {
  const lista = abrirMenu(campo);
  return within(lista)
    .getAllByRole("option")
    .map((o) => o.textContent ?? "");
}

/** Abre e escolhe pelo RÓTULO — o `selectOptions` escolhia pelo valor. */
export function escolherNoMenu(campo: HTMLElement, rotulo: string | RegExp): void {
  const lista = abrirMenu(campo);
  fireEvent.click(within(lista).getByRole("option", { name: rotulo }));
}
