/**
 * Resolve o caminho de arquivo devolvido pela API para uma URL que o navegador
 * consiga abrir.
 *
 * A API devolve algo como `/api/v1/files/<token>`. Em produção o frontend está
 * num domínio e a API em outro, então um caminho relativo seria buscado no
 * domínio errado — daí o prefixo com a base configurada em VITE_API_URL.
 */

function apiBase(): string {
  return import.meta.env.VITE_API_URL ?? "/api/v1";
}

export function resolveFileUrl<T extends string | null | undefined>(
  path: T,
  base: string = apiBase(),
): T {
  if (!path) return path;
  // URL completa (http, https, data:) já está pronta
  if (/^[a-z][a-z0-9+.-]*:/i.test(path)) return path;

  const cleanBase = base.replace(/\/+$/, "");
  // A base normalmente já termina em /api/v1 e o caminho começa com /api/v1
  const suffix = path.startsWith("/api/v1")
    ? path.slice("/api/v1".length)
    : path.startsWith("/")
      ? path
      : `/${path}`;

  return `${cleanBase}${suffix}` as T;
}
