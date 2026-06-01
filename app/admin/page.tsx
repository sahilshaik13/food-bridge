"use client";

import { RoleGuard } from "@/components/RoleGuard";
import { AppNav } from "@/components/AppNav";
import { AdminUsersPanel } from "@/components/AdminUsersPanel";
import { useAuth } from "@/lib/AuthProvider";
import { apiGet, apiSend } from "@/lib/api";
import { useState, useEffect } from "react";
import { Users, Package, AlertTriangle, CheckCircle2, BarChart3 } from "lucide-react";
import { HeatMapPanel } from "@/components/HeatMapPanel";
import { EntityNameTables } from "@/components/EntityNameTables";
import { realtimeDatabase } from "@/lib/firebase";
import { onValue, ref } from "firebase/database";

export default function AdminPage() {
  return (
    <RoleGuard allowedRoles={["super_admin"]}>
      <AdminDashboard />
    </RoleGuard>
  );
}

function AdminDashboard() {
  const { profile } = useAuth();
  const [stats, setStats] = useState<any>(null);
  const [flagged, setFlagged] = useState<any[]>([]);
  const [emergencyHistory, setEmergencyHistory] = useState<any[]>([]);
  const [directory, setDirectory] = useState<{ donors: any[]; ngos: any[]; volunteers: any[] }>({
    donors: [],
    ngos: [],
    volunteers: [],
  });
  const [error, setError] = useState<string | null>(null);

  const loadAdminData = async () => {
    setError(null);
    try {
      const [impact, donations] = await Promise.all([
        apiGet<any>("/impact"),
        apiGet<any[]>("/donations"),
      ]);
      setStats(impact);
      setFlagged(donations.filter((d) => d.status === "needs_review"));
    } catch {
      setError("Backend request failed. Admin data is not loaded.");
      setStats(null);
      setFlagged([]);
    }
  };

  useEffect(() => {
    loadAdminData();
  }, []);

  useEffect(() => {
    const historyRef = ref(realtimeDatabase, "history_feeds/emergency/admin");
    const impactRef = ref(realtimeDatabase, "metrics/impact/global");
    const directoryRef = ref(realtimeDatabase, "directory/entities");
    const unsub = onValue(historyRef, (snap) => {
      const val = snap.val() || {};
      const list = Object.values(val as Record<string, any>).sort((a: any, b: any) =>
        new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
      );
      setEmergencyHistory(list);
    });
    const unsubImpact = onValue(impactRef, (snap) => {
      const val = snap.val();
      if (val) setStats(val);
    });
    const unsubDirectory = onValue(directoryRef, (snap) => {
      const val = snap.val() || {};
      setDirectory({
        donors: Object.values(val.donors || {}),
        ngos: Object.values(val.ngos || {}),
        volunteers: Object.values(val.volunteers || {}),
      });
    });
    return () => {
      unsub();
      unsubImpact();
      unsubDirectory();
    };
  }, []);

  return (
    <div className="min-h-screen bg-paper/30">
      <AppNav />

      <div className="mx-auto max-w-7xl px-5 py-8">
        <div className="mb-8">
          <p className="text-[10px] font-bold uppercase tracking-widest text-ink/40">System Console</p>
          <h1 className="text-3xl font-bold text-ink">Admin Dashboard</h1>
        </div>
        {error && (
          <div className="mb-6 rounded-xl bg-chili/10 px-4 py-3 text-sm font-bold text-chili">{error}</div>
        )}

        {/* Stat cards */}
        <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            { label: "Total Meals", value: stats?.meals_served ?? "—", icon: Package, color: "text-leaf", bg: "bg-leaf/10" },
            { label: "Kg Saved", value: stats?.kg_saved ?? "—", icon: BarChart3, color: "text-civic", bg: "bg-civic/10" },
            { label: "Flagged Queue", value: flagged.length, icon: AlertTriangle, color: "text-chili", bg: "bg-chili/10" },
            { label: "Active Donations", value: stats?.active_donations ?? "—", icon: CheckCircle2, color: "text-saffron", bg: "bg-saffron/10" },
          ].map(({ label, value, icon: Icon, color, bg }) => (
            <div key={label} className="flex items-center gap-4 rounded-2xl border border-ink/10 bg-white p-5 shadow-lift">
              <div className={`rounded-xl p-3 ${bg} ${color}`}><Icon className="size-6" /></div>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-ink/40">{label}</p>
                <p className="text-2xl font-bold text-ink">{typeof value === "number" ? value.toLocaleString() : value}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Flagged donations */}
        {flagged.length > 0 && (
          <div className="mb-8 rounded-2xl border border-chili/20 bg-chili/5 p-6">
            <h2 className="mb-4 flex items-center gap-2 font-bold text-chili">
              <AlertTriangle className="size-5" /> Manual Review Queue ({flagged.length})
            </h2>
            <div className="grid gap-3">
              {flagged.map((d) => (
                <div key={d.id} className="flex items-center justify-between rounded-xl bg-white p-4 shadow-sm">
                  <div>
                    <p className="font-bold text-ink">{d.food_type} — {d.donor_name}</p>
                    <p className="text-xs text-ink/50">{d.scan?.reason}</p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          await apiSend(`/donations/${d.id}/admin/approve`, {}, "POST");
                          await loadAdminData();
                        } catch {
                          setError("Approve failed. Check role claim is super_admin.");
                        }
                      }}
                      className="rounded-lg bg-leaf/10 px-3 py-1.5 text-xs font-bold text-leaf hover:bg-leaf hover:text-white"
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          await apiSend(`/donations/${d.id}/admin/reject`, {}, "POST");
                          await loadAdminData();
                        } catch {
                          setError("Reject failed. Check role claim is super_admin.");
                        }
                      }}
                      className="rounded-lg bg-chili/10 px-3 py-1.5 text-xs font-bold text-chili hover:bg-chili hover:text-white"
                    >
                      Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {emergencyHistory.length > 0 && (
          <div className="mb-8 rounded-2xl border border-ink/10 bg-white p-6 shadow-lift">
            <h2 className="mb-4 text-xl font-bold text-ink">Emergency History (Realtime)</h2>
            <div className="grid gap-2">
              {emergencyHistory.slice(0, 10).map((item: any) => (
                <div key={item.id} className="rounded-xl border border-ink/10 p-3 text-sm">
                  <p className="font-bold text-ink">{item.ngo_name} · {item.food_type} · {item.status}</p>
                  <p className="text-ink/60">{item.pledged_kg}/{item.quantity_goal_kg} kg · Urgency: {item.urgency_level || "high"}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="mb-8">
          <h2 className="mb-4 text-xl font-bold text-ink">Entity Directory (Realtime)</h2>
          <EntityNameTables donors={directory.donors} ngos={directory.ngos} volunteers={directory.volunteers} />
        </div>


        {/* User verification */}
        <div className="mb-8">
          <AdminUsersPanel />
        </div>

        {/* Heat Map Panel */}
        <div>
          <h2 className="mb-4 text-xl font-bold text-ink">Live Distribution Map</h2>
          <HeatMapPanel />
        </div>
      </div>
    </div>
  );
}
