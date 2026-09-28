import { describe, expect, it } from "vitest";
import { callTones } from "@/lib/callTones";

describe("callTones", () => {
  it("rings from the moment the user dials", () => {
    expect(callTones("idle", "dialing")).toEqual({ ring: "start", once: null });
  });

  it("stops ringing and plays the connect tone once the call connects", () => {
    expect(callTones("dialing", "connected")).toEqual({ ring: "stop", once: "connect" });
  });

  it("stops ringing and plays the hang-up tone when a call ends before it connects", () => {
    // It could not be connected: refused, over the limit, the microphone denied, ...
    expect(callTones("dialing", "ended")).toEqual({ ring: "stop", once: "hang-up" });
    // The user cancelled the dialing: that goes straight back to idle.
    expect(callTones("dialing", "idle")).toEqual({ ring: "stop", once: "hang-up" });
  });

  it("plays the hang-up tone however a connected call ends", () => {
    // The backend ended it, or the connection dropped.
    expect(callTones("connected", "ended")).toEqual({ ring: "stop", once: "hang-up" });
    // The user hung up: that goes straight back to idle.
    expect(callTones("connected", "idle")).toEqual({ ring: "stop", once: "hang-up" });
  });

  it("does nothing when the end of a call is dismissed", () => {
    expect(callTones("ended", "idle")).toEqual({ ring: null, once: null });
  });

  it("does nothing while the phase stays the same, so an ended call is not heard hanging up twice", () => {
    for (const phase of ["idle", "dialing", "connected", "ended"] as const) {
      expect(callTones(phase, phase)).toEqual({ ring: null, once: null });
    }
  });

  it("rings again when the user calls back after a call ended", () => {
    expect(callTones("ended", "dialing")).toEqual({ ring: "start", once: null });
  });
});
