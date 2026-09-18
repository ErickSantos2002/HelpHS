import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
  Alert,
  Badge,
  Button,
  FileUpload,
  Icon,
  Input,
  Modal,
  ModalFooter,
  Pagination,
  RadioCards,
  Select,
  Selector,
  Spinner,
  Textarea,
} from "../../components/ui";
import type { BadgeProps } from "../../components/ui";
import { useAuth } from "../../contexts/AuthContext";
import { getApiError } from "../../lib/apiError";
import { toastApiError } from "../../lib/toastError";
import {
  deleteLibraryFile,
  getLibraryFileUrl,
  getLibraryFiles,
  updateLibraryFile,
  uploadLibraryFile,
  type LibraryFile,
  type LibraryVisibility,
} from "../../services/libraryService";
import { getProducts, type Product } from "../../services/productService";

// ── Constantes ────────────────────────────────────────────────

/**
 * Os limites do envio, espelhando o backend.
 *
 * São os mesmos do anexo de chamado — `allowed_extensions` e
 * `upload_max_file_size_mb` do `config.py` valem para os dois caminhos —, mas
 * o `maxFiles` **não** é: o anexo aceita dez de uma vez, e aqui cada item da
 * biblioteca é um arquivo, porque o binário é guardado uma vez e apontado por
 * muitas mensagens. Repetir os limites na tela não muda o servidor; quem
 * recusa de verdade é ele.
 */
const EXTENSOES_ACEITAS = [
  ".pdf", ".doc", ".docx", ".xls", ".xlsx",
  ".png", ".jpg", ".jpeg", ".gif", ".txt", ".csv", ".zip", ".rar",
];
const TAMANHO_MAXIMO_MB = 25;

const PAGE_SIZE = 20;

/**
 * A visibilidade, com o que ela significa escrito por extenso.
 *
 * Uma tabela só, e todo lugar que fala de visibilidade lê dela: o selo da
 * lista, as opções do filtro, as fichas do modal e a frase que explica a
 * consequência. Antes de existir tabela, um rótulo novo nasce em um lugar e
 * envelhece nos outros três — foi o que deu três cópias do mapa de papel
 * dentro do `UsersPage`.
 *
 * Fica local porque tem um consumidor. Se a `ChatPanel` precisar do mesmo
 * vocabulário para explicar por que não dá para anexar um item interno, ela
 * sobe para `src/lib/` pela regra registrada no `lib/papel.ts` — dois
 * consumidores, e a tabela muda de casa.
 */
interface Visibilidade {
  rotulo: string;
  variante: BadgeProps["variant"];
  /** O que a escolha faz. Vai no modal, no momento em que ela é feita. */
  consequencia: string;
}

const VISIBILIDADE: Record<LibraryVisibility, Visibilidade> = {
  internal: {
    rotulo: "Uso interno",
    variante: "muted",
    consequencia:
      "Só administradores e técnicos veem este arquivo. A API recusa anexá-lo a uma conversa, que o cliente lê.",
  },
  client: {
    rotulo: "Visível ao cliente",
    variante: "info",
    consequencia:
      "Técnicos poderão anexar este arquivo às conversas, e o cliente vai baixá-lo. Manual com senha de configuração não entra aqui.",
  },
};

/**
 * As opções do filtro, DERIVADAS da tabela em vez de escritas ao lado dela.
 * Duas listas paralelas mantidas à mão é onde a terceira visibilidade futura
 * entra em uma e não na outra.
 */
const OPCOES_DE_VISIBILIDADE = (
  Object.keys(VISIBILIDADE) as LibraryVisibility[]
).map((v) => ({ value: v, label: VISIBILIDADE[v].rotulo }));

/**
 * As fichas da decisão. `muted` para o interno e `info` para o aberto — e o
 * que distingue as duas **não é a cor**: é o rótulo e a frase de consequência
 * logo abaixo. Cor sozinha não carrega significado (WCAG 1.4.1), e aqui ela
 * carregaria o significado mais caro da tela.
 */
const FICHAS_DE_VISIBILIDADE = [
  { value: "internal", label: VISIBILIDADE.internal.rotulo, icon: "lock" as const, tone: "muted" as const },
  { value: "client", label: VISIBILIDADE.client.rotulo, icon: "eye" as const, tone: "info" as const },
];

// ── Formatação ────────────────────────────────────────────────

/**
 * Tamanho em unidade legível.
 *
 * `(bytes / 1024 / 1024).toFixed(1)` direto — como a `TicketDetailPage` faz na
 * linha do anexo — mostra **"0.0 MB"** para um formulário de 40 KB, que é a
 * unidade certa aplicada ao número errado. Aquela tela é da outra frente;
 * relatado, não consertado daqui.
 */
function formataTamanho(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** A extensão, em caixa alta, para o selo. Sem ponto e sem o nome inteiro. */
function extensaoDe(nome: string): string {
  const partes = nome.split(".");
  return partes.length > 1 ? (partes.pop() ?? "").toUpperCase() : "—";
}

// ── Tela ──────────────────────────────────────────────────────

export default function LibraryPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [arquivos, setArquivos] = useState<LibraryFile[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [busca, setBusca] = useState("");
  const [filtroProduto, setFiltroProduto] = useState("");
  const [filtroVisibilidade, setFiltroVisibilidade] = useState("");
  const [produtos, setProdutos] = useState<Product[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erroDaLista, setErroDaLista] = useState<string | null>(null);

  const [enviando, setEnviando] = useState(false);
  const [editando, setEditando] = useState<LibraryFile | null>(null);
  const [excluindo, setExcluindo] = useState<LibraryFile | null>(null);
  const [exclusaoEmCurso, setExclusaoEmCurso] = useState(false);
  const [baixando, setBaixando] = useState<string | null>(null);

  useEffect(() => {
    setOffset(0);
  }, [busca, filtroProduto, filtroVisibilidade]);

  useEffect(() => {
    getProducts({ limit: 100 })
      .then((res) => setProdutos(res.items))
      .catch(() => setProdutos([]));
  }, []);

  useEffect(() => {
    setCarregando(true);
    setErroDaLista(null);
    getLibraryFiles({
      search: busca || undefined,
      product_id: filtroProduto || undefined,
      visibility: (filtroVisibilidade as LibraryVisibility) || undefined,
      offset,
      limit: PAGE_SIZE,
    })
      .then((res) => {
        setArquivos(res.items);
        setTotal(res.total);
      })
      .catch((err) => {
        /*
          A lista que não carrega precisa DIZER. Sem este ramo a tela mostrava
          o estado vazio — "Nenhum arquivo encontrado" — para uma falha de
          rede, que é a mesma pintura para duas situações opostas: não há nada,
          e não deu para saber se há. O aviso é inline porque é o conteúdo
          principal que faltou; toast serve para ação que falhou, não para
          leitura que não veio.
        */
        setErroDaLista(getApiError(err, "Não foi possível carregar a biblioteca."));
        setArquivos([]);
        setTotal(0);
      })
      .finally(() => setCarregando(false));
  }, [busca, filtroProduto, filtroVisibilidade, offset]);

  async function baixar(arquivo: LibraryFile) {
    setBaixando(arquivo.id);
    try {
      // Dois passos: o link com validade é PEDIDO, e o servidor confere a
      // visibilidade antes de emitir. A tela nunca monta o endereço.
      const url = await getLibraryFileUrl(arquivo.id);
      window.open(url, "_blank");
    } catch (err) {
      toastApiError(err, "Não foi possível abrir o arquivo.");
    } finally {
      setBaixando(null);
    }
  }

  async function confirmarExclusao() {
    if (!excluindo) return;
    setExclusaoEmCurso(true);
    try {
      await deleteLibraryFile(excluindo.id);
      setArquivos((prev) => prev.filter((a) => a.id !== excluindo.id));
      setTotal((t) => t - 1);
      setExcluindo(null);
    } catch (err) {
      toastApiError(err, "Não foi possível excluir o arquivo.");
    } finally {
      setExclusaoEmCurso(false);
    }
  }

  function limparFiltros() {
    setBusca("");
    setFiltroProduto("");
    setFiltroVisibilidade("");
  }

  const paginaAtual = Math.floor(offset / PAGE_SIZE) + 1;
  const temFiltro = !!(busca || filtroProduto || filtroVisibilidade);

  return (
    <div className="space-y-5 pb-10">
      {/* ── Cabeçalho ────────────────────────────────────────── */}
      {/*
        A casca é desenhada à mão e não vira `Card`: o cabeçalho é
        `rounded-2xl` e o `Card` é `rounded-xl`. O `cn()` deste projeto é
        concatenação simples, não `tailwind-merge` — mandar o raio por
        `className` deixaria as duas classes no atributo e quem vence sairia
        da ordem do CSS gerado.
      */}
      <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center sm:justify-between gap-4 rounded-2xl border border-borda/40 bg-surface px-5 py-4">
        <div className="text-center sm:text-left">
          <h1 className="text-xl font-extrabold text-conteudo-heading">Biblioteca</h1>
          <p className="mt-0.5 text-sm text-conteudo-muted">
            Manuais, guias e formulários de uso frequente
            {total > 0 && ` · ${total} arquivo${total !== 1 ? "s" : ""}`}
          </p>
        </div>

        <div className="flex flex-wrap items-center justify-center sm:justify-end gap-2">
          {/* Busca */}
          <div className="relative w-full sm:w-auto">
            {/* `pointer-events-none`: o ícone fica por cima do campo, e sem
                isso o clique na lupa não põe o cursor no campo. */}
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-conteudo-muted">
              <Icon name="search" size={16} strokeWidth={2} />
            </span>
            {/*
              `aria-label` porque nenhum campo pode se identificar só pelo
              `placeholder` — o texto que some exatamente quando a pessoa
              começa a digitar, e que em leitor de tela vale como dica, não
              como nome (CHECKLIST-29).

              O backend busca no título E no nome original do arquivo: quem
              procura "phoebus" pode estar lembrando do nome do arquivo, não do
              título que o administrador escreveu.
            */}
            <input
              type="text"
              aria-label="Buscar arquivos na biblioteca"
              placeholder="Buscar por título ou nome do arquivo…"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              className="pl-9 pr-8 py-2 text-sm w-full sm:w-64 rounded-lg border border-borda-control bg-surface-elevated text-conteudo placeholder:text-conteudo-muted focus:outline-none focus:ring-2 focus:ring-action focus:border-transparent transition-colors"
            />
            {busca && (
              <button
                onClick={() => setBusca("")}
                aria-label="Limpar busca"
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-conteudo-muted hover:text-conteudo cursor-pointer"
              >
                <Icon name="close" size={14} strokeWidth={2.5} />
              </button>
            )}
          </div>

          {/* Produto — D9.2: lista LONGA. As opções vêm de `getProducts` e
              crescem com o cadastro, então o controle é o
              `Selector variant="filter"`, que também traz o rótulo. */}
          {produtos.length > 0 && (
            <Selector
              variant="filter"
              label="Produto"
              value={filtroProduto}
              onChange={(v) => setFiltroProduto(v ?? "")}
              placeholder="Todos os produtos"
              options={produtos.map((p) => ({ value: p.id, label: p.name }))}
            />
          )}

          {/* Visibilidade — D9.2: duas opções, vindas de uma constante do
              próprio código. Lista curta e conhecida, logo `<select>` nativo.

              O rótulo é `sr-only` porque a barra não tem espaço para ele: sem
              rótulo, o filtro se anunciaria pelo VALOR escolhido — "Uso
              interno" — sem dizer de que filtro é. */}
          <span id="rotulo-filtro-visibilidade" className="sr-only">
            Visibilidade
          </span>
          <Select
            id="filtro-visibilidade"
            aria-labelledby="rotulo-filtro-visibilidade"
            value={filtroVisibilidade}
            onChange={(e) => setFiltroVisibilidade(e.target.value)}
            placeholder="Todas as visibilidades"
            options={OPCOES_DE_VISIBILIDADE}
          />

          {temFiltro && (
            /* `hover:text-on-tint-danger` e não `hover:text-danger`: a cor
               cheia da rampa como cor de TEXTO reprova o piso. A borda
               continua na cor cheia a 30%, que é forma e não texto. */
            <button
              onClick={limparFiltros}
              className="flex items-center gap-1.5 text-xs font-medium text-conteudo-muted hover:text-on-tint-danger transition-colors cursor-pointer px-2 py-2 rounded-lg border border-borda/40 hover:border-danger/30"
            >
              <Icon name="close" size={14} strokeWidth={2.5} />
              Limpar
            </button>
          )}

          {/* Ação, não navegação: abre um modal, então é `<button>`. O `Button`
              sem `to=` já é um; com `to=` ele vira `Link`. */}
          {isAdmin && (
            <Button
              onClick={() => setEnviando(true)}
              icon={<Icon name="plus" size={16} strokeWidth={2.5} />}
            >
              Enviar arquivo
            </Button>
          )}
        </div>
      </div>

      {/* ── Lista ────────────────────────────────────────────── */}
      {erroDaLista ? (
        <Alert variant="danger" title="Erro ao carregar">
          {erroDaLista}
        </Alert>
      ) : carregando ? (
        <div className="flex h-48 items-center justify-center">
          <Spinner size="lg" />
        </div>
      ) : arquivos.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-borda/40 bg-surface py-20">
          {/* `conteudo-muted` e não `faint`: o círculo é `bg-surface-elevated` e
              o texto está no mesmo elemento — o par que a varredura media em
              2,34:1 no claro e 1,79:1 no escuro. */}
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-surface-elevated text-conteudo-muted">
            <Icon name="folder" size={20} strokeWidth={1.5} />
          </div>
          <p className="text-sm font-medium text-conteudo-muted">Nenhum arquivo encontrado.</p>
          {temFiltro && (
            <button
              onClick={limparFiltros}
              className="mt-2 text-xs text-conteudo-link hover:text-conteudo-link-hover cursor-pointer transition-colors"
            >
              Limpar filtros
            </button>
          )}
          {isAdmin && !temFiltro && (
            <button
              onClick={() => setEnviando(true)}
              className="mt-3 text-xs font-medium text-conteudo-link hover:text-conteudo-link-hover cursor-pointer transition-colors"
            >
              + Enviar primeiro arquivo
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {arquivos.map((arquivo) => {
            const vis = VISIBILIDADE[arquivo.visibility];
            return (
              <div
                key={arquivo.id}
                className="flex items-start gap-4 rounded-xl border border-borda/40 bg-surface px-5 py-4"
              >
                <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-tint-primary text-on-tint-primary">
                  <Icon name="document" size={20} strokeWidth={1.5} />
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    {/*
                      Baixar é AÇÃO, não navegação: o link com validade só
                      existe depois de o servidor conferir a visibilidade, e
                      por isso há uma chamada antes de abrir qualquer coisa.
                      Um `<a href>` daqui teria de montar o endereço na tela,
                      que é justo o que faria da regra de visibilidade uma
                      sugestão.
                    */}
                    <button
                      onClick={() => baixar(arquivo)}
                      disabled={baixando === arquivo.id}
                      className="text-sm font-semibold text-conteudo-heading hover:text-conteudo-link transition-colors truncate cursor-pointer disabled:cursor-wait"
                    >
                      {arquivo.title}
                    </button>
                    <Badge variant={vis.variante}>{vis.rotulo}</Badge>
                    {arquivo.product_name ? (
                      <Badge variant="primary" className="max-w-[10rem] truncate">
                        {arquivo.product_name}
                      </Badge>
                    ) : (
                      <Badge variant="secondary">Todos os produtos</Badge>
                    )}
                    {/*
                      `virus_scanned = false` quer dizer que o ClamAV estava
                      fora quando o arquivo subiu, e ele foi gravado assim
                      mesmo. Não existe estado "verificando": a varredura é
                      síncrona, e o que é recusado nunca vira linha. Quem for
                      abrir precisa saber qual dos dois está olhando.
                    */}
                    {!arquivo.virus_scanned && (
                      <Badge variant="warning">Não verificado</Badge>
                    )}
                  </div>

                  {arquivo.description && (
                    <p className="text-xs text-conteudo-muted line-clamp-1">
                      {arquivo.description}
                    </p>
                  )}

                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-conteudo-muted">
                    <span className="font-mono">{extensaoDe(arquivo.original_name)}</span>
                    <span>{formataTamanho(arquivo.size_bytes)}</span>
                    <span className="truncate max-w-[18rem]" title={arquivo.original_name}>
                      {arquivo.original_name}
                    </span>
                    <span>
                      Enviado em {new Date(arquivo.created_at).toLocaleDateString("pt-BR")}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-1 shrink-0 self-center">
                  {/*
                    O nome acessível carrega o TÍTULO do arquivo: numa lista de
                    vinte linhas, vinte controles chamados "Baixar" não dizem
                    qual dos vinte.
                  */}
                  <button
                    onClick={() => baixar(arquivo)}
                    disabled={baixando === arquivo.id}
                    title="Baixar"
                    aria-label={`Baixar ${arquivo.title}`}
                    className="p-1.5 rounded-lg text-conteudo-muted hover:text-conteudo-link hover:bg-primary/10 transition-colors cursor-pointer disabled:cursor-wait"
                  >
                    <Icon name="download" size={16} strokeWidth={2} />
                  </button>
                  {isAdmin && (
                    <>
                      <button
                        onClick={() => setEditando(arquivo)}
                        title="Editar"
                        aria-label={`Editar ${arquivo.title}`}
                        className="p-1.5 rounded-lg text-conteudo-muted hover:text-conteudo-link hover:bg-primary/10 transition-colors cursor-pointer"
                      >
                        <Icon name="edit" size={16} strokeWidth={2} />
                      </button>
                      <button
                        onClick={() => setExcluindo(arquivo)}
                        title="Excluir"
                        aria-label={`Excluir ${arquivo.title}`}
                        className="p-1.5 rounded-lg text-conteudo-muted hover:text-on-tint-danger hover:bg-tint-danger transition-colors cursor-pointer"
                      >
                        <Icon name="trash" size={16} strokeWidth={2} />
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── Paginação ────────────────────────────────────────── */}
      {/* O `Pagination` conta a partir de 1 e este estado guarda `offset`; a
          conversão fica num lugar só, aqui. */}
      {total > PAGE_SIZE && (
        <Pagination
          page={paginaAtual}
          pageSize={PAGE_SIZE}
          total={total}
          onPageChange={(p) => setOffset((p - 1) * PAGE_SIZE)}
          itemLabel="arquivos"
        />
      )}

      {/* ── Modais ───────────────────────────────────────────── */}
      {/*
        Renderização condicional, e não `open={!!alvo}`: o formulário é
        remontado a cada abertura, então o `react-hook-form` reinicia sozinho.
        Com o modal sempre montado, o segundo envio herdaria os campos do
        primeiro.
      */}
      {enviando && (
        <ModalDeEnvio
          produtos={produtos}
          onClose={() => setEnviando(false)}
          onEnviado={(novo) => {
            setEnviando(false);
            // Recarrega da primeira página: a lista vem ordenada por título, e
            // encaixar o item novo na posição certa aqui seria reimplementar a
            // ordenação do servidor — que é onde ela precisa continuar valendo.
            if (offset === 0) {
              setArquivos((prev) => [novo, ...prev].slice(0, PAGE_SIZE));
              setTotal((t) => t + 1);
            } else {
              setOffset(0);
            }
          }}
        />
      )}

      {editando && (
        <ModalDeEdicao
          arquivo={editando}
          produtos={produtos}
          onClose={() => setEditando(null)}
          onSalvo={(salvo) => {
            setArquivos((prev) => prev.map((a) => (a.id === salvo.id ? salvo : a)));
            setEditando(null);
          }}
        />
      )}

      <Modal
        open={!!excluindo}
        onClose={() => setExcluindo(null)}
        size="sm"
        title="Excluir arquivo"
      >
        <div className="space-y-4">
          {excluindo && (
            <div className="flex items-center gap-3 rounded-xl border border-borda bg-surface-elevated px-4 py-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-tint-primary text-on-tint-primary">
                <Icon name="document" size={20} strokeWidth={1.5} />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-conteudo-heading truncate">
                  {excluindo.title}
                </p>
                <p className="text-xs text-conteudo-muted">
                  {excluindo.original_name} · {formataTamanho(excluindo.size_bytes)}
                </p>
              </div>
            </div>
          )}

          <p className="text-sm text-conteudo-muted">
            Tem certeza que deseja excluir{" "}
            <span className="text-conteudo-heading font-medium">
              "{excluindo?.title}"
            </span>
            ? O arquivo sai da biblioteca e esta ação não pode ser desfeita.
          </p>
          {/*
            A frase existe porque a consequência não é adivinhável: quem exclui
            um manual que foi mandado em vinte conversas espera ou que as
            conversas sumam, ou que a exclusão seja recusada. É nenhuma das
            duas — as mensagens continuam lá, sem o arquivo. Ruim, mas
            recuperável; apagar a fala do técnico não seria.
          */}
          <p className="text-sm text-conteudo-muted">
            As conversas em que ele já foi anexado continuam existindo — só
            deixam de ter o arquivo.
          </p>
        </div>
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={() => setExcluindo(null)}
            disabled={exclusaoEmCurso}
          >
            Cancelar
          </Button>
          <Button variant="danger" onClick={confirmarExclusao} loading={exclusaoEmCurso}>
            Excluir
          </Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}

// ── Modal de envio ────────────────────────────────────────────

const esquemaDeEnvio = z.object({
  title: z.string().min(1, "O título é obrigatório").max(255, "Título muito longo"),
  description: z.string().max(2000, "Descrição muito longa").optional(),
  product_id: z.string().optional(),
});

type ValoresDeEnvio = z.infer<typeof esquemaDeEnvio>;

function ModalDeEnvio({
  produtos,
  onClose,
  onEnviado,
}: {
  produtos: Product[];
  onClose: () => void;
  onEnviado: (arquivo: LibraryFile) => void;
}) {
  /*
    O arquivo e a visibilidade ficam FORA do `react-hook-form`, como o
    `TicketFormPage` já faz com os anexos: nem o `FileUpload` nem o
    `RadioCards` são `<input>` registrável — o primeiro é controlado por
    `files`/`onChange`, o segundo é um `fieldset` de rádios com valor próprio.
    Registrá-los exigiria `Controller` para nada; o que o formulário valida são
    os três campos de texto.
  */
  const [arquivos, setArquivos] = useState<File[]>([]);
  const [visibilidade, setVisibilidade] = useState<LibraryVisibility>("internal");
  const [erroDeArquivo, setErroDeArquivo] = useState<string | null>(null);
  const [erroDeEnvio, setErroDeEnvio] = useState<string | null>(null);

  const form = useForm<ValoresDeEnvio>({
    resolver: zodResolver(esquemaDeEnvio),
    defaultValues: { title: "", description: "", product_id: "" },
  });

  async function onSubmit(valores: ValoresDeEnvio) {
    setErroDeEnvio(null);
    const arquivo = arquivos[0];
    if (!arquivo) {
      /*
        A falta do arquivo é avisada AO LADO da zona de anexo, e não por toast.
        O `FileUpload` é controlado e não participa da validação do zod, então
        sem esta guarda o botão de enviar simplesmente não fazia nada — a tela
        que não explica o que falta é a que a pessoa clica três vezes.
      */
      setErroDeArquivo("Escolha o arquivo que vai para a biblioteca.");
      return;
    }
    try {
      const salvo = await uploadLibraryFile({
        file: arquivo,
        title: valores.title,
        description: valores.description || undefined,
        product_id: valores.product_id || undefined,
        visibility: visibilidade,
      });
      onEnviado(salvo);
    } catch (err) {
      // Inline e não toast: o modal continua aberto com o que a pessoa
      // escreveu, e a razão precisa estar onde ela está olhando. O servidor
      // recusa por extensão, por tamanho e por vírus, cada um com seu texto.
      setErroDeEnvio(getApiError(err, "Não foi possível enviar o arquivo."));
    }
  }

  return (
    <Modal open onClose={onClose} size="lg" title="Enviar arquivo para a biblioteca">
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        {erroDeEnvio && <Alert variant="danger">{erroDeEnvio}</Alert>}

        <div>
          <FileUpload
            files={arquivos}
            onChange={(f) => {
              // Um item da biblioteca é um arquivo: o binário é guardado uma
              // vez e apontado por muitas mensagens. `maxFiles={1}` já corta,
              // mas a última escolha é a que vale — escolher outro troca, em
              // vez de ser ignorado em silêncio.
              setArquivos(f.slice(-1));
              setErroDeArquivo(null);
            }}
            accept={EXTENSOES_ACEITAS}
            maxFiles={1}
            maxSizeMb={TAMANHO_MAXIMO_MB}
          />
          {erroDeArquivo && (
            <p className="mt-1.5 text-xs text-on-tint-danger">{erroDeArquivo}</p>
          )}
        </div>

        <Input
          label="Título *"
          autoFocus
          placeholder="ex: Manual de operação do Phoebus"
          error={form.formState.errors.title?.message}
          {...form.register("title")}
        />

        <Textarea
          label="Descrição"
          rows={2}
          placeholder="Quando usar este arquivo, o que ele cobre…"
          error={form.formState.errors.description?.message}
          {...form.register("description")}
        />

        {/* Produto — o mesmo controle do filtro, em `variant="form"`. Vazio
            significa que o arquivo vale para todos os produtos. */}
        <Selector
          variant="form"
          label="Produto"
          value={form.watch("product_id") || null}
          onChange={(v) => form.setValue("product_id", v ?? "")}
          placeholder="Todos os produtos"
          emptyLabel="Todos os produtos"
          options={produtos.map((p) => ({ value: p.id, label: p.name }))}
        />

        {/*
          A visibilidade é a única escolha desta tela com consequência fora
          dela, e por isso é a que parece uma decisão: duas fichas lado a lado,
          com a consequência escrita embaixo — em vez de uma caixa de marcar
          que a pessoa passa sem ler.

          O padrão é `internal`, o mesmo do banco, e a razão é a regra inteira:
          abrir para o cliente é ato explícito de um administrador, então
          esquecer falha do lado seguro.
        */}
        <RadioCards
          name="visibilidade-do-envio"
          label="Quem pode ver este arquivo"
          layout="linha"
          required
          value={visibilidade}
          onChange={(v) => setVisibilidade(v as LibraryVisibility)}
          options={FICHAS_DE_VISIBILIDADE}
          hint={VISIBILIDADE[visibilidade].consequencia}
        />

        <ModalFooter>
          <Button
            type="button"
            variant="secondary"
            onClick={onClose}
            disabled={form.formState.isSubmitting}
          >
            Cancelar
          </Button>
          {/*
            O rótulo do envio NÃO repete o do botão que abriu o modal.

            "Enviar arquivo" já é o nome da ação na barra, e ela continua
            montada atrás do painel: dois controles com o mesmo nome acessível
            na mesma tela, fazendo coisas diferentes — um abre, o outro grava.
            Quem usa leitor de tela ouve "Enviar arquivo, botão" duas vezes e
            não tem como saber qual é qual. É o mesmo cuidado que a
            `ProductsPage` já tem: o gatilho é "Novo produto" e o envio é
            "Criar produto".
          */}
          <Button type="submit" loading={form.formState.isSubmitting}>
            Enviar para a biblioteca
          </Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

// ── Modal de edição ───────────────────────────────────────────

function ModalDeEdicao({
  arquivo,
  produtos,
  onClose,
  onSalvo,
}: {
  arquivo: LibraryFile;
  produtos: Product[];
  onClose: () => void;
  onSalvo: (arquivo: LibraryFile) => void;
}) {
  const [visibilidade, setVisibilidade] = useState<LibraryVisibility>(arquivo.visibility);
  const [erro, setErro] = useState<string | null>(null);

  const form = useForm<ValoresDeEnvio>({
    resolver: zodResolver(esquemaDeEnvio),
    defaultValues: {
      title: arquivo.title,
      description: arquivo.description ?? "",
      product_id: arquivo.product_id ?? "",
    },
  });

  async function onSubmit(valores: ValoresDeEnvio) {
    setErro(null);
    try {
      const salvo = await updateLibraryFile(arquivo.id, {
        title: valores.title,
        // `null`, e não `undefined`: a descrição apagada precisa CHEGAR ao
        // servidor como apagada. `undefined` some do JSON, e o PATCH só grava
        // o que recebe — o campo ficaria com o texto antigo.
        description: valores.description || null,
        product_id: valores.product_id || null,
        visibility: visibilidade,
      });
      onSalvo(salvo);
    } catch (err) {
      setErro(getApiError(err, "Não foi possível salvar as alterações."));
    }
  }

  const mudouVisibilidade = visibilidade !== arquivo.visibility;

  return (
    <Modal open onClose={onClose} size="lg" title="Editar arquivo da biblioteca">
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        {erro && <Alert variant="danger">{erro}</Alert>}

        {/*
          O binário não se troca por aqui, e dizer isso custa uma linha. Sem
          ela, quem quer substituir a versão 3 do manual pela 4 abre esta tela,
          não acha onde, e conclui que a biblioteca não faz isso — quando o
          caminho é enviar outro item e excluir o antigo.
        */}
        <div className="flex items-center gap-3 rounded-xl border border-borda bg-surface-elevated px-4 py-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-tint-primary text-on-tint-primary">
            <Icon name="document" size={20} strokeWidth={1.5} />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-conteudo-heading truncate">
              {arquivo.original_name}
            </p>
            <p className="text-xs text-conteudo-muted">
              {formataTamanho(arquivo.size_bytes)} · o arquivo em si não muda aqui; para
              trocá-lo, envie outro item.
            </p>
          </div>
        </div>

        <Input
          label="Título *"
          autoFocus
          error={form.formState.errors.title?.message}
          {...form.register("title")}
        />

        <Textarea
          label="Descrição"
          rows={2}
          error={form.formState.errors.description?.message}
          {...form.register("description")}
        />

        <Selector
          variant="form"
          label="Produto"
          value={form.watch("product_id") || null}
          onChange={(v) => form.setValue("product_id", v ?? "")}
          placeholder="Todos os produtos"
          emptyLabel="Todos os produtos"
          options={produtos.map((p) => ({ value: p.id, label: p.name }))}
        />

        <RadioCards
          name="visibilidade-da-edicao"
          label="Quem pode ver este arquivo"
          layout="linha"
          required
          value={visibilidade}
          onChange={(v) => setVisibilidade(v as LibraryVisibility)}
          options={FICHAS_DE_VISIBILIDADE}
          hint={VISIBILIDADE[visibilidade].consequencia}
        />

        {/*
          O que rebaixar NÃO desfaz.

          Quem fecha um arquivo para o cliente está tentando tirá-lo das vistas
          dele, e é razoável supor que isso alcance as conversas onde ele já
          foi mandado. Não alcança: o histórico da conversa não é reescrito. Se
          o conteúdo vazou, fechar aqui não é a contenção — é preciso excluir o
          arquivo, e mesmo assim a mensagem permanece.
        */}
        {mudouVisibilidade && visibilidade === "internal" && (
          <Alert variant="warning" title="O histórico não muda">
            As conversas em que este arquivo já foi anexado continuam com ele. Fechar
            para o cliente vale daqui para a frente.
          </Alert>
        )}

        <ModalFooter>
          <Button
            type="button"
            variant="secondary"
            onClick={onClose}
            disabled={form.formState.isSubmitting}
          >
            Cancelar
          </Button>
          <Button type="submit" loading={form.formState.isSubmitting}>
            Salvar
          </Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}
