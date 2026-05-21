/**
 * DemoBadge55 — indicates 55+ audience signal.
 */
interface DemoBadge55Props {
  show?: boolean;
}

export function DemoBadge55({ show = true }: DemoBadge55Props) {
  if (!show) {
    return null;
  }

  return (
    <span
      className="inline-flex items-center rounded-full bg-[#E6A817]/10 px-2 py-0.5 text-xs font-medium text-[#E6A817] cursor-help"
      title="Probable 55+ Audience — matched keyword taxonomy"
    >
      55+ Signal
    </span>
  );
}
