"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, ShieldAlert, Truck, Loader2, XCircle, Route, X, Navigation } from "lucide-react";
import { FreshnessRing } from "@/components/FreshnessRing";
import { StatusBadge } from "@/components/StatusBadge";
import { useAuth } from "@/lib/AuthProvider";
import { apiGet, apiSend } from "@/lib/api";
import { MapViewer } from "@/components/MapViewer";

export function DonationCard({ donation: initial, onUpdate }: { donation: any; onUpdate?: () => void }) {
  const { role, profile } = useAuth();
  const [donation, setDonation] = useState(initial);
  const [loading, setLoading] = useState(false);
  const [showRoute, setShowRoute] = useState(false);
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [routeError, setRouteError] = useState<string | null>(null);
  const [ngoLocation, setNgoLocation] = useState<{ lat: number; lng: number; name: string } | null>(null);
  const topMatch = donation.ngo_queue?.[0];

  const updateStatus = async (status: string, extra: Record<string, any> = {}) => {
    setLoading(true);
    try {
      const updated: any = await apiSend(`/donations/${donation.id}/status`, { status, ...extra }, "PATCH");
      setDonation(updated);
      onUpdate?.();
    } catch (err: any) {
      alert(err.message || "Failed to update status");
    } finally {
      setLoading(false);
    }
  };

  const canAccept = role === "ngo_coordinator" && ["notified", "pending_match"].includes(donation.status);
  const canDecline = role === "ngo_coordinator" && ["notified", "pending_match"].includes(donation.status);
  const canCancelAcceptedByNgo = role === "ngo_coordinator" && ["accepted", "assigned"].includes(donation.status);
  const canCancelAcceptedByDonor = role === "donor" && ["accepted", "assigned"].includes(donation.status);
  const canCancelAccepted = canCancelAcceptedByNgo || canCancelAcceptedByDonor;
  const canConfirmDelivery =
    role === "ngo_coordinator" &&
    donation.volunteer_task_status === "delivered_pending_confirmation" &&
    donation.status !== "completed";
  const isNgoView = role === "ngo_coordinator";
  const canOpenRoute = ["accepted", "assigned", "completed", "wasted"].includes(donation.status);

  // Keep card state aligned with realtime parent updates.
  useEffect(() => {
    setDonation(initial);
  }, [initial]);

  const openRoute = async () => {
    setRouteError(null);
    const ngoId =
      role === "ngo_coordinator"
        ? (profile?.entity_id || donation.assigned_ngo_id || topMatch?.ngo_id)
        : (donation.assigned_ngo_id || topMatch?.ngo_id);
    if (!ngoId) {
      setRouteError("NGO location not available for this donation yet.");
      setShowRoute(true);
      return;
    }
    try {
      const ngos = await apiGet<any[]>("/ngos");
      const ngo = ngos.find((n) => n.id === ngoId);
      if (!ngo?.location) {
        throw new Error("NGO location missing");
      }
      setNgoLocation({ lat: ngo.location.lat, lng: ngo.location.lng, name: ngo.name });
      setShowRoute(true);
    } catch {
      setRouteError("Unable to load route map from backend NGO data.");
      setShowRoute(true);
    }
  };

  return (
    <article className="rounded-2xl border border-ink/10 bg-white p-5 shadow-lift transition hover:shadow-hover">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-lg font-bold text-ink capitalize">{donation.food_type}</h3>
            <StatusBadge status={donation.status} />
            {["accepted", "assigned"].includes(donation.status) && (
              <span className="inline-flex items-center rounded-full bg-civic/15 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-civic">
                Pickup timer
              </span>
            )}
          </div>
          <p className="mt-0.5 truncate text-xs text-ink/55">{donation.donor_name} · {donation.location?.area}</p>
        </div>
        <FreshnessRing expiresAt={donation.expires_at} />
      </div>

      {/* Stats */}
      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="rounded-xl bg-field p-3">
          <p className="text-[9px] font-bold uppercase tracking-widest text-ink/40">Quantity</p>
          <p className="text-base font-bold text-ink">{donation.quantity_kg} kg</p>
        </div>
        <div className="rounded-xl bg-field p-3">
          <p className="text-[9px] font-bold uppercase tracking-widest text-ink/40">Est. Meals</p>
          <p className="text-base font-bold text-ink">{donation.meal_count}</p>
        </div>
      </div>
      {Array.isArray(donation.items) && donation.items.length > 0 && (
        <div className="mt-3 rounded-xl border border-ink/10 bg-paper/60 p-3">
          <p className="text-[10px] font-bold uppercase tracking-widest text-ink/40">Itemized Surplus</p>
          <div className="mt-2 grid gap-1.5">
            {donation.items.map((item: any, idx: number) => (
              <p key={`${donation.id}-item-${idx}`} className="text-xs text-ink/75">
                <span className="font-bold capitalize text-ink">{item.food_type}</span> - {item.quantity_kg} kg, {item.meal_count} meals
              </p>
            ))}
          </div>
        </div>
      )}

      {/* Scan result */}
      <div className="mt-4 space-y-2">
        <div className="flex items-start gap-2 text-xs text-ink/70">
          {donation.scan?.passed
            ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-leaf" />
            : <ShieldAlert className="mt-0.5 size-4 shrink-0 text-chili" />}
          <span>
            <strong className={donation.scan?.passed ? "text-leaf" : "text-chili"}>
              Gemini {Math.round((donation.scan?.confidence || 0) * 100)}%
            </strong>
            {" "}· {donation.scan?.reason}
          </span>
        </div>

        {topMatch && donation.status !== "completed" && (
          <div className="flex items-start gap-2 text-xs text-ink/70">
            <Truck className="mt-0.5 size-4 shrink-0 text-civic" />
            <span>
              Best match: <strong className="text-ink">{topMatch.ngo_name}</strong> ({topMatch.distance_km} km · score {topMatch.total_score})
            </span>
          </div>
        )}

        <button
          onClick={openRoute}
          disabled={!canOpenRoute}
          className="flex items-center gap-1.5 text-xs font-bold text-civic hover:underline disabled:cursor-not-allowed disabled:text-ink/35"
          title={canOpenRoute ? "View donor-ngo route" : "Route is available after NGO accepts donation"}
        >
          <Route className="size-3" />
          {canOpenRoute ? "View donor-ngo route" : "Route available after acceptance"}
        </button>
        {donation.wave_expires_at && ["notified", "pending_match", "escalated_radius_2", "escalated_radius_3"].includes(donation.status) && (
          <p className="text-[11px] font-bold text-ink/55">
            Wave {donation.broadcast_wave || donation.escalation_level || 1} live until {new Date(donation.wave_expires_at).toLocaleTimeString()}
          </p>
        )}
      </div>

      {/* NGO action buttons */}
      {(canAccept || canDecline) && (
        <div className="mt-5 flex gap-2 border-t border-ink/5 pt-4">
          {canAccept && (
            <button
              disabled={loading}
              onClick={() => updateStatus("accepted", { ngo_id: profile?.entity_id })}
              className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-leaf py-2.5 text-sm font-bold text-white shadow-line hover:bg-ink disabled:opacity-50"
            >
              {loading ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
              Accept Pickup
            </button>
          )}
          {canDecline && (
            <button
              disabled={loading}
              onClick={() => updateStatus("declined")}
              className="rounded-xl border border-ink/10 bg-white px-4 py-2.5 text-sm font-bold text-chili hover:bg-chili/5 disabled:opacity-50"
            >
              <XCircle className="size-4" />
            </button>
          )}
        </div>
      )}

      {canConfirmDelivery && (
        <div className="mt-3 border-t border-ink/5 pt-3">
          <button
            disabled={loading}
            onClick={() =>
              updateStatus("completed", {
                ngo_id: profile?.entity_id,
                volunteer_task_status: "delivered_confirmed",
              })
            }
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-leaf py-2.5 text-sm font-bold text-white shadow-line hover:bg-ink disabled:opacity-50"
          >
            {loading ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
            Confirm Delivery
          </button>
        </div>
      )}

      {canCancelAccepted && (
        <div className="mt-3 border-t border-ink/5 pt-3">
          <button
            onClick={() => setShowCancelConfirm(true)}
            className="w-full rounded-xl border border-chili/30 bg-white px-4 py-2.5 text-sm font-bold text-chili hover:bg-chili/5"
          >
            Cancel Pickup
          </button>
        </div>
      )}

      {showRoute && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-3xl rounded-2xl bg-white p-4 shadow-2xl">
            <div className="mb-3 flex items-center justify-between">
              <h4 className="font-bold text-ink">Donation Route</h4>
              <button onClick={() => setShowRoute(false)} className="rounded-lg p-1 text-ink/60 hover:bg-field">
                <X className="size-4" />
              </button>
            </div>
            {routeError ? (
              <div className="rounded-xl bg-chili/10 p-3 text-sm font-bold text-chili">{routeError}</div>
            ) : donation.location && ngoLocation ? (
              <div className="space-y-3">
                <div className="h-[420px] overflow-hidden rounded-xl border border-ink/10">
                  <MapViewer
                    markers={[
                      { id: "donor", lat: donation.location.lat, lng: donation.location.lng, title: donation.donor_name, type: "donor" },
                      { id: "ngo", lat: ngoLocation.lat, lng: ngoLocation.lng, title: ngoLocation.name, type: "ngo" },
                    ]}
                    center={
                      isNgoView
                        ? { lat: ngoLocation.lat, lng: ngoLocation.lng }
                        : { lat: donation.location.lat, lng: donation.location.lng }
                    }
                    zoom={12}
                    routePath={
                      isNgoView
                        ? [
                            { lat: ngoLocation.lat, lng: ngoLocation.lng },
                            { lat: donation.location.lat, lng: donation.location.lng },
                          ]
                        : [
                            { lat: donation.location.lat, lng: donation.location.lng },
                            { lat: ngoLocation.lat, lng: ngoLocation.lng },
                          ]
                    }
                  />
                </div>
                <a
                  href={`https://www.google.com/maps/dir/?api=1&origin=${
                    isNgoView ? `${ngoLocation.lat},${ngoLocation.lng}` : `${donation.location.lat},${donation.location.lng}`
                  }&destination=${
                    isNgoView ? `${donation.location.lat},${donation.location.lng}` : `${ngoLocation.lat},${ngoLocation.lng}`
                  }&travelmode=driving`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 rounded-lg bg-leaf px-3 py-2 text-xs font-bold text-white hover:bg-ink"
                >
                  <Navigation className="size-3" />
                  Open in Google Maps
                </a>
              </div>
            ) : (
              <div className="rounded-xl bg-field p-3 text-sm font-bold text-ink/60">Route data unavailable.</div>
            )}
          </div>
        </div>
      )}

      {showCancelConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-2xl">
            <h4 className="text-lg font-bold text-ink">Confirm pickup cancellation</h4>
            <p className="mt-2 text-sm text-ink/70">
              Are you sure you want to cancel this accepted pickup? This will move the donation back to rejected flow.
            </p>
            <div className="mt-5 flex gap-3">
              <button
                onClick={() => setShowCancelConfirm(false)}
                className="flex-1 rounded-xl border border-ink/15 bg-white py-2.5 text-sm font-bold text-ink hover:bg-field"
              >
                Keep pickup
              </button>
              <button
                disabled={loading}
                onClick={async () => {
                  await updateStatus("declined", role === "ngo_coordinator" ? { ngo_id: profile?.entity_id } : {});
                  setShowCancelConfirm(false);
                }}
                className="flex-1 rounded-xl bg-chili py-2.5 text-sm font-bold text-white hover:bg-chili/90 disabled:opacity-50"
              >
                Confirm cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </article>
  );
}
