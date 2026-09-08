import type { SVGAttributes } from "react";
import { cn } from "../../lib/utils";

/**
 * Ícone de traço 24×24, de `DS/components/core/Icon.jsx`.
 *
 * Os traçados do pacote saíram do próprio HelpHS — `layout/Sidebar.tsx`,
 * `ui/Alert.tsx`, `ui/Modal.tsx` e `ui/SlaChip.tsx`. Este arquivo fecha a
 * volta: traz o conjunto de lá para cá como componente único, e é o destino das
 * 229 tags `<svg>` que ainda estão soltas pelas telas — a troca é das Fases
 * 11–16, uma tela por vez.
 *
 * Os **25 primeiros** vieram por extração do pacote, não digitados: 25 de 25
 * conferem caractere a caractere. Os que vêm depois deles não são do pacote, e
 * o bloco onde começam diz de onde vieram. A distinção importa: um dia o
 * pacote pode ganhar um nome igual com traçado diferente, e é preciso saber
 * qual dos dois é a cópia.
 */
/**
 * Os 25 do pacote. **Não editar à mão** — é cópia, e o hash prende.
 */
export const ICON_PATHS_PACOTE = {
  dashboard:
    "M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6",
  ticket:
    "M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z",
  users:
    "M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z",
  groups:
    "M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z",
  box:
    "M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4",
  chart:
    "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z",
  shield:
    "M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z",
  clock:
    "M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z",
  cpu:
    "M9 3H7a2 2 0 00-2 2v2M9 3h6M9 3v2m6-2h2a2 2 0 012 2v2M15 3v2M3 9h2m16 0h-2M3 15h2m16 0h-2M9 21H7a2 2 0 01-2-2v-2m4 4h6m-6 0v-2m6 2h2a2 2 0 002-2v-2m-4 4v-2M9 9h6v6H9V9z",
  book:
    "M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253",
  tag:
    "M7 7h.01M7 3h5.586a1 1 0 01.707.293l7.414 7.414a2 2 0 010 2.828l-5.586 5.586a2 2 0 01-2.828 0L4.879 11.707A2 2 0 014.293 11.1L3 5.414A2 2 0 014.414 4L7 3z",
  chat:
    "M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.86 9.86 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z",
  calendar:
    "M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z",
  info:
    "M13 16h-1v-4h-1m1-4h.01M12 2a10 10 0 100 20A10 10 0 0012 2z",
  check:
    "M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z",
  warning:
    "M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z",
  error:
    "M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z",
  close:
    "M6 18L18 6M6 6l12 12",
  plus:
    "M12 4v16m8-8H4",
  menu:
    "M4 6h16M4 12h16M4 18h16",
  search:
    "M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z",
  bell:
    "M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9",
  chevronDown:
    "M6 9l6 6 6-6",
  logout:
    "M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1",
  filter:
    "M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z",
} as const;

/**
 * Os que **não** vêm do pacote.
 *
 * A procedência é tabela separada, e não comentário, porque é ela que dá
 * sentido ao hash de cima: o teste prende os 25 do pacote a um número tirado do
 * `Icon.jsx` no dia da cópia, e um acréscimo local misturado ali derrubaria
 * essa conferência para sempre — o conserto seria trocar o número, e trocar o
 * número é justamente o que o teste existe para impedir.
 *
 * Estes nove estavam soltos dentro do `TicketFormPage`, e vieram para cá
 * **verbatim**. Verbatim de propósito: trocar `server` pelo `cpu` que já
 * existia, ou `help` pelo `info`, mudaria o desenho da tela dentro de um commit
 * que promete não mudar pixel. Troca de ícone é decisão de produto, não efeito
 * colateral de migração.
 *
 * Se um destes nomes aparecer no pacote um dia, o traçado de lá ganha e este
 * sai — e o hash de cima passa a cobri-lo.
 */
export const ICON_PATHS_LOCAIS = {
  server:
    "M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18",
  code:
    "M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4",
  network:
    "M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064",
  key:
    "M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z",
  mail:
    "M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z",
  help:
    "M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
  ellipsis:
    "M5 12h.01M12 12h.01M19 12h.01M6 12a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0z",
  arrowLeft:
    "M10 19l-7-7m0 0l7-7m-7 7h18",
  paperclip:
    "M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13",
  // Nao ha `checkCircle` aqui: o `check` do pacote JA e o visto dentro do
  // circulo, com o mesmo tracado. O caso "cada nome desenha um tracado
  // diferente" pegou a duplicata antes de ela existir.
  user:
    "M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z",

  // ── Do `TicketDetailPage`, movidos verbatim ────────────────────
  //
  // Varios sao PARENTES de icones do pacote com tracado diferente:
  // `checkMark` contra `check` (o do pacote e dentro do circulo),
  // `alert` contra `warning` (outro triangulo), `tagOutline` contra
  // `tag`. Ficam separados de proposito — unificar muda o desenho da
  // tela, e isso e decisao de produto. Anotado para o operador.
  checkMark:
    "M5 13l4 4L19 7",
  folder:
    "M3 7a2 2 0 012-2h3.586a1 1 0 01.707.293l1.414 1.414A1 1 0 0011.414 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V7z",
  edit:
    "M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z",
  lock:
    "M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z",
  trash:
    "M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16",
  refresh:
    "M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15",
  userPlus:
    "M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z",
  download:
    "M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4",
  eye: [
    "M15 12a3 3 0 11-6 0 3 3 0 016 0z",
    "M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z",
  ],
  alert:
    "M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z",
  tagOutline:
    "M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z",
  text:
    "M4 6h16M4 12h16M4 18h7",
  activity:
    "M13 10V3L4 14h7v7l9-11h-7z",
  star:
    "M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z",
  chatBubble:
    "M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z",
  document:
    "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
} as const;

/** O conjunto que o `Icon` desenha: os do pacote mais os locais. */
export const ICON_PATHS = {
  ...ICON_PATHS_PACOTE,
  ...ICON_PATHS_LOCAIS,
} as const;

/**
 * Derivado do próprio mapa, e não repetido à mão.
 *
 * A lista existia escrita duas vezes. Acrescentar traçado sem acrescentar nome
 * dava um ícone que o TypeScript recusa; o contrário dava um nome que devolve
 * `null` em silêncio, porque o `Icon` sai fora quando não acha o traçado. As
 * duas metades agora não têm como divergir.
 */
export type IconName = keyof typeof ICON_PATHS;

export interface IconProps extends Omit<SVGAttributes<SVGSVGElement>, "name"> {
  name: IconName;
  /** 16 em botão, 20 em item de nav (padrão), 24 em cabeçalho. */
  size?: number;
  /** 1,75 na navegação, 2 dentro de botão. */
  strokeWidth?: number;
}

export function Icon({
  name,
  size = 20,
  strokeWidth = 1.75,
  className,
  ...props
}: IconProps) {
  const d = ICON_PATHS[name];
  if (!d) return null;
  // Alguns desenhos precisam de mais de um traçado — o olho é pupila mais
  // contorno. O conjunto do pacote é todo de traçado único, então isto é
  // acréscimo local e não muda nada do que já existia.
  const tracos: readonly string[] = typeof d === "string" ? [d] : d;

  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn("shrink-0", className)}
      {...props}
    >
      {tracos.map((t) => (
        <path key={t} d={t} />
      ))}
    </svg>
  );
}
