"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/AuthProvider";
import { apiSendForm, apiGet } from "@/lib/api";
import { Camera, Send, Loader2, CheckCircle2, AlertCircle, MapPin, Clock, RadioTower, Thermometer } from "lucide-react";
import { MapViewer } from "./MapViewer";

interface BroadcastedNgo {
  id: string;
  name: string;
  area: string;
  location: { lat: number; lng: number; address: string; area: string };
  notified: boolean;
}

export function DonationForm({ onSuccess, mode = "standalone" }: { onSuccess?: () => void; mode?: "embedded" | "standalone" }) {
  const { profile } = useAuth();
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [donationId, setDonationId] = useState<string | null>(null);
  const [pendingRetryId, setPendingRetryId] = useState<string | null>(null);
  const [reviewHold, setReviewHold] = useState(false);
  const [scanResult, setScanResult] = useState<any>(null);
  const [broadcastedNgos, setBroadcastedNgos] = useState<BroadcastedNgo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoPreviewUrl, setPhotoPreviewUrl] = useState<string | null>(null);
  const [items, setItems] = useState<Array<{ food_type: string; quantity: string; meals: string }>>([
    { food_type: "", quantity: "", meals: "" },
  ]);
  const [foodPreparedLocal, setFoodPreparedLocal] = useState("");
  const [roomTemp, setRoomTemp] = useState("");
  const [fridge, setFridge] = useState<"unknown" | "yes" | "no">("unknown");
  const [opNotes, setOpNotes] = useState("");

  useEffect(() => {
    if (!photoFile) {
      setPhotoPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(photoFile);
    setPhotoPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [photoFile]);

  useEffect(() => {
    if (mode === "standalone" && submitted && donationId) {
      apiGet(`/donations/${donationId}/broadcasted-ngos`, []).then(setBroadcastedNgos).catch(() => {});
    }
  }, [mode, submitted, donationId]);

  useEffect(() => {
    if (mode !== "embedded" || !submitted) return;
    const timer = setTimeout(() => {
      setSubmitted(false);
      setScanResult(null);
      setDonationId(null);
      setPendingRetryId(null);
      setReviewHold(false);
      setBroadcastedNgos([]);
      setError(null);
      setPhotoFile(null);
      setFoodPreparedLocal("");
      setRoomTemp("");
      setFridge("unknown");
      setOpNotes("");
    }, 5000);
    return () => clearTimeout(timer);
  }, [mode, submitted]);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setScanResult(null);
    setSubmitted(false);
    setDonationId(null);
    setBroadcastedNgos([]);

    const fd = new FormData(e.currentTarget);
    const normalizedItems = items
      .map((item) => ({
        food_type: item.food_type.trim(),
        quantity_kg: Number(item.quantity),
        meal_count: Number(item.meals),
      }))
      .filter((item) => item.food_type && item.quantity_kg > 0 && item.meal_count > 0);
    if (normalizedItems.length === 0) {
      setError("Please add at least one valid surplus item.");
      setLoading(false);
      return;
    }
    if (!photoFile) {
      setError("Please add a clear photo of the surplus food so Gemini Vision can verify it.");
      setLoading(false);
      return;
    }

    const payload: Record<string, unknown> = {
      donor_id: profile?.id || profile?.entity_id || "donor_unknown",
      donor_name: profile?.name || profile?.display_name || "Unknown",
      food_type: normalizedItems[0].food_type,
      quantity_kg: normalizedItems.reduce((sum, item) => sum + item.quantity_kg, 0),
      meal_count: normalizedItems.reduce((sum, item) => sum + item.meal_count, 0),
      items: normalizedItems,
      notes: fd.get("notes") as string,
      source: "web",
    };

    if (foodPreparedLocal.trim()) {
      const d = new Date(foodPreparedLocal);
      if (!Number.isNaN(d.getTime())) payload.food_prepared_at = d.toISOString();
    }
    const rt = parseFloat(roomTemp);
    if (roomTemp.trim() !== "" && !Number.isNaN(rt)) payload.storage_ambient_temp_c = rt;
    if (fridge === "yes") payload.held_in_refrigeration = true;
    if (fridge === "no") payload.held_in_refrigeration = false;
    if (opNotes.trim()) payload.operational_metrics_notes = opNotes.trim();

    try {
      const path = pendingRetryId ? `/donations/${pendingRetryId}/retry-scan` : "/donations";
      const method = pendingRetryId ? "PATCH" : "POST";
      const formData = new FormData();
      formData.append("payload", JSON.stringify(payload));
      formData.append("photo", photoFile);
      const result: any = await apiSendForm(path, formData, method);
      setDonationId(result.id);
      setScanResult(result.scan);
      if (result.status === "pending_scan_retry") {
        setPendingRetryId(result.id);
        setReviewHold(false);
        return;
      }
      if (result.status === "needs_review") {
        setPendingRetryId(null);
        setReviewHold(true);
        return;
      }
      setPendingRetryId(null);
      setReviewHold(false);
      setSubmitted(true);
      onSuccess?.();
    } catch (err: any) {
      setError(err.message || "Failed to post donation.");
    } finally {
      setLoading(false);
    }
  };

  const markers = broadcastedNgos.map((ngo) => ({
    id: ngo.id,
    lat: ngo.location.lat,
    lng: ngo.location.lng,
    title: ngo.name,
    type: "ngo" as const,
  }));

  if (submitted) return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-leaf/20 bg-leaf/5 p-8 text-center shadow-lift">
        <CheckCircle2 className="mx-auto size-12 text-leaf" />
        <h3 className="mt-4 text-xl font-bold text-ink">Donation Posted!</h3>
        <p className="mt-2 text-sm text-ink/60">
          Gemini Vision verified your photo. Nearby NGOs have been notified.
          {scanResult && (
            <span className="mt-1 block font-bold text-leaf">
              {Math.round(scanResult.confidence * 100)}% freshness confidence
            </span>
          )}
        </p>
        {mode === "embedded" && (
          <p className="mt-2 text-xs font-bold uppercase tracking-wide text-ink/40">
            Returning to form in 5 seconds...
          </p>
        )}
      </div>

      {mode === "standalone" && broadcastedNgos.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-bold text-ink flex items-center gap-2">
              <RadioTower className="size-5 text-civic" />
              Broadcasted to {broadcastedNgos.length} NGOs
            </h3>
          </div>

          <div className="h-80 overflow-hidden rounded-xl border border-ink/10">
            <MapViewer markers={markers} zoom={12} />
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            {broadcastedNgos.map((ngo) => (
              <div key={ngo.id} className="rounded-xl border border-ink/10 bg-white p-4 flex items-start gap-3">
                <div className="rounded-full bg-saffron/20 p-2 text-saffron">
                  <MapPin className="size-4" />
                </div>
                <div className="flex-1">
                  <h4 className="font-bold text-ink">{ngo.name}</h4>
                  <p className="text-xs text-ink/60 flex items-center gap-1">
                    <MapPin className="size-3" />
                    {ngo.area}
                  </p>
                  <div className="mt-2 flex items-center gap-1 text-xs text-leaf">
                    <Clock className="size-3" />
                    Waiting for response
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {mode === "standalone" && (
        <button
          onClick={() => {
            setSubmitted(false);
            setScanResult(null);
            setDonationId(null);
            setPendingRetryId(null);
            setReviewHold(false);
            setBroadcastedNgos([]);
            setPhotoFile(null);
            setFoodPreparedLocal("");
            setRoomTemp("");
            setFridge("unknown");
            setOpNotes("");
          }}
          className="w-full rounded-xl bg-ink py-3.5 font-bold text-white shadow-line hover:bg-ink/90"
        >
          Post another →
        </button>
      )}

      {mode === "standalone" && (
        <Link href="/donor" className="inline-flex w-full items-center justify-center rounded-xl border border-ink/15 bg-white py-3 text-sm font-bold text-ink hover:bg-field">
          Back to dashboard
        </Link>
      )}
    </div>
  );

  if (reviewHold) {
    return (
      <div className="space-y-4 rounded-2xl border border-amber-200 bg-amber-50 p-6 shadow-lift">
        <div className="flex items-start gap-2">
          <AlertCircle className="mt-0.5 size-5 shrink-0 text-amber-700" />
          <div>
            <p className="font-bold text-amber-900">Queued for Super Admin review</p>
            <p className="mt-1 text-sm text-amber-900/80">
              Gemini could not safely auto-verify this listing after your attempts. Our team will clear or reject it — check your donor dashboard for updates.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => {
            setReviewHold(false);
            setScanResult(null);
            setDonationId(null);
            setPhotoFile(null);
          }}
          className="w-full rounded-xl bg-ink py-3 text-sm font-bold text-white shadow-line hover:bg-ink/90"
        >
          Start a new listing
        </button>
        <Link href="/donor" className="inline-flex w-full items-center justify-center rounded-xl border border-ink/15 bg-white py-3 text-sm font-bold text-ink hover:bg-field">
          Back to dashboard
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-2xl border border-ink/10 bg-white p-6 shadow-lift">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-ink">Post Surplus</h2>
          <p className="text-[10px] font-bold uppercase tracking-widest text-ink/40">New Listing</p>
        </div>
        <div className="rounded-xl bg-leaf/10 p-2.5 text-leaf"><Camera className="size-5" /></div>
      </div>

      <div className="grid gap-4">
        <div className="grid gap-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-widest text-ink/50">Surplus Items</p>
            <button
              type="button"
              onClick={() => setItems((prev) => [...prev, { food_type: "", quantity: "", meals: "" }])}
              className="rounded-lg border border-leaf/30 bg-leaf/10 px-3 py-1 text-[11px] font-bold text-leaf hover:bg-leaf/20"
            >
              + Add item
            </button>
          </div>
          {items.map((item, idx) => (
            <div key={idx} className="rounded-xl border border-ink/10 bg-field/50 p-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-[11px] font-bold uppercase tracking-widest text-ink/45">Item {idx + 1}</p>
                {items.length > 1 && (
                  <button
                    type="button"
                    onClick={() => setItems((prev) => prev.filter((_, i) => i !== idx))}
                    className="text-[11px] font-bold text-chili hover:underline"
                  >
                    Remove
                  </button>
                )}
              </div>
              <div className="grid gap-2">
                <input
                  value={item.food_type}
                  onChange={(e) =>
                    setItems((prev) => prev.map((row, i) => (i === idx ? { ...row, food_type: e.target.value } : row)))
                  }
                  required
                  placeholder="e.g. Chicken Biryani, Paneer Curry"
                  className="rounded-xl border border-ink/15 bg-paper px-4 py-2.5 text-sm font-normal outline-none focus:border-leaf"
                />
                <div className="grid grid-cols-2 gap-2">
                  <input
                    value={item.quantity}
                    onChange={(e) =>
                      setItems((prev) => prev.map((row, i) => (i === idx ? { ...row, quantity: e.target.value } : row)))
                    }
                    type="number"
                    step="0.5"
                    min="0.5"
                    required
                    placeholder="Quantity kg"
                    className="rounded-xl border border-ink/15 bg-paper px-4 py-2.5 text-sm font-normal outline-none focus:border-leaf"
                  />
                  <input
                    value={item.meals}
                    onChange={(e) =>
                      setItems((prev) => prev.map((row, i) => (i === idx ? { ...row, meals: e.target.value } : row)))
                    }
                    type="number"
                    min="1"
                    required
                    placeholder="Approx meals"
                    className="rounded-xl border border-ink/15 bg-paper px-4 py-2.5 text-sm font-normal outline-none focus:border-leaf"
                  />
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="grid gap-2">
          <label className="grid gap-1.5 text-xs font-bold uppercase tracking-widest text-ink/50">
            Food photo (required)
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              capture="environment"
              onChange={(e) => setPhotoFile(e.target.files?.[0] ?? null)}
              className="text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-leaf/15 file:px-3 file:py-2 file:text-xs file:font-bold file:text-leaf"
            />
          </label>
          {photoPreviewUrl && (
            <div className="overflow-hidden rounded-xl border border-ink/10 bg-field/50">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={photoPreviewUrl} alt="Food preview" className="max-h-48 w-full object-cover" />
            </div>
          )}
          <p className="text-[11px] leading-snug text-ink/50">
            Each listing is scanned with Gemini Vision on this photo before NGOs are notified.
          </p>
        </div>

        <label className="grid gap-1.5 text-xs font-bold uppercase tracking-widest text-ink/50">
          Notes (optional)
          <textarea name="notes" rows={2} placeholder="Packed in containers, ready for pickup now."
            className="rounded-xl border border-ink/15 bg-paper px-4 py-2.5 text-sm font-normal outline-none focus:border-leaf" />
        </label>

        <details className="rounded-xl border border-ink/10 bg-field/40 p-4">
          <summary className="cursor-pointer list-none font-bold text-sm text-ink [&::-webkit-details-marker]:hidden flex items-center gap-2">
            <Thermometer className="size-4 text-civic shrink-0" />
            Optional kitchen &amp; storage details
            <span className="ml-auto text-[10px] font-normal uppercase tracking-widest text-ink/45">helps AI routing</span>
          </summary>
          <p className="mt-3 text-[11px] leading-snug text-ink/55">
            Many kitchens cannot measure everything — leave blank if unknown. When provided, these signals improve accuracy scoring together with weather near your venue.
          </p>
          <div className="mt-4 grid gap-3">
            <label className="grid gap-1 text-[11px] font-bold uppercase tracking-widest text-ink/45">
              Food prepared (local time)
              <input
                type="datetime-local"
                value={foodPreparedLocal}
                onChange={(e) => setFoodPreparedLocal(e.target.value)}
                className="rounded-xl border border-ink/15 bg-paper px-4 py-2.5 text-sm font-normal outline-none focus:border-leaf"
              />
            </label>
            <label className="grid gap-1 text-[11px] font-bold uppercase tracking-widest text-ink/45">
              Room / storage temperature (°C)
              <input
                type="number"
                step="0.5"
                value={roomTemp}
                onChange={(e) => setRoomTemp(e.target.value)}
                placeholder="e.g. 24"
                className="rounded-xl border border-ink/15 bg-paper px-4 py-2.5 text-sm font-normal outline-none focus:border-leaf"
              />
            </label>
            <label className="grid gap-1 text-[11px] font-bold uppercase tracking-widest text-ink/45">
              Held under refrigeration?
              <select
                value={fridge}
                onChange={(e) => setFridge(e.target.value as "unknown" | "yes" | "no")}
                className="rounded-xl border border-ink/15 bg-paper px-4 py-2.5 text-sm font-normal outline-none focus:border-leaf"
              >
                <option value="unknown">Unknown / not sure</option>
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </select>
            </label>
            <label className="grid gap-1 text-[11px] font-bold uppercase tracking-widest text-ink/45">
              Handling notes
              <textarea
                rows={2}
                value={opNotes}
                onChange={(e) => setOpNotes(e.target.value)}
                placeholder="e.g. Blast chilled after service, held in walk-in until pickup."
                className="rounded-xl border border-ink/15 bg-paper px-4 py-2.5 text-sm font-normal outline-none focus:border-leaf"
              />
            </label>
          </div>
        </details>

        {pendingRetryId && (
          <div className="flex items-start gap-2 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm">
            <AlertCircle className="mt-0.5 size-4 shrink-0 text-amber-800" />
            <div>
              <p className="font-bold text-amber-900">First scan inconclusive — one retry left</p>
              <p className="text-xs text-amber-900/85">
                Adjust food details or notes, then submit again. A second failure sends this to Super Admin review before NGOs see it.
              </p>
            </div>
          </div>
        )}

        {/* Scan result feedback */}
        {scanResult && !scanResult.passed && (
          <div className="flex items-start gap-2 rounded-xl bg-chili/10 p-3 text-sm">
            <AlertCircle className="mt-0.5 size-4 shrink-0 text-chili" />
            <div>
              <p className="font-bold text-chili">Scan uncertain — {Math.round(scanResult.confidence * 100)}% confidence</p>
              <p className="text-xs text-chili/80">{scanResult.reason}</p>
            </div>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 rounded-xl bg-chili/10 p-3 text-sm font-bold text-chili">
            <AlertCircle className="size-4" /> {error}
          </div>
        )}

        <button disabled={loading}
          className="flex items-center justify-center gap-2 rounded-xl bg-leaf py-3.5 font-bold text-white shadow-line hover:bg-ink disabled:opacity-50">
          {loading ? <Loader2 className="size-5 animate-spin" /> : <Send className="size-5" />}
          {loading
            ? "Scanning & Broadcasting…"
            : pendingRetryId
              ? "Retry scan & broadcast"
              : "Broadcast to NGOs"}
        </button>
      </div>
    </form>
  );
}
