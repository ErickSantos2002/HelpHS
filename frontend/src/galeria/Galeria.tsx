import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { Alert } from "../components/ui/Alert";
import { Avatar } from "../components/ui/Avatar";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, CardHeader, CardTitle } from "../components/ui/Card";
import { Icon } from "../components/ui/Icon";
import { Checkbox } from "../components/ui/Checkbox";
import { Input } from "../components/ui/Input";
import { KpiCard } from "../components/ui/KpiCard";
import { Pagination } from "../components/ui/Pagination";
import { RadioCards } from "../components/ui/RadioCards";
import { PRIORIDADE, PRIORIDADES } from "../lib/prioridade";
import { Select } from "../components/ui/Select";
import { SelectMenu } from "../components/ui/SelectMenu";
import { Selector } from "../components/ui/Selector";
import { SlaChip } from "../components/ui/SlaChip";
import { Switch } from "../components/ui/Switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "../components/ui/Table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/Tabs";
import { Textarea } from "../components/ui/Textarea";

/**
 * Galeria de componentes do Checkpoint 2.
 *
 * Existe por causa de um erro concreto: na Fase 7 a medição de tokens do
 * `Badge` mostrou **zero** reprovações, e o componente renderizado tinha
 * **sete em quarenta e duas**. Medir o token responde "esta cor sobre aquela
 * passa?"; só a galeria responde "o que este componente PINTA passa?".
 *
 * Não é uma página do app: é uma entrada própria do Vite, sem roteador, sem
 * sessão e sem backend. O que ela precisa é do CSS real — tokens do pacote mais
 * Tailwind compilado —, e é isso que a separa de um teste em jsdom, onde
 * `getComputedStyle` não resolve classe nenhuma.
 *
 * O `e2e/galeria.spec.ts` a visita nos dois temas, lê o estilo COMPUTADO de
 * cada elemento marcado com `data-medir` e calcula o contraste real.
 */

const BOTOES = ["primary", "secondary", "danger", "success", "ghost"] as const;
const SELOS = [
  "primary",
  "secondary",
  "danger",
  "warning",
  "info",
  "success",
  "muted",
] as const;
const AVISOS = ["info", "success", "warning", "danger"] as const;

/**
 * Quantos blocos esta galeria mostra.
 *
 * É o **marcador de identidade** da página, publicado no DOM como
 * `data-galeria`. Serve a duas checagens que a medição faz antes de capturar
 * qualquer pixel, e que existem por dois incidentes distintos do mesmo dia:
 *
 * 1. **A página é a galeria?** O `galeria.html` é servido pelo mesmo servidor
 *    de desenvolvimento que serve a aplicação, e um servidor subido ANTES do
 *    arquivo existir devolve a 404 da SPA — com o mesmo CSS, o que faz o
 *    canário de classes passar. Aquela vez só a espera pelo seletor caiu, por
 *    tempo esgotado, e "tempo esgotado" não diz o que houve.
 *
 * 2. **É a galeria DESTE código?** A medição compara este número, lido do
 *    navegador, com a constante lida do repositório. Servidor servindo pacote
 *    velho mostra a galeria de antes, com os blocos de antes, e os dois
 *    números divergem. Contar apenas os blocos do próprio DOM não pegaria
 *    nada: pacote velho é coerente consigo mesmo.
 *
 * Ao acrescentar um `Bloco`, ajuste este número — a suíte cobra.
 */
/*
  18 depois do merge com a `main`, e o caminho até aqui merece nota porque o
  git NÃO acusa: a `main` subiu este número de 16 para 17 ao acrescentar o
  bloco "Button como link", e esta frente subiu de 16 para 17 ao acrescentar o
  bloco "SelectMenu". Os dois lados gravaram o MESMO texto (`= 17`), então a
  mesclagem passou limpa — com dezoito blocos no arquivo e dezessete na conta.
  Quem acusaria é só o `e2e/galeria.spec.ts`, que roda por `workflow_dispatch`.
*/
export const AMOSTRAS = 18;

/** `texto` cobra 4,5:1; `grafico` cobra 3:1 (WCAG 1.4.11). */
function Bloco({
  nome,
  piso = "texto",
  children,
}: {
  nome: string;
  piso?: "texto" | "grafico";
  children: React.ReactNode;
}) {
  return (
    <section className="mb-8" data-bloco={nome} data-piso={piso}>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-conteudo-muted">
        {nome}
      </h2>
      <div className="flex flex-wrap items-start gap-3">{children}</div>
    </section>
  );
}

/** Expedientes de mentira, so para a galeria desenhar os estados do chip. */
const EXPEDIENTE_ABERTO = {
  agora: new Date().toISOString(),
  aberto: true,
  proxima_virada: new Date(Date.now() + 3 * 3600_000).toISOString(),
  fuso: "America/Sao_Paulo",
};

const EXPEDIENTE_FECHADO = { ...EXPEDIENTE_ABERTO, aberto: false };

export function Galeria() {
  const [escuro, setEscuro] = useState(
    () => document.documentElement.classList.contains("dark"),
  );
  const [aba, setAba] = useState("um");

  function alternar() {
    const proximo = !escuro;
    document.documentElement.classList.toggle("dark", proximo);
    setEscuro(proximo);
  }

  return (
    <div className="min-h-screen bg-surface-base p-6" data-galeria={AMOSTRAS}>
      <header className="mb-8 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-conteudo-heading">
          Galeria de componentes — Checkpoint 2
        </h1>
        <Button variant="secondary" onClick={alternar} data-testid="alternar-tema">
          Tema: {escuro ? "escuro" : "claro"}
        </Button>
      </header>

      <Bloco nome="Button">
        {BOTOES.map((v) => (
          <Button key={v} variant={v} data-medir>
            {v}
          </Button>
        ))}
        {BOTOES.map((v) => (
          <Button key={v + "-off"} variant={v} disabled data-medir>
            {v} off
          </Button>
        ))}
      </Bloco>

      {/*
        Cada variante duas vezes, lado a lado: como `<button>` e como `<a>`.

        O `Button` com `to` vira link, e link herda as regras de `a` do
        `base.css` do pacote — que estão fora do Tailwind e, no hover, têm
        especificidade maior que uma classe só. A regra que o par prova é que o
        destino muda o ELEMENTO e não a APARÊNCIA: o `e2e/galeria.spec.ts` passa
        o mouse nos dois e exige a mesma pintura.

        O roteador de memória existe só porque `Link` exige um.
      */}
      <Bloco nome="Button como link">
        <MemoryRouter>
          {BOTOES.map((v) => (
            <div key={v} className="flex gap-2">
              <Button variant={v} data-par={"botao-" + v}>
                {v}
              </Button>
              <Button variant={v} to="/destino" data-par={"link-" + v}>
                {v} link
              </Button>
            </div>
          ))}
        </MemoryRouter>
      </Bloco>

      <Bloco nome="Badge">
        {SELOS.map((v) => (
          <Badge key={v} variant={v} data-medir>
            {v}
          </Badge>
        ))}
      </Bloco>

      <Bloco nome="Alert">
        {AVISOS.map((v) => (
          <div key={v} className="w-72">
            <Alert variant={v} title={v} onDismiss={() => {}}>
              <span data-medir>corpo do aviso {v}</span>
            </Alert>
          </div>
        ))}
      </Bloco>

      <Bloco nome="SlaChip">
        {/* O chip conta tempo ÚTIL, e quem calcula é o backend. A galeria monta
            um expediente de mentira para desenhar os quatro estados: correndo,
            congelado fora do expediente, vencido e respondido. */}
        <SlaChip
          label="Resposta"
          restanteMin={251}
          venceEm={new Date(Date.now() + 9e6).toISOString()}
          expediente={EXPEDIENTE_ABERTO}
          breached={false}
        />
        <SlaChip
          label="Resolução"
          restanteMin={692}
          venceEm={new Date(Date.now() + 9e6).toISOString()}
          expediente={EXPEDIENTE_FECHADO}
          breached={false}
        />
        <SlaChip
          label="Resolução"
          restanteMin={0}
          venceEm={new Date(Date.now() - 9e6).toISOString()}
          expediente={EXPEDIENTE_ABERTO}
          breached
        />
        <SlaChip
          label="Resposta"
          restanteMin={0}
          venceEm={new Date(Date.now() - 9e6).toISOString()}
          expediente={EXPEDIENTE_ABERTO}
          breached={false}
          respondedAt={new Date().toISOString()}
        />
      </Bloco>

      <Bloco nome="KpiCard">
        {(["neutral", "primary", "info", "success", "warning", "danger"] as const).map(
          (tone) => (
            <div key={tone} className="w-56">
              <KpiCard
                label={tone}
                value={42}
                sub="últimos 7 dias"
                tone={tone}
                icon={<Icon name="ticket" size={20} />}
              />
            </div>
          ),
        )}
      </Bloco>

      <Bloco nome="Campos">
        <div className="w-64">
          <Input label="Título" placeholder="Descreva o problema" data-medir />
        </div>
        <div className="w-64">
          <Input label="Com erro" error="Informe o título" data-medir />
        </div>
        <div className="w-64">
          <Input label="Com dica" hint="Máximo de 80 caracteres" data-medir />
        </div>
        <div className="w-64">
          <Textarea label="Descrição" placeholder="Detalhe" data-medir />
        </div>
        <div className="w-64">
          <Select
            label="Prioridade"
            options={[{ value: "a", label: "Alta" }]}
            placeholder="Selecione"
            data-medir
          />
        </div>
      </Bloco>

      {/*
        O seletor de lista fechada com painel NOSSO.

        Ele e o `Select` nativo do bloco acima são o mesmo papel em duas
        encarnações: a divisão do trabalho continua sendo a de quem escreve a
        lista — fechada no código fica aqui, lista que vem da rede e cresce vai
        para o `Selector variant="filter"`, logo abaixo. O que mudou foi só o
        controle deste lado, e a amostra do nativo fica onde está enquanto o
        primitivo existir: o que a galeria mede é o que ainda pode ser pintado.

        A amostra fica FECHADA de propósito. O painel mora num portal em
        `document.body`, fora de `[data-bloco]`, e a medição só enxerga o que
        está dentro do bloco — aberta, ela mediria o gatilho e nada mais, com a
        lista por cima dos vizinhos. Fechado, o gatilho é o que há para medir:
        a borda de repouso, o rótulo e o texto da opção escolhida.

        O `data-medir` vai no INVÓLUCRO, e não no primitivo: o `SelectMenu`
        não espalha prop que não conhece, então ali ele não chegaria ao DOM —
        e atributo que some em silêncio é pior que atributo nenhum, porque
        quem lê acha que está marcado. Medido hoje: ninguém consulta esse
        marcador (nem o `galeria.spec.ts`, nem os scripts de captura); ele é
        simetria com as outras amostras do arquivo.
      */}
      <Bloco nome="SelectMenu">
        <div className="w-64" data-medir>
          <SelectMenu
            label="Prioridade"
            value="a"
            onChange={() => {}}
            options={[{ value: "a", label: "Alta" }]}
            placeholder="Selecione"
          />
        </div>
      </Bloco>

      <Bloco nome="Selector">
        <div className="w-64">
          <Selector
            variant="form"
            label="Situação"
            value="aberto"
            onChange={() => {}}
            options={[{ value: "aberto", label: "Aberto", dot: "#22c55e" }]}
          />
        </div>
        <Selector
          variant="filter"
          value=""
          onChange={() => {}}
          options={[{ value: "aberto", label: "Aberto" }]}
        />
      </Bloco>

      {/*
        As quatro cores de PRIORIDADE em gráfico, sobre as três superfícies.

        Elas não saem da `--chart-*`: prioridade tem significado próprio, já
        pintado na interface inteira, e um gráfico de prioridade com cores de
        categoria obrigaria a consultar a legenda para algo que o resto do
        sistema ensina pela cor.

        Mas por serem preenchimento elas devem 3:1, e é aqui que isso se prova.
        Foi assim que apareceu que `--color-warning-500` dava 1,96 no claro — e
        o módulo passou a apontar para `--fill-warning`, que inverte por tema.
      */}
      <Bloco nome="Prioridade em gráfico">
        {(
          [
            ["base", "bg-surface-base"],
            ["surface", "bg-surface"],
            ["elevada", "bg-surface-elevated"],
          ] as const
        ).map(([nome, classe]) => (
          <div
            key={nome}
            data-superficie={"prio-" + nome}
            className={"flex items-center gap-2 rounded-lg p-3 " + classe}
          >
            <span className="w-16 text-xs text-conteudo">{nome}</span>
            {PRIORIDADES.map((p) => (
              <span
                key={p}
                data-chart={p}
                title={PRIORIDADE[p].rotulo}
                className="block h-8 w-8 rounded"
                style={{ background: PRIORIDADE[p].grafico }}
              />
            ))}
          </div>
        ))}
      </Bloco>

      {/*
        As 36 células da E16-b: seis séries sobre as TRÊS superfícies, e o
        arquivo se visita nos dois temas — 6 × 3 × 2.

        O preenchimento sai de `var(--chart-N)` e não de um hexadecimal escrito
        aqui, de propósito: o que precisa ser medido é o que o TOKEN entrega na
        tela, não o valor que a emenda diz ter. Se a recópia do `colors.css`
        não tivesse chegado, um hexadecimal cravado aqui mediria a paleta certa
        sobre um sistema que ainda serve a antiga.

        O piso é 3:1 (WCAG 1.4.11): série é forma, não texto.
      */}
      <Bloco nome="Gráfico E16-b">
        {(
          [
            ["base", "bg-surface-base"],
            ["surface", "bg-surface"],
            ["elevada", "bg-surface-elevated"],
          ] as const
        ).map(([nome, classe]) => (
          <div
            key={nome}
            data-superficie={nome}
            className={"flex items-center gap-2 rounded-lg p-3 " + classe}
          >
            <span className="w-16 text-xs text-conteudo">{nome}</span>
            {[1, 2, 3, 4, 5, 6].map((n) => (
              <span
                key={n}
                data-chart={n}
                className="block h-8 w-8 rounded"
                style={{ background: "var(--chart-" + n + ")" }}
              />
            ))}
          </div>
        ))}
      </Bloco>

      {/*
        As seis tonalidades ESCOLHIDAS, uma por cartão.

        A galeria é o único lugar onde estas classes se provam: `peer-checked:`
        e a variante descendente `[&_[data-ponto]]` não existem em jsdom, e uma
        delas que o Tailwind não gere deixa o cartão escolhido idêntico ao não
        escolhido — sem erro e sem aviso.

        Cada grupo mostra a opção escolhida primeiro, porque é o par
        tinta/`on-tint` dela que precisa ser medido.
      */}
      <Bloco nome="RadioCards">
        {(["primary", "info", "success", "warning", "danger", "muted"] as const).map(
          (tone) => (
            <div key={tone} className="w-40">
              <RadioCards
                name={"galeria-" + tone}
                label={tone}
                layout="linha"
                value="sim"
                onChange={() => {}}
                options={[
                  { value: "sim", label: "Escolhido", tone },
                  { value: "nao", label: "Livre", tone },
                ]}
              />
            </div>
          ),
        )}
      </Bloco>

      <Bloco nome="Checkbox e Switch" piso="grafico">
        <Checkbox checked onChange={() => {}} label="Marcado" />
        <Checkbox checked={false} onChange={() => {}} label="Vazio" />
        <Checkbox checked={false} indeterminate onChange={() => {}} label="Parcial" />
        <Switch checked onChange={() => {}} label="Ligado" />
        <Switch checked={false} onChange={() => {}} label="Desligado" />
      </Bloco>

      <Bloco nome="Avatar" piso="grafico">
        <Avatar name="Rickelme David" />
        <Avatar name="Erick Dantas" />
        <Avatar name="Ana Paula" />
      </Bloco>

      <Bloco nome="Card">
        <Card className="w-72">
          <CardHeader>
            <CardTitle>Título do cartão</CardTitle>
          </CardHeader>
          <p className="text-sm text-conteudo" data-medir>
            Corpo do cartão, com texto normal.
          </p>
        </Card>
      </Bloco>

      <Bloco nome="Tabs">
        <Tabs value={aba} onChange={setAba}>
          <TabsList>
            <TabsTrigger value="um">Um</TabsTrigger>
            <TabsTrigger value="dois">Dois</TabsTrigger>
          </TabsList>
          <TabsContent value="um">
            <p className="pt-3 text-sm text-conteudo" data-medir>
              Conteúdo da primeira aba.
            </p>
          </TabsContent>
          <TabsContent value="dois">
            <p className="pt-3 text-sm text-conteudo" data-medir>
              Conteúdo da segunda aba.
            </p>
          </TabsContent>
        </Tabs>
      </Bloco>

      <Bloco nome="Table">
        <div className="w-full">
          <Table>
            <TableHead>
              <TableRow>
                <TableHeaderCell sortable sorted="asc" onSort={() => {}}>
                  Título
                </TableHeaderCell>
                <TableHeaderCell>Situação</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableRow clickable onClick={() => {}}>
                <TableCell data-medir>Chamado 42</TableCell>
                <TableCell muted data-medir>
                  secundário
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </Bloco>

      <Bloco nome="Pagination">
        <div className="w-full">
          <Pagination page={2} pageSize={10} total={42} onPageChange={() => {}} />
        </div>
      </Bloco>
    </div>
  );
}
