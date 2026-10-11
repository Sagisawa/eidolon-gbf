import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api";
import { droppedEnd, backendEnd, startFailedEnd, MicUnavailable } from "@/lib/callEnd";

describe("startFailedEnd", () => {
  it.each([
    ["the microphone is refused", new MicUnavailable("no mic"), "mic_denied", null],
    ["the hour's calls are used up", new ApiError("本小时的通话次数已用完", 429), "over_limit", "本小时的通话次数已用完"],
    [
      "the deployment requires the user's own LLM",
      new ApiError("这个部署需要你自带 LLM，可以在设置里填写。", 403, { ownLLMRequired: true }),
      "own_llm_required",
      "这个部署需要你自带 LLM，可以在设置里填写。",
    ],
    ["calls are unavailable", new ApiError("通话暂时不可用", 503), "not_connected", "通话暂时不可用"],
    ["the connection cannot be made", new Error("无法接通，请稍后再试"), "not_connected", null],
  ])("says why when %s, and that it did not count", (_, error, reason, detail) => {
    // GLOSSARY.md「限额」：被拒绝的、没能接通的通话都不计入。
    expect(startFailedEnd(error)).toEqual({ reason, detail, counts: false });
  });
});

describe("backendEnd", () => {
  it("keeps the backend's word on whether the call counted", () => {
    expect(backendEnd({ type: "ended", reason: "duration_limit", message: "满 30 分钟了", counts: true })).toEqual({
      reason: "duration_limit",
      detail: null,
      counts: true,
    });
    expect(backendEnd({ type: "ended", reason: "not_connected", message: "语音服务出了故障", counts: false })).toEqual({
      reason: "not_connected",
      detail: null,
      counts: false,
    });
  });

  it("keeps which own key failed", () => {
    const end = backendEnd({ type: "ended", reason: "own_key", message: "你的语音识别（Soniox）密钥调用失败", counts: false });

    expect(end.detail).toBe("你的语音识别（Soniox）密钥调用失败");
  });
});

describe("droppedEnd", () => {
  it("counts a connected call that drops, unless it is on the user's own keys alone", () => {
    expect(droppedEnd(false)).toEqual({ reason: "dropped", detail: null, counts: true });
    expect(droppedEnd(true).counts).toBe(false);
  });
});
