"use client";

import type { TooltipRenderProps } from "react-joyride";

// All styles are inline — Joyride's positioning engine can conflict with
// Tailwind class-based transforms on the tooltip container.
const styles = {
  tooltip: {
    backgroundColor: "#1A1A2E",
    border: "1px solid rgba(201, 168, 76, 0.3)",
    borderRadius: 12,
    padding: "20px 24px",
    width: "min(360px, calc(100vw - 32px))",
    minWidth: 260,
    boxShadow: "0 25px 50px rgba(0, 0, 0, 0.5)",
    fontFamily: "inherit",
    boxSizing: "border-box",
  } as React.CSSProperties,

  title: {
    color: "#C9A84C",
    fontSize: 12,
    fontWeight: 700,
    letterSpacing: "0.1em",
    textTransform: "uppercase" as const,
    marginBottom: 10,
  } as React.CSSProperties,

  body: {
    color: "#F7F4EE",
    fontSize: 14,
    lineHeight: 1.65,
    margin: 0,
  } as React.CSSProperties,

  footer: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 18,
    gap: 8,
  } as React.CSSProperties,

  progress: {
    color: "rgba(247, 244, 238, 0.35)",
    fontSize: 11,
    flexShrink: 0,
  } as React.CSSProperties,

  btnRow: {
    display: "flex",
    gap: 6,
    alignItems: "center",
    flexShrink: 0,
  } as React.CSSProperties,

  primaryBtn: {
    backgroundColor: "#C9A84C",
    color: "#1A1A2E",
    border: "none",
    borderRadius: 8,
    padding: "7px 16px",
    fontSize: 12,
    fontWeight: 700,
    cursor: "pointer",
    letterSpacing: "0.02em",
  } as React.CSSProperties,

  ghostBtn: {
    backgroundColor: "transparent",
    color: "rgba(247, 244, 238, 0.45)",
    border: "1px solid rgba(247, 244, 238, 0.15)",
    borderRadius: 8,
    padding: "6px 12px",
    fontSize: 12,
    cursor: "pointer",
  } as React.CSSProperties,
};

export function TourTooltip({
  continuous,
  index,
  step,
  backProps,
  closeProps,
  primaryProps,
  skipProps,
  tooltipProps,
  size,
  isLastStep,
}: TooltipRenderProps) {
  return (
    <div {...tooltipProps} style={styles.tooltip}>
      {step.title && <div style={styles.title}>{step.title}</div>}
      <p style={styles.body}>{step.content as React.ReactNode}</p>
      <div style={styles.footer}>
        <span style={styles.progress}>
          {index + 1} / {size}
        </span>
        <div style={styles.btnRow}>
          {index > 0 && (
            <button {...backProps} style={styles.ghostBtn}>
              Back
            </button>
          )}
          {!isLastStep && (
            <button {...skipProps} style={styles.ghostBtn}>
              Skip
            </button>
          )}
          {continuous ? (
            <button {...primaryProps} style={styles.primaryBtn}>
              {isLastStep ? "Done" : "Next"}
            </button>
          ) : (
            <button {...closeProps} style={styles.primaryBtn}>
              Close
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

