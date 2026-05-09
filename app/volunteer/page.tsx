"use client";

import { RoleGuard } from "@/components/RoleGuard";
import { AppNav } from "@/components/AppNav";
import { useAuth } from "@/lib/AuthProvider";
import { apiGet, apiSend, replayPendingActions } from "@/lib/api";
import { useState, useEffect } from "react";
import { CheckCircle2, MapPin, Phone, Truck, Loader2, Navigation } from "lucide-react";
import { onValue, ref } from "firebase/database";
import { realtimeDatabase } from "@/lib/firebase";

export default function VolunteerPage() {
  return (
    <RoleGuard allowedRoles={["ngo_volunteer"]}>
      <div className="min-h-screen bg-paper/30">
        <AppNav />
        <VolunteerDashboard />
      </div>
    </RoleGuard>
  );
}

function VolunteerDashboard() {
  const { profile } = useAuth();
  const [tasks, setTasks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirmingTaskId, setConfirmingTaskId] = useState<string | null>(null);
  const [mealsServedByTask, setMealsServedByTask] = useState<Record<string, string>>({});
  const [pickupPhotoByTask, setPickupPhotoByTask] = useState<Record<string, string>>({});
  const [rejectReasonByTask, setRejectReasonByTask] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [overdueTask, setOverdueTask] = useState<any | null>(null);
  const [showRejectConfirm, setShowRejectConfirm] = useState(false);
  const [rejectLock, setRejectLock] = useState(5);
  const activeStatuses = new Set(["accepted", "assigned"]);
  const activeTasks = tasks.filter((t) => activeStatuses.has(t.status));
  const completedHistory = tasks.filter(
    (t) =>
      (t.status === "completed" ||
        t.volunteer_task_status === "delivered_confirmed" ||
        Boolean(t.completed_at)) &&
      (!t.volunteer_uid || t.volunteer_uid === profile?.id),
  );

  const loadTasks = async () => {
    setError(null);
    try {
      const donations = await apiGet<any[]>("/donations");
      setTasks(donations);
    } catch {
      setError("Failed to load volunteer pickups from backend.");
      setTasks([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    replayPendingActions();
    loadTasks();
  }, []);

  useEffect(() => {
    if (!profile?.id) return;
    const activeRef = ref(realtimeDatabase, `active_feeds/volunteer/${profile.id}`);
    const unsub = onValue(activeRef, (snap) => {
      const val = snap.val() || {};
      const activeList = Object.values(val as Record<string, any>);
      if (activeList.length === 0) {
        // Fallback to backend-filtered list to avoid losing tasks when RTDB projection misses a volunteer path.
        loadTasks();
        return;
      }
      setTasks((prev) => {
        const history = prev.filter(
          (t) =>
            t.status === "completed" ||
            t.volunteer_task_status === "delivered_confirmed" ||
            Boolean(t.completed_at),
        );
        return [...activeList, ...history];
      });
    });
    return () => unsub();
  }, [profile?.id]);

  useEffect(() => {
    if (!showRejectConfirm) {
      setRejectLock(5);
      return;
    }
    const timer = setInterval(() => {
      setRejectLock((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [showRejectConfirm]);

  const transitionTask = async (task: any, volunteerTaskStatus: string, patch: Record<string, any> = {}) => {
    setConfirmingTaskId(task.id);
    try {
      await apiSend(
        `/donations/${task.id}/status`,
        {
          status: task.status,
          volunteer_uid: profile?.id,
          volunteer_name: profile?.name || profile?.display_name,
          volunteer_task_status: volunteerTaskStatus,
          ...patch,
        },
        "PATCH",
      );
      await loadTasks();
    } catch {
      setError("Failed to update volunteer task step. Please refresh and retry.");
    } finally {
      setConfirmingTaskId(null);
    }
  };

  const handleOverdueYes = async () => {
    if (!overdueTask) return;
    setConfirmingTaskId(overdueTask.id);
    try {
      await apiSend(`/donations/${overdueTask.id}/status`, {
        status: "assigned",
        buffer_minutes: 15,
        volunteer_uid: profile?.id,
        volunteer_name: profile?.name || profile?.display_name,
        notes: "Volunteer confirmed pickup after delivery timeout. Added 15 minute buffer.",
      }, "PATCH");
      setOverdueTask(null);
      await loadTasks();
    } catch {
      setError("Failed to extend pickup buffer.");
    } finally {
      setConfirmingTaskId(null);
    }
  };

  const handleOverdueReject = async () => {
    if (!overdueTask || rejectLock > 0) return;
    setConfirmingTaskId(overdueTask.id);
    try {
      await apiSend(`/donations/${overdueTask.id}/status`, {
        status: "declined",
        volunteer_uid: profile?.id,
        volunteer_name: profile?.name || profile?.display_name,
        notes: "Volunteer reported pickup not completed after timeout.",
      }, "PATCH");
      setOverdueTask(null);
      setShowRejectConfirm(false);
      await loadTasks();
    } catch {
      setError("Failed to mark pickup as rejected.");
    } finally {
      setConfirmingTaskId(null);
    }
  };

  if (loading) return (
    <div className="flex h-64 items-center justify-center">
      <Loader2 className="size-8 animate-spin text-leaf" />
    </div>
  );

  if (profile?.status && profile.status !== "active" && profile.status !== "verified") {
    return (
      <div className="mx-auto max-w-3xl px-5 py-10">
        <div className="rounded-2xl border border-saffron/30 bg-saffron/10 p-6">
          <h2 className="text-xl font-bold text-ink">Volunteer approval pending</h2>
          <p className="mt-2 text-sm text-ink/70">
            Your registration has been submitted. Please wait for your NGO coordinator to approve your access.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-5 py-8">
      <div className="mb-6">
        <p className="text-[10px] font-bold uppercase tracking-widest text-ink/40">Field Operations</p>
        <h1 className="text-3xl font-bold text-ink">Assigned Pickups</h1>
      </div>

      {error && (
        <div className="mb-6 rounded-xl bg-chili/10 px-4 py-3 text-sm font-bold text-chili">
          {error}
        </div>
      )}

      {activeTasks.length > 0 ? (
      <div className="grid gap-5 md:grid-cols-2">
        {activeTasks.map((task) => (
          <div key={task.id} className="rounded-2xl border border-ink/10 bg-white p-6 shadow-lift">
            <div className="mb-5 flex items-start justify-between">
              <div>
                <span className="mb-2 inline-block rounded-full bg-saffron/20 px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-ink">
                  {task.status}
                </span>
                <h2 className="text-xl font-bold text-ink">{task.food_type}</h2>
                <p className="text-ink/60">{task.donor_name}</p>
              </div>
              <div className="flex gap-2">
                <a href={`tel:${task.donor_phone || ""}`} className="rounded-full bg-field p-3 text-ink hover:bg-ink hover:text-white">
                  <Phone className="size-5" />
                </a>
                <a
                  href={`https://maps.google.com/?q=${task.location?.lat},${task.location?.lng}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-full bg-leaf p-3 text-white hover:bg-ink"
                >
                  <MapPin className="size-5" />
                </a>
              </div>
            </div>

            <div className="mb-4 grid gap-2 rounded-xl bg-field p-4 text-sm">
              <div className="flex justify-between">
                <span className="text-ink/60">Location</span>
                <span className="font-bold text-ink">{task.location?.area}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-ink/60">Quantity</span>
                <span className="font-bold text-ink">{task.quantity_kg} kg</span>
              </div>
            </div>
            {Array.isArray(task.items) && task.items.length > 0 && (
              <div className="mb-4 rounded-xl border border-ink/10 bg-paper/60 p-3">
                <p className="text-[10px] font-bold uppercase tracking-widest text-ink/45">Items to pick up</p>
                <div className="mt-2 grid gap-1">
                  {task.items.map((item: any, idx: number) => (
                    <p key={`${task.id}-item-${idx}`} className="text-xs text-ink/75">
                      <span className="font-bold capitalize text-ink">{item.food_type}</span> - {item.quantity_kg} kg, {item.meal_count} meals
                    </p>
                  ))}
                </div>
              </div>
            )}

            {task.status !== "completed" ? (
              <div className="grid gap-3 border-t border-ink/5 pt-4">
                {(!task.volunteer_task_status || task.volunteer_task_status === "assigned") && (
                  <>
                    <button
                      type="button"
                      disabled={confirmingTaskId === task.id}
                      onClick={async () => {
                        await transitionTask(task, "heading_to_pickup");
                        window.open(`https://www.google.com/maps/dir/?api=1&destination=${task.location?.lat},${task.location?.lng}&travelmode=driving`, "_blank");
                      }}
                      className="flex items-center justify-center gap-2 rounded-xl bg-leaf py-3 font-bold text-white shadow-line hover:bg-ink disabled:opacity-50"
                    >
                      <Navigation className="size-5" />
                      Head to pickup
                    </button>
                    <label className="grid gap-1.5 text-sm font-bold text-ink/70">
                      Reject reason
                      <input
                        type="text"
                        value={rejectReasonByTask[task.id] || ""}
                        onChange={(e) => setRejectReasonByTask((prev) => ({ ...prev, [task.id]: e.target.value }))}
                        placeholder="Reason for rejecting pickup"
                        className="rounded-xl border border-ink/15 bg-paper px-4 py-3 outline-none focus:border-leaf"
                      />
                    </label>
                    <button
                      type="button"
                      disabled={confirmingTaskId === task.id || !rejectReasonByTask[task.id]}
                      onClick={() => transitionTask(task, "pickup_rejected", { reject_reason: rejectReasonByTask[task.id], notes: rejectReasonByTask[task.id], status: "declined" })}
                      className="rounded-xl border border-chili/30 bg-white py-2.5 text-sm font-bold text-chili hover:bg-chili/5 disabled:opacity-50"
                    >
                      Reject pickup
                    </button>
                  </>
                )}
                {task.volunteer_task_status === "heading_to_pickup" && (
                  <button
                    type="button"
                    disabled={confirmingTaskId === task.id}
                    onClick={() => transitionTask(task, "reached_pickup")}
                    className="rounded-xl bg-leaf py-3 text-sm font-bold text-white hover:bg-ink disabled:opacity-50"
                  >
                    Mark reached pickup
                  </button>
                )}
                {task.volunteer_task_status === "reached_pickup" && (
                  <>
                    <label className="grid gap-1.5 text-sm font-bold text-ink/70">
                      Actual Meals Received
                      <input
                        type="number"
                        required
                        value={mealsServedByTask[task.id] || ""}
                        onChange={(e) => setMealsServedByTask((prev) => ({ ...prev, [task.id]: e.target.value }))}
                        placeholder="e.g. 45"
                        className="rounded-xl border border-ink/15 bg-paper px-4 py-3 outline-none focus:border-leaf"
                      />
                    </label>
                    <label className="grid gap-1.5 text-sm font-bold text-ink/70">
                      Pickup note / what received
                      <input
                        type="text"
                        value={pickupPhotoByTask[task.id] || ""}
                        onChange={(e) => setPickupPhotoByTask((prev) => ({ ...prev, [task.id]: e.target.value }))}
                        placeholder="Packed rice trays, etc."
                        className="rounded-xl border border-ink/15 bg-paper px-4 py-3 outline-none focus:border-leaf"
                      />
                    </label>
                    <button
                      type="button"
                      disabled={confirmingTaskId === task.id}
                      onClick={() =>
                        transitionTask(task, "pickup_successful", {
                          received_meal_count: parseInt(mealsServedByTask[task.id] || "0"),
                          notes: pickupPhotoByTask[task.id] || null,
                        })
                      }
                      className="rounded-xl bg-leaf py-3 text-sm font-bold text-white hover:bg-ink disabled:opacity-50"
                    >
                      Pickup successful
                    </button>
                  </>
                )}
                {task.volunteer_task_status === "pickup_successful" && (
                  <button
                    type="button"
                    disabled={confirmingTaskId === task.id}
                    onClick={() => transitionTask(task, "enroute_to_ngo")}
                    className="rounded-xl bg-leaf py-3 text-sm font-bold text-white hover:bg-ink disabled:opacity-50"
                  >
                    Start delivery to NGO
                  </button>
                )}
                {task.volunteer_task_status === "enroute_to_ngo" && (
                  <button
                    type="button"
                    disabled={confirmingTaskId === task.id}
                    onClick={() => transitionTask(task, "delivered_pending_confirmation")}
                    className="rounded-xl bg-leaf py-3 text-sm font-bold text-white hover:bg-ink disabled:opacity-50"
                  >
                    Mark delivered (await NGO confirmation)
                  </button>
                )}
                {task.volunteer_task_status === "delivered_pending_confirmation" && (
                  <div className="rounded-lg bg-saffron/15 px-3 py-2 text-sm font-bold text-ink">
                    Waiting for NGO coordinator confirmation.
                  </div>
                )}
                {task.volunteer_task_status === "delivered_confirmed" && (
                  <div className="rounded-lg bg-leaf/10 px-3 py-2 text-sm font-bold text-leaf">
                    Delivery confirmed by NGO coordinator.
                  </div>
                )}
              </div>
            ) : (
              <div className="rounded-lg bg-leaf/10 px-3 py-2 text-sm font-bold text-leaf">Completed</div>
            )}
          </div>
        ))}
      </div>
      ) : (
        <div className="mb-6 rounded-2xl border border-dashed border-ink/15 py-10 text-center">
          <Truck className="mx-auto mb-2 size-10 text-ink/20" />
          <p className="font-bold text-ink/50">No active pickups right now.</p>
          <p className="text-sm text-ink/50">Your NGO coordinator will assign pickup tasks. Check back shortly.</p>
        </div>
      )}

      <div className="mt-8">
        <h2 className="mb-4 text-xl font-bold text-ink">Completed Pickup History</h2>
        {completedHistory.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-ink/15 py-10 text-center">
            <p className="font-bold text-ink/50">No completed pickups yet.</p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-2xl border border-ink/10 bg-white shadow-lift">
            <table className="w-full text-left text-sm">
              <thead className="bg-field text-ink/70">
                <tr>
                  <th className="px-4 py-3 font-bold">Food</th>
                  <th className="px-4 py-3 font-bold">Donor</th>
                  <th className="px-4 py-3 font-bold">Status</th>
                  <th className="px-4 py-3 font-bold">Qty</th>
                  <th className="px-4 py-3 font-bold">Meals</th>
                  <th className="px-4 py-3 font-bold">Volunteer Time</th>
                  <th className="px-4 py-3 font-bold">Updated</th>
                </tr>
              </thead>
              <tbody>
                {completedHistory.map((item) => (
                  <tr key={item.id} className="border-t border-ink/5">
                    <td className="px-4 py-3 font-bold capitalize text-ink">{item.food_type}</td>
                    <td className="px-4 py-3 text-ink/70">{item.donor_name}</td>
                    <td className="px-4 py-3">
                      <span className="rounded-full bg-ink/10 px-2 py-1 text-xs font-bold uppercase tracking-wide text-ink">
                        {item.status === "completed" ? "completed" : item.volunteer_task_status || item.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-ink/70">{item.quantity_kg} kg</td>
                    <td className="px-4 py-3 text-ink/70">{item.completed_meals_served || item.meal_count || "-"}</td>
                    <td className="px-4 py-3 text-ink/60">
                      {item.volunteer_total_seconds !== null && item.volunteer_total_seconds !== undefined
                        ? `${Math.floor(item.volunteer_total_seconds / 60)}m ${item.volunteer_total_seconds % 60}s`
                        : "-"}
                    </td>
                    <td className="px-4 py-3 text-ink/60">{item.updated_at ? new Date(item.updated_at).toLocaleString() : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {overdueTask && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl">
            <h3 className="text-lg font-bold text-ink">Pickup delivery timer exceeded</h3>
            <p className="mt-2 text-sm text-ink/70">
              Are you currently carrying this food pickup for <strong>{overdueTask.food_type}</strong>?
            </p>
            {!showRejectConfirm ? (
              <div className="mt-5 flex gap-3">
                <button
                  onClick={handleOverdueYes}
                  disabled={confirmingTaskId === overdueTask.id}
                  className="flex-1 rounded-xl bg-leaf py-3 text-sm font-bold text-white hover:bg-ink disabled:opacity-50"
                >
                  Yes, add buffer time
                </button>
                <button
                  onClick={() => setShowRejectConfirm(true)}
                  className="flex-1 rounded-xl border border-chili/30 bg-white py-3 text-sm font-bold text-chili hover:bg-chili/5"
                >
                  No
                </button>
              </div>
            ) : (
              <div className="mt-5 space-y-3">
                <div className="rounded-xl bg-chili/10 p-3 text-sm font-bold text-chili">
                  This will mark the pickup as rejected. Are you sure you want to proceed?
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={() => setShowRejectConfirm(false)}
                    className="flex-1 rounded-xl border border-ink/15 bg-white py-3 text-sm font-bold text-ink hover:bg-field"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleOverdueReject}
                    disabled={rejectLock > 0 || confirmingTaskId === overdueTask.id}
                    className="flex-1 rounded-xl bg-chili py-3 text-sm font-bold text-white hover:bg-chili/90 disabled:opacity-50"
                  >
                    {rejectLock > 0 ? `Proceed in ${rejectLock}s` : "Proceed"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
