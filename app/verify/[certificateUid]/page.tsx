"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { AlertTriangle, BadgeCheck, ShieldX } from "lucide-react";

type VerifyResult = {
  valid: boolean;
  certificate_uid?: string;
  donation_id?: string;
  donor_name?: string;
  ngo_name?: string;
  food_type?: string;
  quantity_kg?: number;
  meal_count?: number;
  items?: Array<{ food_type?: string; quantity_kg?: number; meal_count?: number }>;
  generated_at?: string;
  reason?: string | null;
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "https://foodbridge-api-aqg35pktda-el.a.run.app";

export default function VerifyCertificatePage() {
  const params = useParams<{ certificateUid: string }>();
  const search = useSearchParams();
  const certificateUid = params?.certificateUid || "";
  const sig = search.get("sig") || "";

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VerifyResult | null>(null);

  const status = useMemo(() => {
    if (loading) return "loading";
    if (error) return "error";
    return result?.valid ? "valid" : "invalid";
  }, [loading, error, result]);

  useEffect(() => {
    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        if (!certificateUid || !sig) {
          setError("Missing certificate details.");
          setResult(null);
          return;
        }
        const response = await fetch(
          `${API_BASE}/reports/verify/${encodeURIComponent(certificateUid)}?sig=${encodeURIComponent(sig)}`,
          { cache: "no-store" }
        );
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          setResult({
            valid: false,
            certificate_uid: certificateUid,
            reason: data?.detail?.reason || data?.reason || "verification_failed",
          });
          return;
        }
        setResult(data as VerifyResult);
      } catch {
        setError("Unable to verify certificate right now. Please retry.");
      } finally {
        setLoading(false);
      }
    };
    run();
  }, [certificateUid, sig]);

  return (
    <main className="min-h-screen bg-paper/30 px-4 py-10">
      <div className="mx-auto max-w-2xl rounded-2xl border border-ink/10 bg-white p-6 shadow-lift">
        <p className="text-[10px] font-bold uppercase tracking-widest text-ink/40">FoodBridge Secure Verify</p>
        <h1 className="mt-1 text-2xl font-bold text-ink">Certificate Verification</h1>

        {status === "loading" && (
          <div className="mt-6 rounded-xl border border-ink/10 bg-field px-4 py-3 text-sm font-bold text-ink/70">
            Verifying certificate...
          </div>
        )}

        {status === "error" && (
          <div className="mt-6 flex items-center gap-2 rounded-xl bg-chili/10 px-4 py-3 text-sm font-bold text-chili">
            <AlertTriangle className="size-4" />
            {error}
          </div>
        )}

        {status === "valid" && result && (
          <>
            <div className="mt-6 flex items-center gap-2 rounded-xl bg-leaf/10 px-4 py-3 text-sm font-bold text-leaf">
              <BadgeCheck className="size-4" />
              VERIFIED - Authentic FoodBridge certificate
            </div>
            <div className="mt-4 grid gap-2 rounded-xl border border-ink/10 p-4 text-sm">
              <Field label="Certificate UID" value={result.certificate_uid} />
              <Field label="Donation ID" value={result.donation_id} />
              <Field label="Donor" value={result.donor_name} />
              <Field label="Recipient NGO" value={result.ngo_name} />
              <Field label="Food Type" value={result.food_type} />
              <Field label="Quantity (kg)" value={result.quantity_kg?.toString()} />
              <Field label="Meals" value={result.meal_count?.toString()} />
              <Field
                label="Items"
                value={
                  result.items && result.items.length > 0
                    ? result.items.map((item) => `${item.food_type} (${item.quantity_kg}kg, ${item.meal_count} meals)`).join(", ")
                    : "-"
                }
              />
              <Field
                label="Generated At"
                value={result.generated_at ? new Date(result.generated_at).toLocaleString() : "-"}
              />
            </div>
          </>
        )}

        {status === "invalid" && result && (
          <>
            <div className="mt-6 flex items-center gap-2 rounded-xl bg-chili/10 px-4 py-3 text-sm font-bold text-chili">
              <ShieldX className="size-4" />
              NOT VERIFIED - Certificate validation failed
            </div>
            <div className="mt-4 rounded-xl border border-chili/20 bg-chili/5 px-4 py-3 text-sm text-chili">
              <p className="font-bold">Reason: {result.reason || "signature_mismatch"}</p>
              <p className="mt-1">Certificate UID: {result.certificate_uid || certificateUid}</p>
            </div>
          </>
        )}

        <p className="mt-6 text-xs text-ink/50">Verified by FoodBridge secure signature pipeline.</p>
      </div>
    </main>
  );
}

function Field({ label, value }: { label: string; value?: string }) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg bg-paper/50 px-3 py-2">
      <span className="text-ink/60">{label}</span>
      <span className="text-right font-bold text-ink">{value || "-"}</span>
    </div>
  );
}
