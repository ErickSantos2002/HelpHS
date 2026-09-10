import { useState, type ReactNode } from "react";
import { cn } from "../../lib/utils";

/**
 * Rótulo que aparece no hover — porte do `feedback/Tooltip.jsx` do pacote.
 *
 * Ele existe aqui por uma decisão do operador (**D9.4**): a barra lateral
 * recolhida mostra só ícones, e a migração da barra tinha desfeito a pastilha
 * escura por não achar token de superfície invertida. O token não faltava — o
 * que faltava era **consumir o primitivo**, que já resolve isso com
 * `--color-slate-900` e `--color-white`, os dois já no `colors.css`.
 *
 * ── Por que as duas cores entram por valor arbitrário ─────────────────
 *
 * `--color-slate-900` é degrau de rampa, e a rampa `slate` **não tem mapa** no
 * `tailwind.config.js` — só a `primary` tem. Escrever `bg-slate-900` pegaria o
 * slate do **Tailwind**, não o token, e seria classe de paleta crua, que a
 * catraca conta. `bg-[var(--color-slate-900)]` aponta para o token e não é
 * paleta crua — a régua exige que o nome da cor venha logo depois do prefixo, e
 * aqui vem `[`.
 *
 * Isto não é atalho: é a forma correta enquanto não existir um token de papel
 * para "superfície invertida". Se um dia existir, esta é a única linha a mudar.
 *
 * ── UM DESVIO DELIBERADO do original, e o motivo ──────────────────────
 *
 * O do pacote põe `role="tooltip"` na pastilha, que fica **sempre no DOM** com
 * `opacity: 0`. `role="tooltip"` sozinho não é anunciado por leitor de tela
 * nenhum — ele só significa alguma coisa quando algum elemento o referencia por
 * `aria-describedby` —, então ali ele não ajuda; e o texto continua na árvore de
 * acessibilidade, disponível para ser lido solto.
 *
 * Aqui a pastilha é `aria-hidden`. Ela é **decoração**, e o próprio comentário
 * do pacote diz a regra que torna isso seguro: *nunca informação que só exista
 * aqui*. Quem dispara a dica precisa ter o próprio nome acessível — na barra
 * lateral, o `aria-label` que cada item já carrega.
 *
 * O desvio é para MENOS: a pastilha deixa de existir para quem não a vê, em vez
 * de existir sem função. Registrado por escrito porque porte que se afasta do
 * original sem dizer vira divergência silenciosa — que é o defeito que esta
 * migração inteira existe para eliminar.
 */

type Posicao = "top" | "bottom" | "left" | "right";

const POSICAO: Record<Posicao, string> = {
  top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
  bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
  left: "right-full top-1/2 -translate-y-1/2 mr-3",
  right: "left-full top-1/2 -translate-y-1/2 ml-3",
};

export interface TooltipProps {
  /** O texto da pastilha. Nunca a única fonte da informação. */
  label: string;
  position?: Posicao;
  children: ReactNode;
  className?: string;
}

export function Tooltip({
  label,
  position = "top",
  children,
  className,
}: TooltipProps) {
  const [aberta, setAberta] = useState(false);

  return (
    <span
      // `onFocus`/`onBlur` e não só o ponteiro: quem navega por teclado alcança
      // o disparador e precisa ver a dica pelo mesmo motivo que quem passa o
      // mouse. O original já fazia isso, e é o que o mantém utilizável.
      onMouseEnter={() => setAberta(true)}
      onMouseLeave={() => setAberta(false)}
      onFocus={() => setAberta(true)}
      onBlur={() => setAberta(false)}
      className={cn("relative inline-flex", className)}
    >
      {children}
      <span
        aria-hidden="true"
        className={cn(
          "pointer-events-none absolute z-[60] whitespace-nowrap rounded-lg px-2.5 py-1.5",
          "text-xs font-medium shadow-lg transition-opacity duration-150",
          "bg-[var(--color-slate-900)] text-[var(--color-white)]",
          POSICAO[position],
          aberta ? "opacity-100" : "opacity-0",
        )}
      >
        {label}
      </span>
    </span>
  );
}
