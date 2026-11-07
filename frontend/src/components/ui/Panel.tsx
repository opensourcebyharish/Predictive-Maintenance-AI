import type { HTMLAttributes, ReactNode } from "react";

interface PanelProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  /** Suppress body padding (used for flush tables/charts). */
  flush?: boolean;
}

/**
 * Surface container used on every page: hairline border, faint inner top
 * highlight, soft ambient shadow. Header carries title / subtitle / actions;
 * hover only brightens the border so panels feel interactive, not loud.
 */
export function Panel({ title, subtitle, actions, children, flush, className = "", ...rest }: PanelProps) {
  return (
    <section
      className={`rounded-lg border border-edge bg-panel shadow-panel transition-colors duration-200 hover:border-edge-bright/80 ${className}`}
      {...rest}
    >
      {(title !== undefined || actions !== undefined) && (
        <header className="flex items-start justify-between gap-3 border-b border-edge px-4 py-3">
          <div className="min-w-0">
            <h2 className="truncate text-[13px] font-semibold tracking-wide text-ink">{title}</h2>
            {subtitle !== undefined && (
              <p className="mt-0.5 truncate text-xs text-ink-dim">{subtitle}</p>
            )}
          </div>
          {actions !== undefined && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={flush ? "" : "p-4"}>{children}</div>
    </section>
  );
}
