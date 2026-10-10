import { describe, expect, it } from "vitest";
import { SETTINGS_TABS, settingsHref, settingsTab, settingsTabSearch } from "@/lib/settingsTab";

describe("settingsTab", () => {
  it.each([
    ["there is no tab", ""],
    ["the tab is empty", "?tab="],
    ["the tab is unknown", "?tab=account"],
    ["the tab is in another case", "?tab=Call"],
  ])("opens on the profile when %s", (_, search) => {
    expect(settingsTab(new URLSearchParams(search))).toBe("profile");
  });

  it.each(SETTINGS_TABS)("opens on %s when the address names it", (tab) => {
    expect(settingsTab(new URLSearchParams({ tab }))).toBe(tab);
  });
});

describe("settingsTabSearch", () => {
  it("changes only the tab, keeping the other parameters", () => {
    expect(settingsTabSearch(new URLSearchParams("from=call&tab=profile&x=1"), "own-keys")).toBe(
      "?from=call&tab=own-keys&x=1",
    );
  });

  it("adds the tab to an address without one", () => {
    expect(settingsTabSearch(new URLSearchParams(""), "call")).toBe("?tab=call");
    expect(settingsTabSearch(new URLSearchParams("x=1"), "sign-in")).toBe("?x=1&tab=sign-in");
  });
});

describe("settingsHref", () => {
  it("points straight at a tab of the settings page", () => {
    expect(settingsHref("own-keys")).toBe("/settings?tab=own-keys");
  });
});
