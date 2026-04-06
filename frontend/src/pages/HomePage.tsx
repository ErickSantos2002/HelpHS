import {
  Avatar,
  Badge,
  Button,
  Card,
  CardHeader,
  CardTitle,
  Input,
  PriorityBadge,
  Spinner,
  StatusBadge,
} from "../components/ui";

export default function HomePage() {
  return (
    <div className="min-h-screen bg-background p-8 space-y-10">
      {/* Header */}
      <div className="flex items-center gap-3">
        <span className="w-3 h-3 rounded-full bg-primary animate-pulse" />
        <h1 className="text-2xl font-bold text-primary">
          HelpHS — Design System
        </h1>
      </div>

      {/* Buttons */}
      <Card>
        <CardHeader>
          <CardTitle>Button</CardTitle>
        </CardHeader>
        <div className="flex flex-wrap gap-3">
          <Button variant="primary">Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="danger">Danger</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="primary" size="sm">
            Small
          </Button>
          <Button variant="primary" size="lg">
            Large
          </Button>
          <Button variant="primary" loading>
            Loading
          </Button>
          <Button variant="primary" disabled>
            Disabled
          </Button>
        </div>
      </Card>

      {/* Inputs */}
      <Card>
        <CardHeader>
          <CardTitle>Input</CardTitle>
        </CardHeader>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-xl">
          <Input label="E-mail" placeholder="email@empresa.com" />
          <Input label="Senha" type="password" placeholder="••••••••" />
          <Input label="Com erro" error="Campo obrigatório" placeholder="..." />
          <Input
            label="Com hint"
            hint="Mínimo 8 caracteres"
            placeholder="Senha"
          />
          <Input placeholder="Sem label" />
          <Input
            label="Desabilitado"
            disabled
            value="Valor fixo"
            onChange={() => {}}
          />
        </div>
      </Card>

      {/* Badges */}
      <Card>
        <CardHeader>
          <CardTitle>Badge — Status &amp; Prioridade</CardTitle>
        </CardHeader>
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <StatusBadge status="open" />
            <StatusBadge status="in_progress" />
            <StatusBadge status="awaiting_client" />
            <StatusBadge status="awaiting_technical" />
            <StatusBadge status="resolved" />
            <StatusBadge status="closed" />
            <StatusBadge status="cancelled" />
          </div>
          <div className="flex flex-wrap gap-2">
            <PriorityBadge priority="critical" />
            <PriorityBadge priority="high" />
            <PriorityBadge priority="medium" />
            <PriorityBadge priority="low" />
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="primary">Primary</Badge>
            <Badge variant="secondary">Secondary</Badge>
            <Badge variant="info">Info</Badge>
            <Badge variant="warning">Warning</Badge>
            <Badge variant="danger">Danger</Badge>
            <Badge variant="muted">Muted</Badge>
          </div>
        </div>
      </Card>

      {/* Spinner */}
      <Card>
        <CardHeader>
          <CardTitle>Spinner</CardTitle>
        </CardHeader>
        <div className="flex items-center gap-6">
          <Spinner size="sm" />
          <Spinner size="md" />
          <Spinner size="lg" />
        </div>
      </Card>

      {/* Avatar */}
      <Card>
        <CardHeader>
          <CardTitle>Avatar</CardTitle>
        </CardHeader>
        <div className="flex items-end gap-4">
          <Avatar name="Erick Santos" size="xs" />
          <Avatar name="Erick Santos" size="sm" />
          <Avatar name="Erick Santos" size="md" />
          <Avatar name="Erick Santos" size="lg" />
          <Avatar name="Maria Oliveira" size="md" />
          <Avatar name="João Silva" size="md" />
          <Avatar name="Ana Costa" size="md" />
        </div>
      </Card>
    </div>
  );
}
