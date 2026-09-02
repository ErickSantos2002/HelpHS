/**
 * Galeria dos primitivos — ARTEFATO DE DESENVOLVIMENTO. NÃO VAI PARA PRODUÇÃO.
 *
 * Irmã da `GaleriaCasca`, com o mesmo contrato e as mesmas garantias, para o que
 * a seção 26 exige do Checkpoint 2: cada primitivo em todos os seus estados, nos
 * dois temas, numa página só.
 *
 * Diferença para a da casca: esta **não monta contexto nenhum**. Os primitivos
 * da Fase 7 não leem sessão, não fazem requisição e não têm estado assíncrono —
 * então aqui não há usuário falso, não há `AuthContext` e não há rede a
 * interceptar. O script de captura intercepta assim mesmo, e falha se algo
 * escapar; é a mesma rede blindada, só que sobre uma página que não tem o que
 * pedir.
 *
 * Sai na Fase 20, junto com a da casca e com o bloco `DEV` do `App.tsx`.
 *
 *   /galeria-primitivos
 */
import {
  Avatar,
  Badge,
  Card,
  CardHeader,
  CardTitle,
  Icon,
  ICON_PATHS,
  PriorityBadge,
  StatusBadge,
} from "../components/ui";
import type { IconName } from "../components/ui";

/** Seis nomes de uma letra consecutiva cobrem os seis pares do `Avatar`: a cor
 *  sai da soma dos char codes % 6. Não é decorativo — é o que garante que o
 *  screenshot mostre os seis, e não seis vezes o mesmo. */
const SEIS_PARES = ["a", "b", "c", "d", "e", "f"];

const NOMES = ["Ana Ferreira", "Bruno Lima", "Carla Dias"];

function Secao({
  titulo,
  descricao,
  children,
}: {
  titulo: string;
  descricao: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-8">
      <h2 className="text-base font-semibold text-conteudo-heading">
        {titulo}
      </h2>
      <p className="mb-3 mt-0.5 text-xs text-conteudo-muted">{descricao}</p>
      <div className="rounded-xl border border-borda bg-surface p-4">
        {children}
      </div>
    </section>
  );
}

export default function GaleriaPrimitivos() {
  return (
    <div
      className="min-h-screen bg-background p-6"
      data-galeria="primitivos"
    >
      <h1 className="mb-1 text-xl font-semibold text-conteudo-heading">
        Primitivos da Fase 7
      </h1>
      <p className="mb-6 text-sm text-conteudo-muted">
        Avatar, Card, Badge e Icon. Rota de desenvolvimento; sai na Fase 20.
      </p>

      <Secao
        titulo="Avatar — os seis pares"
        descricao="O sexto par é o neutro, que a emenda E4 levou de 4,34:1 para 6,92:1 no tema claro."
      >
        <div className="flex flex-wrap items-center gap-3">
          {SEIS_PARES.map((n, i) => (
            <Avatar key={n} name={n} size="lg" title={`par ${i + 1}`} />
          ))}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          {(["xs", "sm", "md", "lg"] as const).map((s) => (
            <Avatar key={s} name="Ana Ferreira" size={s} />
          ))}
          <span className="text-xs text-conteudo-muted">
            xs 24 · sm 32 · md 40 · lg 48
          </span>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          {NOMES.map((n) => (
            <Avatar key={n} name={n} size="md" />
          ))}
          <span className="text-xs text-conteudo-muted">
            iniciais das duas primeiras palavras
          </span>
        </div>
      </Secao>

      <Secao
        titulo="Badge — as sete variantes"
        descricao="secondary e muted agora falam --on-tint-neutral; warning fala --on-tint-warning. secondary e muted ficaram idênticos: é consequência conhecida, não descuido."
      >
        <div className="flex flex-wrap items-center gap-2">
          {(
            [
              "primary",
              "secondary",
              "muted",
              "info",
              "success",
              "warning",
              "danger",
            ] as const
          ).map((v) => (
            <Badge key={v} variant={v}>
              {v}
            </Badge>
          ))}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          {(
            [
              "open",
              "in_progress",
              "awaiting_client",
              "awaiting_technical",
              "resolved",
              "closed",
              "cancelled",
            ] as const
          ).map((s) => (
            <StatusBadge key={s} status={s} />
          ))}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          {(["critical", "high", "medium", "low"] as const).map((p) => (
            <PriorityBadge key={p} priority={p} />
          ))}
        </div>
      </Secao>

      <Secao
        titulo="Card — os quatro paddings, com cabeçalho"
        descricao="Título em --text-heading (era text-slate-100 cravado); superfície e borda pelos nomes do pacote."
      >
        <div className="grid gap-4 md:grid-cols-2">
          {(["none", "sm", "md", "lg"] as const).map((p) => (
            <Card key={p} padding={p}>
              <CardHeader>
                <CardTitle>padding {p}</CardTitle>
                <Badge variant="muted">selo</Badge>
              </CardHeader>
              <p className="text-sm text-conteudo">
                Corpo do cartão, em --text-body.
              </p>
            </Card>
          ))}
        </div>
      </Secao>

      <Secao
        titulo="Icon — os 25 traçados"
        descricao="Herdam currentColor; 20px e traço 1,75 por padrão. Aqui em três pesos de cor para mostrar a herança."
      >
        <div className="flex flex-wrap items-center gap-3 text-conteudo-heading">
          {(Object.keys(ICON_PATHS) as IconName[]).map((n) => (
            <Icon key={n} name={n} />
          ))}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3 text-conteudo-muted">
          {(Object.keys(ICON_PATHS) as IconName[]).map((n) => (
            <Icon key={n} name={n} size={16} strokeWidth={2} />
          ))}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3 text-action">
          {(Object.keys(ICON_PATHS) as IconName[]).map((n) => (
            <Icon key={n} name={n} size={24} />
          ))}
        </div>
      </Secao>
    </div>
  );
}
