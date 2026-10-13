import { useEffect, useState } from "react";

import { autoriaDoAnexo } from "../../lib/anexoNaConversa";
import { toastApiError } from "../../lib/toastError";
import {
  downloadAttachment,
  getAttachmentUrl,
  tipoDePrevia,
  type Attachment,
} from "../../services/attachmentService";
import { Badge, Button, Icon, Modal, ModalFooter, Spinner } from "../ui";

/**
 * O visualizador de anexo do chamado.
 *
 * ── O que ele NÃO faz ─────────────────────────────────────────────────
 *
 * Não cria URL nova e não decide acesso. O link vem de `GET /attachments/{id}`
 * a cada abertura — o backend confere o chamado, e para o cliente o anexo
 * alheio é o mesmo 404 do inexistente. O arquivo vem de `/files/{token}`, com
 * CSP `sandbox` e `nosniff`, exatamente como na aba nova de antes.
 *
 * Só pede o link quando há o que mostrar: formato sem prévia vai direto para
 * "Baixar", sem gastar um token que ninguém vai usar.
 *
 * ── Tamanho ───────────────────────────────────────────────────────────
 *
 * `2xl` (768 px), o maior que o `Modal` tem. A auditoria sugeriu um tamanho
 * novo, e ele não entrou: o `Modal` segue o pacote do design system, e um
 * tamanho que só existe aqui seria divergência a registrar como emenda. Fica
 * como pendência, não como gambiarra de `className` (o `cn()` só concatena, e
 * dois `max-w-*` brigariam pela ordem do CSS).
 */

type Estado =
  | { fase: "sem-previa" }
  | { fase: "carregando" }
  | { fase: "pronto"; url: string }
  | { fase: "indisponivel" }
  | { fase: "falha" };

function status(err: unknown): number | undefined {
  return (err as { response?: { status?: number } })?.response?.status;
}

export function AttachmentPreviewModal({
  anexo,
  onClose,
}: {
  /** `null` fecha o modal. */
  anexo: Attachment | null;
  onClose: () => void;
}) {
  const [estado, setEstado] = useState<Estado>({ fase: "carregando" });
  const [imagemFalhou, setImagemFalhou] = useState(false);
  const [tentativa, setTentativa] = useState(0);
  const [baixando, setBaixando] = useState(false);

  const id = anexo?.id;
  const tipo = anexo ? tipoDePrevia(anexo.original_name) : "nenhuma";

  useEffect(() => {
    if (!id) return;
    setImagemFalhou(false);
    if (tipo === "nenhuma") {
      setEstado({ fase: "sem-previa" });
      return;
    }
    // `vivo` descarta a resposta de um anexo que já não é o aberto — trocar
    // de anexo depressa não pode pintar o link do anterior.
    let vivo = true;
    setEstado({ fase: "carregando" });
    getAttachmentUrl(id)
      .then((url) => {
        if (vivo) setEstado({ fase: "pronto", url });
      })
      .catch((err) => {
        if (!vivo) return;
        // 404: o anexo saiu (ou, para o cliente, nunca foi dele — a API não
        // distingue, de propósito, e a frase também não).
        setEstado({ fase: status(err) === 404 ? "indisponivel" : "falha" });
      });
    return () => {
      vivo = false;
    };
  }, [id, tipo, tentativa]);

  if (!anexo) return null;

  async function baixar() {
    if (!anexo) return;
    setBaixando(true);
    try {
      await downloadAttachment(anexo.id);
    } catch (err) {
      toastApiError(err, "Não foi possível baixar o anexo.");
    } finally {
      setBaixando(false);
    }
  }

  const nome = anexo.original_name;
  const tamanho = `${(anexo.size_bytes / 1024 / 1024).toFixed(1)} MB`;
  const tentarDeNovo = (
    <Button
      variant="secondary"
      size="sm"
      onClick={() => setTentativa((n) => n + 1)}
      icon={<Icon name="refresh" size={14} strokeWidth={2} />}
    >
      Tentar de novo
    </Button>
  );

  return (
    <Modal open onClose={onClose} title={nome} size="2xl">
      <p className="-mt-1 mb-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-conteudo-muted">
        <span>{autoriaDoAnexo(anexo)}</span>
        <span aria-hidden="true">·</span>
        <span>{tamanho}</span>
        {!anexo.virus_scanned && (
          <Badge
            variant="warning"
            title="O antivírus estava indisponível quando este arquivo foi enviado, e ele foi gravado sem verificação."
          >
            não verificado
          </Badge>
        )}
      </p>

      <div className="flex min-h-[12rem] items-center justify-center rounded-lg border border-borda bg-surface-elevated/40">
        {estado.fase === "carregando" && (
          <div className="flex flex-col items-center gap-2 py-10 text-sm text-conteudo-muted">
            <Spinner />
            <span>Carregando o anexo…</span>
          </div>
        )}

        {estado.fase === "sem-previa" && (
          <div className="flex flex-col items-center gap-2 px-6 py-10 text-center text-sm text-conteudo-muted">
            <Icon name="document" size={28} strokeWidth={1.5} />
            <p>Este formato não tem visualização no navegador. Baixe o arquivo para abrir.</p>
          </div>
        )}

        {estado.fase === "indisponivel" && (
          <div className="flex flex-col items-center gap-2 px-6 py-10 text-center text-sm text-conteudo-muted">
            <Icon name="warning" size={28} strokeWidth={1.5} />
            <p>Este anexo não está mais disponível. Ele pode ter sido removido.</p>
          </div>
        )}

        {estado.fase === "falha" && (
          <div className="flex flex-col items-center gap-3 px-6 py-10 text-center text-sm text-conteudo-muted">
            <p>Não foi possível carregar o anexo.</p>
            {tentarDeNovo}
          </div>
        )}

        {estado.fase === "pronto" && imagemFalhou && (
          <div className="flex flex-col items-center gap-3 px-6 py-10 text-center text-sm text-conteudo-muted">
            <p>
              O arquivo não pôde ser exibido. Ele pode ter sido removido do servidor, ou o
              link expirou.
            </p>
            {tentarDeNovo}
          </div>
        )}

        {estado.fase === "pronto" && !imagemFalhou && tipo === "imagem" && (
          <img
            src={estado.url}
            alt={nome}
            referrerPolicy="no-referrer"
            onError={() => setImagemFalhou(true)}
            className="max-h-[65vh] max-w-full object-contain"
          />
        )}

        {estado.fase === "pronto" && (tipo === "pdf" || tipo === "texto") && (
          // Sem atributo `sandbox` no quadro: quem isola o conteúdo é a CSP
          // `sandbox` que o `/files` manda em todo arquivo. Um `sandbox` aqui
          // ainda bloquearia o visualizador de PDF do navegador.
          <iframe
            src={estado.url}
            title={`Visualização de ${nome}`}
            referrerPolicy="no-referrer"
            className="h-[65vh] w-full rounded-lg bg-white"
          />
        )}
      </div>

      {/* Sem "Fechar" aqui: o X do `Modal` já se chama "Fechar", e dois
          controles com o mesmo nome acessível não deixam escolher. Fecha pelo
          X e pelo Escape, como toda modal do sistema. */}
      <ModalFooter>
        <Button
          onClick={baixar}
          loading={baixando}
          disabled={estado.fase === "indisponivel"}
          aria-label={`Baixar ${nome}`}
          icon={<Icon name="download" size={14} strokeWidth={2} />}
        >
          Baixar
        </Button>
      </ModalFooter>
    </Modal>
  );
}
