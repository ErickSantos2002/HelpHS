import type { AxiosError } from "axios";

/**
 * Os campos que um 422 da API recusou, com o motivo de cada um.
 *
 * O backend monta o 422 como `{"detail": [{"field": "category", "message":
 * "..."}]}` (backend/app/core/exceptions.py). O `getApiError` junta as
 * mensagens num texto só, e isso basta para um toast; um formulário precisa
 * saber também QUAL campo foi — para marcá-lo e dizer onde corrigir.
 *
 * `field` pode vir composto (`equipment_ids.0`): o que importa ao formulário é
 * o primeiro segmento. `{loc, msg}`, o formato cru do FastAPI, segue aceito.
 *
 * Mora fora de `apiError.ts` de propósito: é autossuficiente, e por isso entra
 * em qualquer linha de release sem arrastar outras mudanças daquele arquivo.
 */
export interface ErroDeCampo {
  campo: string;
  mensagem: string;
}

/**
 * Sinais de texto que é diagnóstico do servidor, não mensagem para a pessoa.
 *
 * O `apiError.ts` só reconhece o traceback; aqui a lista é mais larga porque o
 * formulário passou a mostrar o motivo da API (INC-01), e um vazamento futuro
 * — handler novo, proxy, ORM — não pode virar texto na frente do cliente.
 * Cada padrão é de coisa que não aparece em mensagem escrita em português para
 * gente: SQL em maiúsculas, quadro de pilha, nome de biblioteca, HTML, URL de
 * conexão e endereço IP.
 */
const SINAIS_DE_TEXTO_INTERNO: readonly RegExp[] = [
  /Traceback \(most recent call last\)/,
  /\bFile "[^"]+", line \d+/,
  /\b(?:SELECT|INSERT|UPDATE|DELETE)\b[\s\S]*\b(?:FROM|INTO|SET|WHERE)\b/,
  /\b(?:sqlalchemy|asyncpg|psycopg2?|pydantic_core|starlette|uvicorn|alembic)\b/i,
  /\b\w+(?:Error|Exception):/,
  /<\s*(?:!doctype|html|head|body|script|title)\b/i,
  /\b[a-z][a-z0-9+.-]*:\/\/[^\s/@]+@/i,
  /\b(?:postgres(?:ql)?|redis|mysql|amqp)(?:\+\w+)?:\/\//i,
  /\b(?:\d{1,3}\.){3}\d{1,3}\b/,
];

/** Texto de servidor que não é para a pessoa ler. */
export function pareceInterno(texto: string): boolean {
  return SINAIS_DE_TEXTO_INTERNO.some((sinal) => sinal.test(texto));
}

function campoDoItem(item: Record<string, unknown>): string | null {
  if (typeof item.field === "string" && item.field.trim()) {
    return item.field.trim().split(".")[0];
  }
  if (Array.isArray(item.loc)) {
    const partes = item.loc.filter((p) => p !== "body" && p !== "query" && p !== "path");
    if (typeof partes[0] === "string") return partes[0];
  }
  return null;
}

function mensagemDoItem(item: Record<string, unknown>): string | null {
  for (const candidato of [item.message, item.msg]) {
    if (typeof candidato === "string" && candidato.trim() && !pareceInterno(candidato)) {
      return candidato.trim();
    }
  }
  return null;
}

/** Um por campo, na ordem em que chegaram; vazio se não for um 422 de campos. */
export function errosDeCampo(err: unknown): ErroDeCampo[] {
  const resposta = (err as AxiosError<{ detail?: unknown }>)?.response;
  if (resposta?.status !== 422) return [];
  const detail = resposta.data && typeof resposta.data === "object" ? resposta.data.detail : undefined;
  if (!Array.isArray(detail)) return [];

  const vistos = new Map<string, string>();
  for (const item of detail) {
    if (!item || typeof item !== "object") continue;
    const campo = campoDoItem(item as Record<string, unknown>);
    const mensagem = mensagemDoItem(item as Record<string, unknown>);
    if (campo && mensagem && !vistos.has(campo)) vistos.set(campo, mensagem);
  }
  return [...vistos].map(([campo, mensagem]) => ({ campo, mensagem }));
}
