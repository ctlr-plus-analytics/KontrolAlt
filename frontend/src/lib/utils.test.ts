import { describe, expect, it } from "vitest";
import { formatEngagementRate } from "@/lib/utils";

describe("formatEngagementRate", () => {
  it("formats valid avg views and subscribers as a percent", () => {
    expect(formatEngagementRate(100000, 25000)).toBe("25.0%");
  });

  it("returns N/A when subscribers is null", () => {
    expect(formatEngagementRate(null, 25000)).toBe("N/A");
  });

  it("returns N/A when avg views is null", () => {
    expect(formatEngagementRate(100000, null)).toBe("N/A");
  });

  it("returns N/A when subscribers is zero", () => {
    expect(formatEngagementRate(0, 25000)).toBe("N/A");
  });

  it("returns N/A when subscribers is negative", () => {
    expect(formatEngagementRate(-100, 25000)).toBe("N/A");
  });

  it("caps engagement rate at 100.0%", () => {
    expect(formatEngagementRate(1000, 5000)).toBe("100.0%");
  });
});
