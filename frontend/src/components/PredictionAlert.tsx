"use client";

import { useEffect, useState } from "react";
import { TrendingUp, Clock } from "lucide-react";
import { apiGet } from "@/lib/api";

type Prediction = {
  id: string;
  donor_id: string;
  donor_name: string;
  area: string;
  food_type: string;
  predicted_time: string;
  probability: number;
  nearby_ngos: number;
  source?: string;
};

/** PRD V3 — predicted surplus window banner for the signed-in donor. */
export function PredictionAlert({ donorId }: { donorId?: string }) {
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Prediction[]>("/predictions/surplus", [])
      .then((rows) => setPredictions(Array.isArray(rows) ? rows : []))
      .catch(() => setErr("Predictions unavailable"));
  }, []);

  const mine = donorId ? predictions.filter((p) => p.donor_id === donorId) : predictions;
  const top = mine.sort((a, b) => b.probability - a.probability)[0];

  if (err || !top) return null;

  const pct = Math.round(top.probability * 100);

  return (
    <div className="rounded-2xl border border-leaf/25 bg-gradient-to-br from-leaf/10 to-paper/80 p-4 shadow-line">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex gap-2">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-leaf/15 text-leaf">
            <TrendingUp className="size-5" />
          </div>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-ink/45">Predicted surplus window</p>
            <p className="mt-0.5 font-bold text-ink">{top.food_type}</p>
            <p className="text-xs text-ink/65">
              {top.area} · ~{top.nearby_ngos} NGOs nearby
              {top.source ? ` · ${top.source}` : ""}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1 rounded-full bg-white/80 px-3 py-1 text-xs font-bold text-ink shadow-sm">
          <Clock className="size-3.5 text-saffron" />
          {pct}%
        </div>
      </div>
      <p className="mt-2 text-xs font-semibold text-leaf">{top.predicted_time}</p>
    </div>
  );
}
