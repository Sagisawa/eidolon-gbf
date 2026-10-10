import { describe, expect, it } from "vitest";
import { SETTINGS_TABS, settingsHref, settingsTab, settingsTabSearch } from "@/lib/settingsTab";

describe("settingsTab", () => {
  it("opens on the tab the address names, and on the profile when it names none we know", () => {
    for (const tab of SETTINGS_TABS) {
      expect(settingsTab(new URLSearchParams({ tab })), tab).toBe(tab);
    }
    for (const search of ["", "?tab=", "?tab=account", "?tab=Call"]) {
      expect(settingsTab(new URLSearchParams(search)), search).toBe("profile");
    }
  });
});

describe("settingsTabSearch", () => {
  it("changes only the tab, keeping the other parameters, and adds it where there is none", () => {
    expect(settingsTabSearch(new URLSearchParams("from=call&tab=profile&x=1"), "own-keys")).toBe(
      "?from=call&tab=own-keys&x=1",
    );
    expect(settingsTabSearch(new URLSearchParams(""), "call")).toBe("?tab=call");
    expect(settingsTabSearch(new URLSearchParams("x=1"), "sign-in")).toBe("?x=1&tab=sign-in");
  });
});

describe("settingsHref", () => {
  it("points straight at a tab of the settings page", () => {
    expect(settingsHref("own-keys")).toBe("/settings?tab=own-keys");
  });
});
