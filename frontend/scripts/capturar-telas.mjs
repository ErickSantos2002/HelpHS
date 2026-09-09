/**
 * Fotografa as telas migradas do sistema de design, num navegador real.
 *
 * Nasceu como `capturar-fase11.mjs`, com as quatro telas do Checkpoint 3.
 * Hoje cobre 22 telas de duas fases, e o nome passou a mentir — daí a
 * renomeação. Cada tela declara a FASE a que pertence, e a foto vai para o
 * diretório daquela fase: o Checkpoint 3 cita os arquivos da Fase 11 pelo
 * caminho, e evidência que muda de lugar deixa de ser citável.
 *
 * ARTEFATO DE DESENVOLVIMENTO — sai na Fase 20, junto com as rotas de galeria.
 *
 * ── A regra que este script existe para cumprir ──────────────────────────
 *
 * **Nenhuma requisição sai para a rede.** O `backend/.env` deste ambiente
 * aponta para o banco de PRODUÇÃO; um screenshot não vale o risco de tocar
 * nele. O script não "evita" chamadas: ele as impede, por lista de permissão.
 *
 * E ele não contorna a autenticação: **semeia** uma sessão falsa e responde ao
 * `/users/me` com um usuário de mentira. As telas são as de verdade, com as
 * rotas de verdade e o `AuthGuard` de verdade — só os dados é que não existem.
 * Uma galeria que renderizasse cópias das telas provaria coisa nenhuma sobre
 * as telas.
 *
 * ── As travas, antes de cada disparo ─────────────────────────────────────
 *
 *   produto   `data-app="helphs"` no `<html>`, falha fechada
 *   pixel     a cor do viewport contra o `--bg-base` lido do `colors.css`
 *   conteúdo  um seletor que só existe na tela pedida
 *
 * As três bloqueiam sozinhas. Ver `sonda-captura.mjs` e o
 * `e2e/sonda-captura.spec.ts`, onde a do pixel é provada isolada.
 *
 * ── Uso ──────────────────────────────────────────────────────────────────
 *
 *   npm run dev                          (noutro terminal, na 5190)
 *   node scripts/capturar-telas.mjs                    todas as telas
 *   node scripts/capturar-telas.mjs 16/relatorios      só o que casar
 *   node scripts/capturar-telas.mjs /claro             idem, por tema
 *
 * O filtro casa contra o rótulo `<fase>/<tela>/<tema>` de cada captura, e
 * existe para o laço de conserto: acrescentar uma tela, rodar SÓ ela, ler qual
 * chamada ficou sem resposta prevista, e repetir. A execução que vale como
 * evidência é sempre a completa, sem filtro.
 *
 * Saída: docs/design-system-migration/fase-<n>/screenshots/
 */
import { chromium } from "@playwright/test";
import { mkdir, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { BASE, conferirPixel, conferirProduto } from "./sonda-captura.mjs";

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const saidaDaFase = (fase) =>
  path.resolve(RAIZ, `../docs/design-system-migration/fase-${fase}/screenshots`);

/**
 * A data-base é CRAVADA, e tudo deriva dela.
 *
 * Era `Date.now()`, e por isso **as fotos mudavam a cada execução**: todo
 * horário relativo — "há 2 horas", "vence amanhã", a grade do mês da agenda —
 * saía diferente, e o `git status` acusava as dez da Fase 11 como modificadas
 * sem que nada no código tivesse mudado.
 *
 * **Evidência que muda entre execuções não é evidência.** Um checkpoint que
 * aponta para uma foto está afirmando algo sobre aquela imagem; se refotografar
 * produz outra, a afirmação não é verificável — e pior, o diff fica cheio de
 * ruído que esconde a mudança real quando ela vier.
 *
 * A escolha da data importa em três detalhes, e nenhum é arbitrário:
 *
 * - **quarta-feira**, para a grade do mês da agenda cair sempre igual e não
 *   depender do dia da semana em que se roda;
 * - **meio do mês**, para `emDias(-15)` e `emDias(+15)` não atravessarem a
 *   virada e mudarem o mês exibido;
 * - **meio-dia UTC**, para o fuso de quem roda não empurrar a data um dia para
 *   trás ou para a frente.
 *
 * Ela é passada com `Z` explícito: sem isso o `new Date("2026-06-17T12:00:00")`
 * seria interpretado no fuso LOCAL, e a data-base voltaria a depender da
 * máquina — que é exatamente o que este bloco existe para impedir.
 */
const AGORA = Date.parse("2026-06-17T12:00:00Z");
const emHoras = (h) => new Date(AGORA + h * 3_600_000).toISOString();
const emDias = (d) => new Date(AGORA + d * 86_400_000).toISOString();
const diaDoMes = (d) => emDias(d).slice(0, 10);

/**
 * O usuário de mentira. O PAPEL varia por tela, e não é detalhe:
 *
 *   · a rota `/` escolhe o painel pelo papel — são TRÊS telas diferentes na
 *     mesma rota, e a Fase 16 migrou a do admin e a do técnico;
 *   · o `RoleGuard` manda para `/403` quem não tem o papel da rota, e a foto
 *     sairia da tela de erro sem que nada acusasse;
 *   · `client-novo` é o cliente que ainda não fez o cadastro. Só ele passa
 *     pelo `OnboardingOnlyRoute`; qualquer outro papel é devolvido para `/`,
 *     e `/onboarding` não teria foto.
 */
const usuario = (papel) => ({
  id: "u-demo",
  name: "Rickelme David",
  email: "demo@exemplo.invalid",
  role: papel === "client-novo" ? "client" : papel,
  is_active: true,
  onboarding_completed: papel !== "client-novo",
  company_id: "c-demo",
  avatar_url: null,
  phone: "(11) 90000-0000",
  created_at: emDias(-400),
  mfa_enabled: false,
});

/** Um chamado por status, para o quadro ter as seis colunas povoadas. */
const CHAMADOS = [
  ["open", "critical", "Sem acesso à plataforma do Phoebus", "hardware"],
  ["open", "medium", "Impressora do 2º andar sem conexão", "network"],
  ["in_progress", "high", "Lentidão no sistema de chamados", "software"],
  ["awaiting_technical", "high", "Troca de HD do notebook da recepção", "hardware"],
  ["awaiting_client", "low", "Confirmação de horário para manutenção", "general"],
  ["resolved", "medium", "E-mail corporativo não sincroniza", "email"],
  ["closed", "low", "Solicitação de acesso ao drive", "access"],
].map(([status, priority, title, category], i) => ({
  id: `t-${i + 1}`,
  protocol: `HS-2026-${String(i + 1).padStart(4, "0")}`,
  title,
  description:
    "Descrição de demonstração. Nenhum dado real foi usado nesta captura.",
  status,
  priority,
  category,
  creator_id: "u-demo",
  creator_name: "Ana Paula",
  assignee_id: i % 3 === 0 ? "u-tec" : null,
  assignee_name: i % 3 === 0 ? "Erick Dantas" : null,
  created_at: emHoras(-30 - i * 6),
  updated_at: emHoras(-2),
  closed_at: status === "closed" ? emHoras(-1) : null,
  sla_response_due_at: emHoras(i % 2 === 0 ? 4 : -3),
  sla_resolve_due_at: emHoras(i % 2 === 0 ? 30 : -6),
  sla_response_breach: i === 3,
  sla_resolve_breach: false,
  sla_first_response: i > 4 ? emHoras(-20) : null,
  equipments: [],
  tags: [],
  product_id: null,
  product_name: null,
  client_observation: null,
}));

const lista = { items: CHAMADOS, total: CHAMADOS.length };

/* ── Os dados de mentira das telas da Fase 16 ────────────────────────────
 *
 * Nada aqui existe. As FORMAS, sim: cada bloco é o `interface` do serviço
 * que consome a rota, lido de `src/services/`. É a forma que derruba a tela,
 * e não o conteúdo — ver a nota da tabela `respostas()`.
 *
 * E os dados não são vazios de propósito. Cinco telas da Fase 16 SÃO listas
 * (produtos, etiquetas, respostas rápidas, equipamentos, notificações);
 * fotografá-las com `{ items: [] }` retrataria o estado vazio, que não mostra
 * nem tabela, nem selo, nem etiqueta — nada do que a migração mexeu.
 */

const TECNICOS = [
  { id: "u-tec", name: "Erick Dantas" },
  { id: "u-tec-2", name: "Marina Lopes" },
  { id: "u-tec-3", name: "Caio Ferreira" },
];

/** Catorze dias, para as séries temporais terem forma em vez de um ponto. */
const porDia = (fn) =>
  Array.from({ length: 14 }, (_, i) => fn(diaDoMes(i - 13), i));

const ESTATISTICAS = {
  tickets: {
    total: 128,
    open: 24,
    in_progress: 17,
    awaiting: 12,
    resolved: 43,
    closed: 30,
    cancelled: 2,
    by_priority_critical: 9,
    by_priority_high: 31,
    by_priority_medium: 58,
    by_priority_low: 30,
  },
  surveys: { total: 37, average_rating: 8.4 },
  sla: { response_breached: 6, resolve_breached: 3 },
};

const CONFORMIDADE = [
  { priority: "critical", total: 9, breached: 2, compliance_rate: 77.8 },
  { priority: "high", total: 31, breached: 4, compliance_rate: 87.1 },
  { priority: "medium", total: 58, breached: 3, compliance_rate: 94.8 },
  { priority: "low", total: 30, breached: 0, compliance_rate: 100 },
];

const RELATORIO = {
  period_days: 30,
  total_tickets: 128,
  tickets_by_day: porDia((date, i) => ({ date, count: 4 + ((i * 5) % 9) })),
  tickets_by_category: [
    { category: "hardware", count: 34 },
    { category: "software", count: 28 },
    { category: "network", count: 21 },
    { category: "email", count: 18 },
    { category: "access", count: 15 },
    { category: "general", count: 12 },
  ],
  sla_compliance: CONFORMIDADE,
  // As dez notas povoadas: é esta série que a E19 vai repintar em três
  // faixas, e uma foto com metade das barras zeradas não mostraria o degrau.
  csat_distribution: [1, 0, 2, 1, 3, 2, 5, 8, 9, 6].map((count, i) => ({
    rating: i + 1,
    count,
  })),
  csat_average: 8.4,
  recommend_average: 8.9,
  avg_resolution_by_priority: [
    { priority: "critical", avg_hours: 3.2 },
    { priority: "high", avg_hours: 9.6 },
    { priority: "medium", avg_hours: 21.4 },
    { priority: "low", avg_hours: 48.1 },
  ],
  avg_first_response_by_priority: [
    { priority: "critical", avg_hours: 0.6 },
    { priority: "high", avg_hours: 1.8 },
    { priority: "medium", avg_hours: 4.3 },
    { priority: "low", avg_hours: 7.9 },
  ],
  csat_by_day: porDia((date, i) => ({
    date,
    avg_rating: 7 + ((i * 3) % 7) / 3,
    count: 1 + (i % 4),
  })),
  tickets_by_product: [
    { product_name: "Phoebus ERP", count: 41 },
    { product_name: "Portal do Cliente", count: 27 },
    { product_name: "Coletor de Ponto", count: 19 },
    { product_name: "Sem produto", count: 12 },
  ],
  tickets_by_weekday: [26, 31, 24, 22, 19, 4, 2].map((count, i) => ({
    weekday: i + 1,
    count,
  })),
  tickets_by_hour: Array.from({ length: 24 }, (_, hour) => ({
    hour,
    count: hour >= 8 && hour <= 18 ? 4 + ((hour * 3) % 11) : hour % 3,
  })),
  oldest_open_tickets: CHAMADOS.slice(0, 5).map((t, i) => ({
    ticket_id: t.id,
    protocol: t.protocol,
    title: t.title,
    priority: t.priority,
    category: t.category,
    status: t.status,
    age_hours: 30 + i * 18,
    sla_breached: i === 3,
    assignee_name: t.assignee_name,
  })),
  technicians_dist: TECNICOS.map(({ name }, i) => ({
    technician_name: name,
    total: [42, 31, 24][i],
    resolved: [30, 22, 15][i],
    open_count: [12, 9, 9][i],
  })),
  reopened_count: 7,
  reopen_rate: 5.5,
  comparison: {
    total_tickets: 112,
    csat_average: 8.1,
    sla_compliance: CONFORMIDADE,
  },
};

const RELATORIO_TECNICOS = {
  period_days: 30,
  technicians: TECNICOS.map(({ id, name }, i) => ({
    technician_id: id,
    technician_name: name,
    total_assigned: [42, 31, 24][i],
    resolved: [30, 22, 15][i],
    open_count: [12, 9, 9][i],
    sla_breached: [2, 1, 3][i],
    sla_compliance_rate: [95.2, 96.8, 87.5][i],
    avg_resolution_hours: [11.4, 14.9, 19.2][i],
    csat_average: [8.7, 8.2, 7.6][i],
    csat_count: [14, 11, 9][i],
  })),
};

const RELATORIO_TECNICO = {
  period_days: 30,
  technician_id: TECNICOS[0].id,
  technician_name: TECNICOS[0].name,
  total_assigned: 42,
  resolved: 30,
  in_progress: 7,
  open_count: 12,
  sla_breached: 2,
  sla_compliance_rate: 95.2,
  avg_resolution_hours: 11.4,
  csat_average: 8.7,
  csat_count: 14,
  tickets_by_day: porDia((date, i) => ({ date, count: 1 + ((i * 2) % 5) })),
};

const USUARIOS = [
  ["Rickelme David", "rickelme@exemplo.invalid", "admin", "active"],
  ["Erick Dantas", "erick@exemplo.invalid", "technician", "active"],
  ["Marina Lopes", "marina@exemplo.invalid", "technician", "active"],
  ["Ana Paula", "ana@exemplo.invalid", "client", "active"],
  ["João Bastos", "joao@exemplo.invalid", "client", "inactive"],
].map(([name, email, role, status], i) => ({
  id: `u-${i + 1}`,
  name,
  email,
  role,
  status,
  phone: "(11) 90000-0000",
  department: role === "client" ? null : "Suporte",
  avatar_url: null,
  last_login: emHoras(-3 - i * 7),
  lgpd_consent: true,
  lgpd_consent_at: emDias(-120),
  company_name: role === "client" ? "Matriz Demonstração" : null,
  cnpj: role === "client" ? "00.000.000/0001-00" : null,
  company_cep: null,
  company_address: null,
  company_city: role === "client" ? "São Paulo" : null,
  company_state: role === "client" ? "SP" : null,
  onboarding_completed: true,
  created_at: emDias(-300 + i * 10),
  updated_at: emDias(-2),
}));

const AUDITORIA = [
  ["create", "ticket", "Ana Paula"],
  ["status_change", "ticket", "Erick Dantas"],
  ["update", "user", "Rickelme David"],
  ["login", "user", "Marina Lopes"],
  ["export", "report", "Rickelme David"],
  ["delete", "tag", "Rickelme David"],
].map(([action, entity_type, user_name], i) => ({
  id: `log-${i + 1}`,
  user_id: `u-${i + 1}`,
  user_name,
  action,
  entity_type,
  entity_id: `e-${i + 1}`,
  old_data: action === "update" ? { role: "client" } : null,
  new_data: action === "update" ? { role: "technician" } : null,
  ip_address: "203.0.113.10",
  user_agent: "Mozilla/5.0 (captura de demonstração)",
  created_at: emHoras(-2 - i * 5),
}));

const GRUPOS = [
  ["Matriz e filiais", "Empresas do grupo principal", 4],
  ["Parceiros", "Revendas e integradores", 2],
  ["Órgãos públicos", null, 1],
].map(([name, description, company_count], i) => ({
  id: `g-${i + 1}`,
  name,
  description,
  notes: null,
  company_count,
  created_at: emDias(-200),
  updated_at: emDias(-3),
}));

const CONFIGS_DE_SLA = ["critical", "high", "medium", "low"].map(
  (level, i) => ({
    id: `sla-${i + 1}`,
    level,
    response_time_hours: [1, 4, 8, 24][i],
    resolve_time_hours: [4, 24, 48, 120][i],
    warning_threshold: 80,
    is_active: true,
    created_at: emDias(-300),
    updated_at: emDias(-30),
  }),
);

const EVENTOS = [
  ["Manutenção programada do servidor", "deadline", "#ef4444", -3, -3],
  ["Treinamento do módulo fiscal", "training", "#10b981", 1, 1],
  ["Reunião de acompanhamento", "meeting", "#6366f1", 4, 4],
  ["Semana de inventário", "event", "#f59e0b", 8, 12],
].map(([title, event_type, color, de, ate], i) => ({
  id: `ev-${i + 1}`,
  title,
  description: "Evento de demonstração.",
  event_type,
  color,
  start_date: `${diaDoMes(de)}T00:00:00Z`,
  end_date: `${diaDoMes(ate)}T23:59:59Z`,
  created_by: "u-demo",
  creator_name: "Rickelme David",
  created_at: emDias(-10),
  updated_at: emDias(-10),
}));

const PRODUTOS = [
  ["Phoebus ERP", "Gestão integrada", "4.2.1", true],
  ["Portal do Cliente", "Autoatendimento na web", "2.0.0", true],
  ["Coletor de Ponto", "Registro de jornada", "1.8.3", false],
].map(([name, description, version, is_active], i) => ({
  id: `p-${i + 1}`,
  name,
  description,
  version,
  is_active,
}));

const EQUIPAMENTOS = [
  ["Notebook da recepção", "NB-2291", "Dell Latitude 5440", "Recepção"],
  ["Impressora do 2º andar", "IMP-0043", "HP LaserJet M428", "2º andar"],
  ["Coletor da portaria", "COL-0117", "Henry Prisma SF", "Portaria"],
].map(([name, serial_number, model, location], i) => ({
  id: `eq-${i + 1}`,
  product_id: PRODUTOS[i % PRODUTOS.length].id,
  owner_id: "u-demo",
  owner_name: "Rickelme David",
  owner_email: "demo@exemplo.invalid",
  company_name: "Matriz Demonstração",
  company_cnpj: "00.000.000/0001-00",
  name,
  serial_number,
  model,
  description: null,
  location,
  is_active: true,
  created_at: emDias(-90 - i * 10),
  updated_at: emDias(-5),
}));

const ETIQUETAS = [
  ["Urgente", "#ef4444"],
  ["Aguardando peça", "#f97316"],
  ["Retorno agendado", "#3b82f6"],
  ["Garantia", "#10b981"],
  ["Interno", "#64748b"],
].map(([name, color], i) => ({
  id: `tag-${i + 1}`,
  name,
  color,
  created_by: "u-demo",
  created_at: emDias(-150 + i * 12),
}));

const RESPOSTAS_RAPIDAS = [
  ["/ola", "Saudação inicial", "Olá! Sou o técnico responsável pelo seu chamado."],
  ["/prazo", "Prazo de atendimento", "O prazo previsto para este chamado é de 24 horas úteis."],
  ["/aguardando", "Aguardando o cliente", "Estamos aguardando o seu retorno para prosseguir."],
  ["/encerrar", "Encerramento", "Como o problema foi resolvido, vou encerrar este chamado."],
].map(([shortcut, title, content], i) => ({
  id: `qr-${i + 1}`,
  shortcut,
  title,
  content,
  is_active: i !== 3,
  created_by: "u-demo",
  created_at: emDias(-80 + i * 9),
  updated_at: emDias(-4),
}));

const NOTIFICACOES = [
  ["sla_breached", "SLA estourado", "O chamado HS-2026-0004 passou do prazo de resposta.", false],
  ["ticket_assigned", "Chamado atribuído", "O chamado HS-2026-0003 foi atribuído a você.", false],
  ["chat_message", "Nova mensagem", "Ana Paula respondeu no chamado HS-2026-0001.", true],
  ["ticket_resolved", "Chamado resolvido", "O chamado HS-2026-0006 foi marcado como resolvido.", true],
  ["satisfaction_survey", "Pesquisa de satisfação", "Avalie o atendimento do chamado HS-2026-0007.", true],
].map(([type, title, message, read], i) => ({
  id: `n-${i + 1}`,
  user_id: "u-demo",
  type,
  title,
  message,
  data: { ticket_id: `t-${i + 1}` },
  read,
  read_at: read ? emHoras(-1) : null,
  email_sent: true,
  created_at: emHoras(-1 - i * 4),
}));

const ARTIGOS = [
  [
    "Como abrir um chamado",
    "geral",
    "published",
    "## Antes de abrir\n\nSepare o **protocolo** do equipamento e uma descrição do que\naconteceu.\n\n1. Entre em *Tickets* e clique em **Novo chamado**.\n2. Escolha a categoria e a prioridade.\n3. Anexe uma foto da tela, se houver.\n\n> Chamado com descrição completa costuma ser resolvido no mesmo dia.\n\n| Prioridade | Prazo de resposta |\n| --- | --- |\n| Crítica | 1 hora |\n| Alta | 4 horas |\n| Média | 8 horas |\n",
  ],
  [
    "Redefinir a senha de acesso",
    "acesso",
    "published",
    "Use o link **Esqueci minha senha** na tela de entrada.\n",
  ],
  [
    "Configurar a impressora de rede",
    "hardware",
    "draft",
    "Passo a passo da instalação do driver.\n",
  ],
].map(([title, category, status, content], i) => ({
  id: `kb-${i + 1}`,
  title,
  content,
  slug: `artigo-${i + 1}`,
  category,
  tags: ["passo a passo", "suporte"],
  status,
  author_id: "u-demo",
  author_name: "Rickelme David",
  view_count: 120 - i * 37,
  helpful: 18 - i * 5,
  not_helpful: i,
  created_at: emDias(-60 - i * 15),
  updated_at: emDias(-3 - i),
  products: [],
}));

const COMENTARIOS = [
  ["Ana Paula", "client", "Ajudou bastante, obrigada!"],
  ["Erick Dantas", "technician", "Acrescentei o prazo da prioridade crítica."],
].map(([author_name, author_role, content], i) => ({
  id: `c-${i + 1}`,
  article_id: "kb-1",
  author_id: `u-${i + 1}`,
  author_name,
  author_role,
  content,
  parent_id: null,
  created_at: emHoras(-6 - i * 20),
  updated_at: emHoras(-6 - i * 20),
  replies: [],
}));

/**
 * Resposta por rota. A chave é testada contra o caminho da API, e **a ordem
 * importa**: a primeira que casa responde.
 *
 * Os sufixos de `/tickets/<id>/...` vêm TODOS antes do `/tickets` solto, que
 * não tem âncora e casa com qualquer coisa abaixo dele. Foi assim que o
 * `/tickets/t-1/messages` recebeu a LISTA DE CHAMADOS como se fossem mensagens
 * — e a tela de detalhe caiu inteira, com o erro apontando para o seletor que
 * faltou em vez de para a resposta errada.
 *
 * A regra que sai daí, e que vale para todo padrão acrescentado depois:
 * **específico antes de genérico**, e padrão novo e largo por último.
 */
const respostas = (papel) => [
  // ── quem entrou ───────────────────────────────────────────────────────
  [/\/users\/me$/, usuario(papel)],
  // `{ items: [...] }`, e nao o array: os dois servicos devolvem
  // `data.items`. Dar array faz `.items` vir indefinido e o `.map` seguinte
  // derruba a arvore inteira — foi assim que a tela de detalhe saiu vazia,
  // com a sonda dizendo "nao montou" e nada dizendo por que.
  [/\/users\/technicians/, { items: TECNICOS }],
  // Ancorado: sem o `$` este padrão engoliria `/users/me` e `/users/<id>`,
  // e a tela de perfil receberia a lista de usuários no lugar do usuário.
  [
    /\/users$/,
    { items: USUARIOS, total: USUARIOS.length, limit: 20, offset: 0 },
  ],

  // ── chamados ──────────────────────────────────────────────────────────
  [/\/tickets\/[^/]+\/history/, { items: [] }],
  [/\/tickets\/[^/]+\/attachments/, { items: [] }],
  [/\/tickets\/[^/]+\/notes/, []], // este devolve array mesmo
  [/\/tickets\/[^/]+\/survey/, null],
  [/\/tickets\/[^/]+\/messages/, { items: [] }],
  [/\/tickets\/[^/]+$/, CHAMADOS[0]],
  [/\/tickets/, lista],

  // ── painéis e relatórios ──────────────────────────────────────────────
  //
  // `technicians` ANTES de `technician`: o segundo não tem âncora e casa com
  // o caminho do primeiro. Invertidos, o painel do técnico receberia a LISTA
  // de técnicos onde espera o detalhe de um — a mesma armadilha do
  // `/tickets/t-1/messages`, com outro nome.
  [/\/dashboard\/stats/, ESTATISTICAS],
  [/\/dashboard\/reports\/technicians/, RELATORIO_TECNICOS],
  [/\/dashboard\/reports\/technician/, RELATORIO_TECNICO],
  [/\/dashboard\/reports/, RELATORIO],

  // ── base de conhecimento ──────────────────────────────────────────────
  [
    /\/kb\/articles\/[^/]+\/comments/,
    { items: COMENTARIOS, total: COMENTARIOS.length },
  ],
  [/\/kb\/articles\/[^/]+$/, ARTIGOS[0]],
  [
    /\/kb\/articles/,
    { items: ARTIGOS, total: ARTIGOS.length, limit: 20, offset: 0 },
  ],

  // ── administração ─────────────────────────────────────────────────────
  //
  // `/groups` e `/sla-configs` devolvem o ARRAY CRU, e não `{ items }`:
  // `listGroups()` e `getSLAConfigs()` leem `data` direto. Embrulhar os dois
  // derruba as duas telas com `groups.filter is not a function`.
  [/\/groups/, GRUPOS],
  [/\/sla-configs/, CONFIGS_DE_SLA],
  [
    /\/audit-logs/,
    { items: AUDITORIA, total: AUDITORIA.length, limit: 50, offset: 0 },
  ],
  [/\/calendar\/events/, { items: EVENTOS, total: EVENTOS.length }],
  [
    /\/quick-replies/,
    { items: RESPOSTAS_RAPIDAS, total: RESPOSTAS_RAPIDAS.length },
  ],
  [
    /\/notifications/,
    {
      items: NOTIFICACOES,
      total: NOTIFICACOES.length,
      unread: NOTIFICACOES.filter((n) => !n.read).length,
      limit: 20,
      offset: 0,
    },
  ],
  [/\/tags/, { items: ETIQUETAS, total: ETIQUETAS.length }],
  [
    /\/products/,
    { items: PRODUTOS, total: PRODUTOS.length, limit: 20, offset: 0 },
  ],
  [
    /\/equipment/,
    { items: EQUIPAMENTOS, total: EQUIPAMENTOS.length, limit: 20, offset: 0 },
  ],
];

/**
 * fase, tela, rota, papel, seletor que SÓ existe nela, largura, altura.
 *
 * O seletor é a trava de conteúdo, e um seletor genérico é pior que nenhum:
 * ele passa na tela errada. Por isso quase todos casam o texto do `<h1>` da
 * própria tela — `:text-is()` é do motor de CSS do Playwright e compara o
 * texto inteiro, não um pedaço.
 */
const TELAS = [
  // ── Fase 11 — Checkpoint 3 ────────────────────────────────────────────
  ["11", "painel", "/", "client", "table", 1366, 900],
  ["11", "lista", "/tickets", "admin", "[aria-labelledby^='coluna-']", 1366, 900],
  ["11", "formulario", "/tickets/new", "client", "fieldset", 1366, 1200],
  ["11", "detalhe", "/tickets/t-1", "admin", "nav[aria-label='Trilha']", 1366, 1200],
  // O quadro rola na horizontal, e a 1366 so cabem quatro das seis colunas —
  // que e o que um usuario nessa largura de fato ve, e por isso a captura de
  // 1366 fica. Esta segunda existe para a EVIDENCIA: as seis colunas juntas,
  // com os dois "Aguardando" no mesmo ambar.
  ["11", "lista-larga", "/tickets", "admin", "[aria-labelledby^='coluna-']", 2100, 900],

  // ── Fase 16 ───────────────────────────────────────────────────────────
  //
  // Os dois primeiros são a MESMA rota: `/` monta o painel do papel de quem
  // entrou. O `<h1>` dos dois diz "Dashboard", então o seletor não pode ser
  // ele — cada um casa um bloco que só existe no seu.
  ["16", "painel-admin", "/", "admin", "[aria-label='Distribuição de status']"],
  ["16", "painel-tecnico", "/", "technician", 'text="Meus tickets ativos"'],
  ["16", "relatorios", "/reports", "admin", 'h1:text-is("Relatórios")'],
  ["16", "grupos", "/grupos", "admin", 'h1:text-is("Grupos")'],
  ["16", "auditoria", "/audit-logs", "admin", 'h1:text-is("Logs de Auditoria")'],
  ["16", "produtos", "/products", "admin", 'h1:text-is("Produtos")'],
  ["16", "usuarios", "/users", "admin", 'h1:text-is("Usuários")'],
  ["16", "sla", "/sla-config", "admin", 'h1:text-is("Configurações de SLA")'],
  ["16", "agenda", "/agenda", "admin", 'h1:text-is("Agenda")'],
  ["16", "etiquetas", "/etiquetas", "admin", 'h1:text-is("Etiquetas")'],
  ["16", "respostas-rapidas", "/respostas-rapidas", "admin", 'h1:text-is("Respostas Rápidas")'],
  ["16", "notificacoes", "/notifications", "admin", 'h1:text-is("Notificações")'],
  ["16", "kb-lista", "/kb", "admin", 'h1:text-is("Base de Conhecimento")'],
  ["16", "kb-artigo", "/kb/kb-1", "admin", 'h1:text-is("Como abrir um chamado")'],
  ["16", "kb-novo", "/kb/new", "admin", 'h1:text-is("Novo artigo")'],
  // As duas telas de EDICAO reusam os componentes de criacao, com o h1
  // trocado. Sao fotos diferentes porque o que interessa nelas e o estado
  // PREENCHIDO: o formulario vazio ja esta fotografado, e um campo com valor
  // tem borda, rotulo e botao habilitado que o vazio nao tem.
  //
  // Nao precisaram de mock novo -- /kb/articles/<id> e /tickets/<id> ja
  // respondem com o primeiro item de cada lista, entao os dois vem cheios.
  ["16", "kb-editar", "/kb/kb-1/edit", "admin", 'h1:text-is("Editar artigo")'],
  ["16", "chamado-editar", "/tickets/t-1/edit", "admin", 'h1:text-is("Editar chamado")'],
  // As duas do CLIENTE. `/equipment` é de todos os papéis, mas a tela se
  // chama "Meus equipamentos" e é do cliente que ela fala.
  ["16", "perfil", "/profile", "client", 'h1:text-is("Meu perfil")'],
  ["16", "equipamentos", "/equipment", "client", 'h1:text-is("Meus equipamentos")'],
  // `/onboarding` só existe para o cliente que ainda não se cadastrou: o
  // `OnboardingOnlyRoute` devolve todo o resto para `/`.
  ["16", "onboarding", "/onboarding", "client-novo", 'h2:text-is("Sobre sua empresa")'],
];

/**
 * Espera o gráfico parar de se mexer.
 *
 * A data cravada deixou 40 das 46 fotos idênticas byte a byte entre duas
 * execuções. As 6 que sobraram são as telas com Recharts — e a causa não é
 * data nenhuma: ele **anima na montagem**, e o disparo pegava um quadro
 * diferente a cada vez.
 *
 * Duas fontes de instabilidade, e a segunda só apareceu depois de a primeira
 * ser eliminada. É por isso que a prova é **refotografar e comparar bytes**, e
 * não "a sonda passou": passar diz que a foto saiu, não que ela é a mesma.
 *
 * A técnica é a da trava de pixel: ler, esperar, reler, e só seguir quando
 * duas leituras seguidas coincidirem. O que se lê é o conjunto dos traçados
 * do SVG — se um ponto ainda está subindo, o `d` muda.
 *
 * Tela sem gráfico sai na primeira leitura, sem custo.
 */
async function assentarGrafico(page, onde) {
  // ⚠️ Lê TODAS as formas, e não só `path` — a primeira versão lia só ele.
  //
  // A medição que fechou isto: no `painel-tecnico` sobravam **2.948 pixels**
  // diferentes numa região de 14×69 px, com variação de cor de **232** num
  // canal. Antialias move centenas de pixels com variação de poucas unidades;
  // 232 é algo que **aparece ou se move**.
  //
  // Era o ponto da série — o Recharts desenha ponto como `<circle>`, e a trava
  // olhava só `<path>`. Os traçados assentavam, a trava dava por encerrado, e o
  // ponto ainda estava a caminho.
  //
  // A lição é a mesma de sempre, uma camada acima: a régua estava certa **no
  // que media** e incompleta **no que incluía**. Aqui a lista de elementos era
  // o buraco, como antes foi a lista de implementadores da tabela de contrato.
  const ler = () =>
    page.evaluate(() =>
      Array.from(
        document.querySelectorAll(
          ".recharts-surface path, .recharts-surface circle, " +
            ".recharts-surface rect, .recharts-surface line",
        ),
      )
        .map((el) =>
          ["d", "cx", "cy", "r", "x", "y", "width", "height", "x1", "y1", "x2", "y2"]
            .map((a) => el.getAttribute(a) ?? "")
            .join(","),
        )
        .join("|"),
    );

  // ⚠️ Leitura vazia significa DUAS coisas, e a primeira versão desta trava as
  // colapsava numa só — o defeito que a sessão inteira vinha achando, cometido
  // aqui dentro:
  //
  //   a) a tela não tem gráfico nenhum        → sair é o certo
  //   b) o gráfico ainda não renderizou nada  → sair é o defeito
  //
  // Com `if (!anterior) return`, o caso (b) saía na hora e a tela era
  // fotografada no meio da animação. Foi por isso que `painel-tecnico` e
  // `relatorios` continuaram mudando entre execuções mesmo com a trava posta:
  // ela não estava errada, estava **desligando sozinha**.
  //
  // Quem separa os dois é o CONTÊINER: o Recharts monta o
  // `.recharts-responsive-container` antes de ter traçado. Se ele existe, há
  // gráfico e é preciso esperar; se não existe, não há nada a esperar.
  // ── Antes de tudo: a FONTE ──────────────────────────────────────────
  //
  // O `ResponsiveContainer` do Recharts mede o contêiner e desenha em cima
  // dessa largura. Se a Plus Jakarta Sans ainda não carregou, o texto ao redor
  // tem outras métricas, o leiaute assenta em outro lugar por FRAÇÃO de pixel,
  // e a linha do gráfico cai num antialias diferente.
  //
  // Foi o que sobrou depois da data e da animação: quatro fotos com **458
  // pixels** de diferença, com variação de 3 a 6 unidades de cor — assinatura
  // de antialias, não de quadro de animação. Medido decodificando os dois PNG
  // e comparando linha a linha, em vez de supor.
  //
  // `document.fonts.ready` resolve quando todas as faces em uso terminaram de
  // carregar. É barato e vale para qualquer tela, com gráfico ou sem.
  // `.then(() => undefined)` porque `document.fonts.ready` resolve com o
  // FontFaceSet, e o Playwright tenta SERIALIZAR o valor de volta. Devolver
  // undefined mantém a espera e não carrega objeto nenhum pela ponte.
  await page.evaluate(() => document.fonts.ready.then(() => undefined));

  const temGrafico = await page
    .locator(".recharts-responsive-container")
    .count();
  if (!temGrafico) return;

  // O contêiner existe, então esperamos o primeiro traçado APARECER antes de
  // começar a medir se ele parou de mudar. Sem isso, a comparação começaria
  // entre dois vazios e daria "assentado" de imediato — a mesma armadilha, um
  // passo adiante.
  // ⚠️ Contêiner sem forma dentro NÃO é erro, e eu tratei como se fosse.
  //
  // A primeira versão desta espera lançava exceção quando o contêiner existia e
  // nenhuma forma aparecia em 10s. Ela derrubou o `painel-tecnico`, que
  // capturava bem antes — e a razão é que **as duas situações são
  // indistinguíveis daqui**:
  //
  //   · o gráfico está vazio POR DESENHO (a tela mostra "sem dados"), e o
  //     contêiner do `ResponsiveContainer` fica lá, medindo espaço;
  //   · o gráfico quebrou.
  //
  // Errei o mesmo erro que esta trava existe para consertar, no sentido
  // contrário: antes eu colapsava dois estados em "seguir", e passei a
  // colapsá-los em "falhar". Um estado sem sinal próprio não vira erro só
  // porque a alternativa incomoda.
  //
  // Enquanto não houver como separá-los — um marcador na tela de vazio
  // resolveria —, a espera é limitada e o silêncio é aceito: se nenhuma forma
  // aparecer, não há animação a esperar, e a foto sai. Fica registrado no
  // CHECKPOINT-4 como lacuna conhecida.
  const temForma = await page
    .waitForSelector(
      ".recharts-surface path, .recharts-surface circle, .recharts-surface rect",
      { timeout: 5_000 },
    )
    .then(() => true)
    .catch(() => false);
  if (!temForma) return;

  let anterior = await ler();

  // O padrão do Recharts é 1500ms de animação. Doze tentativas de 250ms dão
  // folga de sobra, e o laço sai assim que assentar — o custo real é o tempo
  // que a animação leva, não o teto.
  for (let i = 0; i < 12; i++) {
    await page.waitForTimeout(250);
    const agora = await ler();
    if (agora === anterior) return;
    anterior = agora;
  }
  throw new Error(
    `${onde}o gráfico não assentou em 3s: o traçado do SVG ainda muda entre ` +
      `leituras. Fotografar agora daria uma imagem que a próxima execução não ` +
      `reproduz — e evidência que muda entre execuções não é evidência.`,
  );
}
const fugas = [];
const barradas = [];

const FILTRO = process.argv.slice(2).filter((a) => !a.startsWith("-"));
const pedida = (rotulo) =>
  FILTRO.length === 0 || FILTRO.some((termo) => rotulo.includes(termo));

function ehLocal(url) {
  try {
    const u = new URL(url);
    if (u.protocol === "data:" || u.protocol === "blob:") return true;
    return u.host === new URL(BASE).host;
  } catch {
    return false;
  }
}

/**
 * `semResposta` é o balde DESTA captura, e não o global: com 22 telas, uma
 * chamada não prevista na tela anterior apareceria na mensagem de erro da
 * seguinte e mandaria investigar a tela errada.
 */
async function instalarBloqueio(context, papel, semResposta) {
  const RESPOSTAS = respostas(papel);
  await context.route("**/*", async (route) => {
    const url = route.request().url();

    if (/\/api\//.test(url)) {
      const caminho = new URL(url).pathname;
      for (const [padrao, corpo] of RESPOSTAS) {
        if (padrao.test(caminho)) {
          return route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(corpo),
          });
        }
      }
      // Chamada de API que este script não previu. Denuncia, e responde na
      // forma que a maioria dos serviços espera — `{ items: [] }`, e não `{}`.
      //
      // Não é conveniência: `{}` fazia `data.items` vir indefinido, e a tela
      // caía inteira. O `ChatPanel` do detalhe morreu assim, e a captura
      // parou com "a tela não montou" enquanto a causa estava DUAS LINHAS
      // ACIMA, na lista de barradas que ninguém tinha lido ainda.
      barradas.push(caminho);
      semResposta.add(caminho);
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], total: 0 }),
      });
    }

    if (ehLocal(url)) return route.continue();

    if (/fonts\.(googleapis|gstatic)\.com/.test(url)) {
      barradas.push(url);
      return route.abort();
    }

    fugas.push(url);
    return route.abort();
  });
}

/** Uma captura: uma tela, um tema. Devolve o caminho do arquivo. */
async function fotografar(browser, tela, tema) {
  const [fase, nome, rota, papel, seletor, largura = 1366, altura = 900] = tela;
  const semResposta = new Set();

  const context = await browser.newContext({
    viewport: { width: largura, height: altura },
    deviceScaleFactor: 2,
    colorScheme: tema === "escuro" ? "dark" : "light",
  });
  try {
    await instalarBloqueio(context, papel, semResposta);
    await context.addInitScript(
      ([tk, rf, tema]) => {
        try {
          window.localStorage.setItem("helphs_access_token", tk);
          window.localStorage.setItem("helphs_refresh_token", rf);
          window.localStorage.setItem("helphs-theme", tema);
        } catch {
          /* modo anônimo: o colorScheme do contexto já cobre */
        }
      },
      ["token-de-mentira", "refresh-de-mentira", tema === "escuro" ? "dark" : "light"],
    );

    const page = await context.newPage();
    const onde = `${fase}/${nome}/${tema}: `;

    // Erro de JavaScript derruba a arvore inteira e deixa o `<body>`
    // VAZIO — e uma sonda que so olha seletor diz "nao montou" sem dizer
    // por que. Guardado aqui para entrar na mensagem.
    const erros = [];
    page.on("pageerror", (e) => erros.push(String(e.message).slice(0, 160)));
    await page.goto(`${BASE}${rota}`, { waitUntil: "networkidle" });

    await conferirProduto(page, onde);
    await page.waitForSelector(seletor, { timeout: 15_000 }).catch(async () => {
      // A mensagem carrega o que a tela MOSTROU e o que o script não
      // previu. Sem isso, "não montou" manda investigar o seletor — e a
      // causa costuma ser uma resposta de API que ninguém escreveu.
      const texto = (await page.locator("body").innerText().catch(() => ""))
        .replace(/\s+/g, " ")
        .slice(0, 240);
      throw new Error(
        `${onde}a tela não montou: nenhum \`${seletor}\` em ${rota}.\n` +
          `  a tela mostra: ${texto || "(vazia)"}\n` +
          `  chamadas de API sem resposta prevista: ` +
          `${[...semResposta].join(", ") || "nenhuma"}\n` +
          `  erros de JavaScript: ${erros.join(" | ") || "nenhum"}`,
      );
    });
    await conferirPixel(page, tema, onde);
    await assentarGrafico(page, onde);

    if (erros.length > 0) {
      throw new Error(
        `${onde}a tela montou, mas houve erro de JavaScript: ${erros.join(" | ")}\n` +
          `  Uma foto de uma tela que soltou exceção não vale como evidência.`,
      );
    }

    const saida = saidaDaFase(fase);
    await mkdir(saida, { recursive: true });
    const arquivo = path.join(saida, `helphs-${nome}-${tema}-${largura}.png`);
    await page.screenshot({ path: arquivo, fullPage: true });
    return arquivo;
  } finally {
    await context.close();
  }
}

/**
 * Uma tela que falha NÃO interrompe as outras: com 22 telas, parar na primeira
 * esconde as outras vinte e uma e transforma o laço de conserto em uma
 * execução por chamada faltante. O que não muda é o veredito — qualquer falha
 * derruba a execução inteira no fim, e a foto que falta continua faltando.
 */
async function capturar() {
  const falhas = [];
  const feitas = [];
  const browser = await chromium.launch();
  try {
    for (const tela of TELAS) {
      for (const tema of ["claro", "escuro"]) {
        const rotulo = `${tela[0]}/${tela[1]}/${tema}`;
        if (!pedida(rotulo)) continue;
        try {
          const arquivo = await fotografar(browser, tela, tema);
          feitas.push(arquivo);
          console.log(`  ✔ ${path.basename(arquivo)}`);
        } catch (e) {
          falhas.push(String(e.message));
          console.error(`  ✖ ${rotulo}`);
        }
      }
    }
  } finally {
    await browser.close();
  }
  return { falhas, feitas };
}

const quantas = TELAS.flatMap((t) =>
  ["claro", "escuro"].map((tema) => `${t[0]}/${t[1]}/${tema}`),
).filter(pedida).length;

console.log(
  `Capturando ${quantas} foto(s) de ${BASE} — toda a rede está interceptada.` +
    (FILTRO.length ? `\nFiltro: ${FILTRO.join(", ")}` : ""),
);
const { falhas, feitas } = await capturar();

const unicas = [...new Set(barradas)];
console.log(`\nRequisições barradas de propósito (${unicas.length}):`);
for (const u of unicas) console.log(`  · ${u}`);

for (const fase of [...new Set(TELAS.map((t) => t[0]))]) {
  const saida = saidaDaFase(fase);
  const arquivos = await readdir(saida).catch(() => []);
  console.log(
    `\n${arquivos.filter((f) => f.endsWith(".png")).length} screenshot(s) em ${saida}`,
  );
}

let ruim = false;

if (falhas.length > 0) {
  console.error(`\n✖ ${falhas.length} captura(s) falharam:`);
  for (const f of falhas) console.error(`  · ${f}`);
  ruim = true;
}

if (fugas.length > 0) {
  console.error(`\n✖ ${fugas.length} requisição(ões) escaparam do bloqueio:`);
  for (const u of [...new Set(fugas)]) console.error(`  · ${u}`);
  console.error(
    "\nOs screenshots NÃO valem como evidência: algo tentou sair para a rede.",
  );
  ruim = true;
}

if (unicas.some((u) => u.startsWith("/api"))) {
  console.error(
    `\n✖ chamadas de API sem resposta prevista — a tabela \`respostas()\` ` +
      `não as cobre, e a tela foi fotografada com o corpo genérico:`,
  );
  for (const u of unicas.filter((u) => u.startsWith("/api"))) {
    console.error(`  · ${u}`);
  }
  ruim = true;
}

if (ruim) process.exit(1);

console.log(
  `\n✔ ${feitas.length} foto(s), nenhuma requisição escapou, nenhuma chamada ` +
    `sem resposta prevista. Nada saiu para a rede.`,
);
