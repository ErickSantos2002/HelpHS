import { useEffect, useRef, useState } from "react";

import { getApiError } from "./apiError";

/**
 * Uma carga de dados com estado PRÓPRIO: carregando, pronta ou com falha (F1-B-03b).
 *
 * Os painéis carregavam tudo num `Promise.all`: uma chamada que falhasse
 * derrubava a página inteira, o erro nunca era limpo e o seletor de período,
 * que só existia na tela de sucesso, sumia junto. Cada bloco agora tem uma
 * carga sua, e a falha de um não toca no outro.
 *
 * Três garantias, e cada uma é um defeito que existia:
 *
 * - **Resposta velha não sobrescreve a nova.** Ao trocar de período, a
 *   resposta do período anterior que chegar atrasada é descartada — o efeito
 *   da carga antiga já foi encerrado quando ela chega.
 * - **Dado velho não aparece como atual.** Uma carga nova zera os dados antes
 *   de pedir: enquanto o período novo carrega, a tela mostra que está
 *   carregando, e não os números do período anterior.
 * - **Falha não vira número.** Em falha, `dados` é `null` e `erro` traz o texto
 *   do `getApiError`; quem desenha mostra o aviso, nunca um zero inventado.
 *
 * `carregar` é lido no momento da carga, não é dependência: quem chama passa
 * uma função nova a cada render, e o que decide recarregar é `chave` (por
 * exemplo, o intervalo de datas). `carregar === null` desliga a carga — a aba
 * que não está à vista não pede nada.
 */

export type FaseDaCarga = "ocioso" | "carregando" | "pronto" | "falha";

export interface Carga<T> {
  fase: FaseDaCarga;
  dados: T | null;
  erro: string | null;
  /** Pede de novo com a mesma chave. */
  tentarDeNovo: () => void;
}

interface Estado<T> {
  fase: FaseDaCarga;
  dados: T | null;
  erro: string | null;
}

export function useCarga<T>(
  carregar: (() => Promise<T>) | null,
  chave: string,
  mensagemPadrao = "Não foi possível carregar os dados.",
): Carga<T> {
  const ativo = carregar !== null;
  const [estado, setEstado] = useState<Estado<T>>({
    fase: ativo ? "carregando" : "ocioso",
    dados: null,
    erro: null,
  });
  const [tentativa, setTentativa] = useState(0);
  const funcao = useRef(carregar);
  funcao.current = carregar;
  const padrao = useRef(mensagemPadrao);
  padrao.current = mensagemPadrao;

  useEffect(() => {
    const atual = funcao.current;
    if (!atual) {
      setEstado({ fase: "ocioso", dados: null, erro: null });
      return;
    }
    let vigente = true;
    setEstado({ fase: "carregando", dados: null, erro: null });
    atual().then(
      (dados) => {
        if (vigente) setEstado({ fase: "pronto", dados, erro: null });
      },
      (err: unknown) => {
        if (vigente) {
          setEstado({ fase: "falha", dados: null, erro: getApiError(err, padrao.current) });
        }
      },
    );
    return () => {
      vigente = false;
    };
  }, [chave, ativo, tentativa]);

  return { ...estado, tentarDeNovo: () => setTentativa((n) => n + 1) };
}
