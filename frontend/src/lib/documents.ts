/**
 * Validação de documentos brasileiros usados no cadastro do cliente.
 */

export function onlyDigits(value: string): string {
  return value.replace(/\D/g, "");
}

/** Valida CNPJ pelos dois dígitos verificadores. Aceita com ou sem máscara. */
export function isValidCnpj(value: string): boolean {
  const digits = onlyDigits(value);
  if (digits.length !== 14) return false;
  if (/^(\d)\1{13}$/.test(digits)) return false;

  const checkDigit = (length: number): number => {
    let weight = length - 7;
    let sum = 0;
    for (let i = 0; i < length; i++) {
      sum += Number(digits[i]) * weight;
      weight -= 1;
      if (weight < 2) weight = 9;
    }
    const rest = sum % 11;
    return rest < 2 ? 0 : 11 - rest;
  };

  return checkDigit(12) === Number(digits[12]) && checkDigit(13) === Number(digits[13]);
}

/** Valida CEP: exatamente 8 dígitos. Aceita com ou sem máscara. */
export function isValidCep(value: string): boolean {
  return onlyDigits(value).length === 8;
}

/**
 * Máscara de CNPJ para EXIBIÇÃO. O banco guarda 14 dígitos crus — a pontuação
 * é coisa de tela, nunca de armazenamento (`decisoes-e-regras.md`, e a
 * normalização das duas pontas em `backend/app/utils/documents.py`).
 *
 * Aceita valor já pontuado porque, até o backfill rodar, ainda existe linha
 * antiga com máscara em `companies.cnpj`. O que não tiver 14 dígitos volta
 * como veio: inventar máscara em cima de dado torto esconde o problema.
 */
export function formatCnpj(value: string | null | undefined): string {
  if (!value) return "";
  const digits = onlyDigits(value);
  if (digits.length !== 14) return value;
  return digits.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");
}

/**
 * Máscara PROGRESSIVA, para o `onChange` do campo de CNPJ — vai pontuando
 * conforme se digita e trava no 14º dígito.
 *
 * Diferente de `formatCnpj`, que só mascara valor completo para leitura. As
 * duas existem porque servem a momentos diferentes; o que não pode existir é
 * uma cópia por tela, como havia em `OnboardingPage` e `ProfilePage`.
 *
 * O valor mascarado é de tela: quem envia ao backend normaliza com
 * `onlyDigits` antes.
 */
export function maskCnpjInput(value: string): string {
  const digits = onlyDigits(value).slice(0, 14);
  return digits
    .replace(/^(\d{2})(\d)/, "$1.$2")
    .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
    .replace(/\.(\d{3})(\d)/, ".$1/$2")
    .replace(/(\d{4})(\d)/, "$1-$2");
}
