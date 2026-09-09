import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ComponentProps } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AA, contraste } from "../helpers/contraste";

const navegar = vi.fn();
const sair = vi.fn();
const trocarTema = vi.fn();

/** O estado que as fábricas içadas leem. Só os campos mudam entre os casos. */
const SESSAO: {
  usuario: { name: string; email: string; role: string; avatar_url: string | null } | null;
  tema: "claro" | "escuro";
} = {
  usuario: {
    name: "Rita Andrade",
    email: "rita@exemplo.com",
    role: "technician",
    avatar_url: null,
  },
  tema: "claro",
};

vi.mock("react-router-dom", () => ({ useNavigate: () => navegar }));
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: SESSAO.usuario, logout: sair }),
}));
vi.mock("../../contexts/ThemeContext", () => ({
  useTheme: () => ({
    theme: SESSAO.tema === "escuro" ? "dark" : "light",
    toggleTheme: trocarTema,
  }),
}));
vi.mock("../../services/notificationService", () => ({
  getNotifications: vi.fn(),
  markAllRead: vi.fn(),
  markRead: vi.fn(),
}));

import { Topbar } from "../../components/layout/Topbar";
import * as notificationService from "../../services/notificationService";
import type { Notification } from "../../services/notificationService";

/**
 * O botão "Sair" do menu do usuário.
 *
 * Lê o arquivo em vez de montar a `Topbar`, que arrastaria roteador, sessão e o
 * contador de notificações para prender uma linha de classe — mesma escolha do
 * teste do link de pular.
 *
 * Por que este botão tem teste próprio: ele pintava `text-danger`, o degrau 500
 * cru, e reprovava em **todas as quatro** combinações de tema e estado. A
 * varredura de contraste só via uma delas — a do hover no escuro —, porque no
 * repouso o fundo vem do painel do menu, um nível acima, e "fundo declarado no
 * ancestral" é uma limitação que ela declara. As outras três só apareceram
 * medindo à mão depois que a primeira apontou o elemento.
 */
const FONTE = readFileSync(
  resolve(process.cwd(), "src/components/layout/Topbar.tsx"),
  "utf-8",
);

describe("botão de sair", () => {
  it("não pinta o texto com o degrau 500 cru", () => {
    // `text-danger` é `--color-danger-500`. Sobre o painel do menu
    // (`--surface`) dá 3,76:1 no claro e 4,25:1 no escuro; sobre os dois
    // fundos de hover, 3,60:1 nos dois temas.
    expect(FONTE).toContain("text-on-tint-danger");
    expect(FONTE).not.toMatch(/\btext-danger\b/);
  });

  it.each([
    ["--surface", "repouso"],
    ["--bg-base", "hover no claro"],
    ["--surface-elevated", "hover no escuro"],
  ] as const)(
    "aprova em AA sobre %s (%s), nos dois temas",
    (superficie, situacao) => {
      // O hover era `bg-slate-50` no claro e `--surface-elevated` no escuro;
      // depois da Fase 16 é `--surface-elevated` nos dois. O `--bg-base`
      // continua na lista de propósito: ele é o fundo que a página desenha
      // atrás do painel, e a fase seguinte que mexer no menu não deve poder
      // reintroduzir um hover que reprove ali sem este caso reclamar.
      for (const tema of ["claro", "escuro"] as const) {
        expect(
          contraste(superficie, "--on-tint-danger", tema),
          `${situacao}, tema ${tema}`,
        ).toBeGreaterThanOrEqual(AA);
      }
    },
  );

  it("o degrau 500 reprovaria nas três, e é por isso que o token existe", () => {
    for (const superficie of ["--surface", "--bg-base", "--surface-elevated"]) {
      expect(contraste(superficie, "--color-danger-500", "claro")).toBeLessThan(AA);
    }
  });
});

// ── Fase 16 ───────────────────────────────────────────────────

/**
 * Os dois contadores de não lidas — o do sino e o do cabeçalho do painel —
 * eram `bg-danger` com `text-white`: **3,76:1**, nos dois temas, e eram os
 * dois lugares que a catraca de contraste ainda cobrava desta casca.
 *
 * O par certo do degrau de ação é `bg-action-danger` + `text-on-danger`, e a
 * medida abaixo é feita nos tokens de verdade, não nos hexadecimais.
 */
/**
 * O arquivo sem comentário nenhum.
 *
 * A oitava armadilha da varredura de contraste, e ela pegou este teste na
 * primeira execução: o comentário que escrevi ao trocar o par diz «`bg-danger`
 * é a cor CHEIA da rampa», e o caso leu a documentação do defeito como uma
 * instância dele.
 */
const CODIGO = FONTE.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");

describe("contadores de não lidas", () => {
  it("não pintam a cor cheia da rampa com branco por cima", () => {
    expect(CODIGO).not.toMatch(/\bbg-danger\b/);
    expect(CODIGO).not.toMatch(/\btext-white\b/);
    expect(CODIGO.match(/bg-action-danger text-on-danger/g) ?? []).toHaveLength(2);
  });

  it("o par do degrau de ação aprova em AA nos dois temas", () => {
    for (const tema of ["claro", "escuro"] as const) {
      expect(contraste("--action-danger", "--text-on-danger", tema), tema)
        .toBeGreaterThanOrEqual(AA);
    }
  });

  it("o par antigo reprovava, e é por isso que os tokens existem", () => {
    for (const tema of ["claro", "escuro"] as const) {
      expect(contraste("--color-danger-500", "--color-white", tema), tema)
        .toBeLessThan(AA);
    }
  });
});

describe("a casca não desenha mais ícone à mão", () => {
  it("não sobrou `<svg>` solto", () => {
    // Sete saíram: dois `menu`, `bell`, `chevronDown`, `user`, `moon` e
    // `logout` — todos casados caractere a caractere com `ICON_PATHS`.
    expect(FONTE).not.toContain("<svg");
  });

  it("não sobrou classe da paleta crua fora de comentário", () => {
    expect(CODIGO).not.toMatch(
      /\b(?:[a-z-]+:)*(?:bg|text|border|fill|stroke|divide|ring)-(?:slate|gray|zinc|red|orange|amber|emerald|sky|blue|indigo|violet|rose)-\d/,
    );
  });
});

// ── O que a casca promete a quem a usa ────────────────────────

const NAO_LIDA: Notification = {
  id: "n1",
  user_id: "u1",
  type: "ticket_assigned",
  title: "Chamado #42 atribuído a você",
  message: "A Rita assumiu o chamado.",
  data: { ticket_id: "t42" },
  read: false,
  read_at: null,
  email_sent: false,
  created_at: new Date().toISOString(),
};

function montar(props: Partial<ComponentProps<typeof Topbar>> = {}) {
  return render(
    <Topbar
      onMobileMenuClick={() => {}}
      onToggleCollapsed={() => {}}
      sidebarCollapsed={false}
      {...props}
    />,
  );
}

describe("Topbar — o que o usuário alcança", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    SESSAO.usuario = {
      name: "Rita Andrade",
      email: "rita@exemplo.com",
      role: "technician",
      avatar_url: null,
    };
    SESSAO.tema = "claro";
    vi.mocked(notificationService.getNotifications).mockResolvedValue({
      items: [NAO_LIDA],
      unread: 3,
      total: 1,
    } as never);
  });

  it("diz quantas notificações não lidas existem no NOME do sino, não só no número colorido", async () => {
    // 1.4.1: a pastilha vermelha é cor e forma; quem não a vê precisa do
    // número no nome acessível do controle.
    montar();
    expect(
      await screen.findByRole("button", { name: "Notificações — 3 não lidas" }),
    ).toBeTruthy();
  });

  it("usa o singular quando é uma só", async () => {
    vi.mocked(notificationService.getNotifications).mockResolvedValue({
      items: [NAO_LIDA],
      unread: 1,
      total: 1,
    } as never);
    montar();
    expect(
      await screen.findByRole("button", { name: "Notificações — 1 não lida" }),
    ).toBeTruthy();
  });

  it("o painel de notificações abre e lista o título de cada uma", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: /^Notificações/ }));
    expect(
      await screen.findByText("Chamado #42 atribuído a você"),
    ).toBeTruthy();
  });

  it("o menu do usuário anuncia de quem é, e mostra o papel por extenso", async () => {
    montar();
    const gatilho = await screen.findByRole("button", {
      name: "Menu do usuário — Rita Andrade",
    });
    // `rotuloDePapel` é a fonte única; a Topbar era uma das cinco cópias.
    expect(screen.getByText("Técnico")).toBeTruthy();
    await userEvent.click(gatilho);
    expect(await screen.findByText("rita@exemplo.com")).toBeTruthy();
  });

  it("o alternador de tema é um `switch` com estado anunciado", async () => {
    montar();
    await userEvent.click(
      await screen.findByRole("button", { name: /^Menu do usuário/ }),
    );
    const interruptor = await screen.findByRole("switch", { name: /Modo escuro/ });
    expect(interruptor).not.toBeChecked();

    await userEvent.click(interruptor);
    expect(trocarTema).toHaveBeenCalledTimes(1);
  });

  it("o interruptor reflete o tema vigente — e é por isso que o `theme` fica no JS", async () => {
    // O `theme === "dark"` que sobrou na tela não escolhe cor nenhuma: é o
    // ESTADO do controle. Se ele saísse para token, este caso cairia.
    SESSAO.tema = "escuro";
    montar();
    await userEvent.click(
      await screen.findByRole("button", { name: /^Menu do usuário/ }),
    );
    expect(await screen.findByRole("switch", { name: /Modo escuro/ })).toBeChecked();
  });

  it("sair encerra a sessão e leva ao login", async () => {
    montar();
    await userEvent.click(
      await screen.findByRole("button", { name: /^Menu do usuário/ }),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Sair" }));
    await waitFor(() => expect(sair).toHaveBeenCalledTimes(1));
    expect(navegar).toHaveBeenCalledWith("/login");
  });

  it("o título da página, quando existe, é o único `h1` da casca", async () => {
    montar({ pageTitle: "Respostas Rápidas" });
    const titulos = await screen.findAllByRole("heading", { level: 1 });
    expect(titulos.map((h) => h.textContent)).toEqual(["Respostas Rápidas"]);
  });
});
