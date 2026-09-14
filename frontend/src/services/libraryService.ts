import { api } from "./api";
import { resolveFileUrl } from "../lib/fileUrl";

/**
 * Biblioteca de arquivos frequentes — manual, guia, formulário.
 *
 * O acervo é ferramenta de atendimento, não catálogo público: a **listagem é
 * de staff** (`admin` e `technician`), e o cliente recebe o que o técnico
 * manda em vez de escolher da prateleira. O download é aberto a qualquer
 * autenticado porque o anexo que chega na conversa precisa abrir — e ali quem
 * decide é a visibilidade do item, conferida no servidor.
 *
 * ── O campo do arquivo é `file`, no SINGULAR ───────────────────────────
 *
 * O `attachmentService` manda **`files`**, no plural, porque o anexo de chamado
 * aceita vários de uma vez. Aqui o backend declara `file: UploadFile` — um
 * arquivo por item de biblioteca, já que o binário é guardado UMA vez e
 * apontado por muitas mensagens.
 *
 * Errar o nome do campo não quebra compilação nem teste de tipo: o
 * `FormData` aceita qualquer chave, e o servidor devolveria 422 dizendo que
 * `file` é obrigatório — em produção, na primeira vez que alguém tentasse
 * enviar. Por isso o nome está preso em `test/services/libraryService.test.ts`,
 * que é o mesmo cuidado que o contrato do anexo já tinha.
 */

/**
 * Quem alcança o arquivo.
 *
 * `internal` é o default da coluna no banco, e essa escolha é a regra inteira:
 * abrir para o cliente é ato explícito de um administrador, então **esquecer
 * falha do lado seguro**. Há manual técnico com senha de configuração em texto
 * aberto — não é material público por definição.
 */
export type LibraryVisibility = "internal" | "client";

export interface LibraryFile {
  id: string;
  title: string;
  description: string | null;
  product_id: string | null;
  /** Vem do relacionamento na resposta; `null` quando o item não é de produto. */
  product_name: string | null;
  visibility: LibraryVisibility;

  original_name: string;
  mime_type: string;
  size_bytes: number;
  /**
   * `false` significa que o ClamAV estava fora quando o arquivo subiu, e ele
   * foi gravado assim mesmo. Não existe estado "verificando": a varredura é
   * síncrona, e o que é recusado nunca chega a virar linha.
   */
  virus_scanned: boolean;
  virus_clean: boolean;

  uploaded_by: string;
  created_at: string;
  updated_at: string;
}

export interface LibraryFileListResponse {
  items: LibraryFile[];
  total: number;
  limit: number;
  offset: number;
}

export interface LibraryFileFilters {
  product_id?: string;
  visibility?: LibraryVisibility;
  search?: string;
  limit?: number;
  offset?: number;
}

export interface LibraryFileCreatePayload {
  file: File;
  title: string;
  description?: string;
  product_id?: string;
  visibility: LibraryVisibility;
}

/**
 * Edição dos campos de catálogo. O binário não se troca — sobe outro item.
 *
 * `visibility` entra aqui porque promover um arquivo de interno para cliente é
 * a operação que a regra prevê, e o backend registra o antes e o depois na
 * auditoria: abrir um manual para cliente é decisão de alguém, com nome e hora.
 */
export interface LibraryFileUpdatePayload {
  title?: string;
  description?: string | null;
  product_id?: string | null;
  visibility?: LibraryVisibility;
}

export async function getLibraryFiles(
  filters: LibraryFileFilters = {},
): Promise<LibraryFileListResponse> {
  const p = new URLSearchParams();
  if (filters.search) p.set("search", filters.search);
  if (filters.product_id) p.set("product_id", filters.product_id);
  if (filters.visibility) p.set("visibility", filters.visibility);
  if (filters.limit !== undefined) p.set("limit", String(filters.limit));
  if (filters.offset !== undefined) p.set("offset", String(filters.offset));
  const { data } = await api.get<LibraryFileListResponse>(`/library?${p}`);
  return data;
}

export async function uploadLibraryFile(
  payload: LibraryFileCreatePayload,
): Promise<LibraryFile> {
  const form = new FormData();
  // `file`, singular — ver o cabeçalho. O contrato está preso por teste.
  form.append("file", payload.file);
  form.append("title", payload.title);

  /*
    `visibility` vai SEMPRE, mesmo quando é `internal`.

    Omitir funcionaria — a coluna tem default `internal` — mas então a tela
    teria dois jeitos de dizer "interno": mandando a palavra, ou calando. O
    default do servidor continua existindo, e continua sendo a proteção de quem
    chama a API sem passar por aqui; o que ele NÃO deve ser é o modo de esta
    tela transmitir uma escolha que ela coletou. Escolha coletada se transmite.
  */
  form.append("visibility", payload.visibility);

  /*
    Campo vazio não vira campo vazio na requisição: ele some.

    `product_id` em branco chegaria como `""`, que não é UUID — 422 vindo do
    servidor para um campo que a pessoa simplesmente não preencheu. E
    `description` vazia gravaria string vazia onde o banco espera `NULL`, que é
    a diferença entre "não tem descrição" e "tem uma descrição, em branco".
  */
  if (payload.description) form.append("description", payload.description);
  if (payload.product_id) form.append("product_id", payload.product_id);

  const { data } = await api.post<LibraryFile>("/library", form, {
    // O default da instância é `application/json`; sem esta linha o corpo
    // multipart sairia anunciado como JSON.
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function updateLibraryFile(
  id: string,
  payload: LibraryFileUpdatePayload,
): Promise<LibraryFile> {
  const { data } = await api.patch<LibraryFile>(`/library/${id}`, payload);
  return data;
}

export async function deleteLibraryFile(id: string): Promise<void> {
  await api.delete(`/library/${id}`);
}

/**
 * Pede o link com validade de um arquivo da biblioteca.
 *
 * São dois passos de propósito, e não um `<a href>` apontando para a API: a
 * permissão é conferida **antes** de o link existir. Um link já emitido não
 * volta atrás, então gerar primeiro e conferir depois faria deste endereço a
 * rota de fuga da regra de visibilidade.
 *
 * Para o cliente, item interno responde **404**, igual a id inexistente — ele
 * não pode aprender que o arquivo existe. Quem trata o erro é a tela que
 * chamou; este módulo não engole nada.
 */
export async function getLibraryFileUrl(id: string): Promise<string> {
  const { data } = await api.get<{ url: string }>(`/library/${id}/download`);
  // A API devolve o caminho (`/api/v1/files/<token>?filename=…`); o host vem
  // da configuração do frontend, porque em produção os dois domínios diferem.
  return resolveFileUrl(data.url);
}
