import { describe, it, expect, vi, beforeEach } from "vitest";
import { submitSurvey, getTicketSurvey } from "../../services/surveyService";
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
const mockPost = vi.mocked(api.post);

const survey = {
  id: "s1",
  ticket_id: "t1",
  user_id: "u1",
  rating: 5,
  comment: "Excelente atendimento!",
  created_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("submitSurvey", () => {
  it("posts to /tickets/:id/survey and returns the survey", async () => {
    mockPost.mockResolvedValue({ data: survey });

    const result = await submitSurvey("t1", {
      rating: 5,
      comment: "Excelente atendimento!",
    });

    expect(mockPost).toHaveBeenCalledWith("/tickets/t1/survey", {
      rating: 5,
      comment: "Excelente atendimento!",
    });
    expect(result.rating).toBe(5);
  });

  it("posts with rating only (no comment)", async () => {
    mockPost.mockResolvedValue({ data: { ...survey, comment: null } });

    await submitSurvey("t1", { rating: 4 });

    expect(mockPost).toHaveBeenCalledWith("/tickets/t1/survey", { rating: 4 });
  });
});

describe("getTicketSurvey", () => {
  it("returns the survey when it exists", async () => {
    mockGet.mockResolvedValue({ data: survey });

    const result = await getTicketSurvey("t1");

    expect(mockGet).toHaveBeenCalledWith("/tickets/t1/survey");
    expect(result).toEqual(survey);
  });

  it("returns null when the request fails (no survey yet)", async () => {
    mockGet.mockRejectedValue(new Error("404 Not Found"));

    const result = await getTicketSurvey("t1");

    expect(result).toBeNull();
  });
});
