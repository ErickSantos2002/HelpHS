/**
 * Utilidades de cor para elementos que usam a cor escolhida pelo usuário
 * (etiquetas, eventos da agenda) como fundo sólido.
 */

const LIGHT = "#ffffff";
const DARK = "#0f172a";

function parseHex(value: string): { r: number; g: number; b: number } | null {
  const hex = value.trim().replace(/^#/, "");
  const full =
    hex.length === 3
      ? hex
          .split("")
          .map((c) => c + c)
          .join("")
      : hex;

  if (!/^[0-9a-fA-F]{6}$/.test(full)) return null;

  return {
    r: parseInt(full.slice(0, 2), 16),
    g: parseInt(full.slice(2, 4), 16),
    b: parseInt(full.slice(4, 6), 16),
  };
}

/**
 * Devolve branco ou quase-preto, o que tiver mais contraste sobre `background`.
 * Usa luminância relativa (WCAG) — sem isso, uma etiqueta amarela com texto
 * branco fica ilegível.
 */
export function readableTextColor(background: string): string {
  const rgb = parseHex(background);
  if (!rgb) return LIGHT;

  const channel = (value: number): number => {
    const c = value / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };

  const luminance =
    0.2126 * channel(rgb.r) + 0.7152 * channel(rgb.g) + 0.0722 * channel(rgb.b);

  return luminance > 0.45 ? DARK : LIGHT;
}
