import { Alert, Button, Icon } from "../ui";

/**
 * O aviso de que UM bloco do painel não carregou, com o caminho de volta (F1-B-03b).
 *
 * Fica no lugar do bloco, e não da página: o resto do painel e o seletor de
 * período continuam funcionando. O texto é o do `getApiError` — a pessoa lê o
 * motivo que a API deu ("A data final não pode estar no futuro."), e não um
 * genérico. O botão pede de novo a mesma coisa; trocar de período também
 * limpa o aviso, porque a carga nova recomeça do zero.
 */
export function FalhaDoBloco({
  titulo,
  erro,
  onTentarDeNovo,
}: {
  titulo: string;
  erro: string | null;
  onTentarDeNovo: () => void;
}) {
  return (
    <Alert variant="danger" title={titulo}>
      <p>{erro ?? "Não foi possível carregar os dados."}</p>
      <Button
        variant="secondary"
        size="sm"
        className="mt-2"
        onClick={onTentarDeNovo}
        icon={<Icon name="refresh" size={14} strokeWidth={2} />}
      >
        Tentar de novo
      </Button>
    </Alert>
  );
}
