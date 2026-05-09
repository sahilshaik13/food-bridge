"use client";

import { useState, useEffect } from "react";
import { RadioTower } from "lucide-react";
import { apiGet } from "@/lib/api";

type Prediction = {
  id: string;
  donor_name: string;
  area: string;
  food_type: string;
  predicted_time: string;
  probability: number;
};

export function PredictionPanel() {
  const [predictions, setPredictions] = useState<Prediction[]>([]);

  useEffect(() => {
    apiGet("/predictions/surplus", []).then(setPredictions);
  }, []);

  if (predictions.length === 0) {
    return (
      <section className="rounded-lg border border-ink/12 bg-white/75 p-4 shadow-line">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-2xl">Prediction Queue</h2>
          <RadioTower className="size-5 text-civic" />
        </div>
        <p className="text-sm text-ink/50">No predictions available yet.</p>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-ink/12 bg-white/75 p-4 shadow-line">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-display text-2xl">Prediction Queue</h2>
        <RadioTower className="size-5 text-civic" />
      </div>
      <div className="space-y-3">
        {predictions.map((prediction) => (
          <div key={prediction.id} className="rounded-md bg-field/70 p-3">
            <div className="flex items-center justify-between gap-3">
              <strong>{prediction.area}</strong>
              <span className="text-sm font-bold text-leaf">{Math.round(prediction.probability * 100)}%</span>
            </div>
            <p className="mt-1 text-sm text-ink/68">
              {prediction.food_type} from {prediction.donor_name}, {prediction.predicted_time}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
