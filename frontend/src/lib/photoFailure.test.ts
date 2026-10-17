import { describe, expect, it } from "vitest";
import { photoFailureNote } from "@/lib/photoFailure";

describe("photoFailureNote", () => {
  it.each([
    ["timeout", "等太久了"],
    ["service_error", "生图服务出错了"],
    ["bad_image", "生成的图不对"],
    ["used_up", "这一小时的照片用完了"],
  ])("says why for %s, with no link", (reason, said) => {
    expect(photoFailureNote(reason)).toEqual({ reason: said, toOwnKeys: false });
  });

  it("sends the user to their own keys where their image key failed", () => {
    expect(photoFailureNote("own_key_failed")).toEqual({ reason: "你的生图密钥没能用", toOwnKeys: true });
  });

  it.each([null, "something_new", "toString"])("says the service failed for a reason it does not know: %s", (reason) => {
    expect(photoFailureNote(reason)).toEqual({ reason: "生图服务出错了", toOwnKeys: false });
  });
});
