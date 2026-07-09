import { describe, expect, it } from "vitest";
import { shortenAddress, formatUsd, formatDecimal, formatTimestamp, riskClass } from "@/lib/format";

describe("format helpers", () => {
  it("shortens long addresses", () => {
    const a = "0x" + "ab".repeat(20);
    expect(shortenAddress(a)).toMatch(/^0xabab…[0-9a-f]{4}$/);
  });

  it("returns short addresses unchanged", () => {
    expect(shortenAddress("0x1234")).toBe("0x1234");
  });

  it("formats USD", () => {
    expect(formatUsd("1234.5")).toBe("$1,234.50");
    expect(formatUsd(null)).toBe("—");
  });

  it("formats decimals with bounded digits", () => {
    expect(formatDecimal("1.234567891234", 4)).toBe("1.2346");
    expect(formatDecimal("")).toBe("—");
  });

  it("formats ISO timestamps", () => {
    expect(formatTimestamp("2026-07-09T12:00:00Z")).toMatch(/2026/);
    expect(formatTimestamp(null)).toBe("—");
  });

  it("maps risk to badge class", () => {
    expect(riskClass("low")).toBe("badge-risk-low");
    expect(riskClass("medium")).toBe("badge-risk-medium");
    expect(riskClass("high")).toBe("badge-risk-high");
    expect(riskClass("unknown")).toBe("badge-risk-low");
  });
});
