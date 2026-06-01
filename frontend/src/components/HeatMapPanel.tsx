"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Download, Loader2 } from "lucide-react";
import { apiGet } from "@/lib/api";

import { MapViewer } from "./MapViewer";

type GeoFeature = {
  type: "Feature";
  properties: Record<string, unknown>;
  geometry: { type: string; coordinates: number[] };
};

type HeatmapPayload = {
  generated_at?: string;
  city?: string;
  surplus?: { type: string; features: GeoFeature[] };
  demand?: { type: string; features: GeoFeature[] };
  coverage_gaps?: { type: string; features: GeoFeature[] };
  stats?: {
    donor_pins?: number;
    ngo_pins?: number;
    gap_zones?: number;
    surplus_weight_total?: number;
    demand_weight_total?: number;
  };
  coverage_gap_summary?: Array<{
    area: string;
    severity: string;
    reason: string;
    nearest_donor_km?: number;
  }>;
};

function featuresToMarkers(
  fc: { features: GeoFeature[] } | undefined,
  kind: "donor" | "ngo" | "gap"
): Array<{ id: string; lat: number; lng: number; title: string; type: "donor" | "ngo" | "gap" }> {
  if (!fc?.features?.length) return [];
  return fc.features.map((f, i) => {
    const coords = f.geometry?.coordinates ?? [78.4867, 17.385];
    const lng = coords[0];
    const lat = coords[1];
    const p = f.properties || {};
    const title =
      kind === "gap"
        ? String(p.area ?? `Gap ${i + 1}`)
        : String(p.name ?? `Pin ${i + 1}`);
    return {
      id: `${kind}-${i}-${lat}-${lng}`,
      lat,
      lng,
      title,
      type: kind,
    };
  });
}

export function HeatMapPanel() {
  const [heatmap, setHeatmap] = useState<HeatmapPayload | null>(null);
  const [donors, setDonors] = useState<any[]>([]);
  const [ngos, setNgos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      apiGet<HeatmapPayload | null>("/heatmap/data", null),
      apiGet("/donors", []),
      apiGet("/ngos", []),
    ]).then(([hm, d, n]) => {
      setHeatmap(hm);
      setDonors(d);
      setNgos(n);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center rounded-xl border border-ink/10 bg-white shadow-line">
        <Loader2 className="size-8 animate-spin text-leaf" />
      </div>
    );
  }

  const surplusMarkers = featuresToMarkers(heatmap?.surplus, "donor");
  const demandMarkers = featuresToMarkers(heatmap?.demand, "ngo");
  const gapMarkers = featuresToMarkers(heatmap?.coverage_gaps, "gap");

  const fallbackDonorMarkers =
    surplusMarkers.length > 0
      ? surplusMarkers
      : (donors || []).map((d: any) => ({
          id: d.id,
          lat: d.location?.lat || 17.385,
          lng: d.location?.lng || 78.4867,
          title: d.name,
          type: "donor" as const,
        }));

  const fallbackNgoMarkers =
    demandMarkers.length > 0
      ? demandMarkers
      : (ngos || []).map((n: any) => ({
          id: n.id,
          lat: n.location?.lat || 17.385,
          lng: n.location?.lng || 78.4867,
          title: n.name,
          type: "ngo" as const,
        }));

  const mapMarkers = [...fallbackDonorMarkers, ...fallbackNgoMarkers, ...gapMarkers];

  const stats = heatmap?.stats;
  const donorCount = stats?.donor_pins ?? donors?.length ?? 0;
  const ngoCount = stats?.ngo_pins ?? ngos?.length ?? 0;
  const gapCount = stats?.gap_zones ?? gapMarkers.length;

  const gapRows = heatmap?.coverage_gap_summary?.length ? heatmap.coverage_gap_summary : [];

  return (
    <div className="grid gap-6">
      <section className="overflow-hidden rounded-xl border border-ink/12 bg-white shadow-lift">
        <div className="flex items-center justify-between border-b border-ink/5 p-4">
          <div>
            <h3 className="font-bold text-ink">Live Visibility Map (Hyderabad)</h3>
            {heatmap?.generated_at && (
              <p className="mt-0.5 text-[10px] font-semibold uppercase tracking-widest text-ink/40">
                Heatmap data · {new Date(heatmap.generated_at).toLocaleString()}
              </p>
            )}
          </div>
          <div className="flex gap-4 text-xs font-bold uppercase tracking-widest text-ink/50">
            <span className="flex items-center gap-1">
              <div className="size-2 rounded-full bg-leaf" /> Donors
            </span>
            <span className="flex items-center gap-1">
              <div className="size-2 rounded-full bg-civic" /> NGOs
            </span>
            <span className="flex items-center gap-1">
              <div className="size-2 rounded-full bg-chili" /> Gaps
            </span>
          </div>
        </div>

        <div className="relative h-[450px]">
          <MapViewer markers={mapMarkers} />
        </div>

        <div className="grid grid-cols-3 divide-x divide-ink/5 border-t border-ink/5 bg-field/30">
          <div className="p-4 text-center">
            <span className="block text-xs font-bold uppercase tracking-widest text-ink/40">Active Donors</span>
            <strong className="text-2xl text-ink">{donorCount}</strong>
          </div>
          <div className="p-4 text-center">
            <span className="block text-xs font-bold uppercase tracking-widest text-ink/40">Partner NGOs</span>
            <strong className="text-2xl text-ink">{ngoCount}</strong>
          </div>
          <div className="p-4 text-center">
            <span className="block text-xs font-bold uppercase tracking-widest text-ink/40">Coverage Gaps</span>
            <strong className="text-2xl text-chili">{gapCount}</strong>
          </div>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-ink/10 bg-white p-5 shadow-line">
          <h4 className="mb-4 font-bold text-ink">Urgent Coverage Gaps</h4>
          <div className="grid gap-3">
            {gapRows.length === 0 ?
              <p className="text-sm text-ink/55">No coverage gaps flagged with the current thresholds.</p>
            : gapRows.slice(0, 8).map((row, idx) => (
                <div
                  key={`${row.area}-${idx}`}
                  className={`flex items-center justify-between rounded-lg p-3 text-sm ${
                    row.severity === "high" ? "bg-chili/5"
                    : row.severity === "medium" ? "bg-saffron/10"
                    : "bg-field/70"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <AlertTriangle
                      className={`size-4 shrink-0 ${
                        row.severity === "high" ? "text-chili"
                        : row.severity === "medium" ? "text-saffron"
                        : "text-ink/50"
                      }`}
                    />
                    <div>
                      <span className="font-bold">{row.area}</span>
                      <p className="text-xs text-ink/55">{row.reason}</p>
                    </div>
                  </div>
                  {row.nearest_donor_km != null && (
                    <span className="shrink-0 text-ink/60">{row.nearest_donor_km} km</span>
                  )}
                </div>
              ))
            }
          </div>
        </div>

        <div className="rounded-xl border border-ink/10 bg-white p-5 shadow-line">
          <h4 className="mb-4 font-bold text-ink">Compliance Reports</h4>
          <div className="grid gap-3">
            <button
              type="button"
              className="flex items-center justify-between rounded-lg border border-ink/10 px-4 py-3 text-sm font-bold text-ink hover:bg-field"
            >
              Monthly NFSA Report
              <Download className="size-4" />
            </button>
            <button
              type="button"
              className="flex items-center justify-between rounded-lg border border-ink/10 px-4 py-3 text-sm font-bold text-ink hover:bg-field"
            >
              CSR Contribution Audit
              <Download className="size-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
