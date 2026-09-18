import { useEffect, useRef, useState } from "react";
import { useAuth } from "../../contexts/AuthContext";
import {
  Alert,
  Badge,
  Button,
  Card,
  Icon,
  Input,
  Spinner,
} from "../../components/ui";
import {
  changePassword,
  completeOnboarding,
  getMe,
  updateMe,
  uploadAvatar,
  type UserSummary,
} from "../../services/userService";
import {
  activateMfaApi,
  disableMfaApi,
  getMfaStatusApi,
  setupMfaApi,
  type MfaSetup,
  type MfaStatus,
} from "../../services/authService";
import { lookupCnpj, lookupCep } from "../../services/equipmentService";
import { getApiError } from "../../lib/apiError";
import { rotuloDePapel, varianteDePapel } from "../../lib/papel";
import { formatCnpj, isValidCep, isValidCnpj, maskCnpjInput, onlyDigits } from "../../lib/documents";

// ── Shared ────────────────────────────────────────────────────

/**
 * Rótulo e selo do papel, numa entrada só.
 *
 * Eram duas tabelas paralelas indexadas pela mesma chave — `ROLE_LABEL` e
 * `ROLE_BADGE` —, e a segunda escrevia classe crua
 * (`bg-slate-100 dark:bg-slate-700/50 text-slate-600 …`) para dizer o que uma
 * variante de `Badge` já diz. Duas tabelas com a mesma chave divergem no dia em
 * que um papel novo entra numa e não na outra; foi assim que prioridade virou
 * dez mapas.
 *
 * Era local, e o agente que migrou esta tela registrou por quê: as mesmas
 * três linhas existiam no `Topbar`, no `UsersPage` e na `KBArticlePage`, e
 * `src/lib` estava fora do escopo de quem migra UMA tela. Ele relatou em vez de
 * inventar um quinto lugar, que é o comportamento certo.
 *
 * O módulo existe agora — `lib/papel.ts` —, e esta tela consome dele. A cópia
 * daqui dizia `secondary` onde a do `UsersPage` dizia `muted`; as duas pintam
 * igual no `Badge`, e é justamente por isso que a divergência sobreviveu.
 */

/**
 * Ação de texto no cabeçalho de uma seção — "Editar", "Alterar senha".
 *
 * Fica como `<button>` e não como `Button`: o primitivo traz borda, altura e
 * preenchimento de botão, e estas três moram na mesma linha do título. O que a
 * migração troca é a cor — `text-primary` é o degrau de MARCA, e sobre
 * `--bg-base` dá 3,66:1; `--text-link` existe justamente para isto e dá 5,05:1
 * no claro e 6,47:1 no escuro.
 */
function SectionAction({
  onClick,
  children,
  tone = "link",
}: {
  onClick: () => void;
  children: React.ReactNode;
  /** `danger` é a saída destrutiva — hoje só o "Desativar" do segundo fator. */
  tone?: "link" | "danger";
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`text-xs font-medium transition-colors cursor-pointer rounded ${
        tone === "danger"
          ? "text-on-tint-danger hover:bg-tint-danger px-1.5 py-0.5"
          : "text-conteudo-link hover:text-conteudo-link-hover"
      }`}
    >
      {children}
    </button>
  );
}

// ── Sub-components ────────────────────────────────────────────

/**
 * O retrato de 80px com o botão de trocar a foto.
 *
 * Segue desenhado aqui, e não com o primitivo `Avatar`: ele para em 48px
 * (`lg`), e o `cn()` do projeto é concatenação simples — mandar `w-20` por
 * `className` deixaria duas larguras na mesma classe e quem vencesse sairia da
 * ordem do CSS gerado, não do código. Relatado como falta do primitivo.
 *
 * O que mudou foi a cor. `text-primary` sobre `bg-primary/15` é exatamente o
 * par que a emenda E8 mediu em **2,77:1** no escuro: o degrau de marca como
 * cor de TEXTO sobre a própria tinta. `on-tint-primary` é o par medido dessa
 * tinta, e a tinta entra pelo token — sem modificador de opacidade, porque ela
 * já carrega 15% (regra (a) do D8-a).
 */
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
      <div className="w-20 h-20 rounded-full bg-tint-primary border-2 border-primary/30 overflow-hidden flex items-center justify-center">
        {avatarUrl ? (
          <img src={avatarUrl} alt={name} className="w-full h-full object-cover" />
        ) : (
          <span className="text-2xl font-bold text-on-tint-primary">{initials}</span>
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
        className="absolute bottom-0 right-0 w-7 h-7 rounded-full bg-surface border border-borda flex items-center justify-center shadow-sm hover:bg-surface-elevated transition-colors cursor-pointer disabled:opacity-50"
      >
        {/* Os dois traçados da máquina fotográfica batiam caractere a caractere
            com o `camera` que a E21 subiu para o pacote — mesma família, 24×24,
            `fill="none"` e traço em `currentColor`. */}
        <Icon name="camera" size={14} strokeWidth={2} className="text-conteudo-muted" />
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
      <p className="text-xs font-medium text-conteudo-muted">{label}</p>
      <p className="text-sm text-conteudo">{value || "—"}</p>
    </div>
  );
}

/**
 * A casca vem do `Card`, com `padding="none"` porque o cabeçalho é sangrado:
 * o divisor atravessa o cartão de ponta a ponta, e o `p-6` do primitivo o
 * encolheria. O que o `Card` dá aqui é o que a tela repetia — canto, borda e
 * superfície — e é o que deixa de divergir quando o token mudar.
 */
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
    <Card padding="none" className="overflow-hidden">
      <div className="flex items-center justify-between px-6 py-4 border-b border-borda-muted">
        <h2 className="text-sm font-semibold text-conteudo">{title}</h2>
        {action}
      </div>
      <div className="px-6 py-5">{children}</div>
    </Card>
  );
}

/**
 * O par Cancelar/Salvar de um formulário.
 *
 * `bg-primary text-white` dava **3,83:1** nos dois temas — o degrau 500 é
 * absoluto e não inverte. O `Button` primário resolve pelo par certo,
 * `--action` com `--text-on-primary`, que é branco no claro e navy no escuro.
 */
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
      <Button type="button" variant="ghost" onClick={onCancel}>
        Cancelar
      </Button>
      <Button type="submit" disabled={saving}>
        {saving ? "Salvando…" : (saveLabel ?? "Salvar")}
      </Button>
    </div>
  );
}

// ── Segundo fator (TOTP) ──────────────────────────────────────

/**
 * Cadastro e desligamento do segundo fator. Só aparece para o staff.
 *
 * Não há leitor de QR aqui de propósito: renderizar o código exigiria uma
 * dependência nova para uma tela que cada pessoa usa uma vez na vida. O segredo
 * vem do servidor já agrupado de quatro em quatro, e o link `otpauth://` abre o
 * aplicativo autenticador direto no celular.
 */
function MfaSection() {
  const [status, setStatus] = useState<MfaStatus | null>(null);
  const [cadastro, setCadastro] = useState<MfaSetup | null>(null);
  const [codigo, setCodigo] = useState("");
  const [senha, setSenha] = useState("");
  const [desligando, setDesligando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    getMfaStatusApi().then(setStatus).catch(() => setStatus(null));
  }, []);

  function limpar() {
    setCadastro(null);
    setCodigo("");
    setSenha("");
    setDesligando(false);
    setErro(null);
  }

  async function comErro(acao: () => Promise<void>, padrao: string) {
    setOcupado(true);
    setErro(null);
    try {
      await acao();
    } catch (e) {
      setErro(getApiError(e, padrao));
    } finally {
      setOcupado(false);
    }
  }

  const iniciar = () =>
    comErro(async () => {
      setCadastro(await setupMfaApi());
    }, "Não foi possível iniciar o cadastro.");

  const ativar = () =>
    comErro(async () => {
      await activateMfaApi(codigo);
      limpar();
      setStatus(await getMfaStatusApi());
    }, "Código inválido. Confira o aplicativo e tente de novo.");

  const desativar = () =>
    comErro(async () => {
      await disableMfaApi(senha);
      limpar();
      setStatus(await getMfaStatusApi());
    }, "Não foi possível desativar.");

  if (!status) return null;

  return (
    <SectionCard
      title="Verificação em duas etapas"
      action={
        status.enabled && !desligando ? (
          <SectionAction tone="danger" onClick={() => setDesligando(true)}>
            Desativar
          </SectionAction>
        ) : undefined
      }
    >
      <div className="space-y-4">
        {/* Aparece em resposta a uma ação, então a região viva é o certo: é
            mudança, e o `Alert` de perigo interrompe a leitura de propósito. */}
        {erro && <Alert variant="danger">{erro}</Alert>}

        {!status.available && (
          <p className="text-sm text-conteudo-muted">
            A verificação em duas etapas não está disponível neste ambiente. Fale com o
            administrador do sistema.
          </p>
        )}

        {status.available && status.enabled && !desligando && (
          <div className="flex items-center gap-3">
            {/* O ponto nunca informa sozinho — o texto ao lado diz "Ativa". A
                cor sai de `--fill-success` e não do degrau 500, que a E19 mediu
                em 2,54:1 como preenchimento no tema claro, abaixo do piso de
                3:1 da WCAG 1.4.11. */}
            <span className="w-1.5 h-1.5 rounded-full bg-fill-success" />
            <p className="text-sm text-conteudo">
              Ativa. Ao entrar, o sistema pedirá o código do seu aplicativo autenticador.
            </p>
          </div>
        )}

        {status.available && status.enabled && desligando && (
          <div className="space-y-3">
            <p className="text-sm text-conteudo-muted">
              Confirme sua senha para desativar. Todas as sessões abertas serão encerradas.
            </p>
            <Input
              label="Sua senha atual"
              type="password"
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              autoComplete="current-password"
            />
            <div className="flex gap-2 justify-end">
              <Button type="button" variant="ghost" onClick={limpar}>
                Cancelar
              </Button>
              <Button
                type="button"
                variant="danger"
                onClick={desativar}
                disabled={ocupado || !senha}
              >
                {ocupado ? "Desativando…" : "Desativar"}
              </Button>
            </div>
          </div>
        )}

        {status.available && !status.enabled && !cadastro && (
          <div className="space-y-3">
            <p className="text-sm text-conteudo-muted">
              Uma segunda camada além da senha: ao entrar, o sistema pede um código de seis
              dígitos gerado no seu celular.
            </p>
            <Button type="button" onClick={iniciar} disabled={ocupado}>
              {ocupado ? "Gerando…" : "Ativar"}
            </Button>
          </div>
        )}

        {status.available && !status.enabled && cadastro && (
          <div className="space-y-4">
            <ol className="text-sm text-conteudo space-y-3 list-decimal list-inside">
              <li>
                Abra seu aplicativo autenticador (Google Authenticator, Microsoft
                Authenticator, 1Password…).
              </li>
              <li>
                Adicione uma conta e informe esta chave:
                <code className="mt-2 block rounded-lg bg-surface-elevated px-3 py-2 font-mono text-sm tracking-wider text-conteudo break-all">
                  {cadastro.secret}
                </code>
                <a
                  href={cadastro.otpauth_uri}
                  className="mt-1.5 inline-block text-xs font-medium text-conteudo-link hover:text-conteudo-link-hover"
                >
                  Ou toque aqui para abrir no aplicativo
                </a>
              </li>
              <li>Digite abaixo o código que aparecer.</li>
            </ol>

            <Input
              label="Código do aplicativo"
              type="text"
              inputMode="numeric"
              placeholder="000000"
              value={codigo}
              onChange={(e) => setCodigo(e.target.value)}
              autoComplete="one-time-code"
              maxLength={7}
              hint="A verificação só é ligada depois que o código confere — se o aplicativo não pareou, nada muda e você não fica trancado fora."
            />
            <div className="flex gap-2 justify-end">
              <Button type="button" variant="ghost" onClick={limpar}>
                Cancelar
              </Button>
              <Button
                type="button"
                onClick={ativar}
                disabled={ocupado || !codigo}
              >
                {ocupado ? "Verificando…" : "Confirmar"}
              </Button>
            </div>
          </div>
        )}
      </div>
    </SectionCard>
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
      {error && <Alert variant="danger">{error}</Alert>}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="sm:col-span-2">
          <Input label="Nome completo" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <Input label="Telefone" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="(11) 99999-9999" />
        <Input label="Departamento" value={department} onChange={(e) => setDepartment(e.target.value)} placeholder="Ex: TI, RH" />
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

  // O "certo" desenhado à mão aqui era, caractere a caractere, o `check` do
  // pacote — e é o mesmo traçado que o `Alert` de sucesso já desenha. Trocar o
  // parágrafo verde pelo primitivo tira o `<svg>` solto E o par
  // `text-green-600`/`dark:text-green-400`, e ainda faz a confirmação virar
  // região viva polida: quem não vê a tela passava a trocar de senha sem
  // ouvir que deu certo.
  if (success)
    return <Alert variant="success">Senha alterada com sucesso!</Alert>;

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && <Alert variant="danger">{error}</Alert>}
      {(
        [
          ["Senha atual", current, setCurrent],
          ["Nova senha", next, setNext],
          ["Confirmar nova senha", confirm, setConfirm],
        ] as [string, string, (v: string) => void][]
      ).map(([label, val, setter]) => (
        <Input
          key={label}
          label={label}
          type="password"
          value={val}
          onChange={(e) => setter(e.target.value)}
          autoComplete="off"
        />
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

  // Clientes cadastrados antes da regra podem estar sem esses dados
  const cadastroIncompleto = !profile.cnpj || !profile.company_cep;

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
    if (!cnpj.trim()) { setError("Informe o CNPJ da empresa."); return; }
    if (!isValidCnpj(cnpj)) { setError("CNPJ inválido. Confira os números digitados."); return; }
    if (!cep.trim()) { setError("Informe o CEP da empresa."); return; }
    if (!isValidCep(cep)) { setError("CEP inválido. Deve ter 8 dígitos."); return; }
    setSaving(true);
    setError("");
    try {
      const updated = await completeOnboarding({
        company_name: companyName.trim(),
        cnpj: onlyDigits(cnpj),
        company_cep: onlyDigits(cep),
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
          <SectionAction onClick={() => setEditing(true)}>Editar</SectionAction>
        ) : undefined
      }
    >
      {/* `live={false}`: este aviso já está na tela quando ela termina de
          carregar, e não responde a ação nenhuma. Região viva anuncia MUDANÇA —
          anunciá-lo faria o leitor de tela ler a consequência antes da causa
          (emenda E12). */}
      {!editing && cadastroIncompleto && (
        <Alert variant="warning" live={false} className="mb-4">
          Complete o cadastro da sua empresa: CNPJ e CEP são obrigatórios.
        </Alert>
      )}

      {editing ? (
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && <Alert variant="danger">{error}</Alert>}
          {/* O asterisco de obrigatório era `text-danger-400` — um vermelho
              claro sobre superfície clara. Agora ele mora no texto do rótulo,
              como no `ProductsPage`: quem lê com leitor de tela ouve o
              asterisco junto do nome do campo, em vez de um `<span>` sem
              ligação nenhuma com o `<input>`. */}
          <div className="relative">
            <Input
              label="CNPJ *"
              value={cnpj}
              onChange={(e) => setCnpj(maskCnpjInput(e.target.value))}
              onBlur={handleCnpjBlur}
              placeholder="00.000.000/0000-00"
            />
            {lookingCnpj && <div className="absolute right-3 bottom-2.5"><Spinner size="sm" /></div>}
          </div>
          <Input
            label="Nome da empresa"
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            placeholder="Razão social ou nome fantasia"
            required
          />
          <div className="relative">
            <Input
              label="CEP *"
              value={cep}
              onChange={(e) => setCep(formatCep(e.target.value))}
              onBlur={handleCepBlur}
              placeholder="00000-000"
            />
            {lookingCep && <div className="absolute right-3 bottom-2.5"><Spinner size="sm" /></div>}
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
            <Input
              label="Estado (UF)"
              value={state}
              onChange={(e) => setState(e.target.value.toUpperCase().slice(0, 2))}
              placeholder="PE"
              maxLength={2}
            />
          </div>
          <FormActions saving={saving} onCancel={() => setEditing(false)} />
        </form>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <Field label="Nome da empresa" value={profile.company_name ?? ""} />
          <Field label="CNPJ" value={formatCnpj(profile.cnpj)} />
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
      <div className="max-w-2xl mx-auto px-4 py-10 text-center text-conteudo-muted text-sm">
        Não foi possível carregar o perfil.
      </div>
    );

  const papelRotulo = rotuloDePapel(profile.role);
  const papelVariante = varianteDePapel(profile.role);
  const joinedAt = new Date(profile.created_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" });
  const lastLogin = profile.last_login
    ? new Date(profile.last_login).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })
    : "—";

  return (
    <div className="space-y-5">
      {/* Page header */}
      <div>
        <h1 className="text-xl font-semibold text-conteudo-heading">Meu perfil</h1>
        <p className="text-sm text-conteudo-muted mt-0.5">Gerencie suas informações pessoais e segurança</p>
      </div>

      {/* Identity card */}
      <Card padding="lg">
        {avatarError && (
          <Alert variant="danger" className="mb-3">{avatarError}</Alert>
        )}
        <div className="flex items-center gap-5">
          <ProfileAvatar
            name={profile.name}
            avatarUrl={profile.avatar_url}
            uploading={uploadingAvatar}
            onFileSelect={handleAvatarFile}
          />
          <div className="min-w-0 flex-1 space-y-1.5">
            <h2 className="text-lg font-semibold text-conteudo-heading truncate">{profile.name}</h2>
            <p className="text-sm text-conteudo-muted truncate">{profile.email}</p>
            {/* Papel desconhecido cai no neutro e mostra o valor cru: o dado vem
                da REDE, e um papel novo no backend não pode derrubar a tela. */}
            <Badge variant={papelVariante}>{papelRotulo}</Badge>
          </div>
          <div className="hidden sm:flex flex-col gap-3 text-right shrink-0">
            <div>
              <p className="text-xs font-medium text-conteudo-muted">Membro desde</p>
              <p className="text-sm text-conteudo mt-0.5">{joinedAt}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-conteudo-muted">Último acesso</p>
              <p className="text-sm text-conteudo mt-0.5">{lastLogin}</p>
            </div>
          </div>
        </div>
      </Card>

      {/* Personal info */}
      <SectionCard
        title="Informações pessoais"
        action={
          !editingInfo ? (
            <SectionAction onClick={() => setEditingInfo(true)}>Editar</SectionAction>
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
            <SectionAction onClick={() => setEditingPassword(true)}>Alterar senha</SectionAction>
          ) : undefined
        }
      >
        {editingPassword ? (
          <ChangePasswordForm onDone={() => setEditingPassword(false)} />
        ) : (
          <div className="flex items-center gap-4">
            <div className="w-9 h-9 rounded-lg bg-surface-elevated flex items-center justify-center shrink-0">
              {/* Traçado idêntico ao `lock` do pacote, conferido caractere a
                  caractere — e mesma família: 24×24, sem preenchimento. */}
              <Icon name="lock" size={18} strokeWidth={2} className="text-conteudo-muted" />
            </div>
            <div>
              <p className="text-sm font-medium text-conteudo">Senha</p>
              <p className="text-xs text-conteudo-muted mt-0.5">Recomendamos trocar sua senha periodicamente</p>
            </div>
          </div>
        )}
      </SectionCard>

      {/* Segundo fator — só staff tem */}
      {(authUser?.role === "admin" || authUser?.role === "technician") && <MfaSection />}

      {/* Account info */}
      <SectionCard title="Conta">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div className="space-y-0.5">
            <p className="text-xs font-medium text-conteudo-muted">Status</p>
            <div className="flex items-center gap-1.5 mt-1">
              {/* O neutro é `--border-control`, o único que inverte por tema —
                  mesmo raciocínio do selo de ativo/inativo do `ProductsPage`. E
                  o estado nunca fica só na cor: o texto ao lado o carrega. */}
              <span className={`w-1.5 h-1.5 rounded-full ${profile.status === "active" ? "bg-fill-success" : "bg-borda-control"}`} />
              <p className="text-sm text-conteudo">
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
