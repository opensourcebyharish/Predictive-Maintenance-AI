import type { ReactNode } from "react";

/** Skeleton placeholder for suspense-free initial loads. */
export function Skeleton({ className = "h-4" }: { className?: string }) {
  return (
    <div className={`relative overflow-hidden rounded bg-white/5 ${className}`} aria-hidden="true">
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
      className={`flex ${compact ? "flex-row items-center gap-3 p-3" : "flex-col items-center justify-center gap-3 p-8"} rounded-lg border border-critical/25 bg-critical/5 text-center`}
    >
      <div>
        <p className={`font-medium text-critical ${compact ? "text-xs" : ""}`}>Request failed</p>
        <p className={`mt-1 text-ink-dim ${compact ? "text-[11px]" : "text-sm"}`}>{message}</p>
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="rounded border border-edge-bright bg-panel-2 px-3 py-1.5 text-xs font-medium text-ink transition hover:border-accent/50 hover:text-accent"
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
}

/** Empty data state. */
export function EmptyState({ title, hint, compact = false }: EmptyStateProps) {
  return (
    <div
      className={`flex ${compact ? "p-4" : "p-10"} flex-col items-center justify-center gap-1 text-center`}
      role="status"
    >
      <p className={`text-ink-dim ${compact ? "text-xs" : "font-medium"}`}>{title}</p>
      {hint !== undefined && <p className="mt-0.5 text-xs text-ink-faint">{hint}</p>}
    </div>
  );
}
