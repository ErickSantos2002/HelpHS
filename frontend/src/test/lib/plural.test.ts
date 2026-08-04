import { describe, it, expect } from "vitest";
import { plural } from "../../lib/utils";

describe("plural", () => {
  it("usa o singular para 1", () => {
    expect(plural(1, "violação", "violações")).toBe("violação");
  });

  it("usa o plural para 0", () => {
    expect(plural(0, "violação", "violações")).toBe("violações");
  });

  it("usa o plural para mais de 1", () => {
    expect(plural(3, "avaliação", "avaliações")).toBe("avaliações");
  });
});
