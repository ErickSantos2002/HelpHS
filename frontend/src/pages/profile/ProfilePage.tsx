import { useEffect, useState } from "react";
import { useAuth } from "../../contexts/AuthContext";
import { Spinner } from "../../components/ui";
import {
  changePassword,
  completeOnboarding,
  getMe,
  updateMe,
  type UserSummary,
} from "../../services/userService";
import {
  createMyEquipment,
  deleteMyEquipment,
  getMyEquipment,
  lookupCnpj,
  type Equipment,
} from "../../services/equipmentService";
import { api } from "../../services/api";

// ── Shared primitives ──────────────────────────────────────────

const ROLE_LABEL: Record<string, string> = {
  admin: "Administrador",
  technician: "Técnico",
  client: "Cliente",
};

const ROLE_COLOR: Record<string, string> = {
  admin: "bg-primary/20 text-primary",
  technician: "bg-info/20 text-info",
  client: "bg-slate-700 text-slate-300",
};

const INPUT_CLS =
  "w-full rounded-lg border border-border bg-background-elevated px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors";

function Avatar({ name, size = "lg" }: { name: string; size?: "sm" | "lg" }) {
  const initials = name
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
  const cls = size === "lg" ? "w-20 h-20 text-2xl" : "w-10 h-10 text-sm";
  return (
    <div
      className={`${cls} rounded-full bg-primary/20 border-2 border-primary/30 flex items-center justify-center font-semibold text-primary`}
    >
      {initials}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-slate-500 mb-0.5">{label}</p>
      <p className="text-sm text-slate-200">{value || "—"}</p>
    </div>
  );
}

function SectionCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl bg-background-surface border border-border p-6 space-y-4">
      <h2 className="text-sm font-semibold text-slate-300">{title}</h2>
      {children}
    </div>
  );
}

function ErrorMsg({ msg }: { msg: string }) {
  return (
    <p className="text-sm text-danger bg-danger/10 border border-danger/20 rounded-lg px-3 py-2">
      {msg}
    </p>
  );
}

function FormActions({
  saving,
  saveLabel,
  onCancel,
}: {
  saving: boolean;
  saveLabel?: string;
  onCancel: () => void;
}) {
  return (
    <div className="flex gap-2 justify-end">
      <button
        type="button"
        onClick={onCancel}
        className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 transition-colors"
      >
        Cancelar
      </button>
      <button
        type="submit"
        disabled={saving}
        className="px-4 py-2 rounded-lg bg-primary text-white text-sm hover:bg-primary/90 disabled:opacity-50 transition-colors"
      >
        {saving ? "Salvando…" : (saveLabel ?? "Salvar")}
      </button>
    </div>
  );
}

// ── Edit profile form ──────────────────────────────────────────

function EditProfileForm({
  profile,
  onSaved,
  onCancel,
}: {
  profile: UserSummary;
  onSaved: (updated: UserSummary) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(profile.name);
  const [phone, setPhone] = useState(profile.phone ?? "");
  const [department, setDepartment] = useState(profile.department ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError("Nome é obrigatório");
      return;
    }
    setSaving(true);
    setError("");
    try {
      onSaved(
        await updateMe({
          name: name.trim(),
          phone: phone.trim() || null,
          department: department.trim() || null,
        }),
      );
    } catch {
      setError("Erro ao salvar. Tente novamente.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && <ErrorMsg msg={error} />}
      <div className="space-y-1.5">
        <label className="text-xs text-slate-400">Nome completo</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          className={INPUT_CLS}
        />
      </div>
      <div className="space-y-1.5">
        <label className="text-xs text-slate-400">Telefone</label>
        <input
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="(11) 99999-9999"
          className={INPUT_CLS}
        />
      </div>
      <div className="space-y-1.5">
        <label className="text-xs text-slate-400">Departamento</label>
        <input
          value={department}
          onChange={(e) => setDepartment(e.target.value)}
          placeholder="Ex: TI, RH, Operações"
          className={INPUT_CLS}
        />
      </div>
      <FormActions saving={saving} onCancel={onCancel} />
    </form>
  );
}

// ── Change password form ───────────────────────────────────────

function ChangePasswordForm({ onDone }: { onDone: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (next.length < 8) {
      setError("A nova senha deve ter no mínimo 8 caracteres");
      return;
    }
    if (!/[A-Z]/.test(next)) {
      setError("A nova senha deve conter ao menos uma letra maiúscula");
      return;
    }
    if (!/[0-9]/.test(next)) {
      setError("A nova senha deve conter ao menos um número");
      return;
    }
    if (next !== confirm) {
      setError("As senhas não coincidem");
      return;
    }
    setSaving(true);
    try {
      await changePassword(current, next);
      setSuccess(true);
      setTimeout(onDone, 1500);
    } catch (err: unknown) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Erro ao alterar senha. Tente novamente.",
      );
    } finally {
      setSaving(false);
    }
  }

  if (success)
    return (
      <p className="text-sm text-green-400 py-2">Senha alterada com sucesso!</p>
    );

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && <ErrorMsg msg={error} />}
      {(
        [
          ["Senha atual", current, setCurrent],
          ["Nova senha", next, setNext],
          ["Confirmar nova senha", confirm, setConfirm],
        ] as [string, string, (v: string) => void][]
      ).map(([label, val, setter]) => (
        <div key={label} className="space-y-1.5">
          <label className="text-xs text-slate-400">{label}</label>
          <input
            type="password"
            value={val}
            onChange={(e) => setter(e.target.value)}
            autoComplete="off"
            className={INPUT_CLS}
          />
        </div>
      ))}
      <FormActions
        saving={saving}
        saveLabel="Alterar senha"
        onCancel={onDone}
      />
    </form>
  );
}

// ── Company section ────────────────────────────────────────────

function CompanySection({
  profile,
  onSaved,
}: {
  profile: UserSummary;
  onSaved: (u: UserSummary) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [companyName, setCompanyName] = useState(profile.company_name ?? "");
  const [cnpj, setCnpj] = useState(profile.cnpj ?? "");
  const [city, setCity] = useState(profile.company_city ?? "");
  const [state, setState] = useState(profile.company_state ?? "");
  const [looking, setLooking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function formatCnpj(v: string) {
    const d = v.replace(/\D/g, "").slice(0, 14);
    return d
      .replace(/^(\d{2})(\d)/, "$1.$2")
      .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/\.(\d{3})(\d)/, ".$1/$2")
      .replace(/(\d{4})(\d)/, "$1-$2");
  }

  async function handleCnpjBlur() {
    const digits = cnpj.replace(/\D/g, "");
    if (digits.length !== 14) return;
    setLooking(true);
    try {
      const info = await lookupCnpj(digits);
      setCompanyName(info.trade_name || info.company_name);
      setCity(info.city);
      setState(info.state);
    } catch {
      /* manual fill */
    } finally {
      setLooking(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!companyName.trim()) {
      setError("Nome da empresa é obrigatório");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const updated = await completeOnboarding({
        company_name: companyName.trim(),
        cnpj: cnpj.replace(/\D/g, "") || null,
        company_city: city.trim() || null,
        company_state: state.trim().toUpperCase().slice(0, 2) || null,
      });
      onSaved(updated);
      setEditing(false);
    } catch {
      setError("Erro ao salvar. Tente novamente.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <SectionCard title="Empresa">
      {editing ? (
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && <ErrorMsg msg={error} />}
          <div className="space-y-1.5">
            <label className="text-xs text-slate-400">CNPJ</label>
            <div className="relative">
              <input
                value={cnpj}
                onChange={(e) => setCnpj(formatCnpj(e.target.value))}
                onBlur={handleCnpjBlur}
                placeholder="00.000.000/0000-00"
                className={INPUT_CLS}
              />
              {looking && (
                <div className="absolute right-3 top-2.5">
                  <Spinner size="sm" />
                </div>
              )}
            </div>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs text-slate-400">Nome da empresa</label>
            <input
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder="Razão social ou nome fantasia"
              className={INPUT_CLS}
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label className="text-xs text-slate-400">Cidade</label>
              <input
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="Ex: Recife"
                className={INPUT_CLS}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs text-slate-400">Estado (UF)</label>
              <input
                value={state}
                onChange={(e) =>
                  setState(e.target.value.toUpperCase().slice(0, 2))
                }
                placeholder="PE"
                maxLength={2}
                className={INPUT_CLS}
              />
            </div>
          </div>
          <FormActions saving={saving} onCancel={() => setEditing(false)} />
        </form>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Nome da empresa" value={profile.company_name ?? ""} />
            <Field
              label="CNPJ"
              value={
                profile.cnpj
                  ? profile.cnpj.replace(
                      /^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/,
                      "$1.$2.$3/$4-$5",
                    )
                  : ""
              }
            />
            <Field label="Cidade" value={profile.company_city ?? ""} />
            <Field label="Estado" value={profile.company_state ?? ""} />
          </div>
          <div className="flex justify-end">
            <button
              onClick={() => setEditing(true)}
              className="text-sm text-primary hover:text-primary/80 transition-colors"
            >
              Editar empresa
            </button>
          </div>
        </>
      )}
    </SectionCard>
  );
}

// ── Equipment section ──────────────────────────────────────────

interface Product {
  id: string;
  name: string;
  version: string | null;
  is_active: boolean;
}

function EquipmentSection() {
  const [equipments, setEquipments] = useState<Equipment[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [showForm, setShowForm] = useState(false);

  const [productId, setProductId] = useState("");
  const [name, setName] = useState("");
  const [serial, setSerial] = useState("");
  const [location, setLocation] = useState("");
  const [formError, setFormError] = useState("");

  useEffect(() => {
    Promise.all([
      api.get<{ items: Product[] }>("/products").then((r) => r.data.items),
      getMyEquipment(),
    ])
      .then(([prods, equips]) => {
        const active = prods.filter((p) => p.is_active);
        setProducts(active);
        setEquipments(equips);
        if (active.length > 0) setProductId(active[0].id);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!productId) {
      setFormError("Selecione um produto.");
      return;
    }
    if (!name.trim()) {
      setFormError("Nome do equipamento é obrigatório.");
      return;
    }
    setAdding(true);
    setFormError("");
    try {
      const eq = await createMyEquipment(productId, {
        name: name.trim(),
        serial_number: serial.trim() || null,
        location: location.trim() || null,
      });
      setEquipments((prev) => [...prev, eq]);
      setName("");
      setSerial("");
      setLocation("");
      setShowForm(false);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setFormError(detail ?? "Erro ao adicionar equipamento.");
    } finally {
      setAdding(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Remover este equipamento?")) return;
    try {
      await deleteMyEquipment(id);
      setEquipments((prev) => prev.filter((e) => e.id !== id));
    } catch {
      /* ignore */
    }
  }

  if (loading)
    return (
      <SectionCard title="Meus equipamentos">
        <div className="flex justify-center py-4">
          <Spinner size="sm" />
        </div>
      </SectionCard>
    );

  return (
    <SectionCard title="Meus equipamentos">
      {equipments.length === 0 && !showForm && (
        <p className="text-sm text-slate-500">
          Nenhum equipamento cadastrado ainda.
        </p>
      )}

      {equipments.length > 0 && (
        <div className="space-y-2">
          {equipments.map((eq) => {
            const prod = products.find((p) => p.id === eq.product_id);
            return (
              <div
                key={eq.id}
                className="flex items-start gap-3 rounded-lg border border-border bg-background-elevated px-4 py-3"
              >
                <div className="w-2 h-2 rounded-full bg-primary mt-1.5 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-slate-200 font-medium truncate">
                    {eq.name}
                  </p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {[prod?.name, eq.serial_number, eq.location]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
                <button
                  onClick={() => handleDelete(eq.id)}
                  className="text-xs text-slate-600 hover:text-danger transition-colors shrink-0 mt-0.5"
                >
                  Remover
                </button>
              </div>
            );
          })}
        </div>
      )}

      {showForm && (
        <form
          onSubmit={handleAdd}
          className="space-y-3 pt-2 border-t border-border"
        >
          {formError && <ErrorMsg msg={formError} />}
          <div className="space-y-1.5">
            <label className="text-xs text-slate-400">Produto</label>
            <select
              value={productId}
              onChange={(e) => setProductId(e.target.value)}
              className={INPUT_CLS}
            >
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                  {p.version ? ` (${p.version})` : ""}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs text-slate-400">
              Nome do equipamento
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ex: Phoebus-Pernambuco"
              className={INPUT_CLS}
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label className="text-xs text-slate-400">Número de série</label>
              <input
                value={serial}
                onChange={(e) => setSerial(e.target.value)}
                placeholder="Ex: WATFR01-12453"
                className={INPUT_CLS}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs text-slate-400">Localização</label>
              <input
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="Ex: Sala 201, Recife"
                className={INPUT_CLS}
              />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={() => {
                setShowForm(false);
                setFormError("");
              }}
              className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 transition-colors"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={adding}
              className="px-4 py-2 rounded-lg bg-primary text-white text-sm hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {adding ? "Adicionando…" : "Adicionar"}
            </button>
          </div>
        </form>
      )}

      {!showForm && products.length > 0 && (
        <div className="flex justify-end">
          <button
            onClick={() => setShowForm(true)}
            className="text-sm text-primary hover:text-primary/80 transition-colors"
          >
            + Adicionar equipamento
          </button>
        </div>
      )}

      {!showForm && products.length === 0 && (
        <p className="text-xs text-slate-600">
          Nenhum produto disponível no sistema ainda.
        </p>
      )}
    </SectionCard>
  );
}

// ── Main page ──────────────────────────────────────────────────

export default function ProfilePage() {
  const { user: authUser } = useAuth();
  const [profile, setProfile] = useState<UserSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [editingInfo, setEditingInfo] = useState(false);
  const [editingPassword, setEditingPassword] = useState(false);

  useEffect(() => {
    getMe()
      .then(setProfile)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading)
    return (
      <div className="max-w-2xl mx-auto px-4 py-10 text-center text-slate-500 text-sm">
        Carregando…
      </div>
    );

  if (!profile)
    return (
      <div className="max-w-2xl mx-auto px-4 py-10 text-center text-slate-500 text-sm">
        Não foi possível carregar o perfil.
      </div>
    );

  const joinedAt = new Date(profile.created_at).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
  const lastLogin = profile.last_login
    ? new Date(profile.last_login).toLocaleString("pt-BR", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

  return (
    <div className="max-w-2xl mx-auto px-4 py-6 space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">Meu perfil</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Gerencie suas informações pessoais e segurança
        </p>
      </div>

      {/* Identity card */}
      <div className="rounded-xl bg-background-surface border border-border p-6 flex items-center gap-5">
        <Avatar name={profile.name} />
        <div className="space-y-1 min-w-0">
          <h2 className="text-lg font-semibold text-slate-100 truncate">
            {profile.name}
          </h2>
          <p className="text-sm text-slate-400 truncate">{profile.email}</p>
          <span
            className={`inline-block text-xs px-2 py-0.5 rounded-full font-medium ${ROLE_COLOR[profile.role] ?? ""}`}
          >
            {ROLE_LABEL[profile.role] ?? profile.role}
          </span>
        </div>
        <div className="ml-auto text-right shrink-0 hidden sm:block">
          <p className="text-xs text-slate-500">Membro desde</p>
          <p className="text-sm text-slate-300">{joinedAt}</p>
          <p className="text-xs text-slate-500 mt-2">Último acesso</p>
          <p className="text-sm text-slate-300">{lastLogin}</p>
        </div>
      </div>

      {/* Personal info */}
      <SectionCard title="Informações pessoais">
        {editingInfo ? (
          <EditProfileForm
            profile={profile}
            onSaved={(u) => {
              setProfile(u);
              setEditingInfo(false);
            }}
            onCancel={() => setEditingInfo(false)}
          />
        ) : (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field label="Nome completo" value={profile.name} />
              <Field label="E-mail" value={profile.email} />
              <Field label="Telefone" value={profile.phone ?? ""} />
              <Field label="Departamento" value={profile.department ?? ""} />
            </div>
            <div className="flex justify-end">
              <button
                onClick={() => setEditingInfo(true)}
                className="text-sm text-primary hover:text-primary/80 transition-colors"
              >
                Editar informações
              </button>
            </div>
          </>
        )}
      </SectionCard>

      {/* Company + Equipment — clients only */}
      {profile.role === "client" && (
        <>
          <CompanySection profile={profile} onSaved={setProfile} />
          <EquipmentSection />
        </>
      )}

      {/* Password */}
      <SectionCard title="Segurança">
        {editingPassword ? (
          <ChangePasswordForm onDone={() => setEditingPassword(false)} />
        ) : (
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-300">Senha</p>
              <p className="text-xs text-slate-500">
                Recomendamos trocar sua senha periodicamente
              </p>
            </div>
            <button
              onClick={() => setEditingPassword(true)}
              className="text-sm text-primary hover:text-primary/80 transition-colors"
            >
              Alterar senha
            </button>
          </div>
        )}
      </SectionCard>

      {/* Account info */}
      <SectionCard title="Conta">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field
            label="Status"
            value={profile.status === "active" ? "Ativo" : profile.status}
          />
          <Field
            label="Consentimento LGPD"
            value={
              profile.lgpd_consent
                ? `Concedido em ${new Date(profile.lgpd_consent_at!).toLocaleDateString("pt-BR")}`
                : "Não concedido"
            }
          />
          <Field
            label="ID do usuário"
            value={String(authUser?.id ?? profile.id ?? "").slice(0, 8) + "…"}
          />
        </div>
      </SectionCard>
    </div>
  );
}
