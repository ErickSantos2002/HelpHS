import { useEffect, useRef, useState } from "react";
import { cn } from "../../lib/utils";
import {
  formataUtil,
  precisaRecarregar,
  restanteUtil,
  textoDoVencimento,
  type Expediente,
} from "../../lib/tempoUtil";
import { Icon } from "./Icon";

export interface SlaChipProps {
  label: string;
  /** Minutos ÚTEIS restantes, como o backend os mandou. Nulo: o chip não existe. */
  restanteMin: number | null;
  /** O prazo EFETIVO, para o detalhe do vencimento. */
  venceEm: string | null;
  /** O relógio do servidor. Nulo: o chip não existe. */
  expediente: Expediente | null;
  /** Flag de violação que o backend gravou — decide a COR. */
  breached: boolean;
  /**
   * Quando a resposta foi dada. Preenchido, o relógio para: o chip diz
   * "Respondido" e não conta mais nada, porque o prazo de resposta já foi
   * atendido (ou perdido — aí `breached` segue pintando de vermelho).
   */
  respondedAt?: string | null;
  /**
   * Chamado quando a janela do expediente vira e o dado fica velho. É o que
   * faz o contador voltar a andar quando a jornada seguinte começa: a página
   * busca de novo, e o backend devolve o restante atualizado.
   */
  onExpirou?: () => void;
}

/**
 * Chip de prazo de SLA, em tempo ÚTIL.
 *
 * ── O que mudou, e por quê ────────────────────────────────────────────
 *
 * Ele fazia `new Date(dueAt) - Date.now()`: tempo CORRIDO. Um prazo de 12h
 * ÚTEIS carimbado às 09:11 aparecia como **27h**, porque a conta incluía as 15
 * horas entre 17:00 e 08:00. E ignorava `sla_total_paused_ms`, então num
 * chamado que ficou três horas em "Aguardando cliente" ele escrevia "Vencido"
 * três horas antes de o backend concordar.
 *
 * Agora o backend manda os minutos úteis restantes e o estado do expediente, e
 * este componente só desconta o tempo que passa enquanto a janela está aberta.
 * A aritmética mora em `lib/tempoUtil.ts`; o calendário mora no backend e não
 * é duplicado aqui.
 *
 * ── O que NÃO mudou ───────────────────────────────────────────────────
 *
 * As três responsabilidades continuam separadas: o restante dá a contagem,
 * `breached` dá a cor, `respondedAt` desliga o relógio. Misturar os dois
 * últimos é a tentação a evitar — "se não violou, não escreva Vencido" —
 * porque `breached` só é recalculado em caminhos de ESCRITA do backend, nunca
 * na leitura. Um chamado que venceu há duas horas e ninguém tocou chega com
 * `breached = false`, e é exatamente para ele que a contagem ao vivo existe.
 *
 * O caso que motivou `respondedAt`: chamado respondido no prazo e reaberto
 * dias depois. O prazo de resposta é o do primeiro ciclo, muito no passado, e
 * sem saber da resposta o chip dizia "Vencido" em âmbar — cor certa, letra
 * errada.
 */
export function SlaChip({
  label,
  restanteMin,
  venceEm,
  expediente,
  breached,
  respondedAt,
  onExpirou,
}: SlaChipProps) {
  const respondido = Boolean(respondedAt);
  // `== null` pega nulo E indefinido: uma resposta antiga em cache nao tem
  // os campos novos, e o chip nao pode derrubar a tela do chamado por isso.
  const temPrazo = restanteMin != null && expediente != null;

  // O instante em que ESTE dado chegou. O tempo decorrido é medido daqui, e
  // não de `Date.now() - expediente.agora`: aquela subtração mistura o relógio
  // do servidor com o da máquina de quem olha, e um desvio no segundo vira
  // minutos a mais no contador.
  const chegouEm = useRef<number>(Date.now());
  const [decorridoMs, setDecorridoMs] = useState(0);

  useEffect(() => {
    chegouEm.current = Date.now();
    setDecorridoMs(0);
  }, [restanteMin, expediente]);

  useEffect(() => {
    if (!temPrazo || respondido) return;
    const tick = () => setDecorridoMs(Date.now() - chegouEm.current);
    tick();
    const t = setInterval(tick, 60_000);
    return () => clearInterval(t);
  }, [temPrazo, respondido]);

  // A virada é um efeito à parte: avisar a página durante a renderização
  // dispararia atualização de estado alheio no meio do render do React.
  const jaAvisou = useRef<string | null>(null);
  useEffect(() => {
    if (!expediente || !onExpirou || respondido) return;
    if (!precisaRecarregar(expediente, decorridoMs)) return;
    // Uma vez por virada: sem esta trava, o relógio pediria recarga a cada
    // minuto depois de passar da marca.
    if (jaAvisou.current === expediente.proxima_virada) return;
    jaAvisou.current = expediente.proxima_virada;
    onExpirou();
  }, [expediente, decorridoMs, onExpirou, respondido]);

  if (restanteMin == null || expediente == null) return null;

  const restante = restanteUtil(restanteMin, expediente, decorridoMs);
  const vencido = restante <= 0;

  // As tres tintas vinham da paleta CRUA do Tailwind — `bg-red-500/15` com
  // `text-red-700 dark:text-red-400` —, fora do sistema de tokens e com a
  // razao de contraste nunca medida. Passam a usar os pares `tint`/`on-tint`,
  // que sao os que a E2 e a E8 mediram contra as tres superficies nos dois
  // temas. E o mesmo par que o `Badge` adotou na Fase 7.
  const tom = breached
    ? "bg-tint-danger text-on-tint-danger ring-danger/30"
    : respondido
      ? "bg-tint-success text-on-tint-success ring-success/30"
      : "bg-tint-warning text-on-tint-warning ring-warning/30";

  const texto = respondido
    ? "Respondido"
    : vencido
      ? "Vencido"
      : `${formataUtil(restante)} úteis`;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-semibold ring-1 ring-inset",
        tom,
      )}
      title={venceEm ? textoDoVencimento(venceEm, expediente.fuso) : undefined}
    >
      {/* O `Icon` ja marca `aria-hidden`; repetir aqui sugeriria que a garantia
          mora neste arquivo, e ela mora la. */}
      <Icon name="clock" size={16} strokeWidth={2} />
      {label ? `${label}: ` : ""}
      <span>{texto}</span>
      {/* Fora do expediente o número não se mexe, e o sufixo diz por quê — sem
          ele o contador parado parece tela travada. Some quando já venceu ou
          já foi respondido, onde não explicaria nada. */}
      {!respondido && !vencido && !expediente.aberto && (
        <span className="font-normal opacity-80">· fora do expediente</span>
      )}
    </span>
  );
}
