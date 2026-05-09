"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { AlertTriangle, BadgeCheck, ShieldX } from "lucide-react";

type CsrVerifyResult = {
  valid: boolean;
  report_id?: string;
  donor_id?: string;
  donor_name?: string;
  period_label?: string;
  generated_at?: string;
  monthly_meals?: number;
  total_kg_saved?: number;
  co2_offset_kg?: number;
  reason?: string | null;
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "https://foodbridge-api-aqg35pktda-el.a.run.app";

export default function VerifyCsrPage() {
  const params = useParams<{ reportId: string }>();
  const search = useSearchParams();
  const reportId = params?.reportId || "";
  const sig = search.get("sig") || "";

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CsrVerifyResult | null>(null);

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
        if (!reportId || !sig) {
          setError("Missing CSR verification details.");
          setResult(null);
          return;
        }
        const response = await fetch(
          `${API_BASE}/reports/csr/verify/${encodeURIComponent(reportId)}?sig=${encodeURIComponent(sig)}`,
          { cache: "no-store" }
        );
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          setResult({
            valid: false,
            report_id: reportId,
            reason: data?.detail?.reason || data?.reason || "verification_failed",
          });
          return;
        }
        setResult(data as CsrVerifyResult);
      } catch {
        setError("Unable to verify CSR report right now. Please retry.");
      } finally {
        setLoading(false);
      }
    };
    run();
  }, [reportId, sig]);

  return (
    <main className="min-h-screen bg-paper/30 px-4 py-10">
      <div className="mx-auto max-w-2xl rounded-2xl border border-ink/10 bg-white p-6 shadow-lift">
        <p className="text-[10px] font-bold uppercase tracking-widest text-ink/40">FoodBridge Secure Verify</p>
        <h1 className="mt-1 text-2xl font-bold text-ink">CSR Report Verification</h1>

        {status === "loading" && (
          <div className="mt-6 rounded-xl border border-ink/10 bg-field px-4 py-3 text-sm font-bold text-ink/70">
            Verifying CSR report...
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
              VERIFIED - Authentic FoodBridge CSR report
            </div>
            <div className="mt-4 grid gap-2 rounded-xl border border-ink/10 p-4 text-sm">
              <Field label="Report ID" value={result.report_id} />
              <Field label="Donor" value={result.donor_name} />
              <Field label="Donor ID" value={result.donor_id} />
              <Field label="Period" value={result.period_label} />
              <Field label="Meals Served" value={result.monthly_meals?.toString()} />
              <Field label="Food Rescued (kg)" value={result.total_kg_saved?.toString()} />
              <Field label="CO2 Offset (kg)" value={result.co2_offset_kg?.toString()} />
              <Field label="Generated At" value={result.generated_at ? new Date(result.generated_at).toLocaleString() : "-"} />
            </div>
          </>
        )}

        {status === "invalid" && result && (
          <>
            <div className="mt-6 flex items-center gap-2 rounded-xl bg-chili/10 px-4 py-3 text-sm font-bold text-chili">
              <ShieldX className="size-4" />
              NOT VERIFIED - CSR report validation failed
            </div>
            <div className="mt-4 rounded-xl border border-chili/20 bg-chili/5 px-4 py-3 text-sm text-chili">
              <p className="font-bold">Reason: {result.reason || "signature_mismatch"}</p>
              <p className="mt-1">Report ID: {result.report_id || reportId}</p>
            </div>
          </>
        )}
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
