export const APP_VERSION = "v1.2.0";

export type EntryType = "novidade" | "corrigido" | "melhoria";

export interface ChangelogEntry {
  type: EntryType;
  text: string;
}

export interface ChangelogVersion {
  version: string;
  date: string;
  entries: ChangelogEntry[];
}

export const CHANGELOG: ChangelogVersion[] = [
  {
    version: "v1.2.0",
    date: "05/08/2026",
    entries: [
      { type: "novidade", text: "Artigos da Base de Conhecimento agora indicam a quais produtos se aplicam." },
      { type: "novidade", text: "No chamado, os artigos sugeridos consideram o produto e a categoria do ticket." },
      { type: "novidade", text: "Cliente passa a ver a aba Base de Conhecimento dentro do próprio chamado." },
      { type: "novidade", text: "Filtro por produto na listagem da Base de Conhecimento." },
      { type: "melhoria", text: "Qualquer técnico pode concluir e responder qualquer chamado, sem precisar ser o responsável." },
      { type: "melhoria", text: "Etiquetas do ticket: a selecionada agora fica com a cor cheia, bem mais visível." },
      { type: "melhoria", text: "Agenda com 16 cores padrão, organizadas em duas linhas." },
      { type: "corrigido", text: "Etiquetas com nome comprido não estouram mais a lateral do ticket." },
      { type: "corrigido", text: "Paginação mostrava \"Nenhum registros\" quando a lista estava vazia." },
    ],
  },
  {
    version: "v1.1.0",
    date: "04/08/2026",
    entries: [
      { type: "novidade", text: "Respostas rápidas no chat: digite \"/\" para inserir uma mensagem pronta, como no WhatsApp." },
      { type: "novidade", text: "Nova página Respostas Rápidas, em Gestão, para criar, editar e excluir as mensagens da equipe." },
      { type: "novidade", text: "Técnicos agora podem excluir comentários de clientes na Base de Conhecimento." },
      { type: "melhoria", text: "Agenda: 15 cores padrão para escolher no evento, no lugar do seletor de cor livre." },
      { type: "melhoria", text: "Mensagens de erro explicam o motivo do problema em vez de mostrar um aviso genérico." },
      { type: "melhoria", text: "CNPJ e CEP passaram a ser obrigatórios no cadastro da empresa, com validação dos dígitos." },
      { type: "corrigido", text: "Avaliação de satisfação: relatórios e gráficos mostravam a nota fora de escala e escondiam notas de 6 a 10." },
      { type: "corrigido", text: "Erros de ortografia e acentuação corrigidos em várias telas, incluindo a página de Grupos." },
      { type: "corrigido", text: "Atribuição de ticket agora avisa quando o chamado está fechado ou o técnico está inativo." },
      { type: "corrigido", text: "Formulário da Base de Conhecimento não abre mais em branco ao recarregar a página." },
    ],
  },
  {
    version: "v1.0.0",
    date: "20/05/2026",
    entries: [
      { type: "novidade", text: "Técnicos agora têm acesso completo a Grupos, Usuários, Produtos e Etiquetas." },
      { type: "melhoria", text: "Interface totalmente responsiva para mobile e tablet em todas as páginas." },
      { type: "melhoria", text: "Modais sem scroll indesejado nos formulários de criação e edição." },
      { type: "corrigido", text: "Sidebar mobile não era mais sobreposta pelo painel lateral de Grupos." },
      { type: "novidade", text: "Equipamentos: clique na linha ou no ícone de olho para abrir detalhes completos." },
      { type: "melhoria", text: "Audit Logs: tabela adaptada para tablet com layout em cards." },
    ],
  },
  {
    version: "v0.9.0",
    date: "01/05/2026",
    entries: [
      { type: "novidade", text: "Módulo de Audit Logs com rastreabilidade completa de todas as ações." },
      { type: "novidade", text: "Configuração de SLA por prioridade com alertas automáticos de vencimento." },
      { type: "novidade", text: "Etiquetas coloridas para classificação de tickets com seletor de cor." },
      { type: "melhoria", text: "Performance do dashboard com carregamento assíncrono de métricas." },
      { type: "corrigido", text: "Notificações em tempo real corrigidas no Safari." },
    ],
  },
  {
    version: "v0.8.0",
    date: "15/04/2026",
    entries: [
      { type: "novidade", text: "Base de Conhecimento com artigos, categorias e busca integrada." },
      { type: "novidade", text: "Gestão de grupos e empresas com vinculação de clientes." },
      { type: "novidade", text: "Suporte a modo escuro/claro com preferência salva por usuário." },
      { type: "novidade", text: "Relatórios com gráficos de tickets por período, prioridade e técnico." },
    ],
  },
];
