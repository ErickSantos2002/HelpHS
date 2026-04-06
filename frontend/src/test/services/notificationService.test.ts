import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getNotifications,
  markRead,
  markAllRead,
  deleteNotification,
} from "../../services/notificationService";
import { api } from "../../services/api";

vi.mock("../../services/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockGet = vi.mocked(api.get);
const mockPatch = vi.mocked(api.patch);
const mockDelete = vi.mocked(api.delete);

const notification = {
  id: "n1",
  user_id: "u1",
  type: "ticket_created",
  title: "Novo chamado",
  message: "Chamado HS-2026-0001 criado",
  data: null,
  read: false,
  read_at: null,
  email_sent: false,
  created_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("getNotifications", () => {
  it("calls GET /notifications with no params", async () => {
    mockGet.mockResolvedValue({
      data: {
        items: [notification],
        total: 1,
        unread: 1,
        limit: 20,
        offset: 0,
      },
    });

    const result = await getNotifications();

    expect(mockGet).toHaveBeenCalledWith("/notifications?");
    expect(result.unread).toBe(1);
  });

  it("appends unread_only, limit and offset params", async () => {
    mockGet.mockResolvedValue({
      data: { items: [], total: 0, unread: 0, limit: 5, offset: 0 },
    });

    await getNotifications({ unread_only: true, limit: 5, offset: 0 });

    const url = mockGet.mock.calls[0][0] as string;
    expect(url).toContain("unread_only=true");
    expect(url).toContain("limit=5");
  });
});

describe("markRead", () => {
  it("patches /notifications/:id/read", async () => {
    mockPatch.mockResolvedValue({ data: { ...notification, read: true } });

    const result = await markRead("n1");

    expect(mockPatch).toHaveBeenCalledWith("/notifications/n1/read");
    expect(result.read).toBe(true);
  });
});

describe("markAllRead", () => {
  it("patches /notifications/read-all", async () => {
    mockPatch.mockResolvedValue({});

    await markAllRead();

    expect(mockPatch).toHaveBeenCalledWith("/notifications/read-all");
  });
});

describe("deleteNotification", () => {
  it("calls DELETE /notifications/:id", async () => {
    mockDelete.mockResolvedValue({});

    await deleteNotification("n1");

    expect(mockDelete).toHaveBeenCalledWith("/notifications/n1");
  });
});
