import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Alert } from "../ui";
import { useAuth } from "../../contexts/AuthContext";
import { getExibicaoDaFoto, type ExibicaoDaFoto } from "../../services/userService";
import {
  EVENTO_EXIBICAO_DA_FOTO,
  avisoFoiDispensado,
  dispensaAviso,
} from "../../lib/exibicaoDaFoto";

/**
 * O aviso de lançamento da foto para outras pessoas (Fase 3B).
 *
 * Não bloqueia nada: é um `Alert` no topo do conteúdo, não um modal nem uma
 * guarda de rota. Entrar, abrir chamado e conversar seguem iguais com ele
 * aberto, fechado ou ignorado. Não dispara e-mail e não usa as notificações.
 *
 * **Fechar não autoriza.** Fechar só guarda, neste navegador, que a pessoa já
 * viu — a escolha continua desligada até ela mudar no perfil.
 *
 * Só aparece quando há o que escolher: a opção disponível e ainda não
 * autorizada. Sai sozinho quando o perfil confirma a autorização, e não
 * aparece na própria página do perfil, onde a opção já está à vista. Falhar ao
 * ler o estado é motivo para NÃO mostrar: um aviso sobre uma opção que talvez
 * nem esteja disponível confundiria mais do que ajudaria.
 */
export function AvisoDaFotoParaTerceiros() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const [estado, setEstado] = useState<ExibicaoDaFoto | null>(null);
  const [dispensado, setDispensado] = useState(false);

  useEffect(() => {
    if (!user) return;
    let ativo = true;
    getExibicaoDaFoto()
      .then((e) => {
        if (ativo) setEstado(e);
      })
      .catch(() => {
        if (ativo) setEstado(null);
      });
    return () => {
      ativo = false;
    };
  }, [user]);

  useEffect(() => {
    function aoMudar(evento: Event) {
      setEstado((evento as CustomEvent<ExibicaoDaFoto>).detail);
    }
    window.addEventListener(EVENTO_EXIBICAO_DA_FOTO, aoMudar);
    return () => window.removeEventListener(EVENTO_EXIBICAO_DA_FOTO, aoMudar);
  }, []);

  if (!user || !estado || !estado.disponivel || estado.autorizada || !estado.aviso) return null;
  if (pathname === "/profile") return null;
  const versao = estado.aviso.versao;
  if (dispensado || avisoFoiDispensado(user.id, versao)) return null;

  return (
    <Alert
      variant="info"
      // Já está na tela quando a página abre: região viva anunciaria fora de
      // ordem (emenda E12).
      live={false}
      title="Novidade: sua foto para outras pessoas"
      className="mb-4"
      onDismiss={() => {
        dispensaAviso(user.id, versao);
        setDispensado(true);
      }}
    >
      Agora você pode escolher se a sua foto de perfil aparece para os outros
      participantes dos seus atendimentos. É opcional e começa desligado: sem a
      sua permissão, eles continuam vendo as suas iniciais. Fechar este aviso não
      muda nada.{" "}
      <Link
        to="/profile#foto-para-outras-pessoas"
        className="font-medium underline underline-offset-2"
      >
        Ver a opção no meu perfil
      </Link>
    </Alert>
  );
}
