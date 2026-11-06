import type { ReactNode } from "react";
import { motion } from "framer-motion";

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
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="mb-5 flex flex-wrap items-end justify-between gap-3"
    >
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-ink">{title}</h1>
        {description !== undefined && <p className="mt-1 max-w-3xl text-sm text-ink-dim">{description}</p>}
      </div>
      {actions !== undefined && <div className="flex items-center gap-2">{actions}</div>}
    </motion.div>
  );
}
