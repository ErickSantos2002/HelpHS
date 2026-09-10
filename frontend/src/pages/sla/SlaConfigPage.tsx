import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm, type Resolver } from "react-hook-form";
import { z } from "zod";
import {
  Alert,
  Badge,
  Button,
  Card,
  Icon,
  Input,
  Modal,
  ModalFooter,
  Spinner,
} from "../../components/ui";
import {
  PRIORIDADE,
  PRIORIDADES,
  TOM_PRIORIDADE,
  rotuloDePrioridade,
  varianteDePrioridade,
  type TicketPriority,
} from "../../lib/prioridade";
import {
  getSLAConfigs,
  updateSLAConfig,
  type SLAConfig,
} from "../../services/slaService";

// ── A prioridade, que aqui se chamava "nível" ─────────────────
//
// Esta tela tinha os três mapas de sempre — `LEVEL_LABEL`, `LEVEL_STYLE` e
// `LEVEL_ORDER` —, e os três diziam coisa própria: o rótulo estava no
// MASCULINO ("Crítico", "Alto", "Médio", "Baixo"), contra o feminino que a
// emenda E17 fixou por concordar com "prioridade"; a cor era um sexto esquema
// (vermelho/laranja/amarelo/cinza da paleta crua) que não batia com nenhuma das
// outras telas; e a ordem repetia à mão o campo `ordem` do módulo.
//
// Os três saíram para `lib/prioridade.ts`. O que a tela chama de "nível de
// SLA" é a prioridade do chamado — o backend manda os mesmos quatro valores —,
// e duas palavras para o mesmo dado era metade do problema.

/**
 * A ordem de urgência sai do módulo, com recuo.
 *
 * O recuo manda a prioridade desconhecida para o **fim** da lista. `indexOf`
 * daria -1, que a ordenaria como mais urgente que "crítica" — um valor que o
 * backend passasse a mandar apareceria no topo da tela por acidente aritmético.
 */
function ordemDePrioridade(p: string): number {
  return PRIORIDADE[p as TicketPriority]?.ordem ?? PRIORIDADES.length;
}

// ── Helpers ───────────────────────────────────────────────────

/**
 * `null` NÃO é um caso de borda aqui — é o caso normal da Crítica.
 *
 * `response_time_hours` e `resolve_time_hours` são derivados de
 * `*_time_minutes` no backend e valem `None` quando o prazo não é hora cheia.
 * A Crítica tem 30 min, então chegam nulos por desenho, todo dia.
 *
 * A versão anterior recebia `h: number` e não se defendia, porque o tipo dizia
 * que não precisava. `null < 24` é `true` (o `null` vira 0 na comparação), a
 * interpolação escrevia `${null}h`, e a tela mostrava "nullh" em produção —
 * sem erro de TypeScript, sem exceção em runtime, sem nada. Tipo que mente
 * custa mais caro que tipo ausente: ele desliga a única checagem que havia.
 */
function formatHours(h: number | null | undefined) {
  if (h === null || h === undefined) return null;
  if (h < 24) return `${h}h`;
  const days = Math.floor(h / 24);
  const rest = h % 24;
  return rest > 0 ? `${days}d ${rest}h` : `${days}d`;
}

/**
 * O prazo, ou um traço quando ele não cabe em horas.
 *
 * O traço sozinho é ambíguo — pode ser "não configurado", pode ser zero — e a
 * nota é o que separa os dois. Ela vive em `sr-only` e não em `title`: `title`
 * não é anunciado de forma confiável por leitor de tela nenhum, e o valor mais
 * importante da tela não pode ficar mudo para quem não vê o traço.
 */
function Prazo({ horas }: { horas: number | null | undefined }) {
  const texto = formatHours(horas);
  if (texto !== null) {
    return <p className="text-sm font-semibold text-conteudo-heading mt-0.5">{texto}</p>;
  }
  return (
    <p
      className="text-sm font-semibold text-conteudo-heading mt-0.5"
      title="Prazo não representável em horas inteiras — edite para ver o valor exato."
    >
      <span aria-hidden="true">—</span>
      <span className="sr-only">não representável em horas</span>
    </p>
  );
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

// ── PrioridadeChip ────────────────────────────────────────────

/**
 * O selo de prioridade da tela, que é o `Badge` do pacote com o ponto dentro.
 *
 * Não é o `PriorityBadge` porque este desenho leva o ponto colorido junto do
 * rótulo — e o ponto é justamente o que o módulo pede que nunca apareça
 * sozinho. Aqui ele tem o rótulo ao lado, então a cor é reforço e não o único
 * portador da informação.
 */
function PrioridadeChip({ level }: { level: string }) {
  const variante = varianteDePrioridade(level);
  return (
    <Badge variant={variante} className="gap-1.5">
      <span
        aria-hidden="true"
        className={`h-1.5 w-1.5 shrink-0 rounded-full ${TOM_PRIORIDADE[variante].ponto}`}
      />
      {rotuloDePrioridade(level)}
    </Badge>
  );
}

// ── SlaEditModal ──────────────────────────────────────────────

function SlaEditModal({ config, onClose, onSaved }: {
  config: SLAConfig;
  onClose: () => void;
  onSaved: (updated: SLAConfig) => void;
}) {
  const [submitError, setSubmitError] = useState<string | null>(null);

  const form = useForm<EditValues>({
    resolver: zodResolver(editSchema) as Resolver<EditValues>,
    // `?? undefined` porque o prazo pode não ser hora cheia, e o formulário só
    // fala em horas inteiras. Semear com `null` deixava o campo num estado que
    // o react-hook-form não declara — e o tipo honesto foi exatamente o que
    // mostrou isso: com `number` mentindo, esta linha compilava.
    //
    // Campo vazio é a leitura certa aqui: a Crítica tem 30 min, e o formulário
    // NÃO CONSEGUE escrever esse valor. Vazio obriga a pessoa a digitar um
    // prazo que o formulário sabe representar, em vez de mostrar um número
    // arredondado que ela salvaria sem perceber que mudou o SLA.
    defaultValues: {
      response_time_hours: config.response_time_hours ?? undefined,
      resolve_time_hours: config.resolve_time_hours ?? undefined,
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
    <Modal open onClose={onClose} title={`Editar SLA — ${rotuloDePrioridade(config.level)}`}>
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
        <PrioridadeChip level={config.level} />

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

        <p className="text-xs text-conteudo-muted">
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
        setConfigs(
          [...data].sort(
            (a, b) => ordemDePrioridade(a.level) - ordemDePrioridade(b.level),
          ),
        );
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
        <h1 className="text-2xl font-bold text-conteudo-heading">Configurações de SLA</h1>
        <p className="text-conteudo-muted text-sm mt-0.5">
          Tempos limite de resposta e resolução por nível de prioridade (seg–sex, 08h–17h)
        </p>
      </div>

      {error && <Alert variant="danger">{error}</Alert>}

      {loading ? (
        <div className="flex h-48 items-center justify-center"><Spinner size="lg" /></div>
      ) : (
        <>
          <Card padding="none">
            {/* Card header */}
            <div className="px-4 py-3 border-b border-borda">
              <p className="text-sm font-semibold text-conteudo-heading">Níveis de SLA</p>
              <p className="text-xs text-conteudo-muted mt-0.5">Clique em editar para ajustar os tempos de cada nível.</p>
            </div>

            <div className="divide-y divide-borda">
              {configs.map((c) => {
                const rotulo = rotuloDePrioridade(c.level);
                // Os dois prazos podem ser nulos, e `null / null` e NaN --
                // `width: NaN%` e atributo invalido, descartado em silencio.
                // Sem prazo nao ha proporcao a desenhar: a barra fica em zero.
                const proporcao =
                  c.response_time_hours != null && c.resolve_time_hours
                    ? Math.min((c.response_time_hours / c.resolve_time_hours) * 100, 100)
                    : 0;
                return (
                  <div key={c.id} className="flex items-center gap-4 px-4 py-4 hover:bg-surface-elevated/40 transition-colors">

                    {/* Level badge */}
                    <div className="shrink-0">
                      <PrioridadeChip level={c.level} />
                    </div>

                    {/* Times */}
                    <div className="flex-1 min-w-0">
                      {/* Progress bar — mostra resposta vs resolução. Decorativa:
                          os dois números que ela compara estão escritos logo
                          abaixo, então ela não é o único portador de nada. */}
                      <div className="flex items-center gap-3 mb-2">
                        <div className="flex-1 h-1.5 rounded-full bg-surface-elevated overflow-hidden">
                          <div
                            aria-hidden="true"
                            className={`h-full rounded-full opacity-60 ${TOM_PRIORIDADE[varianteDePrioridade(c.level)].ponto}`}
                            style={{ width: `${proporcao}%` }}
                          />
                        </div>
                      </div>

                      <div className="flex flex-wrap gap-4">
                        {/* Resposta */}
                        <div className="flex items-center gap-1.5">
                          <Icon name="clock" size={16} strokeWidth={2} className="text-conteudo-muted" />
                          <div>
                            <p className="text-[10px] text-conteudo-muted leading-none">Resposta</p>
                            <Prazo horas={c.response_time_hours} />
                          </div>
                        </div>

                        {/* Resolução */}
                        <div className="flex items-center gap-1.5">
                          <Icon name="shield" size={16} strokeWidth={2} className="text-conteudo-muted" />
                          <div>
                            <p className="text-[10px] text-conteudo-muted leading-none">Resolução</p>
                            <Prazo horas={c.resolve_time_hours} />
                          </div>
                        </div>

                        {/* Alerta */}
                        <div className="flex items-center gap-1.5">
                          <Icon name="bell" size={16} strokeWidth={2} className="text-conteudo-muted" />
                          <div>
                            <p className="text-[10px] text-conteudo-muted leading-none">Alerta</p>
                            <p className="text-sm font-semibold text-conteudo-heading mt-0.5">{c.warning_threshold}%</p>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Updated at */}
                    <p className="hidden md:block shrink-0 text-xs text-conteudo-muted">
                      {new Date(c.updated_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" })}
                    </p>

                    {/* Edit */}
                    <button
                      type="button"
                      onClick={() => setEditing(c)}
                      title="Editar"
                      // Quatro linhas, quatro botões só de ícone, e o `Icon` é
                      // `aria-hidden`: sem o rótulo com a prioridade dentro,
                      // quem usa leitor de tela ouvia "Editar" quatro vezes e
                      // não tinha como saber qual linha estava escolhendo.
                      aria-label={`Editar SLA da prioridade ${rotulo}`}
                      className="p-1.5 rounded-lg text-conteudo-muted hover:text-conteudo-link hover:bg-action-tint transition-colors cursor-pointer shrink-0"
                    >
                      <Icon name="edit" size={16} strokeWidth={2} />
                    </button>
                  </div>
                );
              })}
            </div>
          </Card>

          {/* Info card */}
          <div className="rounded-xl border border-borda/60 bg-surface/50 p-4">
            <div className="flex items-center gap-2 mb-2 text-conteudo">
              <Icon name="info" size={16} strokeWidth={2} className="text-conteudo-muted" />
              <p className="text-sm font-medium">Como funciona</p>
            </div>
            <ul className="space-y-1 text-xs text-conteudo-muted">
              <li><span className="text-conteudo font-medium">Resposta:</span> tempo máximo para a primeira interação de um técnico no chamado.</li>
              <li><span className="text-conteudo font-medium">Resolução:</span> tempo máximo para fechar o chamado.</li>
              <li><span className="text-conteudo font-medium">Alerta:</span> notificação antecipada quando o percentual do prazo consumido atingir o limiar.</li>
              <li>Períodos de espera (aguardando cliente / aguardando técnico) <span className="text-conteudo font-medium">pausam</span> o contador de SLA.</li>
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
