import { describe, expect, it } from "vitest";
import { formatEngagementRate } from "@/lib/utils";

describe("formatEngagementRate", () => {
  it("formats valid avg comments and subscribers as a percent", () => {
    expect(formatEngagementRate(100000, 25000)).toBe("25.000%");
  });

  it("returns N/A when subscribers is null", () => {
    expect(formatEngagementRate(null, 25000)).toBe("N/A");
  });

  it("returns N/A when avg comments is null", () => {
    expect(formatEngagementRate(100000, null)).toBe("N/A");
  });

  it("returns N/A when subscribers is zero", () => {
    expect(formatEngagementRate(0, 25000)).toBe("N/A");
  });

  it("returns N/A when subscribers is negative", () => {
    expect(formatEngagementRate(-100, 25000)).toBe("N/A");
  });

  it("caps engagement rate at 100.000%", () => {
    expect(formatEngagementRate(1000, 5000)).toBe("100.000%");
  });
});
