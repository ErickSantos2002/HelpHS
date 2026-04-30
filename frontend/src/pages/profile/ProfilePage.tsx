import { useEffect, useState } from "react";
import { useAuth } from "../../contexts/AuthContext";
import {
  changePassword,
  getMe,
  updateMe,
  type UserSummary,
} from "../../services/userService";

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
      const updated = await updateMe({
        name: name.trim(),
        phone: phone.trim() || null,
        department: department.trim() || null,
      });
      onSaved(updated);
    } catch {
      setError("Erro ao salvar. Tente novamente.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && (
        <p className="text-sm text-danger bg-danger/10 border border-danger/20 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      <div className="space-y-1.5">
        <label className="text-xs text-slate-400">Nome completo</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-lg border border-border bg-background-elevated px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors"
        />
      </div>

      <div className="space-y-1.5">
        <label className="text-xs text-slate-400">Telefone</label>
        <input
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="(11) 99999-9999"
          className="w-full rounded-lg border border-border bg-background-elevated px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors"
        />
      </div>

      <div className="space-y-1.5">
        <label className="text-xs text-slate-400">Departamento</label>
        <input
          value={department}
          onChange={(e) => setDepartment(e.target.value)}
          placeholder="Ex: TI, RH, Operações"
          className="w-full rounded-lg border border-border bg-background-elevated px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors"
        />
      </div>

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
          {saving ? "Salvando…" : "Salvar"}
        </button>
      </div>
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
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Erro ao alterar senha. Tente novamente.";
      setError(msg);
    } finally {
      setSaving(false);
    }
  }

  if (success) {
    return (
      <p className="text-sm text-green-400 py-2">Senha alterada com sucesso!</p>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && (
        <p className="text-sm text-danger bg-danger/10 border border-danger/20 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

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
            className="w-full rounded-lg border border-border bg-background-elevated px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors"
          />
        </div>
      ))}

      <div className="flex gap-2 justify-end">
        <button
          type="button"
          onClick={onDone}
          className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 transition-colors"
        >
          Cancelar
        </button>
        <button
          type="submit"
          disabled={saving}
          className="px-4 py-2 rounded-lg bg-primary text-white text-sm hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {saving ? "Alterando…" : "Alterar senha"}
        </button>
      </div>
    </form>
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

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-10 text-center text-slate-500 text-sm">
        Carregando…
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-10 text-center text-slate-500 text-sm">
        Não foi possível carregar o perfil.
      </div>
    );
  }

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
            onSaved={(updated) => {
              setProfile(updated);
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
