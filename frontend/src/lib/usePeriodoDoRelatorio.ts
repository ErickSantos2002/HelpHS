import { useState } from "react";

import {
  PRESET_PADRAO,
  chaveDoIntervalo,
  datasPersonalizadasIniciais,
  descreveIntervalo,
  resolvePeriodo,
  type IntervaloDeDatas,
  type PresetDePeriodo,
} from "./periodoRelatorio";

/**
 * O estado do seletor de período e o intervalo que ele pede (F1-B-03b).
 *
 * `intervalo` é `null` quando o "Personalizado" está inválido: nesse caso a
 * tela não pede nada e mostra `erro`. `chave` muda só quando os DIAS mudam —
 * é o que as cargas usam para decidir recarregar.
 */
export interface PeriodoDoRelatorio {
  preset: PresetDePeriodo;
  setPreset: (p: PresetDePeriodo) => void;
  inicio: string;
  fim: string;
  setInicio: (v: string) => void;
  setFim: (v: string) => void;
  intervalo: IntervaloDeDatas | null;
  erro: string | null;
  chave: string;
  descricao: string | null;
}

export function usePeriodoDoRelatorio(
  inicial: PresetDePeriodo = PRESET_PADRAO,
): PeriodoDoRelatorio {
  const [preset, setPreset] = useState<PresetDePeriodo>(inicial);
  const [datas, setDatas] = useState(datasPersonalizadasIniciais);

  const resolvido = resolvePeriodo(preset, {
    inicio: datas.start_date,
    fim: datas.end_date,
  });
  const intervalo = resolvido.ok ? resolvido.intervalo : null;

  return {
    preset,
    setPreset,
    inicio: datas.start_date,
    fim: datas.end_date,
    setInicio: (v) => setDatas((d) => ({ ...d, start_date: v })),
    setFim: (v) => setDatas((d) => ({ ...d, end_date: v })),
    intervalo,
    erro: resolvido.ok ? null : resolvido.erro,
    chave: chaveDoIntervalo(intervalo),
    descricao: intervalo ? descreveIntervalo(intervalo) : null,
  };
}
