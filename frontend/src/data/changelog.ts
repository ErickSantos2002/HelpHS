export const APP_VERSION = "v1.17.0";

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
    version: "v1.17.0",
    date: "24/09/2026",
    entries: [
      { type: "novidade", text: "Chamado aberto agora avisa a equipe inteira, e não só quem abriu. Todos os técnicos e administradores ativos recebem o aviso no sininho na hora, com o número e o título do chamado, e clicar nele abre o chamado direto. Antes o chamado novo só aparecia para quem estivesse olhando o quadro, e um pedido aberto no fim da tarde podia esperar a manhã seguinte para ser visto. O aviso vai para a equipe toda de propósito, e não para um técnico sorteado: o chamado nasce sem responsável, e escolher um seria inventar uma atribuição que ninguém pediu." },
      { type: "melhoria", text: "Quem abre o chamado continua recebendo a mesma confirmação de antes, com o protocolo. Um técnico ou administrador que abre chamado em nome de um cliente recebe só essa confirmação, uma vez — ele não recebe também o aviso de chamado novo." },
      { type: "novidade", text: "O chamado novo passa a gerar também aviso por e-mail para os técnicos e administradores ativos, nos ambientes em que o envio de e-mail estiver configurado. É o único evento da equipe que sai por e-mail: atribuição e reabertura seguem só no sininho, a pedido de quem trabalha dentro do sistema o dia inteiro." },
      { type: "melhoria", text: "Os e-mails do sistema passam a usar um layout único com a identidade da Health & Safety: a marca no topo, o texto organizado e um botão que abre o chamado. A mesma mensagem leva também uma versão em texto simples, para quem lê e-mail em programa que não mostra imagem ou formatação — o conteúdo é o mesmo nos dois casos, e o nome da empresa continua legível mesmo se a imagem for bloqueada." },
      { type: "melhoria", text: "O assunto dos e-mails passa a começar com [HelpHS] e a trazer o número do chamado. Antes cinco chamados resolvidos renderiam cinco e-mails com o mesmo assunto, sem dizer de qual chamado se tratava. Observação operacional: o envio de e-mail depende da configuração do servidor de e-mail (SMTP) do ambiente. Sem isso, os avisos do sininho funcionam normalmente e nenhum e-mail é enviado." },
    ],
  },
  {
    version: "v1.16.0",
    date: "22/09/2026",
    entries: [
      { type: "melhoria", text: "As listas de escolha do sistema — os filtros das telas e os campos de formulário — passaram a abrir dentro do próprio sistema. Antes quem desenhava a lista era o Windows, o Android ou o navegador, e ela ficava de fora do tema: no modo escuro abria clara, e mudava de aparência conforme o aparelho de cada pessoa. Agora ela segue as cores do sistema em qualquer navegador, marca a opção que está escolhida e, no celular, abre para cima quando não há espaço embaixo. O que cada campo faz continua igual: as setas, o Enter e a digitação da primeira letra funcionam como antes, e nenhum filtro, formulário ou prazo mudou de comportamento." },
    ],
  },
  {
    version: "v1.15.0",
    date: "16/09/2026",
    entries: [
      { type: "novidade", text: "Biblioteca de arquivos: a equipe guarda uma vez os manuais, formulários e documentos que manda toda semana, e passa a anexá-los nos chamados sem subir o mesmo arquivo de novo. Cada item nasce interno à equipe; deixá-lo visível para o cliente é uma escolha explícita de um administrador." },
      { type: "novidade", text: "No chat do chamado, a equipe anexa um arquivo da biblioteca direto na conversa. Item marcado como interno não chega ao cliente." },
      { type: "novidade", text: "Os eventos da agenda passaram a ter hora de início e de fim. Quem marca um treinamento que ocupa o dia todo deixa a chave \"dia inteiro\" ligada e não digita horário nenhum, e um plantão que vira a madrugada aparece nos dois dias. Os eventos que já existiam viraram dia inteiro, na mesma data de sempre." },
      { type: "melhoria", text: "A cor do evento da agenda passou a vir do tipo dele, e a legenda voltou ao rodapé do calendário dizendo qual cor é qual. Antes a cor era escolhida à mão e não queria dizer nada: dois treinamentos podiam sair de cores diferentes, e um treinamento e uma reunião saíam do mesmo azul. Os tons foram escolhidos para o texto sobre a cor ficar legível." },
      { type: "melhoria", text: "A agenda mostra quem criou cada evento." },
      { type: "melhoria", text: "Os motivos de atraso informados pela equipe passaram a aparecer no relatório, logo depois da conformidade de SLA por prioridade. O relatório já dizia quantos chamados estouraram o prazo, mas não por quê — e cinco atrasos por peça em falta pedem providência diferente de cinco atrasos por chamado aberto na sexta às 17h." },
      { type: "melhoria", text: "Quando o login é bloqueado por tentativas erradas, a tela passou a mostrar a contagem regressiva ao vivo até a liberação, e se libera sozinha quando ela zera." },
      { type: "corrigido", text: "Entrar com o e-mail escrito em maiúsculas passou a funcionar. Antes \"Fulano@empresa.com\" e \"fulano@empresa.com\" podiam virar duas contas diferentes, e quem digitasse a caixa errada recebia \"senha incorreta\" sem entender o motivo." },
      { type: "corrigido", text: "Clicar fora de uma janela do sistema não a fecha mais — um clique fora por engano descartava tudo o que já estava digitado. Ela sai pelo X ou pelo Cancelar, e todas as janelas passaram a ter o X." },
      { type: "corrigido", text: "O indicador de SLA deixou de dar como cumprido um chamado que passou do prazo e ficou parado até ser resolvido. Na medição dos últimos seis meses o percentual não mudou — esses chamados já contavam pela data —, mas a marca de violação no chamado agora fica correta." },
    ],
  },
  {
    version: "v1.14.0",
    date: "11/09/2026",
    entries: [
      { type: "novidade", text: "Ao concluir um chamado que passou do prazo, a equipe informa o motivo do atraso, que fica registrado no histórico do chamado." },
      { type: "melhoria", text: "Os prazos de atendimento ficaram mais curtos e passaram a ser acompanhados em minutos. Um chamado de prioridade Crítica, por exemplo, recebe a primeira resposta em até 30 minutos." },
      { type: "melhoria", text: "Feriados nacionais e o Carnaval deixaram de contar no prazo de atendimento. Feriados municipais continuam contando." },
      { type: "corrigido", text: "Na tela de Configuração de SLA, os prazos passaram a ser exibidos e editados em minutos. Antes a prioridade Crítica aparecia como \"nullh\", editar a Crítica apagava os 30 minutos, e o texto informava o expediente das 8h às 18h, quando ele vai das 8h às 17h." },
    ],
  },
  {
    version: "v1.13.0",
    date: "09/09/2026",
    entries: [
      { type: "novidade", text: "Interface alinhada ao design system da Health & Safety: cores, tipografia, contraste e tema escuro." },
    ],
  },
  {
    version: "v1.12.0",
    date: "31/08/2026",
    entries: [
      { type: "novidade", text: "A Política de Privacidade agora pode ser lida dentro do sistema. Na tela de cadastro, o texto \"política de privacidade\" virou um link que abre o documento completo — antes ele tinha aparência de link mas não abria nada, e a pessoa marcava a caixa dizendo ter lido algo que não tinha como ler." },
    ],
  },
  {
    version: "v1.11.0",
    date: "31/08/2026",
    entries: [
      { type: "melhoria", text: "A resposta da Helô passou a contar como a primeira resposta do chamado. Como ela responde em segundos, o indicador de primeira resposta dentro do prazo sobe para perto de 100% a partir desta versão: ele passa a medir o atendimento da IA, e não mais quanto tempo o cliente esperou até alguém da equipe falar com ele." },
      { type: "corrigido", text: "Chamado que ainda não tem responsável deixou de ir para \"Aguardando técnico\" quando o cliente responde. Aquele estado pausa a contagem de prazo — ou seja, o relógio parava justamente enquanto o cliente esperava alguém da equipe assumir. Ele volta a ser usado só depois que um técnico assume o chamado." },
    ],
  },
  {
    version: "v1.10.0",
    date: "27/08/2026",
    entries: [
      { type: "novidade", text: "A Helô passa a responder no chamado assim que ele é aberto: dá as boas-vindas, acompanha a conversa e chama alguém da equipe quando você pede para falar com uma pessoa." },
      { type: "novidade", text: "A equipe pode desligar a IA em um cliente ou em um chamado específico. Desligada no chamado, ela para de fazer tudo ali — inclusive a classificação automática e a sugestão de resposta — e qualquer pessoa da equipe pode religar no mesmo botão." },
      { type: "melhoria", text: "Ao criar uma conta com um e-mail que já está cadastrado, o sistema não avisa mais na tela que aquele endereço existe — em vez disso, envia uma mensagem ao dono do e-mail explicando que ele já tem conta e como entrar. Assim ninguém consegue descobrir, de fora, quem é cliente da Health & Safety." },
      { type: "corrigido", text: "Quando o login é bloqueado por tentativas erradas, a tela agora diz que é um bloqueio temporário e quantos minutos faltam. Antes a mensagem culpava a conexão, e não havia como saber quanto esperar." },
      { type: "corrigido", text: "Ao sair do sistema, o chat que estava aberto também é encerrado. Antes aquela conexão continuava valendo até a sessão vencer sozinha." },
      { type: "corrigido", text: "O filtro de situação da lista de usuários oferecia a opção \"Suspenso\", que não existe no sistema — escolhê-la fazia a lista deixar de carregar. A opção foi removida." },
      { type: "corrigido", text: "Não dava para apagar a descrição de um evento da agenda: o texto antigo reaparecia no carregamento seguinte, como se a edição não tivesse acontecido." },
      { type: "corrigido", text: "O resumo automático de uma conversa longa descartava justamente as mensagens mais recentes. Agora ele considera o fim da conversa." },
      { type: "melhoria", text: "A tela de login ganhou o olho para revelar a senha digitada." },
      { type: "melhoria", text: "Os e-mails do sistema passaram a sair por um serviço dedicado de envio, o que torna a entrega mais confiável." },
      { type: "melhoria", text: "O chat em tempo real passou a funcionar com o sistema atendendo em mais de um processo ao mesmo tempo — dá para crescer o atendimento sem que duas pessoas no mesmo chamado deixem de se ver." },
      { type: "melhoria", text: "Mensagens muito longas no chat passaram a ser recusadas na hora, com um aviso sugerindo mandar o texto como anexo." },
    ],
  },
  {
    version: "v1.9.0",
    date: "26/08/2026",
    entries: [
      { type: "novidade", text: "Na tela de Grupos, aceitar a sugestão de empresa agora cria o cadastro e já vincula todos os clientes com o mesmo CNPJ — e limpar o campo de empresa, que havia parado de funcionar, voltou a funcionar." },
      { type: "novidade", text: "Anexos que não puderam ser verificados pelo antivírus ganham um aviso e podem ser verificados de novo depois — e a equipe fica sabendo quando a verificação está fora do ar." },
      { type: "corrigido", text: "Um defeito na renovação automática da sessão podia desconectar você do nada no meio do uso. Agora a sessão se renova sem encerrar a si mesma." },
      { type: "corrigido", text: "A tela de configuração de prazos de SLA voltou a salvar as alterações — toda tentativa terminava em erro." },
      { type: "corrigido", text: "Mensagens do chat e notificações em tempo real podiam se perder dependendo de qual conexão as recebia. Agora chegam sempre." },
      { type: "corrigido", text: "Na Base de Conhecimento, artigos em rascunho deixaram de aparecer para clientes, e um defeito que podia misturar as tags de artigos criados em sequência foi corrigido." },
      { type: "melhoria", text: "Depois de uma atualização do sistema, o navegador passa a buscar a versão nova sozinho — sem tela em branco nem precisar recarregar à força — e as páginas ficaram mais leves de carregar." },
      { type: "melhoria", text: "As listagens administrativas (usuários, grupos, relatórios) carregam mais rápido em contas com muitos registros." },
      { type: "melhoria", text: "Criar conta ficou mais rápido: a confirmação não espera mais o envio de e-mail terminar. E as notificações por e-mail só saem depois que a ação foi de fato registrada." },
      { type: "melhoria", text: "O fechamento automático de chamados resolvidos não para mais por causa de um erro isolado, e ao tentar excluir um usuário que não pode ser excluído o sistema agora explica o motivo." },
    ],
  },
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
