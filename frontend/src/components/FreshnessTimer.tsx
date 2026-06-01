"use client";

/**
 * PRD §9 — circular freshness countdown (green → amber → red as time runs low).
 * Uses same accelerated clock as the rest of the web app via NEXT_PUBLIC_TIMER_ACCELERATION.
 */
export function FreshnessTimer({ expiresAt }: { expiresAt: string }) {
  const acceleration = Number(process.env.NEXT_PUBLIC_TIMER_ACCELERATION || "10");
  const minutesLeft = Math.max(
    0,
    Math.round(((new Date(expiresAt).getTime() - Date.now()) / 60000) * Math.max(1, acceleration)),
  );
  const progress = Math.max(8, Math.min(96, Math.round((minutesLeft / 150) * 100)));
  const stroke = minutesLeft < 45 ? "#b6402a" : minutesLeft < 90 ? "#e8a63a" : "#287a4f";

  return (
    <div className="relative size-16 shrink-0" aria-label={`About ${minutesLeft} minutes of freshness window remaining`}>
      <svg viewBox="0 0 44 44" className="-rotate-90">
        <circle cx="22" cy="22" r="18" fill="none" stroke="rgba(23,32,27,.12)" strokeWidth="5" />
        <circle
          cx="22"
          cy="22"
          r="18"
          fill="none"
          stroke={stroke}
          strokeDasharray={`${progress} 100`}
          strokeLinecap="round"
          strokeWidth="5"
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center text-[11px] font-bold leading-none text-ink">
        {minutesLeft}
        <span className="block text-[9px] font-medium">min</span>
      </div>
    </div>
  );
}
