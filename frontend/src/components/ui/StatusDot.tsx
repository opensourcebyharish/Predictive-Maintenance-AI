import { motion } from "framer-motion";

/** Status dot; optionally soft-pulses (used for live connection + active alerts). */
export function StatusDot({ color, pulse = false, label }: { color: string; pulse?: boolean; label: string }) {
  return (
    <span className="relative inline-flex h-2.5 w-2.5" role="img" aria-label={label}>
      <span className={`absolute inset-0 rounded-full ${color}`} />
      {pulse && (
        <motion.span
          className={`absolute inset-0 rounded-full ${color}`}
          animate={{ opacity: [1, 0.35, 1], scale: [1, 1.45, 1] }}
          transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
        />
      )}
    </span>
  );
}
