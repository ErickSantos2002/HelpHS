import { Icon, SelectMenu } from "../ui";
import {
  OPCOES_DE_PERIODO,
  hojeNosRelatorios,
  type PresetDePeriodo,
} from "../../lib/periodoRelatorio";

/**
 * O seletor de período dos três painéis — dashboard do admin, do técnico e
 * Relatórios (F1-B-03b).
 *
 * Era escrito três vezes, com três listas: o dashboard tinha "Esta Semana",
 * "Este Trimestre" e "Este Ano" contados em dias; os Relatórios, 7/14/30/90
 * dias. Agora é um só, com as opções da decisão D1, e as datas saem de
 * `lib/periodoRelatorio.ts`.
 *
 * D9.2 — sete opções fixas no código: lista curta e conhecida, logo o
 * `SelectMenu`. Sem `placeholder`: escolher o período é obrigatório, e a linha
 * vazia derrubava a tela no filtro antigo.
 *
 * Fica FORA de qualquer ramo de erro de quem o usa: com uma falha na tela, é
 * por ele que a pessoa troca de período e sai do erro.
 *
 * O `max` das datas é o dia de hoje em Recife, e não `toISOString()`: às 21:00
 * de Recife o dia em UTC já é amanhã, e o campo deixaria escolher uma data que
 * a API recusa.
 */
export function SeletorDePeriodo({
  preset,
  onPreset,
  inicio,
  fim,
  onInicio,
  onFim,
  erro,
  descricao,
}: {
  preset: PresetDePeriodo;
  onPreset: (p: PresetDePeriodo) => void;
  inicio: string;
  fim: string;
  onInicio: (v: string) => void;
  onFim: (v: string) => void;
  /** O motivo de o intervalo personalizado não valer, ou `null`. */
  erro: string | null;
  /** Os dias que o período cobre, escritos: `23/10 – 29/10`. */
  descricao: string | null;
}) {
  const hoje = hojeNosRelatorios();
  return (
    <div className="flex flex-col items-center sm:items-end gap-1">
      <div className="flex flex-wrap items-center justify-center sm:justify-end gap-2">
        <span id="rotulo-filtro-periodo" className="sr-only">
          Período
        </span>
        <SelectMenu
          id="filtro-periodo"
          aria-labelledby="rotulo-filtro-periodo"
          value={preset}
          onChange={(v) => onPreset(v as PresetDePeriodo)}
          options={OPCOES_DE_PERIODO}
        />

        {preset === "personalizado" && (
          <div className="flex h-9 items-center gap-1.5 rounded-lg border border-borda/60 bg-surface-elevated px-3 text-sm">
            <Icon name="calendar" size={14} strokeWidth={2} className="shrink-0 text-conteudo-muted" />
            <input
              type="date"
              aria-label="Data inicial"
              value={inicio}
              max={fim || hoje}
              onChange={(e) => onInicio(e.target.value)}
              aria-invalid={erro ? true : undefined}
              className="bg-transparent text-conteudo text-xs outline-none cursor-pointer w-28 [color-scheme:light] dark:[color-scheme:dark]"
            />
            <span className="text-conteudo-muted text-xs">até</span>
            <input
              type="date"
              aria-label="Data final"
              value={fim}
              min={inicio || undefined}
              max={hoje}
              onChange={(e) => onFim(e.target.value)}
              aria-invalid={erro ? true : undefined}
              className="bg-transparent text-conteudo text-xs outline-none cursor-pointer w-28 [color-scheme:light] dark:[color-scheme:dark]"
            />
          </div>
        )}
      </div>

      {erro ? (
        <p role="alert" className="text-xs font-medium text-on-tint-danger">
          {erro}
        </p>
      ) : descricao ? (
        <p className="text-xs text-conteudo-muted" data-testid="dias-do-periodo">
          {descricao} · horário de Recife
        </p>
      ) : null}
    </div>
  );
}
