import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm, type Resolver } from "react-hook-form";
import { z } from "zod";
import {
  Alert,
  Button,
  Card,
  Input,
  Modal,
  ModalFooter,
  Spinner,
} from "../../components/ui";
import {
  getSLAConfigs,
  updateSLAConfig,
  type SLAConfig,
} from "../../services/slaService";

// ── Constants ─────────────────────────────────────────────────

const LEVEL_LABEL: Record<string, string> = {
  critical: "Crítico",
  high: "Alto",
  medium: "Médio",
  low: "Baixo",
};

const LEVEL_STYLE: Record<string, { badge: string; bar: string; dot: string }> = {
  critical: {
    badge: "bg-red-900/30 text-red-300 border border-red-700/40",
    bar: "bg-red-500",
    dot: "bg-red-400",
  },
  high: {
    badge: "bg-orange-900/30 text-orange-300 border border-orange-700/40",
    bar: "bg-orange-500",
    dot: "bg-orange-400",
  },
  medium: {
    badge: "bg-yellow-900/30 text-yellow-300 border border-yellow-700/40",
    bar: "bg-yellow-500",
    dot: "bg-yellow-400",
  },
  low: {
    badge: "bg-slate-800/60 text-slate-400 border border-slate-600/40",
    bar: "bg-slate-500",
    dot: "bg-slate-400",
  },
};

const LEVEL_ORDER = ["critical", "high", "medium", "low"];

// ── Icons ─────────────────────────────────────────────────────

const IC = {
  Clock: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <circle cx="12" cy="12" r="10" /><path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6l4 2" />
    </svg>
  ),
  Shield: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
    </svg>
  ),
  Edit: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
    </svg>
  ),
  Bell: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
    </svg>
  ),
  Info: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
};

// ── Helpers ───────────────────────────────────────────────────

function formatHours(h: number) {
  if (h < 24) return `${h}h`;
  const days = Math.floor(h / 24);
  const rest = h % 24;
  return rest > 0 ? `${days}d ${rest}h` : `${days}d`;
}

// ── Validation schema ─────────────────────────────────────────

const editSchema = z
  .object({
    response_time_hours: z.coerce.number().int("Deve ser inteiro").min(1, "Mínimo 1 hora").max(9999),
    resolve_time_hours: z.coerce.number().int("Deve ser inteiro").min(1, "Mínimo 1 hora").max(9999),
    warning_threshold: z.coerce.number().int("Deve ser inteiro").min(1).max(100, "Máximo 100%"),
  })
  .refine((v) => v.resolve_time_hours > v.response_time_hours, {
    message: "Deve ser maior que o tempo de resposta",
    path: ["resolve_time_hours"],
  });

type EditValues = z.infer<typeof editSchema>;

// ── SlaEditModal ──────────────────────────────────────────────

function SlaEditModal({ config, onClose, onSaved }: {
  config: SLAConfig;
  onClose: () => void;
  onSaved: (updated: SLAConfig) => void;
}) {
  const [submitError, setSubmitError] = useState<string | null>(null);
  const style = LEVEL_STYLE[config.level];

  const form = useForm<EditValues>({
    resolver: zodResolver(editSchema) as Resolver<EditValues>,
    defaultValues: {
      response_time_hours: config.response_time_hours,
      resolve_time_hours: config.resolve_time_hours,
      warning_threshold: config.warning_threshold,
    },
  });

  async function handleSubmit(values: EditValues) {
    setSubmitError(null);
    try {
      const updated = await updateSLAConfig(config.id, values);
      onSaved(updated);
    } catch {
      setSubmitError("Erro ao salvar configuração. Tente novamente.");
    }
  }

  return (
    <Modal open onClose={onClose} title={`Editar SLA — ${LEVEL_LABEL[config.level]}`}>
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
        {/* Level badge */}
        <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium ${style.badge}`}>
          <span className={`w-2 h-2 rounded-full shrink-0 ${style.dot}`} />
          Nível {LEVEL_LABEL[config.level]}
        </div>

        {submitError && <Alert variant="danger">{submitError}</Alert>}

        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Resposta (horas úteis) *"
            type="number"
            min={1}
            error={form.formState.errors.response_time_hours?.message}
            {...form.register("response_time_hours")}
          />
          <Input
            label="Resolução (horas úteis) *"
            type="number"
            min={1}
            error={form.formState.errors.resolve_time_hours?.message}
            {...form.register("resolve_time_hours")}
          />
        </div>

        <Input
          label="Limiar de alerta (%) *"
          type="number"
          min={1}
          max={100}
          error={form.formState.errors.warning_threshold?.message}
          {...form.register("warning_threshold")}
        />

        <p className="text-xs text-slate-500">
          O alerta dispara quando o percentual do tempo já consumido atingir o limiar. Ex.: 80% = alerta quando 80% do prazo foi usado.
        </p>

        <ModalFooter>
          <Button type="button" variant="secondary" onClick={onClose} disabled={form.formState.isSubmitting}>
            Cancelar
          </Button>
          <Button type="submit" loading={form.formState.isSubmitting}>
            Salvar
          </Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

// ── SlaConfigPage ─────────────────────────────────────────────

export default function SlaConfigPage() {
  const [configs, setConfigs] = useState<SLAConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<SLAConfig | null>(null);

  useEffect(() => {
    getSLAConfigs()
      .then((data) => {
        setConfigs([...data].sort((a, b) => LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level)));
      })
      .catch(() => setError("Não foi possível carregar as configurações de SLA."))
      .finally(() => setLoading(false));
  }, []);

  function handleSaved(updated: SLAConfig) {
    setEditing(null);
    setConfigs((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Configurações de SLA</h1>
        <p className="text-slate-400 text-sm mt-0.5">
          Tempos limite de resposta e resolução por nível de prioridade (seg–sex, 08h–18h)
        </p>
      </div>

      {error && <Alert variant="danger">{error}</Alert>}

      {loading ? (
        <div className="flex h-48 items-center justify-center"><Spinner size="lg" /></div>
      ) : (
        <>
          <Card padding="none">
            {/* Card header */}
            <div className="px-4 py-3 border-b border-border">
              <p className="text-sm font-semibold text-slate-200">Níveis de SLA</p>
              <p className="text-xs text-slate-500 mt-0.5">Clique em editar para ajustar os tempos de cada nível.</p>
            </div>

            <div className="divide-y divide-border">
              {configs.map((c) => {
                const style = LEVEL_STYLE[c.level];
                const responseRatio = Math.min((c.response_time_hours / c.resolve_time_hours) * 100, 100);
                return (
                  <div key={c.id} className="flex items-center gap-4 px-4 py-4 hover:bg-background-elevated/40 transition-colors">

                    {/* Level badge */}
                    <div className={`shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${style.badge}`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${style.dot}`} />
                      {LEVEL_LABEL[c.level]}
                    </div>

                    {/* Times */}
                    <div className="flex-1 min-w-0">
                      {/* Progress bar — mostra resposta vs resolução */}
                      <div className="flex items-center gap-3 mb-2">
                        <div className="flex-1 h-1.5 rounded-full bg-background-elevated overflow-hidden">
                          <div
                            className={`h-full rounded-full ${style.bar} opacity-60`}
                            style={{ width: `${responseRatio}%` }}
                          />
                        </div>
                      </div>

                      <div className="flex flex-wrap gap-4">
                        {/* Resposta */}
                        <div className="flex items-center gap-1.5">
                          <span className="text-slate-500">{IC.Clock}</span>
                          <div>
                            <p className="text-[10px] text-slate-500 leading-none">Resposta</p>
                            <p className="text-sm font-semibold text-slate-200 mt-0.5">{formatHours(c.response_time_hours)}</p>
                          </div>
                        </div>

                        {/* Resolução */}
                        <div className="flex items-center gap-1.5">
                          <span className="text-slate-500">{IC.Shield}</span>
                          <div>
                            <p className="text-[10px] text-slate-500 leading-none">Resolução</p>
                            <p className="text-sm font-semibold text-slate-200 mt-0.5">{formatHours(c.resolve_time_hours)}</p>
                          </div>
                        </div>

                        {/* Alerta */}
                        <div className="flex items-center gap-1.5">
                          <span className="text-slate-500">{IC.Bell}</span>
                          <div>
                            <p className="text-[10px] text-slate-500 leading-none">Alerta</p>
                            <p className="text-sm font-semibold text-slate-200 mt-0.5">{c.warning_threshold}%</p>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Updated at */}
                    <p className="hidden md:block shrink-0 text-xs text-slate-600">
                      {new Date(c.updated_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" })}
                    </p>

                    {/* Edit */}
                    <button
                      onClick={() => setEditing(c)}
                      title="Editar"
                      className="p-1.5 rounded-lg text-slate-400 hover:text-primary hover:bg-primary/10 transition-colors cursor-pointer shrink-0"
                    >
                      {IC.Edit}
                    </button>
                  </div>
                );
              })}
            </div>
          </Card>

          {/* Info card */}
          <div className="rounded-xl border border-border/60 bg-background-surface/50 p-4">
            <div className="flex items-center gap-2 mb-2 text-slate-300">
              <span className="text-slate-500">{IC.Info}</span>
              <p className="text-sm font-medium">Como funciona</p>
            </div>
            <ul className="space-y-1 text-xs text-slate-500">
              <li><span className="text-slate-400 font-medium">Resposta:</span> tempo máximo para a primeira interação de um técnico no chamado.</li>
              <li><span className="text-slate-400 font-medium">Resolução:</span> tempo máximo para fechar o chamado.</li>
              <li><span className="text-slate-400 font-medium">Alerta:</span> notificação antecipada quando o percentual do prazo consumido atingir o limiar.</li>
              <li>Períodos de espera (aguardando cliente / aguardando técnico) <span className="text-slate-400 font-medium">pausam</span> o contador de SLA.</li>
            </ul>
          </div>
        </>
      )}

      {editing && (
        <SlaEditModal config={editing} onClose={() => setEditing(null)} onSaved={handleSaved} />
      )}
    </div>
  );
}
