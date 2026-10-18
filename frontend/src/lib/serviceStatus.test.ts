import { describe, expect, it } from "vitest";

import { worst, type Status } from "./serviceStatus";

const of = (...statuses: Status[]) => ({
  window_minutes: 30,
  services: statuses.map((status) => ({ service: "chat_llm" as const, status })),
});

describe("worst", () => {
  it("marks the button by the worst service shown, and not at all when none is failing", () => {
    expect(worst(of("ok", "unsteady", "down", "idle")), "down").toBe("down");
    expect(worst(of("ok", "unsteady", "idle")), "unsteady").toBe("unsteady");
    expect(worst(of("ok", "idle")), "none failing").toBeNull();
  });
});
