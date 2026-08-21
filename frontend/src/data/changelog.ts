export const APP_VERSION = "v1.8.0";

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
    version: "v1.8.0",
    date: "21/08/2026",
    entries: [
      { type: "novidade", text: "O cadastro de equipamento na tela de Produtos agora tem o campo de dono, com busca pelo nome do cliente — e um filtro para encontrar de uma vez os equipamentos que ainda estão sem dono." },
      { type: "melhoria", text: "O tema claro ou escuro passa a seguir a preferência do seu computador na primeira visita. Se você escolher um tema, a sua escolha continua valendo." },
      { type: "corrigido", text: "O prazo de primeira resposta não mostra mais \"Vencido\" em chamados que já foram respondidos — inclusive nos reabertos, onde o aviso ficava para sempre." },
      { type: "corrigido", text: "Não era possível cadastrar um equipamento cujo número de série já tivesse sido usado por outra empresa. Agora o número só precisa ser único dentro do seu próprio cadastro." },
      { type: "melhoria", text: "Ao tentar abrir um chamado que não é seu, a resposta passou a ser a mesma de um chamado que não existe — assim ninguém descobre, pelo endereço, quais chamados existem no sistema." },
      { type: "melhoria", text: "O indicador de primeira resposta do SLA passou a considerar apenas o que foi de fato dito ao cliente. Antes, assumir ou cancelar um chamado já contava como resposta, e responder pelo chat não contava — por isso os números de primeira resposta mudam a partir desta versão." },
    ],
  },
  {
    version: "v1.7.0",
    date: "19/08/2026",
    entries: [
      { type: "corrigido", text: "Contas que ficavam presas no aviso \"Confirme seu e-mail para ativar a conta\" voltaram a entrar normalmente: o aviso só aparecerá quando a confirmação por e-mail estiver de fato ativa." },
      { type: "melhoria", text: "Privacidade dos equipamentos: cada cliente agora vê somente os próprios aparelhos e números de série — equipamentos de outras empresas deixaram de aparecer nas consultas." },
      { type: "melhoria", text: "Proteção extra no acesso: várias tentativas seguidas de senha incorreta passam a ser bloqueadas temporariamente." },
      { type: "melhoria", text: "Entrar no sistema deixou de atrasar as demais operações em andamento nos horários de maior movimento." },
      { type: "melhoria", text: "Reforço de segurança na exibição dos artigos da Base de Conhecimento." },
      { type: "corrigido", text: "O aviso ao consultar um equipamento indisponível aparecia em inglês; agora está traduzido." },
    ],
  },
  {
    version: "v1.6.0",
    date: "10/08/2026",
    entries: [
      { type: "novidade", text: "Um chamado pode cobrir vários aparelhos: marque todos os equipamentos afetados sem precisar abrir um chamado para cada um." },
      { type: "melhoria", text: "A busca encontra o chamado pelo número de série de qualquer um dos aparelhos vinculados." },
      { type: "melhoria", text: "Os artigos sugeridos consideram todos os produtos envolvidos no chamado." },
    ],
  },
  {
    version: "v1.5.0",
    date: "07/08/2026",
    entries: [
      { type: "novidade", text: "Nova pergunta na pesquisa de satisfação: o quanto o cliente recomendaria a empresa, de 1 a 10." },
      { type: "novidade", text: "Card Recomendação nos relatórios, com a média das notas de recomendação do período." },
    ],
  },
  {
    version: "v1.4.0",
    date: "07/08/2026",
    entries: [
      { type: "novidade", text: "Reabrir chamado: se o problema voltar, o cliente reabre o chamado em até 5 dias úteis, sem perder o histórico." },
      { type: "novidade", text: "Chamados resolvidos passam sozinhos para Fechado depois de 3 dias úteis sem manifestação." },
      { type: "novidade", text: "O prazo para reabrir aparece dentro do chamado, junto da nota de resolução." },
      { type: "melhoria", text: "A pesquisa de satisfação deixou de ser enviada por e-mail: agora fica só na notificação e no próprio chamado." },
      { type: "melhoria", text: "Reabrir um chamado devolve um prazo de atendimento novo, em vez de trazê-lo de volta já vencido." },
      { type: "melhoria", text: "Histórico do chamado mostra \"Sistema\" no que foi feito automaticamente." },
      { type: "corrigido", text: "O chat ficava espremido, quase ilegível, quando a pesquisa de satisfação aparecia no chamado." },
      { type: "corrigido", text: "Tempo médio de resolução nos relatórios passou a contar até a resolução, sem somar os dias de espera até o fechamento." },
      { type: "corrigido", text: "Ao mudar o status para Resolvido, o cliente recebia o convite de avaliação duas vezes." },
    ],
  },
  {
    version: "v1.3.0",
    date: "06/08/2026",
    entries: [
      { type: "novidade", text: "Esqueci minha senha: agora dá para criar uma nova senha por um link enviado ao seu e-mail." },
      { type: "novidade", text: "Novos cadastros confirmam o e-mail por um link, garantindo que o endereço é válido." },
      { type: "novidade", text: "Anexos e fotos de perfil voltaram a funcionar: os arquivos agora ficam guardados no servidor." },
      { type: "novidade", text: "Botão de visualizar anexo: imagens, PDF e texto abrem direto no navegador, sem precisar baixar." },
      { type: "novidade", text: "Produto e equipamento do chamado aparecem na lateral e na aba Detalhes." },
      { type: "melhoria", text: "A busca de chamados também encontra pelo número de série do equipamento." },
      { type: "melhoria", text: "Aba Detalhes reúne categoria, prioridade, produto e equipamento, indicando o que não foi informado." },
      { type: "corrigido", text: "Anexos escolhidos ao abrir o chamado eram descartados e nunca chegavam ao ticket." },
      { type: "corrigido", text: "Base de Conhecimento abria em branco em algumas situações." },
      { type: "corrigido", text: "Mensagem de erro ao entrar agora explica quando falta confirmar o e-mail." },
    ],
  },
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
