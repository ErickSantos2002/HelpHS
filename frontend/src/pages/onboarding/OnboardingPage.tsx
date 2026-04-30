import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";
import { Alert, Button, Input, Spinner } from "../../components/ui";
import { completeOnboarding } from "../../services/userService";
import {
  createMyEquipment,
  getMyEquipment,
  lookupCnpj,
  type Equipment,
} from "../../services/equipmentService";
import { api } from "../../services/api";

// ── Types ──────────────────────────────────────────────────────

interface Product {
  id: string;
  name: string;
  version: string | null;
}

// ── Step indicator ─────────────────────────────────────────────

function StepIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center gap-2 justify-center mb-8">
      {Array.from({ length: total }).map((_, i) => (
        <div key={i} className="flex items-center gap-2">
          <div
            className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold transition-colors ${
              i < current
                ? "bg-primary text-white"
                : i === current
                  ? "bg-primary/20 border-2 border-primary text-primary"
                  : "bg-background-elevated border border-border text-slate-500"
            }`}
          >
            {i < current ? "✓" : i + 1}
          </div>
          {i < total - 1 && (
            <div
              className={`w-12 h-0.5 ${i < current ? "bg-primary" : "bg-border"}`}
            />
          )}
        </div>
      ))}
    </div>
  );
}

// ── Step 1: Company info ───────────────────────────────────────

function StepCompany({
  onNext,
}: {
  onNext: (data: {
    company_name: string;
    cnpj: string;
    company_city: string;
    company_state: string;
  }) => void;
}) {
  const [cnpj, setCnpj] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [city, setCity] = useState("");
  const [state, setState] = useState("");
  const [looking, setLooking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function formatCnpj(value: string) {
    const digits = value.replace(/\D/g, "").slice(0, 14);
    return digits
      .replace(/^(\d{2})(\d)/, "$1.$2")
      .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/\.(\d{3})(\d)/, ".$1/$2")
      .replace(/(\d{4})(\d)/, "$1-$2");
  }

  async function handleCnpjBlur() {
    const digits = cnpj.replace(/\D/g, "");
    if (digits.length !== 14) return;
    setLooking(true);
    setError(null);
    try {
      const info = await lookupCnpj(digits);
      setCompanyName(info.trade_name || info.company_name);
      setCity(info.city);
      setState(info.state);
    } catch {
      setError("CNPJ não encontrado. Preencha os dados manualmente.");
    } finally {
      setLooking(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!companyName.trim()) {
      setError("Nome da empresa é obrigatório.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await completeOnboarding({
        company_name: companyName.trim(),
        cnpj: cnpj.replace(/\D/g, "") || null,
        company_city: city.trim() || null,
        company_state: state.trim().toUpperCase().slice(0, 2) || null,
      });
      onNext({
        company_name: companyName,
        cnpj,
        company_city: city,
        company_state: state,
      });
    } catch {
      setError("Erro ao salvar. Tente novamente.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-slate-100">
          Sobre sua empresa
        </h2>
        <p className="text-sm text-slate-500 mt-1">
          Digite o CNPJ para preenchermos automaticamente, ou preencha
          manualmente.
        </p>
      </div>

      {error && (
        <Alert variant="warning" onDismiss={() => setError(null)}>
          {error}
        </Alert>
      )}

      <div className="space-y-1.5">
        <label className="text-xs text-slate-400">CNPJ</label>
        <div className="relative">
          <input
            value={cnpj}
            onChange={(e) => setCnpj(formatCnpj(e.target.value))}
            onBlur={handleCnpjBlur}
            placeholder="00.000.000/0000-00"
            className="w-full rounded-lg border border-border bg-background-elevated px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors"
          />
          {looking && (
            <div className="absolute right-3 top-2.5">
              <Spinner size="sm" />
            </div>
          )}
        </div>
      </div>

      <Input
        label="Nome da empresa"
        value={companyName}
        onChange={(e) => setCompanyName(e.target.value)}
        placeholder="Razão social ou nome fantasia"
        required
      />

      <div className="grid grid-cols-2 gap-3">
        <Input
          label="Cidade"
          value={city}
          onChange={(e) => setCity(e.target.value)}
          placeholder="Ex: Recife"
        />
        <div className="space-y-1.5">
          <label className="text-xs text-slate-400">Estado (UF)</label>
          <input
            value={state}
            onChange={(e) => setState(e.target.value.toUpperCase().slice(0, 2))}
            placeholder="PE"
            maxLength={2}
            className="w-full rounded-lg border border-border bg-background-elevated px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors"
          />
        </div>
      </div>

      <Button
        type="submit"
        variant="primary"
        size="lg"
        loading={saving}
        className="w-full"
      >
        Continuar
      </Button>
    </form>
  );
}

// ── Step 2: Equipment ──────────────────────────────────────────

function StepEquipment({ onNext }: { onNext: () => void }) {
  const [products, setProducts] = useState<Product[]>([]);
  const [myEquipments, setMyEquipments] = useState<Equipment[]>([]);
  const [loadingProducts, setLoadingProducts] = useState(true);

  const [productId, setProductId] = useState("");
  const [name, setName] = useState("");
  const [serial, setSerial] = useState("");
  const [location, setLocation] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.get<{ items: Product[] }>("/products").then((r) => r.data.items),
      getMyEquipment(),
    ])
      .then(([prods, equips]) => {
        setProducts(prods.filter((p) => p.is_active !== false));
        setMyEquipments(equips);
        if (prods.length > 0) setProductId(prods[0].id);
      })
      .catch(() => {})
      .finally(() => setLoadingProducts(false));
  }, []);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!productId) {
      setError("Selecione um produto.");
      return;
    }
    if (!name.trim()) {
      setError("Nome do equipamento é obrigatório.");
      return;
    }
    setAdding(true);
    setError(null);
    try {
      const eq = await createMyEquipment(productId, {
        name: name.trim(),
        serial_number: serial.trim() || null,
        location: location.trim() || null,
      });
      setMyEquipments((prev) => [...prev, eq]);
      setName("");
      setSerial("");
      setLocation("");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setError(detail ?? "Erro ao adicionar equipamento.");
    } finally {
      setAdding(false);
    }
  }

  if (loadingProducts) {
    return (
      <div className="flex justify-center py-10">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-slate-100">
          Seus equipamentos
        </h2>
        <p className="text-sm text-slate-500 mt-1">
          Cadastre os equipamentos que você é responsável. Você pode adicionar
          mais depois.
        </p>
      </div>

      {products.length === 0 ? (
        <div className="rounded-lg border border-border bg-background-elevated p-4 text-sm text-slate-400 text-center">
          Nenhum produto cadastrado ainda. Você poderá adicionar equipamentos
          depois.
        </div>
      ) : (
        <form onSubmit={handleAdd} className="space-y-4">
          {error && (
            <Alert variant="danger" onDismiss={() => setError(null)}>
              {error}
            </Alert>
          )}

          <div className="space-y-1.5">
            <label className="text-xs text-slate-400">Produto</label>
            <select
              value={productId}
              onChange={(e) => setProductId(e.target.value)}
              className="w-full rounded-lg border border-border bg-background-elevated px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors"
            >
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                  {p.version ? ` (${p.version})` : ""}
                </option>
              ))}
            </select>
          </div>

          <Input
            label="Nome do equipamento"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Ex: Phoebus-Pernambuco"
            required
          />

          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Número de série"
              value={serial}
              onChange={(e) => setSerial(e.target.value)}
              placeholder="Ex: WATFR01-12453"
            />
            <Input
              label="Localização"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="Ex: Sala 201, Recife"
            />
          </div>

          <Button
            type="submit"
            variant="secondary"
            loading={adding}
            className="w-full"
          >
            + Adicionar equipamento
          </Button>
        </form>
      )}

      {myEquipments.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">
            Adicionados ({myEquipments.length})
          </p>
          {myEquipments.map((eq) => (
            <div
              key={eq.id}
              className="flex items-center gap-3 rounded-lg border border-border bg-background-elevated px-4 py-3"
            >
              <div className="w-2 h-2 rounded-full bg-primary shrink-0" />
              <div className="min-w-0">
                <p className="text-sm text-slate-200 font-medium truncate">
                  {eq.name}
                </p>
                <p className="text-xs text-slate-500">
                  {[eq.serial_number, eq.location].filter(Boolean).join(" · ")}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      <Button variant="primary" size="lg" className="w-full" onClick={onNext}>
        {myEquipments.length > 0 ? "Continuar" : "Pular por agora"}
      </Button>
    </div>
  );
}

// ── Step 3: Done ───────────────────────────────────────────────

function StepDone() {
  const navigate = useNavigate();
  const { markOnboardingComplete } = useAuth();

  function handleNewTicket() {
    markOnboardingComplete();
    navigate("/tickets/new");
  }

  function handleHome() {
    markOnboardingComplete();
    navigate("/");
  }

  return (
    <div className="text-center space-y-6">
      <div className="w-16 h-16 rounded-full bg-primary/20 border-2 border-primary/40 flex items-center justify-center mx-auto text-3xl">
        ✓
      </div>
      <div>
        <h2 className="text-lg font-semibold text-slate-100">Tudo pronto!</h2>
        <p className="text-sm text-slate-500 mt-2 max-w-xs mx-auto">
          Seu perfil está configurado. Agora você pode abrir chamados sempre que
          precisar de suporte.
        </p>
      </div>
      <div className="space-y-3">
        <Button
          variant="primary"
          size="lg"
          className="w-full"
          onClick={handleNewTicket}
        >
          Abrir primeiro chamado
        </Button>
        <Button variant="ghost" className="w-full" onClick={handleHome}>
          Ir para o início
        </Button>
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────

const STEPS = ["Empresa", "Equipamentos", "Pronto"];

export default function OnboardingPage() {
  const [step, setStep] = useState(0);
  const { logout } = useAuth();

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4 py-8">
      <div className="w-full max-w-md space-y-6">
        {/* Header */}
        <div className="text-center space-y-1">
          <div className="flex items-center justify-center gap-2.5 mb-4">
            <span className="w-3 h-3 rounded-full bg-primary" />
            <span className="text-2xl font-bold text-slate-100 tracking-tight">
              Help<span className="text-primary">HS</span>
            </span>
          </div>
          <p className="text-slate-400 text-sm">
            Vamos configurar seu perfil — leva menos de 2 minutos
          </p>
        </div>

        <StepIndicator current={step} total={STEPS.length} />

        {/* Card */}
        <div className="rounded-xl border border-border bg-background-surface p-6 shadow-xl">
          {step === 0 && <StepCompany onNext={() => setStep(1)} />}
          {step === 1 && <StepEquipment onNext={() => setStep(2)} />}
          {step === 2 && <StepDone />}
        </div>

        <p className="text-center text-xs text-slate-600">
          Passo {step + 1} de {STEPS.length} — {STEPS[step]}
        </p>

        <p className="text-center text-xs text-slate-600">
          Quer sair?{" "}
          <button
            onClick={() => logout()}
            className="text-slate-500 hover:text-slate-300 transition-colors underline underline-offset-2"
          >
            Deslogar
          </button>
        </p>
      </div>
    </div>
  );
}
