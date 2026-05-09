"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, MapPin, Download, Users, Store, Loader2 } from "lucide-react";
import { apiGet } from "@/lib/api";

import { MapViewer } from "./MapViewer";

export function HeatMapPanel() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      apiGet("/donors", []),
      apiGet("/ngos", []),
      apiGet("/donations", [])
    ]).then(([donors, ngos, donations]) => {
      setData({ donors, ngos, donations });
      setLoading(false);
    });
  }, []);

  if (loading) {
    return <div className="flex h-96 items-center justify-center rounded-xl border border-ink/10 bg-white shadow-line">
      <Loader2 className="size-8 animate-spin text-leaf" />
    </div>;
  }

  const mapMarkers = [
    ...(data?.donors || []).map((d: any) => ({
      id: d.id,
      lat: d.location?.lat || 17.385,
      lng: d.location?.lng || 78.4867,
      title: d.name,
      type: "donor" as const
    })),
    ...(data?.ngos || []).map((n: any) => ({
      id: n.id,
      lat: n.location?.lat || 17.385,
      lng: n.location?.lng || 78.4867,
      title: n.name,
      type: "ngo" as const
    })),
    {
      id: "gap_old_city",
      lat: 17.36,
      lng: 78.47,
      title: "Old City Gap",
      type: "gap" as const
    },
    {
      id: "gap_uppal",
      lat: 17.40,
      lng: 78.56,
      title: "Uppal Industrial Gap",
      type: "gap" as const
    }
  ];

  return (
    <div className="grid gap-6">
      <section className="overflow-hidden rounded-xl border border-ink/12 bg-white shadow-lift">
        <div className="flex items-center justify-between border-b border-ink/5 p-4">
          <h3 className="font-bold text-ink">Live Visibility Map (Hyderabad)</h3>
          <div className="flex gap-4 text-xs font-bold text-ink/50 uppercase tracking-widest">
            <span className="flex items-center gap-1"><div className="size-2 rounded-full bg-leaf" /> Donors</span>
            <span className="flex items-center gap-1"><div className="size-2 rounded-full bg-civic" /> NGOs</span>
            <span className="flex items-center gap-1"><div className="size-2 rounded-full bg-chili" /> Gaps</span>
          </div>
        </div>
        
        <div className="relative h-[450px]">
          <MapViewer markers={mapMarkers} />
        </div>

        <div className="grid grid-cols-3 divide-x divide-ink/5 border-t border-ink/5 bg-field/30">
          <div className="p-4 text-center">
            <span className="block text-xs font-bold text-ink/40 uppercase tracking-widest">Active Donors</span>
            <strong className="text-2xl text-ink">{data?.donors?.length}</strong>
          </div>
          <div className="p-4 text-center">
            <span className="block text-xs font-bold text-ink/40 uppercase tracking-widest">Partner NGOs</span>
            <strong className="text-2xl text-ink">{data?.ngos?.length}</strong>
          </div>
          <div className="p-4 text-center">
            <span className="block text-xs font-bold text-ink/40 uppercase tracking-widest">Coverage Gaps</span>
            <strong className="text-2xl text-chili">2</strong>
          </div>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-ink/10 bg-white p-5 shadow-line">
          <h4 className="mb-4 font-bold text-ink">Urgent Coverage Gaps</h4>
          <div className="grid gap-3">
             <div className="flex items-center justify-between rounded-lg bg-chili/5 p-3 text-sm">
                <div className="flex items-center gap-3">
                   <AlertTriangle className="size-4 text-chili" />
                   <span className="font-bold">Old City Zone</span>
                </div>
                <span className="text-ink/60">No NGO within 8km</span>
             </div>
             <div className="flex items-center justify-between rounded-lg bg-saffron/10 p-3 text-sm">
                <div className="flex items-center gap-3">
                   <AlertTriangle className="size-4 text-saffron" />
                   <span className="font-bold">Uppal Industrial</span>
                </div>
                <span className="text-ink/60">High surplus, low pickup</span>
             </div>
          </div>
        </div>

        <div className="rounded-xl border border-ink/10 bg-white p-5 shadow-line">
          <h4 className="mb-4 font-bold text-ink">Compliance Reports</h4>
          <div className="grid gap-3">
             <button className="flex items-center justify-between rounded-lg border border-ink/10 px-4 py-3 text-sm font-bold text-ink hover:bg-field">
                Monthly NFSA Report
                <Download className="size-4" />
             </button>
             <button className="flex items-center justify-between rounded-lg border border-ink/10 px-4 py-3 text-sm font-bold text-ink hover:bg-field">
                CSR Contribution Audit
                <Download className="size-4" />
             </button>
          </div>
        </div>
      </div>
    </div>
  );
}
