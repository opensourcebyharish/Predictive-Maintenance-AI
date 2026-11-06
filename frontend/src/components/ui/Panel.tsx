import type { HTMLAttributes, ReactNode } from "react";

interface PanelProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  /** Suppress body padding (used for flush tables/charts). */
  flush?: boolean;
}

/** Surface container used on every page; carries the restrained panel chrome. */
export function Panel({ title, subtitle, actions, children, flush, className = "", ...rest }: PanelProps) {
  return (
    <section
      className={`rounded-lg border border-edge bg-panel/80 shadow-[0_1px_0_0_rgb(255_255_255/0.03)_inset] ${className}`}
      {...rest}
    >
      {(title !== undefined || actions !== undefined) && (
        <header className="flex items-start justify-between gap-3 border-b border-edge px-4 py-3">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold tracking-wide text-ink">{title}</h2>
            {subtitle !== undefined && <p className="mt-0.5 text-xs text-ink-dim">{subtitle}</p>}
          </div>
          {actions !== undefined && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={flush ? "" : "p-4"}>{children}</div>
    </section>
  );
}
