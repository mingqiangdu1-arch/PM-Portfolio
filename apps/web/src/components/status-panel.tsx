import type { ReactNode } from "react";

export function StatusPanel({ tone = "neutral", title, children, action }: { tone?: "neutral" | "success" | "warning" | "error"; title: string; children: ReactNode; action?: ReactNode }) {
  const tones = { neutral: "bg-subtle text-primary", success: "bg-primary-subtle text-success", warning: "bg-warning-subtle text-warning", error: "bg-error-subtle text-error" };
  return <section role={tone === "error" ? "alert" : "status"} className={`status-banner ${tones[tone]}`}><h2 className="font-semibold">{title}</h2><div className="mt-token-xs text-sm">{children}</div>{action ? <div className="mt-token-md">{action}</div> : null}</section>;
}
