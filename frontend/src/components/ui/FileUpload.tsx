import { useCallback, useRef, useState } from "react";
import { cn } from "../../lib/utils";
import { Icon } from "./Icon";

/**
 * Zona de anexo, de `DS/components/forms/FileUpload.jsx`.
 *
 * Extraída do seletor que vivia dentro do `TicketFormPage`. O comportamento é o
 * mesmo, linha a linha — validação, deduplicação, corte no limite, arrastar e
 * soltar, e o `value = ""` que faz o mesmo arquivo poder ser escolhido duas
 * vezes seguidas.
 *
 * ── O que NÃO muda, e por quê ──────────────────────────────────────────
 *
 * O contrato de rede é combinado com o backend e fica fora deste arquivo: quem
 * monta o `FormData` é o `attachmentService`, com o campo **`files`** no plural,
 * contra `POST /tickets/{id}/attachments`. Um `file` singular chegaria como
 * corpo vazio, sem erro de compilação e sem teste vermelho — por isso o
 * contrato está preso em `test/services/attachmentService.test.ts`, e foi
 * escrito **antes** desta extração.
 *
 * Os limites também espelham o backend e são passados de fora: 10 arquivos,
 * 25 MB cada, e a lista de extensões. Mudá-los aqui não muda o servidor.
 *
 * ── Os três estados do antivírus ───────────────────────────────────────
 *
 * O `.d.ts` do pacote define `status: "ready" | "scanning" | "rejected"`, e esse
 * vocabulário **não descreve o HelpHS**. Aqui a varredura do ClamAV é
 * **síncrona**, feita antes de persistir (`attachments.py`), então:
 *
 * | Estado real | No banco | Onde aparece |
 * |---|---|---|
 * | verificado e limpo | `virus_scanned = true` | selo no anexo já enviado |
 * | **não verificado** | `virus_scanned = false` | selo de aviso — o ClamAV estava fora e o arquivo foi gravado assim mesmo |
 * | rejeitado | **não vira linha** | 422 com `detail: "File 'X' rejected: …"`, mostrado pelo `toastApiError` |
 *
 * Não existe `scanning`: nada fica pendente. E o rejeitado nunca chega a ser um
 * anexo — some antes, com o motivo. Por isso o estado vive no item da lista
 * (`AttachmentItem`) e não aqui: esta zona mostra arquivos **antes** do envio,
 * quando não há veredito nenhum.
 */
export interface FileUploadProps {
  /** Os arquivos já escolhidos, ainda não enviados. */
  files: File[];
  onChange: (files: File[]) => void;
  /** Extensões com ponto, como o `accept` do input pede: `[".pdf", ".png"]`. */
  accept: string[];
  maxFiles: number;
  maxSizeMb: number;
  disabled?: boolean;
  className?: string;
}

export function FileUpload({
  files,
  onChange,
  accept,
  maxFiles,
  maxSizeMb,
  disabled = false,
  className,
}: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [arrastando, setArrastando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const validarEAcrescentar = useCallback(
    (chegando: File[]) => {
      setErro(null);
      const validos: File[] = [];
      for (const f of chegando) {
        const ext = "." + f.name.split(".").pop()?.toLowerCase();
        if (!accept.includes(ext)) {
          setErro(`Tipo não permitido: ${f.name}`);
          continue;
        }
        if (f.size > maxSizeMb * 1024 * 1024) {
          setErro(`Arquivo muito grande (máx ${maxSizeMb} MB): ${f.name}`);
          continue;
        }
        // Mesmo nome e mesmo tamanho já na lista: não duplica.
        if (!files.find((x) => x.name === f.name && x.size === f.size)) {
          validos.push(f);
        }
      }
      onChange([...files, ...validos].slice(0, maxFiles));
    },
    [files, onChange, accept, maxFiles, maxSizeMb],
  );

  return (
    <div className={cn("space-y-3", className)}>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setArrastando(true);
        }}
        onDragLeave={() => setArrastando(false)}
        onDrop={(e) => {
          e.preventDefault();
          setArrastando(false);
          if (!disabled) validarEAcrescentar(Array.from(e.dataTransfer.files));
        }}
        onClick={() => !disabled && inputRef.current?.click()}
        className={cn(
          "flex flex-col items-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-center transition-all",
          disabled
            ? "cursor-not-allowed opacity-50 border-borda"
            : arrastando
              ? "cursor-pointer border-action bg-action-tint"
              : "cursor-pointer border-borda-control hover:border-action hover:bg-action-tint",
        )}
      >
        <Icon name="tag" size={20} className="text-conteudo-muted" />
        <div>
          <p className="text-sm text-conteudo-muted">
            Arraste arquivos aqui ou{" "}
            <span className="font-medium text-conteudo-link">
              clique para selecionar
            </span>
          </p>
          <p className="mt-0.5 text-xs text-conteudo-muted">
            Máx {maxFiles} arquivos · {maxSizeMb} MB cada
          </p>
        </div>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={accept.join(",")}
          disabled={disabled}
          className="hidden"
          onChange={(e) => {
            if (e.target.files) validarEAcrescentar(Array.from(e.target.files));
            // Sem isto, escolher o mesmo arquivo duas vezes seguidas não
            // dispara `change` — o valor não mudou.
            e.target.value = "";
          }}
        />
      </div>

      {erro && <p className="text-xs text-on-tint-danger">{erro}</p>}

      {files.length > 0 && (
        <ul className="space-y-1.5">
          {files.map((f, i) => (
            <li
              key={`${f.name}-${f.size}-${i}`}
              className="flex items-center gap-3 rounded-lg border border-borda bg-surface-elevated px-3 py-2"
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-action-tint text-[9px] font-bold text-conteudo-link">
                {(f.name.split(".").pop() ?? "?").toUpperCase().slice(0, 4)}
              </span>
              <span className="flex-1 truncate text-sm text-conteudo">
                {f.name}
              </span>
              <span className="shrink-0 text-xs text-conteudo-muted">
                {(f.size / 1024 / 1024).toFixed(1)} MB
              </span>
              <button
                type="button"
                aria-label={`Remover ${f.name}`}
                onClick={() => onChange(files.filter((_, j) => j !== i))}
                className="shrink-0 cursor-pointer text-conteudo-muted transition-colors hover:text-on-tint-danger"
              >
                <Icon name="close" size={16} strokeWidth={2} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
