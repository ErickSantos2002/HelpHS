import { describe, expect, it } from "vitest";

import { CAMPO_ANEXO_ADICIONADO, eventosDeAnexo } from "../../lib/anexoNaConversa";
import type { Attachment } from "../../services/attachmentService";
import type { TicketHistory } from "../../services/ticketService";

function linha(over: Partial<TicketHistory> = {}): TicketHistory {
  return {
    id: "h1",
    ticket_id: "t1",
    user_id: "u9",
    user_name: "Bruno Lima",
    user_role: "technician",
    field: CAMPO_ANEXO_ADICIONADO,
    old_value: null,
    new_value: "a1",
    comment: null,
    created_at: "2026-10-09T14:03:00.000Z",
    ...over,
  };
}

const ANEXO: Attachment = {
  id: "a1",
  ticket_id: "t1",
  uploaded_by: "u9",
  uploaded_by_name: "Bruno Lima",
  uploaded_by_role: "technician",
  original_name: "laudo.pdf",
  mime_type: "application/pdf",
  size_bytes: 1024,
  virus_scanned: true,
  virus_clean: true,
  created_at: "2026-10-09T14:03:00.000Z",
};

describe("eventosDeAnexo", () => {
  it("só o evento de anexo vira acontecimento — status e o resto ficam fora", () => {
    const eventos = eventosDeAnexo(
      [linha(), linha({ id: "h2", field: "status", new_value: "in_progress" })],
      [ANEXO],
    );
    expect(eventos.map((e) => e.id)).toEqual(["h1"]);
  });

  it("autor e papel vêm da linha do histórico, e o arquivo é ligado pelo id", () => {
    const [evento] = eventosDeAnexo([linha()], [ANEXO]);
    expect(evento).toEqual({
      id: "h1",
      created_at: "2026-10-09T14:03:00.000Z",
      autor: "Bruno Lima",
      papel: "technician",
      anexo: ANEXO,
    });
  });

  it("anexo excluído depois continua como acontecimento, sem arquivo", () => {
    const [evento] = eventosDeAnexo([linha({ new_value: "sumiu" })], [ANEXO]);
    expect(evento.anexo).toBeNull();
  });

  it("não inventa autor quando a linha não tem", () => {
    const [evento] = eventosDeAnexo([linha({ user_name: null, user_role: null })], [ANEXO]);
    expect(evento.autor).toBeNull();
    expect(evento.papel).toBeNull();
  });

  it("o mesmo histórico lido duas vezes dá os mesmos eventos, sem duplicar", () => {
    const h = [linha(), linha({ id: "h2", new_value: "a2" })];
    expect(eventosDeAnexo(h, [ANEXO])).toEqual(eventosDeAnexo(h, [ANEXO]));
    expect(eventosDeAnexo(h, [ANEXO])).toHaveLength(2);
  });
});
