"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, AlertTriangle } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { RoleGuard } from "@/components/RoleGuard";
import { useAuth } from "@/lib/AuthProvider";
import { apiGet, apiSend } from "@/lib/api";

export default function DonorReportsPage() {
  return (
    <RoleGuard allowedRoles={["donor"]}>
      <ReportsContent />
    </RoleGuard>
  );
}

function ReportsContent() {
  const { profile } = useAuth();
  const [pendingCertificates, setPendingCertificates] = useState<any[]>([]);
  const [certByDonationId, setCertByDonationId] = useState<Record<string, any>>({});
  const [csrReports, setCsrReports] = useState<any[]>([]);
  const [csrResult, setCsrResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [regenerateTarget, setRegenerateTarget] = useState<any | null>(null);
  const [csrRegenerateTarget, setCsrRegenerateTarget] = useState<any | null>(null);

  useEffect(() => {
    const run = async () => {
      setError(null);
      try {
        const certList = await apiGet<any>("/reports/fssai/list");
        const csrList = await apiGet<any>("/reports/csr/list");
        const map: Record<string, any> = {};
        for (const cert of certList?.generated || []) {
          if (cert?.donation_id) {
            map[cert.donation_id] = cert;
          }
        }
        setCertByDonationId(map);
        setCsrReports(csrList?.generated || []);
        const pending = (certList?.pending || []).filter((item: any) => !map[item?.donation_id]);
        setPendingCertificates(pending);
      } catch {
        setError("Failed to load donation records for reports.");
      }
    };
    run();
  }, []);

  const openFssai = async (donationId: string, options?: { force?: boolean; certificateUid?: string }) => {
    setError(null);
    try {
      const params = new URLSearchParams();
      if (options?.force) params.set("force", "true");
      if (options?.certificateUid) params.set("certificate_uid", options.certificateUid);
      const suffix = params.toString() ? `?${params.toString()}` : "";
      const result = await apiSend<any>(`/reports/fssai/${donationId}${suffix}`, {}, "POST");
      if (result?.signed_url) window.open(result.signed_url, "_blank");
      if (result?.donation_id) {
        setCertByDonationId((prev) => ({ ...prev, [result.donation_id]: result }));
        setPendingCertificates((prev) => prev.filter((item: any) => item?.donation_id !== result.donation_id));
      }
    } catch {
      setError("FSSAI report generation failed.");
    }
  };

  const generateCsr = async () => {
    setError(null);
    if (!profile?.entity_id) {
      setError("Donor account is not linked to a donor profile.");
      return;
    }
    try {
      const result = await apiSend<any>(`/reports/csr/${profile.entity_id}`, {});
      setCsrResult(result);
      setCsrReports((prev) => [result, ...prev.filter((item) => item.report_id !== result.report_id)]);
      if (result?.signed_url) window.open(result.signed_url, "_blank");
    } catch {
      setError("CSR report generation failed.");
    }
  };

  const openCsr = async (options?: { force?: boolean; reportId?: string }) => {
    setError(null);
    if (!profile?.entity_id) {
      setError("Donor account is not linked to a donor profile.");
      return;
    }
    try {
      const params = new URLSearchParams();
      if (options?.force) params.set("force", "true");
      if (options?.reportId) params.set("report_id", options.reportId);
      const suffix = params.toString() ? `?${params.toString()}` : "";
      const result = await apiSend<any>(`/reports/csr/${profile.entity_id}${suffix}`, {}, "POST");
      setCsrResult(result);
      setCsrReports((prev) => [result, ...prev.filter((item) => item.report_id !== result.report_id)]);
      if (result?.signed_url) window.open(result.signed_url, "_blank");
    } catch {
      setError("CSR report generation failed.");
    }
  };

  return (
    <main className="min-h-screen">
      <PageHeader eyebrow="Donor owner" title="Reports" description="Live report generation via backend." />
      <section className="mx-auto max-w-5xl px-5 pt-2">
        <Link href="/donor" className="inline-flex items-center gap-2 text-sm font-bold text-leaf hover:underline">
          <ArrowLeft className="size-4" />
          Back to donor dashboard
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
        <div className="rounded-lg border border-ink/12 bg-white/90 p-5 shadow-line md:col-span-2">
          <p className="text-xs font-bold uppercase tracking-widest text-ink/40">FSSAI certificate list</p>
          <div className="mt-3 grid gap-3">
            {Object.keys(certByDonationId).length === 0 && pendingCertificates.length === 0 ? (
              <p className="text-sm font-bold text-ink/50">No completed donations eligible for certificates.</p>
            ) : (
              <>
                {Object.values(certByDonationId).map((cert: any) => (
                  <div key={cert.certificate_uid} className="flex items-center justify-between rounded-lg border border-ink/10 p-3">
                    <div className="min-w-0">
                      <p className="font-bold text-ink capitalize">{cert.food_type || "Food Donation"}</p>
                      <p className="text-xs text-ink/50">Donation ID: {cert.donation_id}</p>
                      {cert?.generated_at && (
                        <p className="text-xs text-leaf">Generated: {new Date(cert.generated_at).toLocaleString()}</p>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => openFssai(cert.donation_id)}
                        className="rounded-lg bg-civic px-3 py-2 text-xs font-bold text-white hover:bg-ink"
                      >
                        View Certificate
                      </button>
                      <button
                        onClick={() => setRegenerateTarget(cert)}
                        className="rounded-lg border border-chili/30 bg-white px-3 py-2 text-xs font-bold text-chili hover:bg-chili/5"
                      >
                        Regenerate
                      </button>
                    </div>
                  </div>
                ))}
                {pendingCertificates.map((item) => (
                  <div key={item.donation_id} className="flex items-center justify-between rounded-lg border border-ink/10 p-3">
                    <div className="min-w-0">
                      <p className="font-bold text-ink capitalize">{item.food_type || "Food Donation"}</p>
                      <p className="text-xs text-ink/50">Donation ID: {item.donation_id}</p>
                      {item?.completed_at && (
                        <p className="text-xs text-ink/50">Completed: {new Date(item.completed_at).toLocaleString()}</p>
                      )}
                    </div>
                    <button
                      onClick={() => openFssai(item.donation_id)}
                      className="rounded-lg bg-leaf px-3 py-2 text-xs font-bold text-white hover:bg-ink"
                    >
                      Generate FSSAI
                    </button>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>
        <div className="rounded-lg border border-ink/12 bg-white/90 p-5 shadow-line">
          <p className="text-xs font-bold uppercase tracking-widest text-ink/40">CSR impact report</p>
          <button onClick={generateCsr} className="mt-3 w-full rounded-lg bg-ink px-3 py-2 text-sm font-bold text-white">
            Generate CSR report
          </button>
          {csrResult && (
            <div className="mt-3 text-xs text-ink/70">
              <p>Meals served: {csrResult.monthly_meals}</p>
              <p>Food redistributed: {csrResult.total_kg_saved} kg</p>
              <p>CO2 offset: {csrResult.co2_offset_kg} kg</p>
              <p>Completion rate: {csrResult.completion_rate_pct}%</p>
              <p>Unique NGOs served: {csrResult.unique_ngos_served}</p>
              <p className="mt-2 text-[11px] text-ink/60">{csrResult.tax_note}</p>
            </div>
          )}
          <div className="mt-4 grid gap-2">
            {csrReports.slice(0, 5).map((report) => (
              <div key={report.report_id} className="rounded-lg border border-ink/10 p-2">
                <p className="truncate text-[11px] font-bold text-ink">{report.report_id}</p>
                <p className="text-[10px] text-ink/55">{report.generated_at ? new Date(report.generated_at).toLocaleString() : "-"}</p>
                <div className="mt-2 flex gap-2">
                  <button
                    onClick={() => openCsr({ reportId: report.report_id })}
                    className="rounded-md bg-civic px-2 py-1 text-[10px] font-bold text-white hover:bg-ink"
                  >
                    View
                  </button>
                  <button
                    onClick={() => setCsrRegenerateTarget(report)}
                    className="rounded-md border border-chili/30 bg-white px-2 py-1 text-[10px] font-bold text-chili hover:bg-chili/5"
                  >
                    Regenerate
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
      {regenerateTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-xl rounded-2xl bg-white p-5 shadow-2xl">
            <h3 className="text-lg font-bold text-ink">Regenerate certificate?</h3>
            <p className="mt-2 text-sm text-ink/70">
              If regenerated, the previous certificate will be deleted. The date and time of delivery will remain the same; only certificate generation timestamp will change.
              Are you sure you want to proceed?
            </p>
            <div className="mt-5 flex gap-3">
              <button
                onClick={() => setRegenerateTarget(null)}
                className="flex-1 rounded-xl border border-ink/15 bg-white py-2.5 text-sm font-bold text-ink hover:bg-field"
              >
                Cancel
              </button>
              <button
                onClick={async () => {
                  await openFssai(regenerateTarget.donation_id, {
                    force: true,
                    certificateUid: regenerateTarget.certificate_uid,
                  });
                  setRegenerateTarget(null);
                }}
                className="flex-1 rounded-xl bg-chili py-2.5 text-sm font-bold text-white hover:bg-chili/90"
              >
                Yes, Regenerate
              </button>
            </div>
          </div>
        </div>
      )}
      {csrRegenerateTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-xl rounded-2xl bg-white p-5 shadow-2xl">
            <h3 className="text-lg font-bold text-ink">Regenerate CSR report?</h3>
            <p className="mt-2 text-sm text-ink/70">
              If regenerated, the previous CSR report will be deleted. Impact period data remains the same; only report generation timestamp will change.
              Are you sure you want to proceed?
            </p>
            <div className="mt-5 flex gap-3">
              <button
                onClick={() => setCsrRegenerateTarget(null)}
                className="flex-1 rounded-xl border border-ink/15 bg-white py-2.5 text-sm font-bold text-ink hover:bg-field"
              >
                Cancel
              </button>
              <button
                onClick={async () => {
                  await openCsr({ force: true, reportId: csrRegenerateTarget.report_id });
                  setCsrRegenerateTarget(null);
                }}
                className="flex-1 rounded-xl bg-chili py-2.5 text-sm font-bold text-white hover:bg-chili/90"
              >
                Yes, Regenerate
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
