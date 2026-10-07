import { describe, expect, it } from "vitest";

import {
  amountTicks,
  costStatus,
  formatMoney,
  formatPrice,
  formatRowUsage,
  formatTotals,
  priceChangeOf,
  priceFormOf,
  trendCurrencies,
  type Price,
  type PriceForm,
} from "@/lib/adminPrices";

const PRESET: Price = { input: 2, output: 8, currency: "USD", per: 1_000_000, as_of: "2026-10-07", source: "preset" };

describe("formatMoney", () => {
  it("writes each currency with its sign, small amounts to two significant digits", () => {
    const cases: [number, string, string][] = [
      [0, "USD", "$0"],
      [0.00004, "USD", "<$0.0001"],
      [0.0123, "CNY", "¥0.012"],
      [1234.567, "USD", "$1,234.57"],
      [3, "EUR", "3.00 EUR"],
    ];
    for (const [amount, currency, shown] of cases) {
      expect(formatMoney(amount, currency), `${amount} ${currency}`).toBe(shown);
    }
  });
});

describe("formatTotals", () => {
  it("keeps the currencies apart, never converting", () => {
    expect(formatTotals([{ currency: "CNY", amount: 3.4 }, { currency: "USD", amount: 1.2 }])).toBe("¥3.40 + $1.20");
    expect(formatTotals([])).toBe("—");
  });
});

describe("formatPrice", () => {
  it("names input and output apart, or one price when output costs as input does", () => {
    expect(formatPrice(PRESET, "tokens")).toBe("输入 $2 · 输出 $8 / 每百万 tokens");
    expect(formatPrice({ ...PRESET, output: null, currency: "CNY", per: 3600 }, "seconds")).toBe("¥2 / 每小时");
  });
});

describe("formatRowUsage", () => {
  it("shows input and output, input alone, or nothing when no call said", () => {
    expect(formatRowUsage({ unit: "tokens", input: 12_000, output: 3400 })).toBe("输入 1.2万 · 输出 3,400 tokens");
    expect(formatRowUsage({ unit: "seconds", input: 360, output: null })).toBe("360 秒");
    expect(formatRowUsage({ unit: null, input: null, output: null })).toBe("—");
  });
});

describe("costStatus", () => {
  it("tells a priced row from one without a price and one whose usage is unknown", () => {
    expect(costStatus({ unit: "tokens", price: PRESET })).toBe("priced");
    expect(costStatus({ unit: "tokens", price: null })).toBe("unpriced");
    expect(costStatus({ unit: null, price: null })).toBe("unknown");
  });
});

describe("trendCurrencies", () => {
  it("lists each currency spent in any stretch once", () => {
    const trend: { start: string; amounts: Record<string, number> }[] = [
      { start: "a", amounts: {} },
      { start: "b", amounts: { USD: 1 } },
      { start: "c", amounts: { USD: 2, CNY: 1 } },
    ];
    expect(trendCurrencies(trend)).toEqual(["CNY", "USD"]);
  });
});

describe("amountTicks", () => {
  it("steps in fractions for small amounts and covers the largest", () => {
    expect(amountTicks(0.012)).toEqual([0, 0.005, 0.01, 0.015]);
    expect(amountTicks(7)).toEqual([0, 2, 4, 6, 8]);
    expect(amountTicks(0)).toEqual([0, 1]);
  });
});

describe("price form", () => {
  const form: PriceForm = {
    provider: " api.deepseek.com ",
    model: "deepseek-chat",
    unit: "tokens",
    input: "0.28",
    output: "",
    currency: "USD",
  };

  it("starts from the admin's price, else the preset", () => {
    const entry = { provider: "p", model: "m", unit: "tokens", preset: PRESET, override: null };
    expect(priceFormOf(entry)).toEqual({
      provider: "p", model: "m", unit: "tokens", input: "2", output: "8", currency: "USD",
    });
    expect(priceFormOf({ ...entry, override: { ...PRESET, input: 3, output: null, currency: "CNY" } })).toMatchObject({
      input: "3", output: "", currency: "CNY",
    });
  });

  it("trims the names and prices output as input when left empty", () => {
    expect(priceChangeOf(form)).toEqual({
      change: { provider: "api.deepseek.com", model: "deepseek-chat", unit: "tokens", input: 0.28, output: null, currency: "USD" },
    });
  });

  it("names the first field that is missing or not an amount", () => {
    const cases: [Partial<PriceForm>, object][] = [
      [{ provider: "  " }, { field: "provider", reason: "required" }],
      [{ model: "" }, { field: "model", reason: "required" }],
      [{ input: "" }, { field: "input", reason: "required" }],
      [{ input: "-1" }, { field: "input", reason: "amount" }],
      [{ output: "abc" }, { field: "output", reason: "amount" }],
    ];
    for (const [change, problem] of cases) {
      expect(priceChangeOf({ ...form, ...change }), JSON.stringify(change)).toEqual({ problem });
    }
  });
});
