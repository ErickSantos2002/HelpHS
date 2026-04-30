import { zodResolver } from "@hookform/resolvers/zod";
import { useCallback, useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useParams } from "react-router-dom";
import { z } from "zod";
import {
  Alert,
  Button,
  Card,
  Input,
  Select,
  Spinner,
  Textarea,
} from "../../components/ui";
import {
  getEquipments,
  getProducts,
  type Equipment,
  type Product,
} from "../../services/productService";
import {
  createTicket,
  getTicket,
  updateTicket,
  type Ticket,
} from "../../services/ticketService";

// ── Validation schema ─────────────────────────────────────────

const schema = z.object({
  title: z
    .string()
    .min(5, "Título deve ter ao menos 5 caracteres")
    .max(200, "Título muito longo"),
  description: z
    .string()
    .min(10, "Descrição deve ter ao menos 10 caracteres")
    .max(5000, "Descrição muito longa"),
  priority: z.enum(["critical", "high", "medium", "low"]).default("medium"),
  category: z.string().min(1, "Selecione uma categoria"),
  product_id: z.string().optional(),
  equipment_id: z.string().optional(),
  client_observation: z.string().max(2000, "Observação muito longa").optional(),
});

type FormValues = z.infer<typeof schema>;

// ── Options ───────────────────────────────────────────────────

const PRIORITY_OPTIONS = [
  { value: "critical", label: "Crítico" },
  { value: "high", label: "Alto" },
  { value: "medium", label: "Médio" },
  { value: "low", label: "Baixo" },
];

const CATEGORY_OPTIONS = [
  { value: "hardware", label: "Hardware" },
  { value: "software", label: "Software" },
  { value: "network", label: "Rede" },
  { value: "access", label: "Acesso" },
  { value: "email", label: "E-mail" },
  { value: "security", label: "Segurança" },
  { value: "general", label: "Geral" },
  { value: "other", label: "Outro" },
];

const PRIORITY_LABEL: Record<string, string> = {
  critical: "Crítico",
  high: "Alto",
  medium: "Médio",
  low: "Baixo",
};

const CATEGORY_LABEL: Record<string, string> = {
  hardware: "Hardware",
  software: "Software",
  network: "Rede",
  access: "Acesso",
  email: "E-mail",
  security: "Segurança",
  general: "Geral",
  other: "Outro",
};

const ALLOWED_EXTENSIONS = [
  ".pdf",
  ".doc",
  ".docx",
  ".xls",
  ".xlsx",
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".txt",
  ".csv",
  ".zip",
  ".rar",
];
const MAX_FILE_SIZE_MB = 25;
const MAX_FILES = 10;

// ── File drop zone ────────────────────────────────────────────

interface DropZoneProps {
  files: File[];
  onChange: (files: File[]) => void;
}

function DropZone({ files, onChange }: DropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);

  const validateAndAdd = useCallback(
    (incoming: File[]) => {
      setFileError(null);
      const valid: File[] = [];
      for (const f of incoming) {
        const ext = "." + f.name.split(".").pop()?.toLowerCase();
        if (!ALLOWED_EXTENSIONS.includes(ext)) {
          setFileError(`Tipo não permitido: ${f.name}`);
          continue;
        }
        if (f.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
          setFileError(
            `Arquivo muito grande (máx ${MAX_FILE_SIZE_MB} MB): ${f.name}`,
          );
          continue;
        }
        if (!files.find((x) => x.name === f.name && x.size === f.size)) {
          valid.push(f);
        }
      }
      const next = [...files, ...valid].slice(0, MAX_FILES);
      onChange(next);
    },
    [files, onChange],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      validateAndAdd(Array.from(e.dataTransfer.files));
    },
    [validateAndAdd],
  );

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium text-slate-300">
        Anexos{" "}
        <span className="text-slate-500 font-normal">
          (opcional — máx {MAX_FILES} arquivos, {MAX_FILE_SIZE_MB} MB cada)
        </span>
      </label>

      {/* Drop area */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`rounded-lg border-2 border-dashed px-6 py-8 text-center cursor-pointer transition-colors ${
          dragOver
            ? "border-primary bg-primary/5"
            : "border-border hover:border-slate-500"
        }`}
      >
        <p className="text-sm text-slate-400">
          Arraste arquivos aqui ou{" "}
          <span className="text-primary font-medium">
            clique para selecionar
          </span>
        </p>
        <p className="text-xs text-slate-600 mt-1">
          {ALLOWED_EXTENSIONS.join(", ")}
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ALLOWED_EXTENSIONS.join(",")}
          className="hidden"
          onChange={(e) => {
            if (e.target.files) validateAndAdd(Array.from(e.target.files));
            e.target.value = "";
          }}
        />
      </div>

      {/* Error */}
      {fileError && <p className="text-xs text-danger">{fileError}</p>}

      {/* File list */}
      {files.length > 0 && (
        <ul className="space-y-1">
          {files.map((f, i) => (
            <li
              key={i}
              className="flex items-center justify-between rounded-md bg-background-elevated px-3 py-2 text-sm"
            >
              <span className="text-slate-300 truncate max-w-xs">{f.name}</span>
              <span className="flex items-center gap-3 shrink-0">
                <span className="text-slate-500 text-xs">
                  {(f.size / 1024 / 1024).toFixed(1)} MB
                </span>
                <button
                  type="button"
                  onClick={() => onChange(files.filter((_, j) => j !== i))}
                  className="text-slate-500 hover:text-danger transition-colors"
                  aria-label="Remover arquivo"
                >
                  ✕
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Preview step ──────────────────────────────────────────────

interface PreviewProps {
  values: FormValues;
  files: File[];
  productName?: string;
  equipmentName?: string;
  onBack: () => void;
  onSubmit: () => void;
  submitting: boolean;
  isEdit: boolean;
}

function PreviewStep({
  values,
  files,
  productName,
  equipmentName,
  onBack,
  onSubmit,
  submitting,
  isEdit,
}: PreviewProps) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-slate-100">
          Confirme os dados do chamado
        </h2>
        <p className="text-sm text-slate-400 mt-0.5">Revise antes de enviar.</p>
      </div>

      <Card className="space-y-4">
        <Field label="Título" value={values.title} />
        <Field label="Categoria" value={CATEGORY_LABEL[values.category]} />
        {productName && <Field label="Produto" value={productName} />}
        {equipmentName && <Field label="Equipamento" value={equipmentName} />}
        <div>
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1">
            Descrição
          </p>
          <p className="text-sm text-slate-200 whitespace-pre-wrap">
            {values.description}
          </p>
        </div>
        {!isEdit && values.client_observation && (
          <div>
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1">
              Observações adicionais
            </p>
            <p className="text-sm text-slate-200 whitespace-pre-wrap">
              {values.client_observation}
            </p>
          </div>
        )}
        {files.length > 0 && (
          <div>
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1">
              Anexos ({files.length})
            </p>
            <ul className="space-y-0.5">
              {files.map((f, i) => (
                <li key={i} className="text-sm text-slate-300">
                  {f.name}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      <div className="flex justify-end gap-3">
        <Button variant="secondary" onClick={onBack} disabled={submitting}>
          Voltar e editar
        </Button>
        <Button onClick={onSubmit} loading={submitting}>
          Confirmar e enviar
        </Button>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-0.5">
        {label}
      </p>
      <p className="text-sm text-slate-200">{value}</p>
    </div>
  );
}

// ── TicketFormPage ────────────────────────────────────────────

export default function TicketFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isEdit = Boolean(id);

  const [step, setStep] = useState<"form" | "preview">("form");
  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Products / equipments cascade
  const [products, setProducts] = useState<Product[]>([]);
  const [equipments, setEquipments] = useState<Equipment[]>([]);
  const [loadingProducts, setLoadingProducts] = useState(true);

  // Existing ticket (edit mode)
  const [loadingTicket, setLoadingTicket] = useState(isEdit);
  const [existingTicket, setExistingTicket] = useState<Ticket | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      priority: "medium",
      category: "",
      product_id: "",
      equipment_id: "",
    },
  });

  const selectedProductId = watch("product_id");

  // Load products on mount
  useEffect(() => {
    getProducts()
      .then((res) => setProducts(res.items))
      .finally(() => setLoadingProducts(false));
  }, []);

  // Load equipments when product changes
  useEffect(() => {
    setValue("equipment_id", "");
    setEquipments([]);
    if (selectedProductId) {
      getEquipments(selectedProductId).then((res) => setEquipments(res.items));
    }
  }, [selectedProductId, setValue]);

  // Load existing ticket in edit mode
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
          equipment_id: t.equipment_id ?? "",
        });
      })
      .catch(() => navigate("/tickets"))
      .finally(() => setLoadingTicket(false));
  }, [id, isEdit, navigate, reset]);

  const productOptions = products.map((p) => ({ value: p.id, label: p.name }));
  const equipmentOptions = equipments.map((e) => ({
    value: e.id,
    label: e.serial_number ? `${e.name} — ${e.serial_number}` : e.name,
  }));

  const currentValues = watch();

  const selectedProduct = products.find(
    (p) => p.id === currentValues.product_id,
  );
  const selectedEquipment = equipments.find(
    (e) => e.id === currentValues.equipment_id,
  );

  async function submitForm() {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const basePayload = {
        title: currentValues.title,
        description: currentValues.description,
        priority: currentValues.priority,
        category: currentValues.category,
        product_id: currentValues.product_id || null,
        equipment_id: currentValues.equipment_id || null,
      };

      let ticket: Ticket;
      if (isEdit && id) {
        ticket = await updateTicket(id, basePayload);
      } else {
        ticket = await createTicket({
          ...basePayload,
          client_observation: currentValues.client_observation || null,
        });
      }

      // Note: file upload requires multipart POST to /attachments/{ticket_id}
      // That flow is handled separately in the ticket detail page.

      navigate(`/tickets/${ticket.id}`);
    } catch {
      setSubmitError("Erro ao salvar o chamado. Tente novamente.");
      setStep("form");
    } finally {
      setSubmitting(false);
    }
  }

  if (loadingTicket || loadingProducts) {
    return (
      <div className="flex h-48 items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-100">
          {isEdit ? "Editar chamado" : "Abrir chamado"}
        </h1>
        {isEdit && existingTicket && (
          <p className="text-slate-400 text-sm mt-0.5 font-mono">
            {existingTicket.protocol}
          </p>
        )}
      </div>

      {submitError && (
        <Alert variant="danger" onDismiss={() => setSubmitError(null)}>
          {submitError}
        </Alert>
      )}

      {step === "preview" ? (
        <PreviewStep
          values={currentValues}
          files={files}
          productName={selectedProduct?.name}
          equipmentName={selectedEquipment?.name}
          onBack={() => setStep("form")}
          onSubmit={submitForm}
          submitting={submitting}
          isEdit={isEdit}
        />
      ) : (
        <form
          onSubmit={handleSubmit(() => setStep("preview"))}
          className="space-y-5"
        >
          {/* Title */}
          <div className="space-y-1">
            <Input
              label="Título *"
              placeholder="Ex: Computador não liga, Impressora sem conexão, Acesso bloqueado ao sistema…"
              error={errors.title?.message}
              {...register("title")}
            />
            <p className="text-xs text-slate-500">
              Resumo curto e objetivo do problema — use entre 5 e 200
              caracteres.
            </p>
          </div>

          {/* Category */}
          <div className="space-y-1">
            <Select
              label="Categoria *"
              options={CATEGORY_OPTIONS}
              placeholder="Selecione o tipo de problema"
              error={errors.category?.message}
              {...register("category")}
            />
            <p className="text-xs text-slate-500">
              Escolha a categoria que melhor descreve a natureza do problema.
            </p>
          </div>

          {/* Product + Equipment cascade */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1">
              <Select
                label="Produto"
                options={productOptions}
                placeholder="Nenhum (opcional)"
                {...register("product_id")}
              />
              <p className="text-xs text-slate-500">
                Informe o produto afetado, se aplicável.
              </p>
            </div>
            <div className="space-y-1">
              <Select
                label="Equipamento"
                options={equipmentOptions}
                placeholder={
                  selectedProductId
                    ? "Nenhum (opcional)"
                    : "Selecione um produto primeiro"
                }
                disabled={!selectedProductId || equipmentOptions.length === 0}
                {...register("equipment_id")}
              />
              <p className="text-xs text-slate-500">
                Equipamento específico vinculado ao produto selecionado.
              </p>
            </div>
          </div>

          {/* Description */}
          <div className="space-y-1">
            <Textarea
              label="Descrição *"
              placeholder={
                "Descreva o problema com o máximo de detalhes:\n" +
                "• O que aconteceu exatamente?\n" +
                "• Quando começou e com que frequência ocorre?\n" +
                "• Aparece alguma mensagem de erro? Qual?\n" +
                "• Outros usuários estão sendo afetados?\n" +
                "• O que você já tentou fazer para resolver?"
              }
              rows={7}
              error={errors.description?.message}
              {...register("description")}
            />
            <p className="text-xs text-slate-500">
              Quanto mais detalhes, mais rápido conseguimos resolver. Mínimo de
              10 caracteres.
            </p>
          </div>

          {/* Client observation — creation only */}
          {!isEdit && (
            <div className="space-y-1">
              <Textarea
                label="Observações adicionais"
                placeholder="Alguma informação extra que pode ajudar o técnico? Ex: horários disponíveis para atendimento, tentativas anteriores de solução, impacto no trabalho…"
                rows={3}
                error={errors.client_observation?.message}
                {...register("client_observation")}
              />
              <p className="text-xs text-slate-500">
                Campo opcional — você poderá editar esta observação depois de
                abrir o chamado.
              </p>
            </div>
          )}

          {/* Attachments */}
          <div className="space-y-1">
            <DropZone files={files} onChange={setFiles} />
            <p className="text-xs text-slate-500">
              Anexe prints de tela, fotos do equipamento ou documentos
              relacionados ao problema — isso ajuda o técnico a entender e
              resolver mais rapidamente.
            </p>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2">
            <Button
              type="button"
              variant="secondary"
              onClick={() => navigate(-1)}
            >
              Cancelar
            </Button>
            <Button type="submit">Revisar e enviar</Button>
          </div>
        </form>
      )}
    </div>
  );
}
