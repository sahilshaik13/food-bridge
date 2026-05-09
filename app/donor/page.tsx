"use client";

import { RoleGuard } from "@/components/RoleGuard";
import { AppNav } from "@/components/AppNav";
import { DonationForm } from "@/components/DonationForm";
import { DonationCard } from "@/components/DonationCard";
import { ImpactStats } from "@/components/ImpactStats";
import { TelegramPanel } from "@/components/TelegramPanel";
import { useAuth } from "@/lib/AuthProvider";
import { apiGetCached, apiSend, replayPendingActions } from "@/lib/api";
import { useState, useEffect } from "react";
import Link from "next/link";
import { BarChart3, Trophy, Bell, AlertTriangle } from "lucide-react";
import { onValue, ref } from "firebase/database";
import { realtimeDatabase } from "@/lib/firebase";

export default function DonorPage() {
  return (
    <RoleGuard allowedRoles={["donor"]}>
      <DonorDashboard />
    </RoleGuard>
  );
}

function DonorDashboard() {
  const { profile } = useAuth();
  const [donations, setDonations] = useState<any[]>([]);
  const [impact, setImpact] = useState<any>(null);
  const [notifications, setNotifications] = useState<any[]>([]);
  const [emergencyPools, setEmergencyPools] = useState<any[]>([]);
  const [activeEmergencyPopups, setActiveEmergencyPopups] = useState<any[]>([]);
  const [dismissedPopupIds, setDismissedPopupIds] = useState<string[]>([]);
  const [poolQtyById, setPoolQtyById] = useState<Record<string, string>>({});
  const [apiError, setApiError] = useState<string | null>(null);

  const normalizeDonation = (item: any) => {
    const normalizeTs = (value: any) => {
      if (!value) return value;
      if (typeof value === "string") return value;
      if (value?.toDate) return value.toDate().toISOString();
      return value;
    };
    return {
      ...item,
      created_at: normalizeTs(item.created_at),
      updated_at: normalizeTs(item.updated_at),
      expires_at: normalizeTs(item.expires_at),
      last_escalation_at: normalizeTs(item.last_escalation_at),
    };
  };

  const refresh = async () => {
    setApiError(null);
    try {
      const [donationsData, impactData, notificationsData, poolsData] = await Promise.all([
        apiGetCached<any[]>("/donations", 8000),
        apiGetCached<any>("/impact", 8000),
        apiGetCached<any[]>("/communications/notifications", 5000),
        apiGetCached<any[]>("/emergency-requests/active-popup", 5000),
      ]);
      setDonations(donationsData.map(normalizeDonation));
      setImpact(impactData);
      setNotifications(notificationsData);
      setEmergencyPools(poolsData);
      setActiveEmergencyPopups(poolsData);
    } catch (err: any) {
      setApiError("Backend unreachable or request failed. Donor data is not loaded.");
      setDonations([]);
      setNotifications([]);
      setImpact(null);
      setEmergencyPools([]);
      setActiveEmergencyPopups([]);
    }
  };

  useEffect(() => {
    replayPendingActions();
    refresh();
    // RTDB is authoritative for active donation list; keep one-time bootstrap only.
  }, [profile?.entity_id]);

  useEffect(() => {
    if (!profile?.entity_id) return;
    const activeRef = ref(realtimeDatabase, `active_feeds/donor/${profile.entity_id}`);
    const unsub = onValue(activeRef, (snap) => {
      const val = snap.val() || {};
      const list = Object.values(val as Record<string, any>);
      setDonations(list.map(normalizeDonation));
    });
    return () => unsub();
  }, [profile?.entity_id]);

  useEffect(() => {
    if (!profile?.entity_id) return;
    const emergencyRef = ref(realtimeDatabase, `active_feeds/emergency/donor/${profile.entity_id}`);
    const unsub = onValue(emergencyRef, (snap) => {
      const val = snap.val() || {};
      const list = Object.values(val as Record<string, any>);
      setEmergencyPools(list);
      setActiveEmergencyPopups(list);
    });
    return () => unsub();
  }, [profile?.entity_id]);

  const contributeToPool = async (requestId: string) => {
    if (!profile?.entity_id) return;
    const quantity = Number(poolQtyById[requestId] || "0");
    if (!quantity || quantity <= 0) return;
    try {
      await apiSend(`/emergency-requests/${requestId}/contribute`, { donor_id: profile.entity_id, quantity_kg: quantity });
      setPoolQtyById((prev) => ({ ...prev, [requestId]: "" }));
    } catch {
      setApiError("Failed to contribute to emergency pool.");
    }
  };

  const unread = notifications.filter((n: any) => !n.read).length;
  const activeStatuses = new Set(["pending_match", "notified", "accepted", "assigned", "needs_review"]);
  const activeDonations = donations.filter((d: any) => activeStatuses.has(d.status));
  const visiblePopup = activeEmergencyPopups.find((item) => !dismissedPopupIds.includes(item.id));

  return (
    <div className="min-h-screen bg-paper/30">
      <AppNav />

      <div className="mx-auto max-w-7xl px-5 py-8">
        {visiblePopup && (
          <div className="mb-5 rounded-2xl border border-chili/30 bg-chili/10 p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-chili">Emergency alert</p>
                <h3 className="text-lg font-bold text-ink">
                  {visiblePopup.ngo_name} needs {visiblePopup.food_type}
                </h3>
                <p className="text-sm text-ink/70">
                  Reason: {visiblePopup.reason} · Remaining: {visiblePopup.remaining_kg} kg · Time left: {Math.ceil((visiblePopup.countdown_seconds || 0) / 60)} min
                </p>
              </div>
              <button
                onClick={() => setDismissedPopupIds((prev) => [...prev, visiblePopup.id])}
                className="rounded-lg border border-ink/10 bg-white px-3 py-1 text-xs font-bold text-ink hover:bg-field"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}
        {/* Header */}
        <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-ink/40">Donor Dashboard</p>
            <h1 className="text-3xl font-bold text-ink">{profile?.name || profile?.display_name || "My Dashboard"}</h1>
          </div>
          <div className="flex gap-3">
            {unread > 0 && (
              <div className="flex items-center gap-1.5 rounded-full bg-chili/10 px-3 py-1.5 text-xs font-bold text-chili">
                <Bell className="size-3" />
                {unread} new alerts
              </div>
            )}
            <Link href="/donor/reports" className="flex items-center gap-2 rounded-xl border border-ink/10 bg-white px-4 py-2.5 text-sm font-bold text-ink shadow-sm hover:bg-field">
              <BarChart3 className="size-4" /> Reports
            </Link>
            <Link href="/donor/history" className="flex items-center gap-2 rounded-xl border border-ink/10 bg-white px-4 py-2.5 text-sm font-bold text-ink shadow-sm hover:bg-field">
              History
            </Link>
            <Link href="/donor/donate" className="flex items-center gap-2 rounded-xl bg-leaf px-4 py-2.5 text-sm font-bold text-white shadow-line hover:bg-ink">
              + Post Surplus
            </Link>
          </div>
        </div>

        <ImpactStats impact={impact} />
        {emergencyPools.length > 0 && (
          <div className="mt-6 rounded-2xl border border-ink/10 bg-white p-5 shadow-lift">
            <h2 className="text-lg font-bold text-ink">Emergency Pool Broadcasts</h2>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              {emergencyPools.map((pool: any) => (
                <div key={pool.id} className="rounded-xl border border-ink/10 bg-paper/60 p-4">
                  <p className="font-bold capitalize text-ink">{pool.food_type}</p>
                  <p className="text-xs text-ink/60">{pool.ngo_name}</p>
                  <p className="mt-1 text-xs text-chili font-bold">Reason: {pool.reason}</p>
                  <p className="mt-1 text-sm text-ink/70">
                    Pool: {pool.pledged_kg} / {pool.quantity_goal_kg} kg
                  </p>
                  <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-ink/10">
                    <div className="h-full bg-leaf" style={{ width: `${pool.progress_pct || 0}%` }} />
                  </div>
                  <p className="text-xs text-ink/50">Status: {pool.status}</p>
                  {pool.pool_open && (
                    <div className="mt-3 flex gap-2">
                      <input
                        type="number"
                        min="1"
                        value={poolQtyById[pool.id] || ""}
                        onChange={(e) => setPoolQtyById((prev) => ({ ...prev, [pool.id]: e.target.value }))}
                        placeholder="kg"
                        className="w-24 rounded-lg border border-ink/15 px-2 py-1 text-sm"
                      />
                      <button
                        onClick={() => contributeToPool(pool.id)}
                        className="rounded-lg bg-leaf px-3 py-1.5 text-xs font-bold text-white hover:bg-ink"
                      >
                        Contribute
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
        {apiError && (
          <div className="mt-4 flex items-center gap-2 rounded-xl bg-chili/10 px-4 py-3 text-sm font-bold text-chili">
            <AlertTriangle className="size-4" />
            {apiError}
          </div>
        )}

        <div className="mt-8 grid gap-8 lg:grid-cols-[1fr_360px]">
          {/* Main: donations list */}
          <div className="grid gap-6">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-ink">Active Surplus Listings</h2>
              <button onClick={refresh} className="text-xs font-bold text-leaf hover:underline">Refresh</button>
            </div>
            {activeDonations.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-ink/15 py-16 text-center">
                <p className="font-bold text-ink/40">No active donations yet</p>
                <Link href="/donor/donate" className="mt-3 inline-block text-sm font-bold text-leaf hover:underline">Post your first surplus →</Link>
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2">
                {activeDonations.map((d: any) => <DonationCard key={d.id} donation={d} onUpdate={refresh} />)}
              </div>
            )}
          </div>

          {/* Sidebar */}
          <aside className="grid content-start gap-6">
            <DonationForm onSuccess={refresh} mode="embedded" />
            <TelegramPanel />
          </aside>
        </div>
      </div>
    </div>
  );
}
