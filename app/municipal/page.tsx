"use client";

import { RoleGuard } from "@/components/RoleGuard";
import { AppNav } from "@/components/AppNav";
import { HeatMapPanel } from "@/components/HeatMapPanel";
import { realtimeDatabase } from "@/lib/firebase";
import { onValue, ref } from "firebase/database";
import { useEffect, useState } from "react";

export default function MunicipalPage() {
  const [emergencyHistory, setEmergencyHistory] = useState<any[]>([]);

  useEffect(() => {
    const historyRef = ref(realtimeDatabase, "history_feeds/emergency/municipal");
    const unsub = onValue(historyRef, (snap) => {
      const val = snap.val() || {};
      const list = Object.values(val as Record<string, any>).sort((a: any, b: any) =>
        new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
      );
      setEmergencyHistory(list);
    });
    return () => unsub();
  }, []);

  return (
    <RoleGuard allowedRoles={["municipal_admin", "super_admin"]}>
      <div className="min-h-screen bg-paper/30">
        <AppNav />
        <div className="mx-auto max-w-7xl px-5 py-8">
          <div className="mb-8">
            <p className="text-[10px] font-bold uppercase tracking-widest text-ink/40">Municipal Dashboard</p>
            <h1 className="text-3xl font-bold text-ink">Surplus Heatmap & Compliance</h1>
            <p className="mt-1 text-sm text-ink/60">Live city-wide visibility of food redistribution activity and coverage gaps.</p>
          </div>
          {emergencyHistory.length > 0 && (
            <div className="mb-6 rounded-2xl border border-ink/10 bg-white p-5 shadow-lift">
              <h2 className="text-lg font-bold text-ink">Emergency Pool History (Realtime)</h2>
              <div className="mt-3 grid gap-2">
                {emergencyHistory.slice(0, 10).map((item: any) => (
                  <div key={item.id} className="rounded-xl border border-ink/10 p-3 text-sm">
                    <p className="font-bold text-ink">{item.ngo_name} · {item.food_type} · {item.status}</p>
                    <p className="text-ink/60">Pledged {item.pledged_kg}/{item.quantity_goal_kg} kg · Beneficiaries: {item.beneficiary_count || "-"}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
          <HeatMapPanel />
        </div>
      </div>
    </RoleGuard>
  );
}
