import { formatCnpj } from "../../lib/documents";
import { Button, Icon, Modal, ModalFooter } from "../ui";
import type { Equipment } from "../../services/productService";

/**
 * O detalhe de um equipamento, para a equipe.
 *
 * Morava dentro da `ProductsPage` e saiu daqui para servir também a tela de
 * Equipamentos, que é só de consulta. A diferença entre as duas é uma prop:
 * sem `onEdit`, o modal não oferece "Editar" — quem mantém o cadastro
 * continua sendo a tela de Produtos.
 */

// ── ActivePill ────────────────────────────────────────────────

/**
 * O selo de ativo/inativo, agora sobre as tintas medidas.
 *
 * Era paleta crua dos dois lados — `emerald-300/50/100/500` no ativo,
 * `slate-100/200/300/400/500` no inativo —, com oito classes `dark:` para
 * inverter à mão o que o token já inverte sozinho. As duas receitas passaram
 * a ser as mesmas do `Badge`: tinta no fundo, o par da tinta no texto, e a
 * cor cheia da rampa a 30% na borda.
 *
 * **O hover mudou de lugar, e é de propósito.** A regra (a) do D8-a proíbe
 * modificador de opacidade sobre as tintas — elas já carregam 15% no token, e
 * `bg-tint-success/20` multiplicaria os dois. Sem `bg-tint-*` mais escuro
 * para onde ir, a resposta ao ponteiro passou para a borda, que é cor cheia e
 * aceita o modificador.
 *
 * O ponto não usa o degrau 500: a E19 mediu `--color-success-500` em 2,54:1
 * como preenchimento no tema claro, abaixo do piso de 3:1 da WCAG 1.4.11. O
 * neutro é `--border-control`, o único que **inverte por tema** — é o mesmo
 * raciocínio que `lib/prioridade.ts` registra para a prioridade baixa.
 *
 * O ponto nunca informa sozinho: o rótulo "Ativo"/"Inativo" vai ao lado, em
 * texto, e é ele que carrega o estado.
 */
export function ActivePill({
  active,
  loading,
  onToggle,
}: {
  active: boolean;
  loading?: boolean;
  onToggle?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={!onToggle || loading}
      title={active ? "Clique para desativar" : "Clique para ativar"}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium transition-colors shrink-0 ${
        active
          ? "border-success/30 bg-tint-success text-on-tint-success hover:border-success/60 cursor-pointer"
          : "border-borda bg-tint-neutral text-on-tint-neutral hover:border-borda-strong cursor-pointer"
      } disabled:cursor-default`}
    >
      {loading ? (
        <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
      ) : (
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${active ? "bg-fill-success" : "bg-borda-control"}`} />
      )}
      {active ? "Ativo" : "Inativo"}
    </button>
  );
}

// ── EquipmentDetailModal ──────────────────────────────────────

function Campo({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] font-semibold uppercase tracking-wide text-conteudo-muted">{rotulo}</span>
      {children}
    </div>
  );
}

/**
 * Responsável e empresa, cada um com o nome do que é.
 *
 * **Responsável, e não "cadastrado por".** `owner_id` é quem responde pelo
 * aparelho HOJE, e a equipe pode trocá-lo na tela de Produtos; o sistema não
 * guarda quem fez o cadastro original, e a tela não inventa essa informação.
 *
 * **Duas empresas, separadas.** A vinculada é a oficial: o vínculo que um
 * admin fez na tela de Grupos. A declarada é o que o responsável digitou no
 * próprio cadastro, e não decide de que empresa ninguém é. Antes o modal
 * mostrava a declarada sob o rótulo "Empresa", como se fosse o vínculo.
 */
export function EquipmentDetailModal({
  equip,
  onClose,
  onEdit,
}: {
  equip: Equipment;
  onClose: () => void;
  /** Ausente = somente leitura: o rodapé não oferece "Editar". */
  onEdit?: () => void;
}) {
  function row(label: string, value?: string | null) {
    if (!value) return null;
    return (
      <Campo rotulo={label}>
        <span className="text-sm text-conteudo break-words">{value}</span>
      </Campo>
    );
  }

  return (
    <Modal open onClose={onClose} title={equip.name}>
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <ActivePill active={equip.is_active} />
          {equip.model && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-surface-elevated border border-borda/50 text-conteudo-muted">
              {equip.model}
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 rounded-xl border border-borda bg-surface-elevated p-4">
          {row("Produto", equip.product_name)}
          {row("Número de série", equip.serial_number)}
          {row("Modelo", equip.model)}
          {row("Localização", equip.location)}
          {row("Descrição", equip.description)}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 rounded-xl border border-borda bg-surface-elevated p-4">
          <Campo rotulo="Responsável">
            {equip.owner_name ? (
              <>
                <span className="text-sm text-conteudo">{equip.owner_name}</span>
                {equip.owner_email && <span className="text-xs text-conteudo-muted">{equip.owner_email}</span>}
              </>
            ) : (
              <span className="text-sm text-conteudo-muted">Sem responsável</span>
            )}
          </Campo>
          <Campo rotulo="Empresa vinculada">
            {equip.linked_company_name ? (
              <span className="text-sm text-conteudo">{equip.linked_company_name}</span>
            ) : (
              <span className="text-sm text-conteudo-muted">Sem empresa vinculada</span>
            )}
          </Campo>
          {equip.company_name && (
            <Campo rotulo="Empresa declarada">
              <span className="text-sm text-conteudo">{equip.company_name}</span>
              {equip.company_cnpj && <span className="text-xs text-conteudo-muted">{formatCnpj(equip.company_cnpj)}</span>}
              <span className="text-xs text-conteudo-muted">Informada pelo responsável no cadastro; não é vínculo.</span>
            </Campo>
          )}
        </div>

        {(equip.created_at || equip.updated_at) && (
          <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-conteudo-muted">
            {equip.created_at && <span>Criado em {new Date(equip.created_at).toLocaleDateString("pt-BR")}</span>}
            {equip.updated_at && <span>Atualizado em {new Date(equip.updated_at).toLocaleDateString("pt-BR")}</span>}
          </div>
        )}
      </div>
      <ModalFooter>
        <Button variant="secondary" onClick={onClose}>Fechar</Button>
        {onEdit && (
          <Button onClick={() => { onClose(); onEdit(); }}><Icon name="edit" size={16} strokeWidth={2} /> Editar</Button>
        )}
      </ModalFooter>
    </Modal>
  );
}
