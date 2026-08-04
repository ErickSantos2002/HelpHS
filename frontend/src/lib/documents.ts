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
