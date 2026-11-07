import type { ReactNode } from "react";
import { Inbox, TriangleAlert } from "lucide-react";

/** Skeleton placeholder for suspense-free initial loads. */
export function Skeleton({ className = "h-4" }: { className?: string }) {
  return (
    <div
      className={`relative overflow-hidden rounded-md bg-white/5 ${className}`}
      aria-hidden="true"
    >
      <div className="absolute inset-0 animate-sweep bg-gradient-to-r from-transparent via-white/8 to-transparent" />
    </div>
  );
}

/** Full-panel loading state. */
export function LoadingState({ label = "Loading", rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div className="space-y-3" role="status" aria-label={label}>
      {[...Array(rows)].map((_, i) => (
        <Skeleton key={i} className="h-9 w-full" />
      ))}
      <span className="sr-only">{label}…</span>
    </div>
  );
}

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
  compact?: boolean;
}

/** Error panel with retry. Backend disconnects render through this. */
export function ErrorState({ message, onRetry, compact = false }: ErrorStateProps) {
  return (
    <div
      role="alert"
      className={`rounded-lg border border-critical/25 bg-critical/5 text-center ${
        compact ? "flex flex-row items-center gap-3 p-3" : "flex flex-col items-center justify-center gap-3 p-8"
      }`}
    >
      {!compact && (
        <span className="grid h-9 w-9 place-items-center rounded-md border border-critical/30 bg-critical/10 text-critical" aria-hidden="true">
          <TriangleAlert className="h-4.5 w-4.5" />
        </span>
      )}
      <div>
        <p className={`font-medium text-critical ${compact ? "text-xs" : ""}`}>Request failed</p>
        <p className={`mt-1 text-ink-dim ${compact ? "text-[11px]" : "text-sm"}`}>{message}</p>
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="rounded-md border border-edge-bright bg-panel-2 px-3 py-1.5 text-xs font-medium text-ink transition hover:border-accent/50 hover:text-accent"
        >
          Retry
        </button>
      )}
    </div>
  );
}

interface EmptyStateProps {
  title: string;
  hint?: ReactNode;
  compact?: boolean;
  /** Optional custom glyph; defaults to an inbox mark. */
  icon?: ReactNode;
}

/** Empty data state with a quiet icon so blank panels feel composed. */
export function EmptyState({ title, hint, compact = false, icon }: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center gap-1.5 text-center ${
        compact ? "p-4" : "p-10"
      }`}
      role="status"
    >
      {!compact && (
        <span className="mb-1 grid h-10 w-10 place-items-center rounded-md border border-edge bg-panel-2 text-ink-faint" aria-hidden="true">
          {icon ?? <Inbox className="h-5 w-5" />}
        </span>
      )}
      <p className={`text-ink-dim ${compact ? "text-xs" : "font-medium"}`}>{title}</p>
      {hint !== undefined && <div className="max-w-md text-xs text-ink-faint">{hint}</div>}
    </div>
  );
}
