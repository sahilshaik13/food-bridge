"use client";

import Link from "next/link";
import { ArrowLeft, AlertTriangle } from "lucide-react";
import { RoleGuard } from "@/components/RoleGuard";
import { PageHeader } from "@/components/PageHeader";
import { apiGet } from "@/lib/api";
import { useEffect, useState } from "react";
import { realtimeDatabase } from "@/lib/firebase";
import { onValue, ref } from "firebase/database";
import { useAuth } from "@/lib/AuthProvider";

export default function DonorHistoryPage() {
  return (
    <RoleGuard allowedRoles={["donor"]}>
      <HistoryContent />
    </RoleGuard>
  );
}

function HistoryContent() {
  const { profile } = useAuth();
  const [items, setItems] = useState<any[]>([]);
  const [emergencyHistory, setEmergencyHistory] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  const formatDuration = (seconds?: number | null) => {
    if (seconds === null || seconds === undefined) return "-";
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    if (mins === 0) return `${secs}s`;
    return `${mins}m ${secs}s`;
  };

  useEffect(() => {
    const run = async () => {
      setError(null);
      try {
        const donations = await apiGet<any[]>("/donations");
        const historyStatuses = new Set(["declined", "completed", "expired", "wasted"]);
        const isHistoryRecord = (d: any) =>
          historyStatuses.has(d.status) ||
          Boolean(d.completed_at) ||
          Boolean(d.delivery_confirmed_at) ||
          d.volunteer_task_status === "delivered_pending_confirmation" ||
          d.volunteer_task_status === "delivered_confirmed";
        setItems(donations.filter(isHistoryRecord));
      } catch {
        setError("Failed to load donor history from backend.");
        setItems([]);
      }
    };
    run();
  }, []);

  useEffect(() => {
    if (!profile?.entity_id) return;
    const historyRef = ref(realtimeDatabase, `history_feeds/emergency/donor/${profile.entity_id}`);
    const unsub = onValue(historyRef, (snap) => {
      const val = snap.val() || {};
      const list = Object.values(val as Record<string, any>).sort((a: any, b: any) =>
        new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
      );
      setEmergencyHistory(list);
    });
    return () => unsub();
  }, [profile?.entity_id]);

  return (
    <main className="min-h-screen">
      <PageHeader eyebrow="Donor" title="Donation History" description="Track completed, rejected, and expired donations." />
      <section className="mx-auto max-w-6xl px-5 pt-2">
        <Link href="/donor" className="inline-flex items-center gap-2 text-sm font-bold text-leaf hover:underline">
          <ArrowLeft className="size-4" />
          Back to donor dashboard
        </Link>
      </section>
      {error && (
        <section className="mx-auto max-w-6xl px-5 pt-4">
          <div className="flex items-center gap-2 rounded-xl bg-chili/10 px-4 py-3 text-sm font-bold text-chili">
            <AlertTriangle className="size-4" />
            {error}
          </div>
        </section>
      )}
      <section className="mx-auto max-w-6xl px-5 py-6">
        {emergencyHistory.length > 0 && (
          <div className="mb-6 overflow-hidden rounded-2xl border border-ink/10 bg-white shadow-lift">
            <div className="border-b border-ink/10 bg-field px-4 py-3 text-sm font-bold text-ink">Emergency Pool History (Realtime)</div>
            <div className="divide-y divide-ink/5">
              {emergencyHistory.map((item: any) => (
                <div key={item.id} className="px-4 py-3 text-sm">
                  <p className="font-bold capitalize text-ink">{item.food_type} · {item.status}</p>
                  <p className="text-ink/60">{item.ngo_name} · {item.pledged_kg}/{item.quantity_goal_kg} kg · {new Date(item.updated_at || item.created_at).toLocaleString()}</p>
                </div>
              ))}
            </div>
          </div>
        )}
        {items.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-ink/15 py-16 text-center">
            <p className="font-bold text-ink/40">No history records yet</p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-2xl border border-ink/10 bg-white shadow-lift">
            <table className="w-full text-left text-sm">
              <thead className="bg-field text-ink/70">
                <tr>
                  <th className="px-4 py-3 font-bold">Food</th>
                  <th className="px-4 py-3 font-bold">NGO</th>
                  <th className="px-4 py-3 font-bold">Qty</th>
                  <th className="px-4 py-3 font-bold">Status</th>
                  <th className="px-4 py-3 font-bold">Accept Time</th>
                  <th className="px-4 py-3 font-bold">Delivery Time</th>
                  <th className="px-4 py-3 font-bold">Updated</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const itemSummary = Array.isArray(item.items) && item.items.length > 0
                    ? item.items.map((entry: any) => `${entry.food_type} (${entry.quantity_kg}kg)`).join(", ")
                    : item.food_type;
                  const effectiveCompleted =
                    item.status === "completed" ||
                    Boolean(item.completed_at) ||
                    Boolean(item.delivery_confirmed_at) ||
                    item.volunteer_task_status === "delivered_pending_confirmation" ||
                    item.volunteer_task_status === "delivered_confirmed";
                  const statusLabel = effectiveCompleted ? "completed" : item.status === "declined" ? "rejected" : item.status;
                  return (
                  <tr key={item.id} className="border-t border-ink/5">
                    <td className="px-4 py-3 font-bold capitalize text-ink">{itemSummary}</td>
                    <td className="px-4 py-3 text-ink/70">{item.assigned_ngo_name || item.ngo_queue?.[0]?.ngo_name || "-"}</td>
                    <td className="px-4 py-3 text-ink/70">{item.quantity_kg} kg</td>
                    <td className="px-4 py-3">
                      <span className="rounded-full bg-ink/10 px-2 py-1 text-xs font-bold uppercase tracking-wide text-ink">
                        {statusLabel}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-ink/60">{formatDuration(item.acceptance_seconds)}</td>
                    <td className="px-4 py-3 text-ink/60">{formatDuration(item.delivery_seconds)}</td>
                    <td className="px-4 py-3 text-ink/60">{item.updated_at ? new Date(item.updated_at).toLocaleString() : "-"}</td>
                  </tr>
                )})}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
