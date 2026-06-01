"use client";

import { useEffect, useState } from "react";
import { Trophy } from "lucide-react";
import { apiGet } from "@/lib/api";

type DonorRow = {
  id: string;
  name: string;
  monthly_meals?: number;
  score?: { trust_score: number; trust_tier: string };
};

/** PRD §9 — lightweight CSR-style donor ranking using public donor directory + trust score. */
export function LeaderboardCard() {
  const [rows, setRows] = useState<DonorRow[]>([]);

  useEffect(() => {
    apiGet<DonorRow[]>("/donors", [])
      .then((list) => {
        const sorted = [...list].sort((a, b) => {
          const sa = a.score?.trust_score ?? a.monthly_meals ?? 0;
          const sb = b.score?.trust_score ?? b.monthly_meals ?? 0;
          return sb - sa;
        });
        setRows(sorted.slice(0, 8));
      })
      .catch(() => setRows([]));
  }, []);

  if (rows.length === 0) return null;

  return (
    <div className="rounded-2xl border border-ink/10 bg-white p-5 shadow-lift">
      <div className="mb-3 flex items-center gap-2">
        <Trophy className="size-5 text-saffron" />
        <h3 className="text-lg font-bold text-ink">Donor leaderboard</h3>
      </div>
      <p className="mb-4 text-xs text-ink/55">Ranked by trust score (falls back to monthly meals when scores are loading).</p>
      <ol className="space-y-2">
        {rows.map((d, i) => (
          <li
            key={d.id}
            className="flex items-center justify-between rounded-xl border border-ink/5 bg-field/50 px-3 py-2 text-sm"
          >
            <span className="flex items-center gap-2">
              <span className="flex size-7 items-center justify-center rounded-full bg-ink/10 text-xs font-bold text-ink">
                {i + 1}
              </span>
              <span className="font-semibold text-ink">{d.name}</span>
            </span>
            <span className="text-xs font-bold text-ink/60">
              {d.score ? `${d.score.trust_score} · ${d.score.trust_tier}` : `${d.monthly_meals ?? 0} meals/mo`}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
