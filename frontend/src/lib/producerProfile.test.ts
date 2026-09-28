import { describe, expect, it } from "vitest";
import {
  clampFormOfAddress,
  fromDraft,
  MAX_FORM_OF_ADDRESS,
  sameDraft,
  toDraft,
} from "@/lib/producerProfile";

describe("toDraft", () => {
  it("把没有设置的项变成空白，表示沿用默认", () => {
    expect(toDraft({ form_of_address: null, gender: null, timezone: null })).toEqual({
      formOfAddress: "",
      gender: "",
      timezone: "",
    });
  });

  it("保留已经设置的项", () => {
    expect(toDraft({ form_of_address: "小林さん", gender: "female", timezone: "Asia/Tokyo" })).toEqual({
      formOfAddress: "小林さん",
      gender: "female",
      timezone: "Asia/Tokyo",
    });
  });
});

describe("fromDraft", () => {
  it("空白的项存成 null，交回默认", () => {
    expect(fromDraft({ formOfAddress: "  ", gender: "", timezone: "" })).toEqual({
      form_of_address: null,
      gender: null,
      timezone: null,
    });
  });

  it("去掉称呼两端的空白", () => {
    expect(fromDraft({ formOfAddress: " 小林さん ", gender: "male", timezone: "Asia/Tokyo" })).toEqual({
      form_of_address: "小林さん",
      gender: "male",
      timezone: "Asia/Tokyo",
    });
  });
});

describe("sameDraft", () => {
  const saved = { formOfAddress: "小林さん", gender: "" as const, timezone: "" };

  it("只差称呼两端空白的不算改动", () => {
    expect(sameDraft({ ...saved, formOfAddress: " 小林さん " }, saved)).toBe(true);
  });

  it("任何一项不同都算改动", () => {
    expect(sameDraft({ ...saved, formOfAddress: "小林" }, saved)).toBe(false);
    expect(sameDraft({ ...saved, gender: "female" }, saved)).toBe(false);
    expect(sameDraft({ ...saved, timezone: "Asia/Tokyo" }, saved)).toBe(false);
  });
});

describe("clampFormOfAddress", () => {
  it("和后端一样最多 20 个字", () => {
    expect(MAX_FORM_OF_ADDRESS).toBe(20);
    expect(clampFormOfAddress("あ".repeat(25))).toBe("あ".repeat(20));
    expect(clampFormOfAddress("小林さん")).toBe("小林さん");
  });

  it("按字数而不是 UTF-16 码元截断，不会切开一个字", () => {
    const clamped = clampFormOfAddress("𠮷".repeat(21));
    expect(Array.from(clamped)).toHaveLength(20);
    expect(clamped).toBe("𠮷".repeat(20));
  });
});
