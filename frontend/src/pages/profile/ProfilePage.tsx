import { useEffect, useRef, useState } from "react";
import { useAuth } from "../../contexts/AuthContext";
import { Spinner } from "../../components/ui";
import {
  changePassword,
  completeOnboarding,
  getMe,
  updateMe,
  uploadAvatar,
  type UserSummary,
} from "../../services/userService";
import { lookupCnpj, lookupCep } from "../../services/equipmentService";

// ── Shared ────────────────────────────────────────────────────

const ROLE_LABEL: Record<string, string> = {
  admin: "Administrador",
  technician: "Técnico",
  client: "Cliente",
};

const ROLE_BADGE: Record<string, string> = {
  admin:      "bg-primary/10 text-primary border border-primary/20",
  technician: "bg-info/10 text-info border border-info/20",
  client:     "bg-slate-100 dark:bg-slate-700/50 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-600",
};

const INPUT_CLS =
  "w-full rounded-lg border border-slate-200 dark:border-border bg-white dark:bg-background-elevated px-3 py-2 text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors";

// ── Sub-components ────────────────────────────────────────────

function ProfileAvatar({
  name,
  avatarUrl,
  uploading,
  onFileSelect,
}: {
  name: string;
  avatarUrl: string | null;
  uploading: boolean;
  onFileSelect: (file: File) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const initials = name
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();

  return (
    <div className="relative shrink-0">
      <div className="w-20 h-20 rounded-full bg-primary/15 border-2 border-primary/30 overflow-hidden flex items-center justify-center">
        {avatarUrl ? (
          <img src={avatarUrl} alt={name} className="w-full h-full object-cover" />
        ) : (
          <span className="text-2xl font-bold text-primary">{initials}</span>
        )}
        {uploading && (
          <div className="absolute inset-0 bg-black/40 flex items-center justify-center rounded-full">
            <Spinner size="sm" />
          </div>
        )}
      </div>
      <button
        type="button"
        aria-label="Alterar foto"
        onClick={() => inputRef.current?.click()}
        disabled={uploading}
        className="absolute bottom-0 right-0 w-7 h-7 rounded-full bg-white dark:bg-background-elevated border border-slate-200 dark:border-border flex items-center justify-center shadow-sm hover:bg-slate-50 dark:hover:bg-background-surface transition-colors cursor-pointer disabled:opacity-50"
      >
        <svg className="w-3.5 h-3.5 text-slate-500 dark:text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/gif,image/webp"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFileSelect(file);
          e.target.value = "";
        }}
      />
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-0.5">
      <p className="text-xs font-medium text-slate-500 dark:text-slate-500">{label}</p>
      <p className="text-sm text-slate-700 dark:text-slate-200">{value || "—"}</p>
    </div>
  );
}

function SectionCard({
  title,
  action,
  children,
}: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl bg-white dark:bg-background-surface border border-slate-200 dark:border-border overflow-hidden">
      <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 dark:border-border/60">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">{title}</h2>
        {action}
      </div>
      <div className="px-6 py-5">{children}</div>
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
    <div className="flex gap-2 justify-end pt-2">
      <button
        type="button"
        onClick={onCancel}
        className="px-4 py-2 text-sm text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 transition-colors rounded-lg hover:bg-slate-100 dark:hover:bg-background-elevated"
      >
        Cancelar
      </button>
      <button
        type="submit"
        disabled={saving}
        className="px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors"
      >
        {saving ? "Salvando…" : (saveLabel ?? "Salvar")}
      </button>
    </div>
  );
}

// ── Edit profile form ─────────────────────────────────────────

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
    if (!name.trim()) { setError("Nome é obrigatório"); return; }
    setSaving(true);
    setError("");
    try {
      onSaved(await updateMe({ name: name.trim(), phone: phone.trim() || null, department: department.trim() || null }));
    } catch {
      setError("Erro ao salvar. Tente novamente.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && <ErrorMsg msg={error} />}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="space-y-1.5 sm:col-span-2">
          <label className="text-xs font-medium text-slate-500">Nome completo</label>
          <input value={name} onChange={(e) => setName(e.target.value)} className={INPUT_CLS} />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-slate-500">Telefone</label>
          <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="(11) 99999-9999" className={INPUT_CLS} />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-slate-500">Departamento</label>
          <input value={department} onChange={(e) => setDepartment(e.target.value)} placeholder="Ex: TI, RH" className={INPUT_CLS} />
        </div>
      </div>
      <FormActions saving={saving} onCancel={onCancel} />
    </form>
  );
}

// ── Change password form ──────────────────────────────────────

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
    if (next.length < 8) { setError("A nova senha deve ter no mínimo 8 caracteres"); return; }
    if (!/[A-Z]/.test(next)) { setError("A nova senha deve conter ao menos uma letra maiúscula"); return; }
    if (!/[0-9]/.test(next)) { setError("A nova senha deve conter ao menos um número"); return; }
    if (next !== confirm) { setError("As senhas não coincidem"); return; }
    setSaving(true);
    try {
      await changePassword(current, next);
      setSuccess(true);
      setTimeout(onDone, 1500);
    } catch (err: unknown) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Erro ao alterar senha. Tente novamente.",
      );
    } finally {
      setSaving(false);
    }
  }

  if (success)
    return (
      <div className="flex items-center gap-2 py-2 text-sm text-green-600 dark:text-green-400">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        Senha alterada com sucesso!
      </div>
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
          <label className="text-xs font-medium text-slate-500">{label}</label>
          <input type="password" value={val} onChange={(e) => setter(e.target.value)} autoComplete="off" className={INPUT_CLS} />
        </div>
      ))}
      <FormActions saving={saving} saveLabel="Alterar senha" onCancel={onDone} />
    </form>
  );
}

// ── Company section ───────────────────────────────────────────

function CompanySection({ profile, onSaved }: { profile: UserSummary; onSaved: (u: UserSummary) => void }) {
  const [editing, setEditing] = useState(false);
  const [companyName, setCompanyName] = useState(profile.company_name ?? "");
  const [cnpj, setCnpj] = useState(profile.cnpj ?? "");
  const [cep, setCep] = useState(profile.company_cep ?? "");
  const [address, setAddress] = useState(profile.company_address ?? "");
  const [city, setCity] = useState(profile.company_city ?? "");
  const [state, setState] = useState(profile.company_state ?? "");
  const [lookingCnpj, setLookingCnpj] = useState(false);
  const [lookingCep, setLookingCep] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function formatCnpj(v: string) {
    const d = v.replace(/\D/g, "").slice(0, 14);
    return d.replace(/^(\d{2})(\d)/, "$1.$2").replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3").replace(/\.(\d{3})(\d)/, ".$1/$2").replace(/(\d{4})(\d)/, "$1-$2");
  }
  function formatCep(v: string) {
    const d = v.replace(/\D/g, "").slice(0, 8);
    return d.replace(/^(\d{5})(\d)/, "$1-$2");
  }

  async function handleCnpjBlur() {
    const digits = cnpj.replace(/\D/g, "");
    if (digits.length !== 14) return;
    setLookingCnpj(true);
    try {
      const info = await lookupCnpj(digits);
      setCompanyName(info.trade_name || info.company_name);
      setCity(info.city);
      setState(info.state);
    } catch { /* manual fill */ } finally { setLookingCnpj(false); }
  }

  async function handleCepBlur() {
    const digits = cep.replace(/\D/g, "");
    if (digits.length !== 8) return;
    setLookingCep(true);
    try {
      const info = await lookupCep(digits);
      if (info.address) setAddress(info.address);
      if (info.city) setCity(info.city);
      if (info.state) setState(info.state);
    } catch { /* manual fill */ } finally { setLookingCep(false); }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!companyName.trim()) { setError("Nome da empresa é obrigatório"); return; }
    setSaving(true);
    setError("");
    try {
      const updated = await completeOnboarding({
        company_name: companyName.trim(),
        cnpj: cnpj.replace(/\D/g, "") || null,
        company_cep: cep.replace(/\D/g, "") || null,
        company_address: address.trim() || null,
        company_city: city.trim() || null,
        company_state: state.trim().toUpperCase().slice(0, 2) || null,
      });
      onSaved(updated);
      setEditing(false);
    } catch { setError("Erro ao salvar. Tente novamente."); } finally { setSaving(false); }
  }

  return (
    <SectionCard
      title="Empresa"
      action={
        !editing ? (
          <button onClick={() => setEditing(true)} className="text-xs font-medium text-primary hover:text-primary/80 transition-colors">
            Editar
          </button>
        ) : undefined
      }
    >
      {editing ? (
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && <ErrorMsg msg={error} />}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-500">CNPJ</label>
            <div className="relative">
              <input value={cnpj} onChange={(e) => setCnpj(formatCnpj(e.target.value))} onBlur={handleCnpjBlur} placeholder="00.000.000/0000-00" className={INPUT_CLS} />
              {lookingCnpj && <div className="absolute right-3 top-2.5"><Spinner size="sm" /></div>}
            </div>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-500">Nome da empresa</label>
            <input value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="Razão social ou nome fantasia" className={INPUT_CLS} required />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-500">CEP</label>
            <div className="relative">
              <input value={cep} onChange={(e) => setCep(formatCep(e.target.value))} onBlur={handleCepBlur} placeholder="00000-000" className={INPUT_CLS} />
              {lookingCep && <div className="absolute right-3 top-2.5"><Spinner size="sm" /></div>}
            </div>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-500">Endereço</label>
            <input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="Ex: Rua das Flores, 123" className={INPUT_CLS} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-500">Cidade</label>
              <input value={city} onChange={(e) => setCity(e.target.value)} placeholder="Ex: Recife" className={INPUT_CLS} />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-500">Estado (UF)</label>
              <input value={state} onChange={(e) => setState(e.target.value.toUpperCase().slice(0, 2))} placeholder="PE" maxLength={2} className={INPUT_CLS} />
            </div>
          </div>
          <FormActions saving={saving} onCancel={() => setEditing(false)} />
        </form>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <Field label="Nome da empresa" value={profile.company_name ?? ""} />
          <Field label="CNPJ" value={profile.cnpj ? profile.cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5") : ""} />
          <Field label="CEP" value={profile.company_cep ? profile.company_cep.replace(/^(\d{5})(\d{3})$/, "$1-$2") : ""} />
          <Field label="Endereço" value={profile.company_address ?? ""} />
          <Field label="Cidade" value={profile.company_city ?? ""} />
          <Field label="Estado" value={profile.company_state ?? ""} />
        </div>
      )}
    </SectionCard>
  );
}

// ── ProfilePage ───────────────────────────────────────────────

export default function ProfilePage() {
  const { user: authUser, updateAvatarUrl } = useAuth();
  const [profile, setProfile] = useState<UserSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [editingInfo, setEditingInfo] = useState(false);
  const [editingPassword, setEditingPassword] = useState(false);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const [avatarError, setAvatarError] = useState<string | null>(null);

  async function handleAvatarFile(file: File) {
    setUploadingAvatar(true);
    setAvatarError(null);
    try {
      const updated = await uploadAvatar(file);
      setProfile(updated);
      updateAvatarUrl(updated.avatar_url);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setAvatarError(detail ?? "Erro ao enviar foto.");
    } finally {
      setUploadingAvatar(false);
    }
  }

  useEffect(() => {
    getMe().then(setProfile).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading)
    return (
      <div className="flex h-48 items-center justify-center">
        <Spinner size="lg" />
      </div>
    );

  if (!profile)
    return (
      <div className="max-w-2xl mx-auto px-4 py-10 text-center text-slate-500 text-sm">
        Não foi possível carregar o perfil.
      </div>
    );

  const joinedAt = new Date(profile.created_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" });
  const lastLogin = profile.last_login
    ? new Date(profile.last_login).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })
    : "—";

  return (
    <div className="space-y-5">
      {/* Page header */}
      <div>
        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Meu perfil</h1>
        <p className="text-sm text-slate-500 mt-0.5">Gerencie suas informações pessoais e segurança</p>
      </div>

      {/* Identity card */}
      <div className="rounded-xl bg-white dark:bg-background-surface border border-slate-200 dark:border-border p-6">
        {avatarError && (
          <p className="mb-3 text-xs text-danger bg-danger/10 border border-danger/20 rounded-lg px-3 py-2">{avatarError}</p>
        )}
        <div className="flex items-center gap-5">
          <ProfileAvatar
            name={profile.name}
            avatarUrl={profile.avatar_url}
            uploading={uploadingAvatar}
            onFileSelect={handleAvatarFile}
          />
          <div className="min-w-0 flex-1 space-y-1.5">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 truncate">{profile.name}</h2>
            <p className="text-sm text-slate-500 truncate">{profile.email}</p>
            <span className={`inline-block text-xs px-2.5 py-0.5 rounded-full font-medium ${ROLE_BADGE[profile.role] ?? ""}`}>
              {ROLE_LABEL[profile.role] ?? profile.role}
            </span>
          </div>
          <div className="hidden sm:flex flex-col gap-3 text-right shrink-0">
            <div>
              <p className="text-xs font-medium text-slate-500">Membro desde</p>
              <p className="text-sm text-slate-700 dark:text-slate-200 mt-0.5">{joinedAt}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500">Último acesso</p>
              <p className="text-sm text-slate-700 dark:text-slate-200 mt-0.5">{lastLogin}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Personal info */}
      <SectionCard
        title="Informações pessoais"
        action={
          !editingInfo ? (
            <button onClick={() => setEditingInfo(true)} className="text-xs font-medium text-primary hover:text-primary/80 transition-colors">
              Editar
            </button>
          ) : undefined
        }
      >
        {editingInfo ? (
          <EditProfileForm
            profile={profile}
            onSaved={(u) => { setProfile(u); setEditingInfo(false); }}
            onCancel={() => setEditingInfo(false)}
          />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            <Field label="Nome completo" value={profile.name} />
            <Field label="E-mail" value={profile.email} />
            <Field label="Telefone" value={profile.phone ?? ""} />
            <Field label="Departamento" value={profile.department ?? ""} />
          </div>
        )}
      </SectionCard>

      {/* Company — clients only */}
      {profile.role === "client" && (
        <CompanySection profile={profile} onSaved={setProfile} />
      )}

      {/* Security */}
      <SectionCard
        title="Segurança"
        action={
          !editingPassword ? (
            <button onClick={() => setEditingPassword(true)} className="text-xs font-medium text-primary hover:text-primary/80 transition-colors">
              Alterar senha
            </button>
          ) : undefined
        }
      >
        {editingPassword ? (
          <ChangePasswordForm onDone={() => setEditingPassword(false)} />
        ) : (
          <div className="flex items-center gap-4">
            <div className="w-9 h-9 rounded-lg bg-slate-100 dark:bg-background-elevated flex items-center justify-center shrink-0">
              <svg className="w-4.5 h-4.5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </div>
            <div>
              <p className="text-sm font-medium text-slate-700 dark:text-slate-200">Senha</p>
              <p className="text-xs text-slate-500 mt-0.5">Recomendamos trocar sua senha periodicamente</p>
            </div>
          </div>
        )}
      </SectionCard>

      {/* Account info */}
      <SectionCard title="Conta">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div className="space-y-0.5">
            <p className="text-xs font-medium text-slate-500">Status</p>
            <div className="flex items-center gap-1.5 mt-1">
              <span className={`w-1.5 h-1.5 rounded-full ${profile.status === "active" ? "bg-green-500" : "bg-slate-400"}`} />
              <p className="text-sm text-slate-700 dark:text-slate-200">
                {profile.status === "active" ? "Ativo" : profile.status}
              </p>
            </div>
          </div>
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
