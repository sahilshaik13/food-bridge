"use client";

import { RoleGuard } from "@/components/RoleGuard";
import { AppNav } from "@/components/AppNav";
import { DonationCard } from "@/components/DonationCard";
import { PredictionPanel } from "@/components/PredictionPanel";
import { useAuth } from "@/lib/AuthProvider";
import { apiGet, apiSend } from "@/lib/api";
import { useState, useEffect } from "react";
import Link from "next/link";
import { UserPlus, Send, Copy, Check, AlertTriangle, Users } from "lucide-react";
import { onValue, ref } from "firebase/database";
import { realtimeDatabase } from "@/lib/firebase";

export default function NgoPage() {
  return (
    <RoleGuard allowedRoles={["ngo_coordinator"]}>
      <NgoDashboard />
    </RoleGuard>
  );
}

function NgoDashboard() {
  const { profile } = useAuth();
  const [donations, setDonations] = useState<any[]>([]);
  const [vName, setVName] = useState("");
  const [vEmail, setVEmail] = useState("");
  const [vPhone, setVPhone] = useState("");
  const [inviteLink, setInviteLink] = useState("");
  const [copied, setCopied] = useState(false);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [inviteError, setInviteError] = useState("");
  const [apiError, setApiError] = useState<string | null>(null);
  const [volunteers, setVolunteers] = useState<any[]>([]);
  const [volunteerFilter, setVolunteerFilter] = useState<"all" | "invited" | "pending_approval" | "active" | "rejected">("all");

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
      const ngoId = profile?.entity_id || profile?.id;
      const [donationsData, volunteersData] = await Promise.all([
        apiGet<any[]>("/donations"),
        ngoId ? apiGet<any[]>(`/volunteers?ngo_id=${encodeURIComponent(ngoId)}`) : Promise.resolve([]),
      ]);
      setDonations(donationsData.map(normalizeDonation));
      setVolunteers(volunteersData);
    } catch {
      setApiError("Backend unreachable or request failed. NGO inbox is not loaded.");
      setDonations([]);
      setVolunteers([]);
    }
  };

  useEffect(() => {
    refresh();
    // RTDB is authoritative for active donation list; keep one-time bootstrap only.
  }, [profile?.entity_id]);

  useEffect(() => {
    if (!profile?.entity_id) return;
    const activeRef = ref(realtimeDatabase, `active_feeds/ngo/${profile.entity_id}`);
    const unsub = onValue(activeRef, (snap) => {
      const val = snap.val() || {};
      const list = Object.values(val as Record<string, any>);
      setDonations(list.map(normalizeDonation));
    });
    return () => unsub();
  }, [profile?.entity_id]);

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    setInviteLoading(true);
    setInviteError("");
    try {
      const res: any = await apiSend("/volunteers/invite", {
        ngo_id: profile?.id || profile?.entity_id || "ngo_default",
        name: vName,
        email: vEmail,
        phone: vPhone || "+910000000000",
      });
      if (res?.invite_link) {
        setInviteLink(res.invite_link);
        setVName(""); setVEmail(""); setVPhone("");
      }
    } catch (err: any) {
      setInviteError(err.message || "Failed to generate invite");
    } finally {
      setInviteLoading(false);
    }
  };

  const copyLink = () => {
    navigator.clipboard.writeText(inviteLink);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const updateVolunteerApproval = async (volunteerId: string, action: "approve" | "reject") => {
    try {
      await apiSend(`/volunteers/${volunteerId}/${action}`, {});
      await refresh();
    } catch (err: any) {
      setApiError(err.message || "Failed to update volunteer approval.");
    }
  };

  const resendInvite = async (volunteerId: string) => {
    try {
      const res: any = await apiSend(`/volunteers/${volunteerId}/resend-invite`, {});
      if (res?.invite_link) setInviteLink(res.invite_link);
      await refresh();
    } catch (err: any) {
      setApiError(err.message || "Failed to resend volunteer invite.");
    }
  };

  const revokeInvite = async (volunteerId: string) => {
    try {
      await apiSend(`/volunteers/${volunteerId}/revoke-invite`, {});
      await refresh();
    } catch (err: any) {
      setApiError(err.message || "Failed to revoke volunteer invite.");
    }
  };

  const pendingDonations = donations.filter((d: any) =>
    ["pending_match", "notified", "needs_review", "accepted", "assigned"].includes(d.status) &&
    d.volunteer_task_status !== "delivered_confirmed"
  );
  const activeDonations = donations.filter((d: any) =>
    ["accepted", "assigned"].includes(d.status)
  );
  const filteredVolunteers = volunteers.filter((v: any) => volunteerFilter === "all" || v.status === volunteerFilter);

  return (
    <div className="min-h-screen bg-paper/30">
      <AppNav />

      <div className="mx-auto max-w-7xl px-5 py-8">
        {/* Header */}
        <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-ink/40">NGO Coordinator</p>
            <h1 className="text-3xl font-bold text-ink">{profile?.name || profile?.display_name || "NGO Dashboard"}</h1>
          </div>
          <div className="flex gap-3">
            <Link href="/ngo/emergency" className="flex items-center gap-2 rounded-xl bg-chili px-4 py-2.5 text-sm font-bold text-white shadow-line hover:bg-chili/90">
              <AlertTriangle className="size-4" /> Emergency Request
            </Link>
            <Link href="/ngo/history" className="flex items-center gap-2 rounded-xl border border-ink/10 bg-white px-4 py-2.5 text-sm font-bold text-ink shadow-sm hover:bg-field">
              History
            </Link>
            <Link href="/ngo/profile" className="flex items-center gap-2 rounded-xl border border-ink/10 bg-white px-4 py-2.5 text-sm font-bold text-ink shadow-sm hover:bg-field">
              <Users className="size-4" /> Our Profile
            </Link>
          </div>
        </div>

        <div className="grid gap-8 lg:grid-cols-[1fr_340px]">
          {apiError && (
            <div className="lg:col-span-2 flex items-center gap-2 rounded-xl bg-chili/10 px-4 py-3 text-sm font-bold text-chili">
              <AlertTriangle className="size-4" />
              {apiError}
            </div>
          )}
          {/* Main: donation queues */}
          <div className="grid gap-8">
            {/* Pending queue */}
            <section>
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-lg font-bold text-ink">
                  Incoming Requests
                  {pendingDonations.length > 0 && (
                    <span className="ml-2 rounded-full bg-saffron px-2 py-0.5 text-xs text-ink">{pendingDonations.length}</span>
                  )}
                </h2>
                <button onClick={refresh} className="text-xs font-bold text-leaf hover:underline">Refresh</button>
              </div>
              {pendingDonations.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-ink/15 py-12 text-center">
                  <p className="font-bold text-ink/40">No pending donations</p>
                  <p className="mt-1 text-xs text-ink/30">New donations will appear here when nearby restaurants post surplus</p>
                </div>
              ) : (
                <div className="grid gap-4 md:grid-cols-2">
                  {pendingDonations.map((d: any) => <DonationCard key={d.id} donation={d} onUpdate={refresh} />)}
                </div>
              )}
            </section>

            {/* Active pickups */}
            {activeDonations.length > 0 && (
              <section>
                <h2 className="mb-4 text-lg font-bold text-ink">Active Pickups</h2>
                <div className="grid gap-4 md:grid-cols-2">
                  {activeDonations.map((d: any) => <DonationCard key={d.id} donation={d} onUpdate={refresh} />)}
                </div>
              </section>
            )}
          </div>

          {/* Sidebar */}
          <aside className="grid content-start gap-6">
            {/* Invite volunteer */}
            <div className="rounded-2xl border border-ink/10 bg-white p-6 shadow-lift">
              <div className="mb-4 flex items-center gap-2">
                <div className="rounded-lg bg-leaf/10 p-2 text-leaf"><UserPlus className="size-5" /></div>
                <h3 className="font-bold text-ink">Invite Volunteer</h3>
              </div>

              {inviteLink ? (
                <div className="grid gap-3">
                  <p className="text-xs text-ink/60">Share this unique link with the volunteer:</p>
                  <div className="flex gap-2">
                    <input readOnly value={inviteLink} className="flex-1 rounded-xl border border-ink/10 bg-field px-3 py-2 font-mono text-xs" />
                    <button onClick={copyLink} className="rounded-xl bg-ink p-2.5 text-white hover:bg-ink/80">
                      {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
                    </button>
                  </div>
                  <button onClick={() => setInviteLink("")} className="text-xs font-bold text-leaf hover:underline">
                    Invite another volunteer
                  </button>
                </div>
              ) : (
                <form onSubmit={handleInvite} className="grid gap-3">
                  <input placeholder="Full Name *" value={vName} onChange={(e) => setVName(e.target.value)}
                    className="rounded-xl border border-ink/10 bg-field px-4 py-2.5 text-sm outline-none focus:border-leaf" required />
                  <input type="email" placeholder="Email Address *" value={vEmail} onChange={(e) => setVEmail(e.target.value)}
                    className="rounded-xl border border-ink/10 bg-field px-4 py-2.5 text-sm outline-none focus:border-leaf" required />
                  <input type="tel" placeholder="Phone Number" value={vPhone} onChange={(e) => setVPhone(e.target.value)}
                    className="rounded-xl border border-ink/10 bg-field px-4 py-2.5 text-sm outline-none focus:border-leaf" />
                  {inviteError && <p className="text-xs font-bold text-chili">{inviteError}</p>}
                  <button type="submit" disabled={inviteLoading}
                    className="flex items-center justify-center gap-2 rounded-xl bg-leaf py-3 font-bold text-white shadow-line hover:bg-ink disabled:opacity-50">
                    <Send className="size-4" />
                    {inviteLoading ? "Generating…" : "Generate Invite Link"}
                  </button>
                </form>
              )}
            </div>

            <div className="rounded-2xl border border-ink/10 bg-white p-6 shadow-lift">
              <h3 className="font-bold text-ink">Volunteer Approval Queue</h3>
              <div className="mt-3 flex flex-wrap gap-2">
                {(["all", "invited", "pending_approval", "active", "rejected"] as const).map((status) => (
                  <button
                    key={status}
                    onClick={() => setVolunteerFilter(status)}
                    className={`rounded-full px-3 py-1 text-xs font-bold ${
                      volunteerFilter === status ? "bg-ink text-white" : "bg-field text-ink/70 hover:bg-ink/10"
                    }`}
                  >
                    {status.replace("_", " ")}
                  </button>
                ))}
              </div>
              {volunteers.length === 0 ? (
                <p className="mt-3 text-sm text-ink/50">No volunteers invited yet.</p>
              ) : (
                <div className="mt-3 grid gap-2">
                  {filteredVolunteers.map((v: any) => (
                    <div key={v.id} className="rounded-xl border border-ink/10 p-3">
                      <p className="font-bold text-ink">{v.name}</p>
                      <p className="text-xs text-ink/60">{v.email || "No email"}</p>
                      <p className="mt-1 text-xs font-bold uppercase tracking-wide text-ink/50">{v.status}</p>
                      {(v.status === "invited" || v.status === "pending_approval") && (
                        <div className="mt-2 flex gap-2">
                          <button
                            onClick={() => updateVolunteerApproval(v.id, "approve")}
                            className="rounded-lg bg-leaf px-3 py-1.5 text-xs font-bold text-white hover:bg-ink"
                          >
                            Approve
                          </button>
                          <button
                            onClick={() => updateVolunteerApproval(v.id, "reject")}
                            className="rounded-lg border border-chili/40 bg-white px-3 py-1.5 text-xs font-bold text-chili hover:bg-chili/5"
                          >
                            Reject
                          </button>
                          <button
                            onClick={() => resendInvite(v.id)}
                            className="rounded-lg border border-civic/30 bg-white px-3 py-1.5 text-xs font-bold text-civic hover:bg-civic/5"
                          >
                            Resend
                          </button>
                          <button
                            onClick={() => revokeInvite(v.id)}
                            className="rounded-lg border border-ink/25 bg-white px-3 py-1.5 text-xs font-bold text-ink hover:bg-field"
                          >
                            Revoke
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                  {filteredVolunteers.length === 0 && (
                    <p className="text-sm text-ink/50">No volunteers in selected status.</p>
                  )}
                </div>
              )}
            </div>

            <PredictionPanel />
          </aside>
        </div>
      </div>
    </div>
  );
}
