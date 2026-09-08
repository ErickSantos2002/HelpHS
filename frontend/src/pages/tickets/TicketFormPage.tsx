import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams } from "react-router-dom";
import { z } from "zod";
import {
  Alert,
  Button,
  FileUpload,
  FormDropdown,
  Icon,
  Input,
  PriorityBadge,
  RadioCards,
  Spinner,
  Textarea,
} from "../../components/ui";
import { CATEGORIAS, rotuloDeCategoria } from "../../lib/categoria";
import { PRIORIDADE, PRIORIDADES, type TicketPriority } from "../../lib/prioridade";
import {
  getProducts,
  type Product,
} from "../../services/productService";
import { getMyEquipment, type Equipment } from "../../services/equipmentService";
import { uploadAttachments } from "../../services/attachmentService";
import { toastApiError } from "../../lib/toastError";
import { cn, plural } from "../../lib/utils";
import {
  createTicket,
  getTicket,
  updateTicket,
  type Ticket,
} from "../../services/ticketService";

// ── Schema ────────────────────────────────────────────────────

/** Espelha MAX_EQUIPMENTS_PER_TICKET do backend — passar disso volta 422. */
const MAX_EQUIPAMENTOS = 20;

const schema = z.object({
  title: z.string().min(5, "Mínimo 5 caracteres").max(200, "Título muito longo"),
  description: z.string().min(10, "Mínimo 10 caracteres").max(5000, "Descrição muito longa"),
  priority: z.enum(["critical", "high", "medium", "low"]),
  category: z.string().min(1, "Selecione uma categoria"),
  product_id: z.string().optional(),
  // Sem .default([]): o default faz o zod gerar um tipo de entrada opcional e
  // um de saída obrigatório, e o resolver do react-hook-form recusa os dois
  // como incompatíveis. O valor inicial vem de defaultValues.
  equipment_ids: z
    .array(z.string())
    .max(MAX_EQUIPAMENTOS, `Máximo de ${MAX_EQUIPAMENTOS} equipamentos por chamado`),
  client_observation: z.string().max(2000, "Observação muito longa").optional(),
});

type FormValues = z.infer<typeof schema>;

// ── Constants ─────────────────────────────────────────────────

const ALLOWED_EXTENSIONS = [".pdf",".doc",".docx",".xls",".xlsx",".png",".jpg",".jpeg",".gif",".txt",".csv",".zip",".rar"];
const MAX_FILE_SIZE_MB = 25;
const MAX_FILES = 10;

/*
 * As oito categorias saíram daqui: moram em `lib/categoria.ts`, que é a fonte
 * única consumida também pelo detalhe do chamado e pelo relatório. Eram TRÊS
 * cópias, todas concordando — e foi exatamente assim que prioridade começou,
 * antes de virar dez mapas divergentes.
 */

/**
 * As quatro prioridades, como opções do `RadioCards`.
 *
 * Vêm de `lib/prioridade`. O que havia aqui era o **sexto** mapa divergente do
 * mesmo dado, e discordava dos outros em duas coisas ao mesmo tempo: pintava
 * `bg-red-500` e `bg-amber-500` crus, fora do sistema, e dizia "Crítico",
 * "Alto", "Médio", "Baixo" — no masculino, contra "prioridade". A emenda E17
 * fixou o feminino no pacote.
 */
const PRIORIDADES_OPCOES = PRIORIDADES.map((p) => ({
  value: p,
  label: PRIORIDADE[p].rotulo,
  tone: PRIORIDADE[p].variante,
}));


// ── Step indicator ────────────────────────────────────────────

/**
 * Onde a pessoa está: preenchendo ou revisando.
 *
 * Era uma fileira de `<span>`, e a etapa corrente existia **só na cor** —
 * `text-slate-200` contra `text-slate-500`. Quem usa leitor de tela ouvia
 * "1 Formulário / 2 Revisão" e não tinha como saber em qual estava.
 *
 * Agora é uma lista ordenada com `aria-current="step"`, que é o que carrega
 * "esta é a atual" para a árvore. A etapa cumprida diz "concluída" em texto,
 * porque o ✓ é desenho e sai da árvore.
 *
 * As cores saíram do sistema: `bg-emerald-600 text-white` era verde cru, e
 * `bg-primary text-white` é a família da emenda E1 — branco sobre primário dá
 * 3,83:1. O par medido é `text-on-primary`.
 */
function StepIndicator({ current }: { current: 1 | 2 }) {
  const etapas = [
    { numero: 1, nome: "Formulário" },
    { numero: 2, nome: "Revisão" },
  ] as const;

  return (
    <ol className="flex shrink-0 items-center gap-2 text-sm">
      {etapas.map((etapa, i) => {
        const atual = current === etapa.numero;
        const cumprida = current > etapa.numero;
        return (
          <li key={etapa.numero} className="flex items-center gap-2">
            {i > 0 && (
              <span className="text-conteudo-muted" aria-hidden="true">
                /
              </span>
            )}
            <span
              className={cn(
                "flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold",
                cumprida
                  // `bg-action-success`, e NÃO `bg-success`: o par de
                  // `text-on-success` é o degrau de AÇÃO da emenda E2. Sobre a
                  // cor cheia da rampa esse mesmo texto dá 2,54:1 — foi o que a
                  // catraca acusou aqui, e é exatamente o defeito que a E2
                  // existe para tornar impossível.
                  ? "bg-action-success text-on-success"
                  : atual
                    ? "bg-primary text-on-primary"
                    : "bg-surface-elevated text-conteudo-muted",
              )}
              aria-hidden="true"
            >
              {cumprida ? <Icon name="check" size={14} strokeWidth={2.5} /> : etapa.numero}
            </span>
            <span
              aria-current={atual ? "step" : undefined}
              className={cn(
                "font-medium",
                atual
                  ? "text-conteudo"
                  : cumprida
                    ? "text-on-tint-success"
                    : "text-conteudo-muted",
              )}
            >
              {etapa.nome}
              {cumprida && <span className="sr-only"> (concluída)</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

// ── Section wrapper ───────────────────────────────────────────

function FormSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-borda/40 bg-surface">
      <div className="border-b border-borda/40 px-5 py-3.5">
        <h2 className="text-sm font-semibold text-conteudo">{title}</h2>
      </div>
      <div className="p-5 space-y-4">{children}</div>
    </div>
  );
}

// ── Sidebar summary ───────────────────────────────────────────

function SidebarSummary({ values, files, productName }: { values: Partial<FormValues>; files: File[]; productName?: string }) {
  const cat = values.category ? rotuloDeCategoria(values.category) : null;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-borda/40 bg-surface p-4">
        <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-conteudo-muted">Resumo</p>
        <div className="space-y-3">
          <SummaryRow label="Título" empty="Não preenchido">
            {values.title && values.title.length >= 5 ? (
              <span className="text-sm text-conteudo line-clamp-2">{values.title}</span>
            ) : null}
          </SummaryRow>
          <SummaryRow label="Categoria" empty="Não selecionada">
            {cat ? <span className="text-sm text-conteudo">{cat}</span> : null}
          </SummaryRow>
          <SummaryRow label="Prioridade" empty="Não definida">
            {values.priority ? <PriorityBadge priority={values.priority} /> : null}
          </SummaryRow>
          {productName && (
            <SummaryRow label="Produto" empty="">
              <span className="text-sm text-conteudo">{productName}</span>
            </SummaryRow>
          )}
          {files.length > 0 && (
            <SummaryRow label="Anexos" empty="">
              <span className="text-sm text-conteudo">{files.length} arquivo{files.length > 1 ? "s" : ""}</span>
            </SummaryRow>
          )}
        </div>
      </div>

      <div className="rounded-xl border border-borda/40 bg-surface p-4">
        <p className="mb-3 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-conteudo-muted">
          <Icon name="info" size={16} />
          Dicas
        </p>
        <ul className="space-y-2.5 text-xs text-conteudo-muted">
          <li className="flex gap-2"><span className="shrink-0 text-primary mt-0.5">•</span>Descreva o problema com o máximo de detalhes possível.</li>
          <li className="flex gap-2"><span className="shrink-0 text-primary mt-0.5">•</span>Informe quando o problema começou e com que frequência ocorre.</li>
          <li className="flex gap-2"><span className="shrink-0 text-primary mt-0.5">•</span>Anexe prints ou fotos — isso acelera muito o atendimento.</li>
          <li className="flex gap-2"><span className="shrink-0 text-primary mt-0.5">•</span>Selecione o produto e equipamento correto para facilitar o diagnóstico.</li>
        </ul>
      </div>
    </div>
  );
}

function SummaryRow({ label, children, empty }: { label: string; children: React.ReactNode; empty: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <p className="text-[10px] font-semibold uppercase tracking-widest text-conteudo-muted">{label}</p>
      {children ?? <span className="text-xs italic text-conteudo-faint">{empty}</span>}
    </div>
  );
}

// ── Preview row ───────────────────────────────────────────────

function PreviewRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-4 py-3 border-b border-borda/30 last:border-0">
      <p className="w-28 shrink-0 text-[11px] font-semibold uppercase tracking-widest text-conteudo-muted pt-0.5">{label}</p>
      <div className="flex-1 text-sm text-conteudo">{children}</div>
    </div>
  );
}

// ── Preview step ──────────────────────────────────────────────

function PreviewStep({ values, files, productName, equipmentNames, onBack, onSubmit, submitting, isEdit }: {
  values: FormValues; files: File[]; productName?: string; equipmentNames: string[];
  onBack: () => void; onSubmit: () => void; submitting: boolean; isEdit: boolean;
}) {
  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_300px]">
      <div className="space-y-5">
        <div className="rounded-xl border border-borda/40 bg-surface">
          <div className="border-b border-borda/40 px-5 py-3.5">
            <h2 className="text-sm font-semibold text-conteudo">Confirme os dados antes de enviar</h2>
          </div>
          <div className="px-5 py-2">
            <PreviewRow label="Título">{values.title}</PreviewRow>
            <PreviewRow label="Categoria">{rotuloDeCategoria(values.category)}</PreviewRow>
            <PreviewRow label="Prioridade">
              <PriorityBadge priority={values.priority} />
            </PreviewRow>
            {productName && <PreviewRow label="Produto">{productName}</PreviewRow>}
            {equipmentNames.length > 0 && (
              <PreviewRow label={plural(equipmentNames.length, "Equipamento", "Equipamentos")}>
                <ul className="space-y-0.5">
                  {equipmentNames.map((nome) => (
                    <li key={nome} className="text-conteudo">{nome}</li>
                  ))}
                </ul>
              </PreviewRow>
            )}
            <PreviewRow label="Descrição">
              <p className="whitespace-pre-wrap leading-relaxed text-conteudo">{values.description}</p>
            </PreviewRow>
            {!isEdit && values.client_observation && (
              <PreviewRow label="Observações">
                <p className="whitespace-pre-wrap text-conteudo">{values.client_observation}</p>
              </PreviewRow>
            )}
            {files.length > 0 && (
              <PreviewRow label={`Anexos (${files.length})`}>
                <ul className="space-y-0.5">{files.map((f, i) => <li key={i} className="text-conteudo-muted">{f.name}</li>)}</ul>
              </PreviewRow>
            )}
          </div>
        </div>

        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={onBack} disabled={submitting}>Voltar e editar</Button>
          <Button onClick={onSubmit} loading={submitting}>Confirmar e enviar</Button>
        </div>
      </div>

      <div>
        <div className="rounded-xl border border-borda/40 bg-surface p-4">
          <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-conteudo-muted">Resumo</p>
          <div className="space-y-2.5 text-xs text-conteudo-muted">
            <p>Revise todas as informações antes de confirmar. Após o envio, o chamado será registrado e encaminhado para a equipe técnica.</p>
            <p className="text-primary font-medium">Você poderá acompanhar o status em Tickets.</p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────

export default function TicketFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isEdit = Boolean(id);

  const [step, setStep] = useState<"form" | "preview">("form");
  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const [products, setProducts] = useState<Product[]>([]);
  const [allMyEquipments, setAllMyEquipments] = useState<Equipment[]>([]);
  const [equipments, setEquipments] = useState<Equipment[]>([]);
  const [loadingProducts, setLoadingProducts] = useState(true);
  const [loadingTicket, setLoadingTicket] = useState(isEdit);
  const [existingTicket, setExistingTicket] = useState<Ticket | null>(null);

  const { register, handleSubmit, watch, setValue, reset, formState: { errors } } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { priority: "medium", category: "", product_id: "", equipment_ids: [] },
  });

  const selectedProductId = watch("product_id");
  const watchedCategory = watch("category");
  const watchedPriority = watch("priority");
  const currentValues = watch();

  useEffect(() => {
    Promise.all([
      getProducts().then((res) => setProducts(res.items)),
      getMyEquipment().then(setAllMyEquipments).catch(() => {}),
    ]).finally(() => setLoadingProducts(false));
  }, []);

  // Trocar de produto descarta a seleção anterior: os aparelhos listados são
  // os daquele produto, e manter os antigos deixaria no chamado equipamento
  // que sumiu da lista.
  useEffect(() => {
    setValue("equipment_ids", []);
    if (selectedProductId) {
      setEquipments(allMyEquipments.filter((e) => e.product_id === selectedProductId));
    } else {
      setEquipments([]);
    }
  }, [selectedProductId, allMyEquipments, setValue]);

  useEffect(() => {
    if (!isEdit || !id) return;
    getTicket(id)
      .then((t) => {
        setExistingTicket(t);
        reset({
          title: t.title,
          description: "",
          priority: t.priority,
          category: t.category,
          product_id: t.product_id ?? "",
          equipment_ids: t.equipments.map((e) => e.id),
        });
      })
      .catch(() => navigate("/tickets"))
      .finally(() => setLoadingTicket(false));
  }, [id, isEdit, navigate, reset]);

  const productOptions = products.map((p) => ({ value: p.id, label: p.name }));
  const selectedProduct = products.find((p) => p.id === currentValues.product_id);
  const selectedEquipmentIds = currentValues.equipment_ids ?? [];
  const selectedEquipments = equipments.filter((e) => selectedEquipmentIds.includes(e.id));
  const selecionaveis = equipments.slice(0, MAX_EQUIPAMENTOS);
  const todosMarcados =
    selecionaveis.length > 0 && selecionaveis.every((e) => selectedEquipmentIds.includes(e.id));
  const noLimite = selectedEquipmentIds.length >= MAX_EQUIPAMENTOS;

  function toggleEquipment(equipmentId: string) {
    const atual = currentValues.equipment_ids ?? [];
    if (!atual.includes(equipmentId) && atual.length >= MAX_EQUIPAMENTOS) return;
    const proximo = atual.includes(equipmentId)
      ? atual.filter((id) => id !== equipmentId)
      : [...atual, equipmentId];
    setValue("equipment_ids", proximo, { shouldValidate: true });
  }

  function toggleAllEquipments() {
    setValue("equipment_ids", todosMarcados ? [] : selecionaveis.map((e) => e.id), {
      shouldValidate: true,
    });
  }

  async function submitForm() {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const base = {
        title: currentValues.title,
        description: currentValues.description,
        priority: currentValues.priority,
        category: currentValues.category,
        product_id: currentValues.product_id || null,
        equipment_ids: currentValues.equipment_ids ?? [],
      };
      const ticket = isEdit && id
        ? await updateTicket(id, base)
        : await createTicket({ ...base, client_observation: currentValues.client_observation || null });

      // Os anexos só podem subir depois que o chamado existe. Se falharem, o
      // chamado já foi criado — avisa em vez de fingir que deu tudo certo.
      if (files.length > 0) {
        try {
          await uploadAttachments(ticket.id, files);
        } catch (err) {
          toastApiError(
            err,
            "O chamado foi criado, mas os anexos não foram enviados. Anexe novamente pelo chamado.",
          );
        }
      }

      navigate(`/tickets/${ticket.id}`);
    } catch {
      setSubmitError("Erro ao salvar o chamado. Tente novamente.");
      setStep("form");
    } finally {
      setSubmitting(false);
    }
  }

  if (loadingTicket || loadingProducts) {
    return <div className="flex h-48 items-center justify-center"><Spinner size="lg" /></div>;
  }

  return (
    <div className="space-y-5 pb-10">
      {/* ── Header ───────────────────────────────────────────── */}
      <div className="flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-borda/40 bg-surface px-5 py-4">
        <div className="min-w-0">
          {/*
            Era um `<button onClick={navigate(-1)}>` com a linha inteira dentro,
            então o nome acessível do controle era "Tickets / Novo chamado" — a
            página de onde se vem E a página onde se está, num controle só.

            Agora é trilha: um LINK para o destino (regra "navegação é link"),
            e a página atual como texto com `aria-current="page"`, que é o que
            diz "esta é a que você está vendo" sem fingir ser clicável.

            A volta também deixou de ser `navigate(-1)`: de um formulário, o
            histórico pode ter vindo do detalhe, da lista ou do painel, e "para
            trás" não é um lugar. `/tickets` é.
          */}
          <nav aria-label="Trilha" className="mb-2">
            <ol className="flex items-center gap-1.5 text-xs font-medium">
              <li>
                <Link
                  to="/tickets"
                  className="flex items-center gap-1.5 text-conteudo-muted transition-colors hover:text-conteudo-link"
                >
                  <Icon name="arrowLeft" size={14} strokeWidth={2.5} />
                  Tickets
                </Link>
              </li>
              <li aria-hidden="true" className="text-conteudo-faint">
                /
              </li>
              <li aria-current="page" className="font-mono text-conteudo-muted">
                {isEdit && existingTicket ? existingTicket.protocol : "Novo chamado"}
              </li>
            </ol>
          </nav>
          <h1 className="text-xl font-extrabold leading-tight text-conteudo-heading">
            {isEdit ? "Editar chamado" : "Abrir chamado"}
          </h1>
          <p className="mt-1 text-sm text-conteudo-muted">
            {isEdit ? "Atualize as informações do chamado." : "Preencha os campos para registrar seu chamado."}
          </p>
        </div>
        <StepIndicator current={step === "form" ? 1 : 2} />
      </div>

      {submitError && (
        <Alert variant="danger" onDismiss={() => setSubmitError(null)}>{submitError}</Alert>
      )}

      {/* ── Body ─────────────────────────────────────────────── */}
      {step === "preview" ? (
        <PreviewStep
          values={currentValues}
          files={files}
          productName={selectedProduct?.name}
          equipmentNames={selectedEquipments.map((e) =>
            e.serial_number ? `${e.name} — ${e.serial_number}` : e.name,
          )}
          onBack={() => setStep("form")}
          onSubmit={submitForm}
          submitting={submitting}
          isEdit={isEdit}
        />
      ) : (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_300px]">
          {/* ── Form column ─────────────────────────────────── */}
          <form onSubmit={handleSubmit(() => setStep("preview"))} className="space-y-4 min-w-0">
            {/* Identificação */}
            <FormSection title="Identificação">
              <div className="space-y-1">
                <Input
                  label="Título *"
                  placeholder="Ex: Sem acesso à Plataforma do Phoebus, Impressora sem conexão…"
                  error={errors.title?.message}
                  {...register("title")}
                />
                <p className="text-xs text-conteudo-muted">Resumo curto e objetivo do problema.</p>
              </div>

              <RadioCards
                name="category"
                label="Categoria"
                required
                value={watchedCategory}
                onChange={(v) => setValue("category", v, { shouldValidate: true })}
                options={CATEGORIAS.map((c) => ({ ...c }))}
                error={errors.category?.message}
              />

              <RadioCards
                name="priority"
                label="Prioridade"
                layout="linha"
                value={watchedPriority}
                onChange={(v) => setValue("priority", v as TicketPriority)}
                options={PRIORIDADES_OPCOES}
              />
            </FormSection>

            {/* Produto / Equipamentos */}
            <FormSection title="Produto e equipamentos (opcional)">
              <FormDropdown
                label="Produto"
                value={currentValues.product_id ?? ""}
                onChange={(v) => setValue("product_id", v, { shouldValidate: true })}
                options={productOptions}
                placeholder="Nenhum (opcional)"
              />

              {/*
                `fieldset` com `legend`, e não um `<label>` solto.

                O que havia aqui era um `<label>` sem `htmlFor` — um rótulo
                pendurado no vazio, que não nomeia coisa nenhuma e some da
                árvore de acessibilidade. As fichas abaixo são botões de
                alternância com `aria-pressed`, então quem usa leitor de tela
                ouvia "Notebook Dell, não pressionado" sem nunca ouvir a palavra
                "Equipamentos": não havia grupo.

                As fichas continuam `<button aria-pressed>` de propósito: é
                seleção MÚLTIPLA, o estado é binário por item, e `aria-pressed`
                é o que a especificação manda para alternância. Não é primitivo
                reinventado — é o controle nativo certo para o caso.
              */}
              <fieldset className="relative min-w-0 space-y-2 border-0 p-0">
                {/*
                  O `legend` é o PRIMEIRO filho, e isso não é estilo: fora dessa
                  posição ele deixa de nomear o grupo. Estava dentro de um `div`
                  de layout, e o grupo ficou sem nome de novo — o teste pegou.

                  Por isso o "Selecionar todos" vai posicionado, e não numa
                  linha de flex junto: pô-lo dentro do `legend` costuraria o
                  texto dele ao nome do grupo ("Equipamentos Selecionar todos
                  (3)"), que é outra forma de perder o nome.
                */}
                <legend className="text-sm font-medium text-conteudo">Equipamentos</legend>
                {equipments.length > 1 && (
                  <button
                    type="button"
                    onClick={toggleAllEquipments}
                    className="absolute right-0 top-0 cursor-pointer text-xs font-medium text-conteudo-link hover:underline"
                  >
                    {todosMarcados
                      ? "Limpar seleção"
                      : `Selecionar todos (${Math.min(equipments.length, MAX_EQUIPAMENTOS)})`}
                  </button>
                )}
                {!selectedProductId ? (
                  <p className="text-sm text-conteudo-muted">Selecione um produto primeiro.</p>
                ) : equipments.length === 0 ? (
                  <p className="text-sm text-conteudo-muted">
                    Você não tem equipamentos cadastrados para este produto.
                  </p>
                ) : (
                  <>
                    <div className="flex flex-wrap gap-2">
                      {equipments.map((e) => {
                        const marcado = selectedEquipmentIds.includes(e.id);
                        const bloqueado = !marcado && noLimite;
                        return (
                          <button
                            key={e.id}
                            type="button"
                            onClick={() => toggleEquipment(e.id)}
                            aria-pressed={marcado}
                            disabled={bloqueado}
                            title={bloqueado ? `Máximo de ${MAX_EQUIPAMENTOS} por chamado` : undefined}
                            className={cn(
                              "rounded-lg border px-3 py-2 text-left text-sm transition-colors",
                              bloqueado ? "cursor-not-allowed opacity-40" : "cursor-pointer",
                              marcado
                                ? "border-primary bg-primary/15 text-conteudo-heading"
                                : "border-borda text-conteudo-muted hover:border-borda",
                            )}
                          >
                            <span className="font-medium">{e.name}</span>
                            {e.serial_number && (
                              <span className="ml-2 font-mono text-xs text-conteudo-muted">
                                {e.serial_number}
                              </span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                    <p className="text-xs text-conteudo-muted">
                      {noLimite
                        ? `Máximo de ${MAX_EQUIPAMENTOS} aparelhos por chamado. Para os demais, abra um segundo chamado.`
                        : selectedEquipmentIds.length > 0
                          ? `${selectedEquipmentIds.length} ${plural(selectedEquipmentIds.length, "aparelho selecionado", "aparelhos selecionados")}. Um mesmo chamado pode cobrir vários.`
                          : "Se o problema atinge mais de um aparelho, marque todos — não é preciso abrir um chamado para cada."}
                    </p>
                  </>
                )}
              </fieldset>
            </FormSection>

            {/* Descrição */}
            <FormSection title="Descrição do problema">
              <div className="space-y-1">
                <Textarea
                  label="Descrição *"
                  placeholder={"Descreva o problema com detalhes:\n• O que aconteceu exatamente?\n• Quando começou?\n• Aparece alguma mensagem de erro?\n• O que você já tentou fazer?"}
                  rows={7}
                  error={errors.description?.message}
                  {...register("description")}
                />
                <p className="text-xs text-conteudo-muted">Quanto mais detalhes, mais rápido conseguimos resolver.</p>
              </div>

              {!isEdit && (
                <div className="space-y-1">
                  <Textarea
                    label="Observações adicionais"
                    placeholder="Horários disponíveis, tentativas de solução, impacto no trabalho…"
                    rows={3}
                    error={errors.client_observation?.message}
                    {...register("client_observation")}
                  />
                  <p className="text-xs text-conteudo-muted">Campo opcional — editável após abrir o chamado.</p>
                </div>
              )}
            </FormSection>

            {/* Anexos */}
            <FormSection title="Anexos (opcional)">
              <FileUpload
                files={files}
                onChange={setFiles}
                accept={ALLOWED_EXTENSIONS}
                maxFiles={MAX_FILES}
                maxSizeMb={MAX_FILE_SIZE_MB}
              />
              <p className="text-xs text-conteudo-muted">
                Prints, fotos ou documentos ajudam o técnico a resolver mais rapidamente.
              </p>
            </FormSection>

            {/* Actions */}
            <div className="flex justify-end gap-3 pt-1">
              <Button type="button" variant="secondary" onClick={() => navigate(-1)}>Cancelar</Button>
              <Button type="submit">Revisar e enviar</Button>
            </div>
          </form>

          {/* ── Sidebar ─────────────────────────────────────── */}
          <SidebarSummary
            values={currentValues}
            files={files}
            productName={selectedProduct?.name}
          />
        </div>
      )}
    </div>
  );
}
