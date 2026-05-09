"use client";

import Link from "next/link";
import { ArrowLeft, AlertTriangle } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { RoleGuard } from "@/components/RoleGuard";
import { useAuth } from "@/lib/AuthProvider";
import { apiGet } from "@/lib/api";
import { useEffect, useState } from "react";

export default function NgoProfilePage() {
  return (
    <RoleGuard allowedRoles={["ngo_coordinator"]}>
      <NgoProfileContent />
    </RoleGuard>
  );
}

function NgoProfileContent() {
  const { profile } = useAuth();
  const [ngo, setNgo] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const run = async () => {
      if (!profile?.entity_id) {
        setError("NGO account is not linked to an NGO entity profile.");
        return;
      }
      try {
        const data = await apiGet<any>(`/ngos/${profile.entity_id}`);
        setNgo(data);
      } catch {
        setError("Failed to load NGO profile from backend.");
      }
    };
    run();
  }, [profile?.entity_id]);

  return (
    <main className="min-h-screen">
      <PageHeader eyebrow="NGO coordinator" title="NGO Profile" description="Live NGO profile data from backend." />
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
      {ngo && (
        <section className="mx-auto grid max-w-5xl gap-4 px-5 py-6 md:grid-cols-2">
          <div className="rounded-lg border border-ink/12 bg-white/90 p-5 shadow-line">
            <p className="text-xs font-bold uppercase tracking-widest text-ink/40">Beneficiary headcount</p>
            <p className="mt-2 text-2xl font-bold text-ink">{ngo.beneficiary_count}</p>
          </div>
          <div className="rounded-lg border border-ink/12 bg-white/90 p-5 shadow-line">
            <p className="text-xs font-bold uppercase tracking-widest text-ink/40">Dietary restrictions</p>
            <p className="mt-2 text-sm font-bold text-ink">{(ngo.dietary_restrictions || []).join(", ") || "None"}</p>
          </div>
          <div className="rounded-lg border border-ink/12 bg-white/90 p-5 shadow-line">
            <p className="text-xs font-bold uppercase tracking-widest text-ink/40">Food preferences</p>
            <p className="mt-2 text-sm font-bold text-ink">{(ngo.food_preferences || []).join(", ") || "Not set"}</p>
          </div>
          <div className="rounded-lg border border-ink/12 bg-white/90 p-5 shadow-line">
            <p className="text-xs font-bold uppercase tracking-widest text-ink/40">Meal schedule</p>
            <p className="mt-2 text-sm font-bold text-ink">{ngo.meal_time_schedule || "Not set"}</p>
          </div>
        </section>
      )}
    </main>
  );
}
