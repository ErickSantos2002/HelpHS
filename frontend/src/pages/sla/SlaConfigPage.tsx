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

const MINUTOS_POR_HORA = 60;
const MINUTOS_POR_DIA = 24 * MINUTOS_POR_HORA;

/**
 * O prazo em dias, horas e minutos, na unidade em que ele é guardado.
 *
 * É a ÚNICA implementação da regra, e agora com os DOIS chamadores da tela: a
 * linha da lista e a dica do formulário. Dois formatadores do mesmo prazo
 * divergiriam na primeira vez que alguém mexesse num só — e aqui a divergência
 * apareceria entre o que a pessoa lê na lista e o que ela lê antes de salvar,
 * que é o pior lugar possível para dois números discordarem.
 *
 * Sem casa decimal em lugar nenhum: 30 min é "30min", não "0,5h".
 */
function descreveMinutos(total: number): string {
  const dias = Math.floor(total / MINUTOS_POR_DIA);
  const horas = Math.floor((total % MINUTOS_POR_DIA) / MINUTOS_POR_HORA);
  const minutos = total % MINUTOS_POR_HORA;
  const partes: string[] = [];
  if (dias) partes.push(`${dias}d`);
  if (horas) partes.push(`${horas}h`);
  if (minutos) partes.push(`${minutos}min`);
  return partes.length > 0 ? partes.join(" ") : "0min";
}

/**
 * O prazo, na mesma unidade em que ele é guardado e editado.
 *
 * Aqui havia um traço com a nota "não representável em horas", e ele era a
 * resposta CERTA enquanto a lista só tinha o campo derivado, que chega nulo
 * quando o prazo não é hora cheia. Assim que o formulário passou a falar
 * minutos, o valor exato ficou disponível também aqui — e traço onde há dado é
 * a tela escondendo o que tem.
 *
 * `descreveMinutos` é o MESMO formatador da dica de edição. A lista e o
 * formulário dizendo o mesmo prazo com palavras diferentes seria o defeito
 * seguinte, e é o tipo de divergência que ninguém percebe até alguém comparar
 * as duas telas lado a lado.
 */
function Prazo({ minutos }: { minutos: number }) {
  return (
    <p className="text-sm font-semibold text-conteudo-heading mt-0.5">
      {descreveMinutos(minutos)}
    </p>
  );
}

// ── Validation schema ─────────────────────────────────────────

/**
 * O formulário fala MINUTOS, que é a unidade em que o prazo é guardado.
 *
 * Falava horas inteiras, e por isso não conseguia escrever os 30 min da
 * Crítica — o prazo que existe em produção e que só entrou lá por script.
 * Enquanto isso durou, abrir "Editar SLA — Crítica" e salvar TROCAVA aquele
 * prazo por um número redondo. Perda de dado silenciosa, na prioridade mais
 * urgente do sistema.
 *
 * A alternativa era um número com seletor de unidade. Ela foi recusada por um
 * motivo concreto: trocar "minutos" para "horas" sem mexer no número multiplica
 * o prazo por 60 SEM PEDIR NADA, e o formulário passaria a converter nos dois
 * sentidos — que é exatamente onde esse erro mora. Em minutos o formulário não
 * converte: a ida e a volta são identidade, e o único número que existe tem um
 * significado só.
 *
 * O teto acompanha o do backend (`SLAConfigUpdate`): 9999 h = 599 940 min.
 */
const editSchema = z
  .object({
    response_time_minutes: z.coerce
      .number()
      .int("Deve ser inteiro")
      .min(1, "Mínimo 1 minuto")
      .max(599_940, "Máximo 599940 minutos"),
    resolve_time_minutes: z.coerce
      .number()
      .int("Deve ser inteiro")
      .min(1, "Mínimo 1 minuto")
      .max(599_940, "Máximo 599940 minutos"),
    warning_threshold: z.coerce.number().int("Deve ser inteiro").min(1).max(100, "Máximo 100%"),
  })
  .refine((v) => v.resolve_time_minutes > v.response_time_minutes, {
    message: "Deve ser maior que o tempo de resposta",
    path: ["resolve_time_minutes"],
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
    // Sem `?? undefined` e sem recuo: `*_time_minutes` é `int` NOT NULL no
    // banco e sempre vem na resposta. O campo que podia faltar era o derivado
    // em horas, e ele saiu do formulário.
    defaultValues: {
      response_time_minutes: config.response_time_minutes,
      resolve_time_minutes: config.resolve_time_minutes,
      warning_threshold: config.warning_threshold,
    },
  });

  // A conversão é FEEDBACK, não entrada: mostra o que o número digitado quer
  // dizer em dias e horas, sem que exista um segundo campo para discordar dele.
  // É o que torna "4320" legível sem reintroduzir a aritmética de duas vias.
  const respostaAgora = form.watch("response_time_minutes");
  const resolucaoAgora = form.watch("resolve_time_minutes");
  const emPalavras = (v: unknown) => {
    const n = Number(v);
    return Number.isFinite(n) && n > 0 ? `= ${descreveMinutos(Math.floor(n))}` : undefined;
  };

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
            label="Resposta (minutos úteis) *"
            type="number"
            min={1}
            error={form.formState.errors.response_time_minutes?.message}
            hint={emPalavras(respostaAgora)}
            {...form.register("response_time_minutes")}
          />
          <Input
            label="Resolução (minutos úteis) *"
            type="number"
            min={1}
            error={form.formState.errors.resolve_time_minutes?.message}
            hint={emPalavras(resolucaoAgora)}
            {...form.register("resolve_time_minutes")}
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
                // Em minutos nao existe o NaN que o campo derivado produzia:
                // `*_time_minutes` e `int` NOT NULL, e o backend exige `ge=1`.
                // A guarda do zero fica assim mesmo -- ela custa nada e o dado
                // vem da REDE, onde "nao pode ser zero" e promessa de outro
                // processo, nao garantia deste.
                const proporcao = c.resolve_time_minutes
                  ? Math.min((c.response_time_minutes / c.resolve_time_minutes) * 100, 100)
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
                            <Prazo minutos={c.response_time_minutes} />
                          </div>
                        </div>

                        {/* Resolução */}
                        <div className="flex items-center gap-1.5">
                          <Icon name="shield" size={16} strokeWidth={2} className="text-conteudo-muted" />
                          <div>
                            <p className="text-[10px] text-conteudo-muted leading-none">Resolução</p>
                            <Prazo minutos={c.resolve_time_minutes} />
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
