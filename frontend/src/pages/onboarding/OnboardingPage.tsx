import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";
import { Alert, Button, Input, Spinner } from "../../components/ui";
import { completeOnboarding } from "../../services/userService";
import { isValidCep, isValidCnpj, maskCnpjInput, onlyDigits } from "../../lib/documents";
import {
  createMyEquipment,
  getMyEquipment,
  lookupCnpj,
  lookupCep,
  type Equipment,
} from "../../services/equipmentService";
import { api } from "../../services/api";

// ── Types ──────────────────────────────────────────────────────

interface Product {
  id: string;
  name: string;
  version: string | null;
  is_active: boolean;
}

// ── Step indicator ─────────────────────────────────────────────

/**
 * Os três degraus do passo a passo.
 *
 * As três bolas concentravam os três pares que a catraca cobrava desta tela:
 * o passo CUMPRIDO era `bg-primary` + `text-white` (3,83:1 — o par errado do
 * degrau de ação), e o passo FUTURO era `text-slate-500` sobre
 * `bg-surface-elevated` (4,34:1 no claro, 2,85:1 no escuro).
 */
function StepIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center gap-2 justify-center mb-8">
      {Array.from({ length: total }).map((_, i) => (
        <div key={i} className="flex items-center gap-2">
          <div
            className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold transition-colors ${
              i < current
                ? "bg-action text-on-primary"
                : i === current
                  ? "bg-action-tint border-2 border-action text-on-tint-primary"
                  : "bg-surface-elevated border border-borda text-conteudo-muted"
            }`}
          >
            {i < current ? "✓" : i + 1}
          </div>
          {i < total - 1 && (
            <div
              className={`w-12 h-0.5 ${i < current ? "bg-action" : "bg-borda"}`}
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
    company_cep: string;
    company_address: string;
    company_city: string;
    company_state: string;
  }) => void;
}) {
  const [cnpj, setCnpj] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [cep, setCep] = useState("");
  const [address, setAddress] = useState("");
  const [city, setCity] = useState("");
  const [state, setState] = useState("");
  const [lookingCnpj, setLookingCnpj] = useState(false);
  const [lookingCep, setLookingCep] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function formatCep(value: string) {
    const digits = value.replace(/\D/g, "").slice(0, 8);
    return digits.replace(/^(\d{5})(\d)/, "$1-$2");
  }

  async function handleCnpjBlur() {
    const digits = cnpj.replace(/\D/g, "");
    if (digits.length !== 14) return;
    setLookingCnpj(true);
    setError(null);
    try {
      const info = await lookupCnpj(digits);
      setCompanyName(info.trade_name || info.company_name);
      setCity(info.city);
      setState(info.state);
    } catch {
      setError("CNPJ não encontrado. Preencha os dados manualmente.");
    } finally {
      setLookingCnpj(false);
    }
  }

  async function handleCepBlur() {
    const digits = cep.replace(/\D/g, "");
    if (digits.length !== 8) return;
    setLookingCep(true);
    setError(null);
    try {
      const info = await lookupCep(digits);
      if (info.address) setAddress(info.address);
      if (info.city) setCity(info.city);
      if (info.state) setState(info.state);
    } catch {
      setError("CEP não encontrado. Preencha os dados manualmente.");
    } finally {
      setLookingCep(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!companyName.trim()) {
      setError("Nome da empresa é obrigatório.");
      return;
    }
    if (!cnpj.trim()) {
      setError("Informe o CNPJ da empresa.");
      return;
    }
    if (!isValidCnpj(cnpj)) {
      setError("CNPJ inválido. Confira os números digitados.");
      return;
    }
    if (!cep.trim()) {
      setError("Informe o CEP da empresa.");
      return;
    }
    if (!isValidCep(cep)) {
      setError("CEP inválido. Deve ter 8 dígitos.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await completeOnboarding({
        company_name: companyName.trim(),
        cnpj: onlyDigits(cnpj),
        company_cep: onlyDigits(cep),
        company_address: address.trim() || null,
        company_city: city.trim() || null,
        company_state: state.trim().toUpperCase().slice(0, 2) || null,
      });
      onNext({
        company_name: companyName,
        cnpj,
        company_cep: cep,
        company_address: address,
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
        <h2 className="text-lg font-semibold text-conteudo-heading">
          Sobre sua empresa
        </h2>
        <p className="text-sm text-conteudo-muted mt-1">
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
        {/* O asterisco de obrigatório era `text-danger-400` — um vermelho
            claro pintado como cor de TEXTO, que é a reprovação da §3.2. Ele
            passa a viver no texto do rótulo, como no `ProfilePage` e no
            `ProductsPage`: quem lê com leitor de tela ouve o asterisco junto
            do nome do campo, em vez de um `<span>` colorido sem ligação
            nenhuma com o campo. */}
        <label className="text-xs text-conteudo-muted">CNPJ *</label>
        <div className="relative">
          <input
            value={cnpj}
            onChange={(e) => setCnpj(maskCnpjInput(e.target.value))}
            onBlur={handleCnpjBlur}
            placeholder="00.000.000/0000-00"
            className="w-full rounded-lg border border-borda-control bg-surface-elevated px-3 py-2 text-sm text-conteudo placeholder:text-conteudo-muted focus:outline-none focus:ring-2 focus:ring-action focus:border-transparent transition-colors"
          />
          {lookingCnpj && (
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

      <div className="space-y-1.5">
        <label className="text-xs text-conteudo-muted">CEP *</label>
        <div className="relative">
          <input
            value={cep}
            onChange={(e) => setCep(formatCep(e.target.value))}
            onBlur={handleCepBlur}
            placeholder="00000-000"
            className="w-full rounded-lg border border-borda-control bg-surface-elevated px-3 py-2 text-sm text-conteudo placeholder:text-conteudo-muted focus:outline-none focus:ring-2 focus:ring-action focus:border-transparent transition-colors"
          />
          {lookingCep && (
            <div className="absolute right-3 top-2.5">
              <Spinner size="sm" />
            </div>
          )}
        </div>
      </div>

      <Input
        label="Endereço"
        value={address}
        onChange={(e) => setAddress(e.target.value)}
        placeholder="Ex: Rua das Flores, 123"
      />

      <div className="grid grid-cols-2 gap-3">
        <Input
          label="Cidade"
          value={city}
          onChange={(e) => setCity(e.target.value)}
          placeholder="Ex: Recife"
        />
        <div className="space-y-1.5">
          <label className="text-xs text-conteudo-muted">Estado (UF)</label>
          <input
            value={state}
            onChange={(e) => setState(e.target.value.toUpperCase().slice(0, 2))}
            placeholder="PE"
            maxLength={2}
            className="w-full rounded-lg border border-borda-control bg-surface-elevated px-3 py-2 text-sm text-conteudo placeholder:text-conteudo-muted focus:outline-none focus:ring-2 focus:ring-action focus:border-transparent transition-colors"
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
        <h2 className="text-lg font-semibold text-conteudo-heading">
          Seus equipamentos
        </h2>
        <p className="text-sm text-conteudo-muted mt-1">
          Cadastre os equipamentos que você é responsável. Você pode adicionar
          mais depois.
        </p>
      </div>

      {products.length === 0 ? (
        <div className="rounded-lg border border-borda bg-surface-elevated p-4 text-sm text-conteudo-muted text-center">
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
            <label className="text-xs text-conteudo-muted">Produto</label>
            <select
              value={productId}
              onChange={(e) => setProductId(e.target.value)}
              className="w-full rounded-lg border border-borda-control bg-surface-elevated px-3 py-2 text-sm text-conteudo focus:outline-none focus:ring-2 focus:ring-action focus:border-transparent transition-colors"
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
          <p className="text-xs text-conteudo-muted font-medium uppercase tracking-wide">
            Adicionados ({myEquipments.length})
          </p>
          {myEquipments.map((eq) => (
            <div
              key={eq.id}
              className="flex items-center gap-3 rounded-lg border border-borda bg-surface-elevated px-4 py-3"
            >
              <div className="w-2 h-2 rounded-full bg-action shrink-0" />
              <div className="min-w-0">
                <p className="text-sm text-conteudo font-medium truncate">
                  {eq.name}
                </p>
                <p className="text-xs text-conteudo-muted">
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
      <div className="w-16 h-16 rounded-full bg-action-tint border-2 border-action-tint-border flex items-center justify-center mx-auto text-3xl text-on-tint-primary">
        ✓
      </div>
      <div>
        <h2 className="text-lg font-semibold text-conteudo-heading">Tudo pronto!</h2>
        <p className="text-sm text-conteudo-muted mt-2 max-w-xs mx-auto">
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
    <div className="min-h-screen flex items-center justify-center bg-surface-base px-4 py-8">
      <div className="w-full max-w-md space-y-6">
        {/* Header */}
        <div className="text-center space-y-1">
          <div className="flex items-center justify-center gap-2.5 mb-4">
            <span className="w-3 h-3 rounded-full bg-primary" />
            {/* `text-primary` no "HS" é a cor de MARCA, e continua sendo: a
                assinatura fica em 24px negrito, que a WCAG conta como texto
                grande (piso 3:1), e o degrau dá 3,66:1 sobre `--bg-base`.
                Trocar por `--text-link` mudaria a assinatura do produto, e
                isso não se decide dentro de uma tela. */}
            <span className="text-2xl font-bold text-conteudo-heading tracking-tight">
              Help<span className="text-primary">HS</span>
            </span>
          </div>
          <p className="text-conteudo-muted text-sm">
            Vamos configurar seu perfil — leva menos de 2 minutos
          </p>
        </div>

        <StepIndicator current={step} total={STEPS.length} />

        {/* Card */}
        <div className="rounded-xl border border-borda bg-surface p-6 shadow-xl">
          {step === 0 && <StepCompany onNext={() => setStep(1)} />}
          {step === 1 && <StepEquipment onNext={() => setStep(2)} />}
          {step === 2 && <StepDone />}
        </div>

        <p className="text-center text-xs text-conteudo-muted">
          Passo {step + 1} de {STEPS.length} — {STEPS[step]}
        </p>

        <p className="text-center text-xs text-conteudo-muted">
          Quer sair?{" "}
          <button
            onClick={() => logout()}
            className="text-conteudo-link hover:text-conteudo-link-hover transition-colors underline underline-offset-2"
          >
            Deslogar
          </button>
        </p>
      </div>
    </div>
  );
}
