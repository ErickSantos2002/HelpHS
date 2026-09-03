import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useParams } from "react-router-dom";
import { z } from "zod";
import {
  Alert,
  Button,
  FileUpload,
  FormDropdown,
  Input,
  Spinner,
  Textarea,
} from "../../components/ui";
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

const CATEGORY_LABEL: Record<string, string> = {
  hardware: "Hardware", software: "Software", network: "Rede",
  access: "Acesso", email: "E-mail", security: "Segurança",
  general: "Geral", other: "Outro",
};

const PRIORITY_CONFIG = {
  critical: { label: "Crítico",  dot: "bg-red-500",    active: "border-red-500/50 bg-red-500/10 text-red-700 dark:text-red-400"    },
  high:     { label: "Alto",     dot: "bg-amber-500",  active: "border-amber-500/50 bg-amber-500/10 text-amber-700 dark:text-amber-400" },
  medium:   { label: "Médio",    dot: "bg-info",       active: "border-info/50 bg-info/10 text-info-700 dark:text-info-400"           },
  low:      { label: "Baixo",    dot: "bg-slate-400",  active: "border-border bg-background-elevated text-slate-400"                 },
} as const;

const CATEGORY_CONFIG = [
  { value: "hardware",  label: "Hardware",  icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" /></svg> },
  { value: "software",  label: "Software",  icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg> },
  { value: "network",   label: "Rede",      icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064" /></svg> },
  { value: "access",    label: "Acesso",    icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" /></svg> },
  { value: "email",     label: "E-mail",    icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg> },
  { value: "security",  label: "Segurança", icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg> },
  { value: "general",   label: "Geral",     icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg> },
  { value: "other",     label: "Outro",     icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M5 12h.01M12 12h.01M19 12h.01M6 12a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0z" /></svg> },
];

// ── Icons ─────────────────────────────────────────────────────

const IC = {
  ArrowLeft: <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>,
  Clip: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" /></svg>,
  X: <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>,
  Check: <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>,
  Info: <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
};

// ── Step indicator ────────────────────────────────────────────

function StepIndicator({ current }: { current: 1 | 2 }) {
  return (
    <div className="flex items-center gap-2 text-sm shrink-0">
      <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${current > 1 ? "bg-emerald-600 text-white" : "bg-primary text-white"}`}>
        {current > 1 ? IC.Check : "1"}
      </span>
      <span className={`font-medium ${current === 1 ? "text-slate-200" : "text-emerald-400"}`}>Formulário</span>
      <span className="text-slate-600">/</span>
      <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${current === 2 ? "bg-primary text-white" : "bg-background-elevated text-slate-500"}`}>2</span>
      <span className={`font-medium ${current === 2 ? "text-slate-200" : "text-slate-500"}`}>Revisão</span>
    </div>
  );
}

// ── Section wrapper ───────────────────────────────────────────

function FormSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border/40 bg-background-surface">
      <div className="border-b border-border/40 px-5 py-3.5">
        <h2 className="text-sm font-semibold text-slate-200">{title}</h2>
      </div>
      <div className="p-5 space-y-4">{children}</div>
    </div>
  );
}

// ── Category grid ─────────────────────────────────────────────

function CategoryGrid({ value, onChange, error }: { value: string; onChange: (v: string) => void; error?: string }) {
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-slate-300">Categoria <span className="text-danger">*</span></p>
      <div className="grid grid-cols-4 sm:grid-cols-8 gap-2">
        {CATEGORY_CONFIG.map((cat) => {
          const selected = value === cat.value;
          return (
            <button
              key={cat.value}
              type="button"
              onClick={() => onChange(cat.value)}
              className={`flex flex-col items-center gap-1.5 rounded-lg border px-2 py-3 text-center transition-all cursor-pointer ${
                selected
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border/50 bg-background-elevated/40 text-slate-400 hover:border-border hover:text-slate-300 hover:bg-background-elevated"
              }`}
            >
              {cat.icon}
              <span className="text-[11px] font-semibold leading-tight">{cat.label}</span>
            </button>
          );
        })}
      </div>
      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  );
}

// ── Priority selector ─────────────────────────────────────────

function PrioritySelector({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-slate-300">Prioridade</p>
      <div className="flex gap-2">
        {(["critical", "high", "medium", "low"] as const).map((p) => {
          const cfg = PRIORITY_CONFIG[p];
          const selected = value === p;
          return (
            <button
              key={p}
              type="button"
              onClick={() => onChange(p)}
              className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-semibold transition-all cursor-pointer ${
                selected ? cfg.active : "border-border/40 bg-background-elevated/40 text-slate-500 hover:border-border hover:text-slate-400"
              }`}
            >
              <span className={`w-2 h-2 rounded-full shrink-0 ${selected ? cfg.dot : "bg-slate-600"}`} />
              {cfg.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── Sidebar summary ───────────────────────────────────────────

function SidebarSummary({ values, files, productName }: { values: Partial<FormValues>; files: File[]; productName?: string }) {
  const pri = values.priority ? PRIORITY_CONFIG[values.priority] : null;
  const cat = values.category ? CATEGORY_LABEL[values.category] : null;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-border/40 bg-background-surface p-4">
        <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-slate-500">Resumo</p>
        <div className="space-y-3">
          <SummaryRow label="Título" empty="Não preenchido">
            {values.title && values.title.length >= 5 ? (
              <span className="text-sm text-slate-200 line-clamp-2">{values.title}</span>
            ) : null}
          </SummaryRow>
          <SummaryRow label="Categoria" empty="Não selecionada">
            {cat ? <span className="text-sm text-slate-200">{cat}</span> : null}
          </SummaryRow>
          <SummaryRow label="Prioridade" empty="Não definida">
            {pri ? (
              <span className={`inline-flex items-center gap-1.5 text-xs font-semibold ${pri.active.split(" ").filter(c => c.startsWith("text-")).join(" ")}`}>
                <span className={`w-2 h-2 rounded-full ${pri.dot}`} />
                {pri.label}
              </span>
            ) : null}
          </SummaryRow>
          {productName && (
            <SummaryRow label="Produto" empty="">
              <span className="text-sm text-slate-200">{productName}</span>
            </SummaryRow>
          )}
          {files.length > 0 && (
            <SummaryRow label="Anexos" empty="">
              <span className="text-sm text-slate-200">{files.length} arquivo{files.length > 1 ? "s" : ""}</span>
            </SummaryRow>
          )}
        </div>
      </div>

      <div className="rounded-xl border border-border/40 bg-background-surface p-4">
        <p className="mb-3 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-slate-500">
          {IC.Info}
          Dicas
        </p>
        <ul className="space-y-2.5 text-xs text-slate-500">
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
      <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">{label}</p>
      {children ?? <span className="text-xs italic text-slate-600">{empty}</span>}
    </div>
  );
}

// ── Preview row ───────────────────────────────────────────────

function PreviewRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-4 py-3 border-b border-border/30 last:border-0">
      <p className="w-28 shrink-0 text-[11px] font-semibold uppercase tracking-widest text-slate-500 pt-0.5">{label}</p>
      <div className="flex-1 text-sm text-slate-200">{children}</div>
    </div>
  );
}

// ── Preview step ──────────────────────────────────────────────

function PreviewStep({ values, files, productName, equipmentNames, onBack, onSubmit, submitting, isEdit }: {
  values: FormValues; files: File[]; productName?: string; equipmentNames: string[];
  onBack: () => void; onSubmit: () => void; submitting: boolean; isEdit: boolean;
}) {
  const pri = PRIORITY_CONFIG[values.priority];
  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_300px]">
      <div className="space-y-5">
        <div className="rounded-xl border border-border/40 bg-background-surface">
          <div className="border-b border-border/40 px-5 py-3.5">
            <h2 className="text-sm font-semibold text-slate-200">Confirme os dados antes de enviar</h2>
          </div>
          <div className="px-5 py-2">
            <PreviewRow label="Título">{values.title}</PreviewRow>
            <PreviewRow label="Categoria">{CATEGORY_LABEL[values.category] ?? values.category}</PreviewRow>
            <PreviewRow label="Prioridade">
              <span className={`inline-flex items-center gap-1.5 text-xs font-semibold ${pri.active.split(" ").filter(c => c.startsWith("text-")).join(" ")}`}>
                <span className={`w-2 h-2 rounded-full ${pri.dot}`} />
                {pri.label}
              </span>
            </PreviewRow>
            {productName && <PreviewRow label="Produto">{productName}</PreviewRow>}
            {equipmentNames.length > 0 && (
              <PreviewRow label={plural(equipmentNames.length, "Equipamento", "Equipamentos")}>
                <ul className="space-y-0.5">
                  {equipmentNames.map((nome) => (
                    <li key={nome} className="text-slate-300">{nome}</li>
                  ))}
                </ul>
              </PreviewRow>
            )}
            <PreviewRow label="Descrição">
              <p className="whitespace-pre-wrap leading-relaxed text-slate-300">{values.description}</p>
            </PreviewRow>
            {!isEdit && values.client_observation && (
              <PreviewRow label="Observações">
                <p className="whitespace-pre-wrap text-slate-300">{values.client_observation}</p>
              </PreviewRow>
            )}
            {files.length > 0 && (
              <PreviewRow label={`Anexos (${files.length})`}>
                <ul className="space-y-0.5">{files.map((f, i) => <li key={i} className="text-slate-400">{f.name}</li>)}</ul>
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
        <div className="rounded-xl border border-border/40 bg-background-surface p-4">
          <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-slate-500">Resumo</p>
          <div className="space-y-2.5 text-xs text-slate-500">
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
      <div className="flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-border/40 bg-background-surface px-5 py-4">
        <div className="min-w-0">
          <button
            onClick={() => navigate(-1)}
            className="mb-2 flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-primary transition-colors cursor-pointer"
          >
            {IC.ArrowLeft}
            <span>Tickets</span>
            <span className="text-slate-600">/</span>
            <span className="font-mono text-slate-500">
              {isEdit && existingTicket ? existingTicket.protocol : "Novo chamado"}
            </span>
          </button>
          <h1 className="text-xl font-extrabold leading-tight text-slate-100">
            {isEdit ? "Editar chamado" : "Abrir chamado"}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
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
                <p className="text-xs text-slate-500">Resumo curto e objetivo do problema.</p>
              </div>

              <CategoryGrid
                value={watchedCategory}
                onChange={(v) => setValue("category", v, { shouldValidate: true })}
                error={errors.category?.message}
              />

              <PrioritySelector
                value={watchedPriority}
                onChange={(v) => setValue("priority", v as FormValues["priority"])}
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

              <div className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <label className="text-sm font-medium text-slate-300">Equipamentos</label>
                  {equipments.length > 1 && (
                    <button
                      type="button"
                      onClick={toggleAllEquipments}
                      className="text-xs font-medium text-primary hover:underline cursor-pointer"
                    >
                      {todosMarcados
                        ? "Limpar seleção"
                        : `Selecionar todos (${Math.min(equipments.length, MAX_EQUIPAMENTOS)})`}
                    </button>
                  )}
                </div>
                {!selectedProductId ? (
                  <p className="text-sm text-slate-500">Selecione um produto primeiro.</p>
                ) : equipments.length === 0 ? (
                  <p className="text-sm text-slate-500">
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
                                ? "border-primary bg-primary/15 text-slate-100"
                                : "border-border text-slate-400 hover:border-slate-500",
                            )}
                          >
                            <span className="font-medium">{e.name}</span>
                            {e.serial_number && (
                              <span className="ml-2 font-mono text-xs text-slate-500">
                                {e.serial_number}
                              </span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                    <p className="text-xs text-slate-500">
                      {noLimite
                        ? `Máximo de ${MAX_EQUIPAMENTOS} aparelhos por chamado. Para os demais, abra um segundo chamado.`
                        : selectedEquipmentIds.length > 0
                          ? `${selectedEquipmentIds.length} ${plural(selectedEquipmentIds.length, "aparelho selecionado", "aparelhos selecionados")}. Um mesmo chamado pode cobrir vários.`
                          : "Se o problema atinge mais de um aparelho, marque todos — não é preciso abrir um chamado para cada."}
                    </p>
                  </>
                )}
              </div>
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
                <p className="text-xs text-slate-500">Quanto mais detalhes, mais rápido conseguimos resolver.</p>
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
                  <p className="text-xs text-slate-500">Campo opcional — editável após abrir o chamado.</p>
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
              <p className="text-xs text-slate-500">
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
