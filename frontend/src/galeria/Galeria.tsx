import { useState } from "react";
import { Alert } from "../components/ui/Alert";
import { Avatar } from "../components/ui/Avatar";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, CardHeader, CardTitle } from "../components/ui/Card";
import { Checkbox } from "../components/ui/Checkbox";
import { Input } from "../components/ui/Input";
import { Pagination } from "../components/ui/Pagination";
import { Select } from "../components/ui/Select";
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
    <div className="min-h-screen bg-background p-6">
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
        <SlaChip label="Resposta" dueAt={new Date(Date.now() + 9e6).toISOString()} breached={false} />
        <SlaChip label="Resolução" dueAt={new Date(Date.now() - 9e6).toISOString()} breached />
        <SlaChip
          label="Resposta"
          dueAt={new Date(Date.now() - 9e6).toISOString()}
          breached={false}
          respondedAt={new Date().toISOString()}
        />
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
