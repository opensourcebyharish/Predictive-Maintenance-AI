import { formatNumber } from "@/lib/format";

/** Temperature/vibration/pressure assignments are conceptual (see Phase 4). */
const GROUP_HINTS: Record<string, string> = {
  s2: "temperature-related",
  s3: "temperature-related",
  s4: "temperature-related",
  s7: "temperature-related",
  s8: "speed/vibration-related",
  s9: "speed/vibration-related",
  s6: "pressure-related",
  s11: "pressure-related",
};

/**
 * Dense sensor-value grid for the latest reading (s1..s21). Values use
 * tabular numerals; conceptual group hints render as subtle footnotes.
 */
export function SensorGrid({ values }: { values: Record<string, number> }) {
  const entries = Object.entries(values);
  if (entries.length === 0) {
    return <p className="text-xs text-ink-faint">No sensor payload</p>;
  }
  return (
    <ul className="grid grid-cols-3 gap-1.5 sm:grid-cols-4" aria-label="Sensor values">
      {entries.map(([name, value]) => {
        const hint = GROUP_HINTS[name];
        return (
          <li
            key={name}
            className="rounded border border-edge/70 bg-panel-2/60 px-2 py-1.5"
            title={hint !== undefined ? `${name}: ${hint} sensor` : `Sensor signal ${name}`}
          >
            <span className="block text-[10px] tracking-wide text-ink-faint uppercase">
              {name}
              {hint !== undefined && <span className="ml-1 text-ink-faint/70 normal-case">· {hint.split("-")[0]}</span>}
            </span>
            <span className="tnum block text-sm font-medium text-ink">{formatNumber(value, 4)}</span>
          </li>
        );
      })}
    </ul>
  );
}
