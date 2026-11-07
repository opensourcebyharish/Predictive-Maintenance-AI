import type { ReactNode } from "react";
import { motion } from "framer-motion";

/**
 * Page masthead: dominant title, muted description, trailing actions.
 * The small accent underline anchors the h1 without extra chrome.
 */
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <motion.header
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="mb-6 flex flex-wrap items-end justify-between gap-3"
    >
      <div className="min-w-0">
        <h1 className="text-[22px] font-semibold leading-tight tracking-tight text-ink">{title}</h1>
        {description !== undefined && (
          <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-ink-dim">{description}</p>
        )}
      </div>
      {actions !== undefined && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </motion.header>
  );
}
