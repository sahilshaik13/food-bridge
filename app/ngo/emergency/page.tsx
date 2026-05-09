"use client";

import Link from "next/link";
import { ArrowLeft, AlertTriangle } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { RoleGuard } from "@/components/RoleGuard";
import { useAuth } from "@/lib/AuthProvider";
import { apiGetCached, apiSend, replayPendingActions } from "@/lib/api";
import { useEffect, useState } from "react";
import { realtimeDatabase } from "@/lib/firebase";
import { onValue, ref } from "firebase/database";

export default function NgoEmergencyPage() {
  return (
    <RoleGuard allowedRoles={["ngo_coordinator"]}>
      <EmergencyContent />
    </RoleGuard>
  );
}

function EmergencyContent() {
  const { profile } = useAuth();
  const [foodType, setFoodType] = useState("cooked meals");
  const [goalKg, setGoalKg] = useState("25");
  const [deadlineMinutes, setDeadlineMinutes] = useState("120");
  const [reason, setReason] = useState("flood relief");
  const [urgencyLevel, setUrgencyLevel] = useState<"low" | "medium" | "high" | "critical">("high");
  const [beneficiaryCount, setBeneficiaryCount] = useState("80");
  const [requiredByMealTime, setRequiredByMealTime] = useState("Dinner");
  const [contactPhone, setContactPhone] = useState("");
  const [pickupAddress, setPickupAddress] = useState("");
  const [minContributionKg, setMinContributionKg] = useState("1");
  const [maxContributionKg, setMaxContributionKg] = useState("15");
  const [requests, setRequests] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const now = Date.now();

  const loadRequests = async () => {
    setError(null);
    try {
      const all = await apiGetCached<any[]>("/emergency-requests", 5000);
      const ngoId = profile?.entity_id;
      const mine = ngoId ? all.filter((item) => item.ngo_id === ngoId) : [];
      setRequests(mine);
    } catch {
      setError("Failed to load emergency requests from backend.");
      setRequests([]);
    }
  };

  useEffect(() => {
    replayPendingActions();
    loadRequests();
  }, [profile?.entity_id]);

  useEffect(() => {
    if (!profile?.entity_id) return;
    const emergencyRef = ref(realtimeDatabase, `active_feeds/emergency/ngo/${profile.entity_id}`);
    const unsubscribe = onValue(emergencyRef, (snapshot) => {
      const val = snapshot.val() || {};
      const mine = Object.values(val as Record<string, any>).sort((a: any, b: any) => {
        const aTime = new Date(a.created_at || 0).getTime();
        const bTime = new Date(b.created_at || 0).getTime();
        return bTime - aTime;
      });
      setRequests(mine);
    });
    return () => unsubscribe();
  }, [profile?.entity_id]);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!profile?.entity_id) {
      setError("NGO account is not linked to an NGO entity profile.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await apiSend("/emergency-requests", {
        ngo_id: profile.entity_id,
        food_type: foodType,
        quantity_goal_kg: Number(goalKg),
        deadline_minutes: Number(deadlineMinutes),
        reason,
        urgency_level: urgencyLevel,
        beneficiary_count: Number(beneficiaryCount),
        required_by_meal_time: requiredByMealTime || null,
        contact_phone: contactPhone || null,
        pickup_address: pickupAddress || null,
        min_contribution_kg: Number(minContributionKg),
        max_contribution_kg: maxContributionKg ? Number(maxContributionKg) : null,
      });
      await loadRequests();
    } catch {
      setError("Failed to create emergency request.");
    } finally {
      setSubmitting(false);
    }
  };

  const resolveRequest = async (requestId: string, action: "accept_partial" | "cancel") => {
    setResolvingId(requestId);
    setError(null);
    try {
      await apiSend(`/emergency-requests/${requestId}/resolve`, {
        action,
        reason: action === "cancel" ? "Deadline reached or no viable contributions" : "Accepting partial contribution to start distribution",
      });
    } catch {
      setError("Failed to resolve emergency request.");
    } finally {
      setResolvingId(null);
    }
  };

  return (
    <main className="min-h-screen">
      <PageHeader eyebrow="NGO coordinator" title="Emergency Supply Request" description="Live emergency requests and pledge progress from backend." />
      <section className="mx-auto max-w-5xl px-5 pt-2">
        <Link href="/ngo" className="inline-flex items-center gap-2 text-sm font-bold text-leaf hover:underline">
          <ArrowLeft className="size-4" />
          Back to NGO dashboard
        </Link>
      </section>
      {error && (
        <section className="mx-auto max-w-5xl px-5 pt-4">
          <div className="flex items-center gap-2 rounded-xl bg-chili/10 px-4 py-3 text-sm font-bold text-chili">
            <AlertTriangle className="size-4" />
            {error}
          </div>
        </section>
      )}
      <section className="mx-auto grid max-w-5xl gap-4 px-5 py-6 md:grid-cols-3">
        <form onSubmit={onCreate} className="rounded-lg border border-ink/12 bg-white/90 p-5 shadow-line">
          <p className="text-xs font-bold uppercase tracking-widest text-ink/40">Request form</p>
          <div className="mt-3 grid gap-2">
            <select value={foodType} onChange={(e) => setFoodType(e.target.value)} className="rounded-lg border border-ink/15 px-3 py-2 text-sm" required>
              <option value="cooked meals">Cooked Meals</option>
              <option value="rice">Rice</option>
              <option value="dal">Dal</option>
              <option value="roti">Roti</option>
              <option value="mixed food">Mixed Food</option>
              <option value="dry ration">Dry Ration</option>
            </select>
            <select value={urgencyLevel} onChange={(e) => setUrgencyLevel(e.target.value as any)} className="rounded-lg border border-ink/15 px-3 py-2 text-sm">
              <option value="low">Low urgency</option>
              <option value="medium">Medium urgency</option>
              <option value="high">High urgency</option>
              <option value="critical">Critical emergency</option>
            </select>
            <input value={goalKg} onChange={(e) => setGoalKg(e.target.value)} type="number" min="1" className="rounded-lg border border-ink/15 px-3 py-2 text-sm" placeholder="Total goal (kg)" required />
            <input value={beneficiaryCount} onChange={(e) => setBeneficiaryCount(e.target.value)} type="number" min="1" className="rounded-lg border border-ink/15 px-3 py-2 text-sm" placeholder="Beneficiaries impacted" required />
            <input value={deadlineMinutes} onChange={(e) => setDeadlineMinutes(e.target.value)} type="number" min="10" className="rounded-lg border border-ink/15 px-3 py-2 text-sm" placeholder="Deadline minutes" required />
            <input value={requiredByMealTime} onChange={(e) => setRequiredByMealTime(e.target.value)} className="rounded-lg border border-ink/15 px-3 py-2 text-sm" placeholder="Required by meal time (Breakfast/Lunch/Dinner)" />
            <input value={contactPhone} onChange={(e) => setContactPhone(e.target.value)} className="rounded-lg border border-ink/15 px-3 py-2 text-sm" placeholder="Emergency contact phone" />
            <input value={pickupAddress} onChange={(e) => setPickupAddress(e.target.value)} className="rounded-lg border border-ink/15 px-3 py-2 text-sm" placeholder="Pickup/drop location notes" />
            <div className="grid grid-cols-2 gap-2">
              <input value={minContributionKg} onChange={(e) => setMinContributionKg(e.target.value)} type="number" min="0.5" step="0.5" className="rounded-lg border border-ink/15 px-3 py-2 text-sm" placeholder="Min pledge (kg)" />
              <input value={maxContributionKg} onChange={(e) => setMaxContributionKg(e.target.value)} type="number" min="1" step="0.5" className="rounded-lg border border-ink/15 px-3 py-2 text-sm" placeholder="Max pledge (kg)" />
            </div>
            <input value={reason} onChange={(e) => setReason(e.target.value)} className="rounded-lg border border-ink/15 px-3 py-2 text-sm" placeholder="Reason (flood/calamity/etc.)" required />
            <button disabled={submitting} className="rounded-lg bg-leaf px-3 py-2 text-sm font-bold text-white disabled:opacity-50">
              {submitting ? "Creating..." : "Create request"}
            </button>
          </div>
        </form>
        <div className="rounded-lg border border-ink/12 bg-white/90 p-5 shadow-line md:col-span-2">
          <p className="text-xs font-bold uppercase tracking-widest text-ink/40">Live pledge pool / requests</p>
          <div className="mt-3 grid gap-3">
            {requests.length === 0 ? (
              <p className="text-sm font-bold text-ink/50">No emergency requests yet.</p>
            ) : (
              requests.map((req) => (
                <div key={req.id} className="rounded-lg border border-ink/10 bg-paper/60 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-bold text-ink capitalize">{req.food_type}</p>
                    <span className="rounded-full bg-chili/10 px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-chili">
                      {req.status}
                    </span>
                  </div>
                  <p className="text-xs text-ink/60">
                    Urgency: <span className="font-bold uppercase">{req.urgency_level || "high"}</span> · Beneficiaries: {req.beneficiary_count || "-"}
                  </p>
                  <p className="text-sm text-ink/70">
                    Pledged: {req.pledged_kg} / {req.quantity_goal_kg} kg
                  </p>
                  <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-ink/10">
                    <div
                      className="h-full bg-leaf"
                      style={{ width: `${req.quantity_goal_kg > 0 ? Math.min(100, (req.pledged_kg / req.quantity_goal_kg) * 100) : 0}%` }}
                    />
                  </div>
                  <p className="text-xs font-bold text-chili">Reason: {req.reason}</p>
                  <p className="mt-1 text-xs text-ink/50">
                    Contributors: {req.contributions?.length || 0} · Deadline:{" "}
                    {req.deadline_at ? `${Math.max(0, Math.ceil((new Date(req.deadline_at).getTime() - now) / 60000))} min` : "-"}
                  </p>
                  {req.pool_open && (
                    <div className="mt-3 flex gap-2">
                      <button
                        onClick={() => resolveRequest(req.id, "accept_partial")}
                        disabled={resolvingId === req.id || Number(req.pledged_kg || 0) <= 0}
                        className="rounded-lg bg-leaf px-3 py-1.5 text-xs font-bold text-white hover:bg-ink disabled:opacity-50"
                      >
                        Accept Partial
                      </button>
                      <button
                        onClick={() => resolveRequest(req.id, "cancel")}
                        disabled={resolvingId === req.id}
                        className="rounded-lg border border-chili/40 bg-white px-3 py-1.5 text-xs font-bold text-chili hover:bg-chili/5 disabled:opacity-50"
                      >
                        Cancel Pool
                      </button>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
