import type { ReactNode } from "react";
import { cn } from "../../lib/utils";
import { Icon, Modal } from "../ui";
import { APP_VERSION, CHANGELOG, type EntryType } from "../../data/changelog";

/**
 * O selo de cada tipo de entrada.
 *
 * As três cores eram paleta crua com opacidade escolhida à mão — `blue-500/15`,
 * `orange-500/15`, `emerald-500/15` com texto no degrau 400 e borda a /25.
 * Passam a ser o mesmo trio que o `Badge` do pacote pinta: fundo na **tinta**,
 * texto no **par da tinta**, borda na cor cheia a 30%.
 *
 * Por que não é o `Badge`: o selo aqui é de 10px com `gap-1`, e o primitivo é
 * de 12px sem espaço entre ícone e rótulo. O `cn` deste projeto **não** é
 * `tailwind-merge` — ele concatena —, então `className="px-2 text-[10px]"` por
 * cima do `px-2.5 text-xs` do primitivo deixaria as duas regras vivas e a
 * vencedora seria a ordem do CSS gerado, que não é nossa. Copiar as três
 * classes de cor mantém a geometria e não inventa cor local.
 *
 * ── A variante sai do SIGNIFICADO, não da cor que estava aqui ─────────
 *
 * A primeira passada traduziu cor por cor: azul→`info`, laranja→`warning`,
 * verde→`success`. Isso preserva a aparência e **não** é o critério do
 * pacote — a cor antiga não era decisão de ninguém, era o que estava lá.
 *
 * | tipo | variante | por quê |
 * |---|---|---|
 * | `novidade` | `info` | é um **anúncio**: algo passou a existir. Não é resultado bom nem ruim, é informação — que é o que `info` significa em toda a interface (o `Alert`, o papel "Técnico", o selo de aviso neutro). |
 * | `corrigido` | `success` | um defeito foi **resolvido**. Decisão do operador, e é a leitura certa: o laranja de antes dizia "atenção", e não há nada a que atentar num defeito que já saiu. |
 * | `melhoria` | `success` | **NÃO É DECISÃO MINHA — ver o bloco abaixo.** |
 *
 * ── `melhoria` está sem casa, e o motivo é medido ─────────────────────
 *
 * "Algo que já existia ficou melhor" não é nenhuma das seis tintas. E o
 * problema não é de gosto: sobre o cartão desta janela (`--surface-elevated`)
 * as seis só oferecem **quatro** aparências distintas.
 *
 * | candidata | por que não serve | medida |
 * |---|---|---|
 * | `success` | é de `corrigido` agora | — |
 * | `primary` | é o **mesmo azul** de `info` | ΔE76 **4,5** claro / **5,7** escuro; razão 1,01:1. O piso do próprio pacote para série distinguível (E16-b) é ΔE ≥ 20 |
 * | `neutral` | é **alias de `--surface-elevated`**, que é o fundo do cartão: o selo perderia a forma | ΔE76 **0,0**; razão **1,00:1** |
 * | `warning` | diz "atenção"; não há a que atentar numa melhoria | — |
 * | `danger` | tom errado | — |
 *
 * Então `melhoria` fica onde estava (`success`) e passa a ser **gêmea de
 * `corrigido`**. O que se perde é a cor *acrescentar* uma distinção entre as
 * duas; o que **não** se perde é a informação, porque o rótulo ("Corrigido" /
 * "Melhoria") é escrito ao lado do ícone e há caso de teste que o prende.
 * 1.4.1 continua satisfeito — a cor nunca foi o único portador.
 *
 * Sair disto é decisão de quem desenha o pacote, não desta tela: ou se aceita
 * a gêmea, ou entra uma sexta tinta distinguível por emenda.
 */
const ENTRY_CONFIG: Record<EntryType, { label: string; className: string; icon: ReactNode }> = {
  novidade: {
    label: "Novidade",
    className: "bg-tint-info text-on-tint-info border border-info/30",
    icon: <Icon name="plus" size={12} strokeWidth={2.5} />,
  },
  corrigido: {
    label: "Corrigido",
    className: "bg-tint-success text-on-tint-success border border-success/30",
    icon: <Icon name="edit" size={12} strokeWidth={2.5} />,
  },
  melhoria: {
    label: "Melhoria",
    className: "bg-tint-success text-on-tint-success border border-success/30",
    icon: <Icon name="trendingUp" size={12} strokeWidth={2.5} />,
  },
};

interface ChangelogModalProps {
  open: boolean;
  onClose: () => void;
}

export function ChangelogModal({ open, onClose }: ChangelogModalProps) {
  return (
    <Modal open={open} onClose={onClose} title="O que há de novo?" size="2xl">
      <p className="-mt-1 mb-5 text-sm text-conteudo-muted">Atualizações recentes do HelpHS</p>

      <div className="space-y-6">
        {CHANGELOG.map((v, idx) => {
          const isCurrent = v.version === APP_VERSION;
          return (
            <div key={v.version}>
              <div className="flex items-center gap-2 mb-3">
                {/* A pastilha da versão vigente era `bg-emerald-500` com
                    `text-white`: a cor CHEIA da rampa, que dá 2,54:1 com
                    branco por cima. O degrau de ação (`--action-success`)
                    existe justamente por isso, e `text-on-success` é o par
                    dele. */}
                <span className={cn(
                  "rounded-full px-2.5 py-0.5 text-xs font-bold",
                  isCurrent
                    ? "bg-action-success text-on-success"
                    : "bg-tint-neutral text-on-tint-neutral",
                )}>
                  {v.version}
                </span>
                <span className="text-xs text-conteudo-muted">{v.date}</span>
                {isCurrent && (
                  <span className="rounded-full bg-tint-success text-on-tint-success border border-success/30 px-2 py-0.5 text-[10px] font-semibold">
                    Versão atual
                  </span>
                )}
              </div>

              <div className="space-y-2">
                {v.entries.map((entry, i) => {
                  const cfg = ENTRY_CONFIG[entry.type];
                  return (
                    <div key={i} className="flex items-start gap-3 rounded-xl border border-borda bg-surface-elevated px-3.5 py-2.5">
                      <span className={cn(
                        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold shrink-0 mt-0.5",
                        cfg.className,
                      )}>
                        {cfg.icon}
                        {cfg.label}
                      </span>
                      <p className="text-sm text-conteudo leading-relaxed">{entry.text}</p>
                    </div>
                  );
                })}
              </div>

              {idx < CHANGELOG.length - 1 && (
                <div className="mt-6 border-b border-borda" />
              )}
            </div>
          );
        })}
      </div>

      <p className="mt-6 text-center text-xs text-conteudo-muted">
        HelpHS — desenvolvido internamente pela equipe
      </p>
    </Modal>
  );
}
