import type { ReactNode } from "react";

interface Props {
  tone?: "error" | "warn" | "good" | "info";
  title?: ReactNode;
  children?: ReactNode;
  onDismiss?: () => void;
}

const STYLE = {
  error: "border-bad/50 bg-bad/10 text-ink",
  warn: "border-warn/50 bg-warn/10 text-ink",
  good: "border-good/50 bg-good/10 text-ink",
  info: "border-accent/50 bg-accent/10 text-ink",
};
const ICON = { error: "✕", warn: "!", good: "✓", info: "i" };
const ICON_TONE = { error: "text-bad", warn: "text-warn", good: "text-good", info: "text-accent" };

export default function ErrorBanner({ tone = "error", title, children, onDismiss }: Props) {
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`flex items-start gap-3 rounded-md border px-3 py-2 text-sm ${STYLE[tone]}`}>
      <span className={`num mt-0.5 w-4 shrink-0 text-center font-bold ${ICON_TONE[tone]}`}>{ICON[tone]}</span>
      <div className="min-w-0 flex-1">
        {title && <div className="font-medium">{title}</div>}
        {children && <div className="text-ink2">{children}</div>}
      </div>
      {onDismiss && (
        <button className="text-muted hover:text-ink" onClick={onDismiss} aria-label="Dismiss">
          ×
        </button>
      )}
    </div>
  );
}
