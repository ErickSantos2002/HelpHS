import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
  Alert,
  Button,
  Input,
  Modal,
  ModalFooter,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
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

const LEVEL_COLOR: Record<string, string> = {
  critical: "text-danger font-semibold",
  high: "text-orange-400 font-semibold",
  medium: "text-warning font-semibold",
  low: "text-slate-400",
};

const LEVEL_ORDER = ["critical", "high", "medium", "low"];

// ── Validation schema ─────────────────────────────────────────

const editSchema = z
  .object({
    response_time_hours: z.coerce
      .number()
      .int("Deve ser inteiro")
      .min(1, "Mínimo 1 hora")
      .max(9999),
    resolve_time_hours: z.coerce
      .number()
      .int("Deve ser inteiro")
      .min(1, "Mínimo 1 hora")
      .max(9999),
    warning_threshold: z.coerce
      .number()
      .int("Deve ser inteiro")
      .min(1)
      .max(100, "Máximo 100%"),
  })
  .refine((v) => v.resolve_time_hours > v.response_time_hours, {
    message: "Tempo de resolução deve ser maior que o tempo de resposta",
    path: ["resolve_time_hours"],
  });

type EditValues = z.infer<typeof editSchema>;

// ── SlaEditModal ──────────────────────────────────────────────

interface SlaEditModalProps {
  config: SLAConfig;
  onClose: () => void;
  onSaved: (updated: SLAConfig) => void;
}

function SlaEditModal({ config, onClose, onSaved }: SlaEditModalProps) {
  const [submitError, setSubmitError] = useState<string | null>(null);

  const form = useForm<EditValues>({
    resolver: zodResolver(editSchema),
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
    <Modal
      open
      onClose={onClose}
      title={`Editar SLA — ${LEVEL_LABEL[config.level]}`}
    >
      {submitError && (
        <Alert variant="danger" className="mb-4">
          {submitError}
        </Alert>
      )}
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
        <Input
          label="Tempo de resposta (horas úteis) *"
          type="number"
          min={1}
          error={form.formState.errors.response_time_hours?.message}
          {...form.register("response_time_hours")}
        />
        <Input
          label="Tempo de resolução (horas úteis) *"
          type="number"
          min={1}
          error={form.formState.errors.resolve_time_hours?.message}
          {...form.register("resolve_time_hours")}
        />
        <Input
          label="Limiar de alerta (%) *"
          type="number"
          min={1}
          max={100}
          error={form.formState.errors.warning_threshold?.message}
          {...form.register("warning_threshold")}
        />
        <p className="text-xs text-slate-500">
          O alerta é disparado quando o percentual do tempo utilizado atingir o
          limiar. Ex.: 80% significa que 80% do tempo já foi consumido.
        </p>
        <ModalFooter>
          <Button
            type="button"
            variant="secondary"
            onClick={onClose}
            disabled={form.formState.isSubmitting}
          >
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
        const sorted = [...data].sort(
          (a, b) => LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level),
        );
        setConfigs(sorted);
      })
      .catch(() =>
        setError("Não foi possível carregar as configurações de SLA."),
      )
      .finally(() => setLoading(false));
  }, []);

  function handleSaved(updated: SLAConfig) {
    setEditing(null);
    setConfigs((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
  }

  const updatedAt = (c: SLAConfig) =>
    new Date(c.updated_at).toLocaleDateString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });

  return (
    <div className="space-y-4">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-100">
          Configurações de SLA
        </h1>
        <p className="text-slate-400 text-sm mt-0.5">
          Tempos limite de resposta e resolução por nível de prioridade (horário
          comercial: seg–sex, 08h–18h)
        </p>
      </div>

      {error && <Alert variant="danger">{error}</Alert>}

      {loading ? (
        <div className="flex h-48 items-center justify-center">
          <Spinner size="lg" />
        </div>
      ) : (
        <div className="rounded-xl border border-border bg-background-surface overflow-hidden">
          <div className="overflow-x-auto">
            <Table>
              <TableHead>
                <TableRow>
                  <TableHeaderCell>Prioridade</TableHeaderCell>
                  <TableHeaderCell className="w-48">
                    Resposta (h úteis)
                  </TableHeaderCell>
                  <TableHeaderCell className="w-48">
                    Resolução (h úteis)
                  </TableHeaderCell>
                  <TableHeaderCell className="w-40">Alerta (%)</TableHeaderCell>
                  <TableHeaderCell className="w-36">
                    Atualizado em
                  </TableHeaderCell>
                  <TableHeaderCell className="w-24 text-right">
                    Ações
                  </TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {configs.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell>
                      <span className={LEVEL_COLOR[c.level]}>
                        {LEVEL_LABEL[c.level]}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="text-slate-200">
                        {c.response_time_hours}h
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="text-slate-200">
                        {c.resolve_time_hours}h
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="text-slate-200">
                        {c.warning_threshold}%
                      </span>
                    </TableCell>
                    <TableCell muted className="text-xs">
                      {updatedAt(c)}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setEditing(c)}
                      >
                        Editar
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}

      {/* Info card */}
      {!loading && (
        <div className="rounded-xl border border-border bg-background-surface p-4 text-sm text-slate-400 space-y-1">
          <p className="font-medium text-slate-300">Como funciona</p>
          <ul className="list-disc list-inside space-y-0.5">
            <li>
              <strong className="text-slate-300">Resposta:</strong> tempo máximo
              para a primeira interação de um técnico no chamado.
            </li>
            <li>
              <strong className="text-slate-300">Resolução:</strong> tempo
              máximo para fechar o chamado.
            </li>
            <li>
              <strong className="text-slate-300">Alerta:</strong> notificação
              antecipada quando o percentual do prazo já consumido atingir o
              limiar configurado.
            </li>
            <li>
              Períodos de espera (aguardando cliente / aguardando técnico)
              pausam o contador de SLA.
            </li>
          </ul>
        </div>
      )}

      {editing && (
        <SlaEditModal
          config={editing}
          onClose={() => setEditing(null)}
          onSaved={handleSaved}
        />
      )}
    </div>
  );
}
