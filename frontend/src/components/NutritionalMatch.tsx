"use client";

import { Leaf } from "lucide-react";

type MatchShape = {
  ngo_name: string;
  distance_km: number;
  total_score: number;
  proximity_score?: number;
  food_type_score?: number;
  nutrition_score?: number;
};

function Bar({ label, value }: { label: string; value: number }) {
  const v = Math.max(0, Math.min(100, value));
  return (
    <div>
      <div className="mb-0.5 flex justify-between text-[10px] font-bold uppercase tracking-wide text-ink/45">
        <span>{label}</span>
        <span className="text-ink/70">{v}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-ink/10">
        <div className="h-full rounded-full bg-gradient-to-r from-leaf to-civic" style={{ width: `${v}%` }} />
      </div>
    </div>
  );
}

/** PRD §9-style NGO ↔ surplus compatibility breakdown (uses MatchScore sub-scores when present). */
export function NutritionalMatch({ match }: { match: MatchShape }) {
  const px = match.proximity_score ?? Math.round(Math.max(0, 100 - (match.distance_km || 0) * 8));
  const food = match.food_type_score ?? Math.round((match.total_score || 0) * 0.35);
  const nut = match.nutrition_score ?? Math.round((match.total_score || 0) * 0.3);

  return (
    <div className="rounded-xl border border-civic/20 bg-civic/5 p-3">
      <div className="mb-2 flex items-center gap-2">
        <Leaf className="size-4 text-leaf" />
        <p className="text-[10px] font-bold uppercase tracking-widest text-ink/50">Nutritional match</p>
      </div>
      <p className="text-xs text-ink/80">
        <strong className="text-ink">{match.ngo_name}</strong>
        <span className="text-ink/55"> · {match.distance_km?.toFixed?.(1) ?? match.distance_km} km · total {match.total_score}</span>
      </p>
      <div className="mt-3 grid gap-2">
        <Bar label="Proximity" value={px} />
        <Bar label="Food fit" value={food} />
        <Bar label="Nutrition fit" value={nut} />
      </div>
    </div>
  );
}
