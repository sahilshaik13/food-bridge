"use client";

import { useEffect } from "react";
import Link from "next/link";
import { AppNav } from "@/components/AppNav";
import { ImpactStats } from "@/components/ImpactStats";
import { useAuth } from "@/lib/AuthProvider";
import { apiGetOrFallback } from "@/lib/api";
import { useState } from "react";
import { ArrowRight, Utensils, Heart, ShieldCheck, Loader2 } from "lucide-react";

export default function LandingPage() {
  const { user, role, redirectTo, loading } = useAuth();
  const [impact, setImpact] = useState<any>(null);

  useEffect(() => {
    apiGetOrFallback("/impact", null).then(setImpact);
  }, []);

  // Show spinner while checking auth
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-paper">
        <Loader2 className="size-10 animate-spin text-leaf" />
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-paper">
      <AppNav />
      <section className="mx-auto grid max-w-7xl gap-12 px-5 py-20 lg:grid-cols-[1.2fr_.8fr] lg:items-center">
        <div>
          <span className="mb-4 inline-flex items-center gap-2 rounded-full bg-saffron/15 px-4 py-1.5 text-xs font-bold uppercase tracking-widest text-ink">
            <ShieldCheck className="size-3" /> FSSAI Verified Network · Hyderabad
          </span>
          <h1 className="font-display text-7xl font-normal leading-tight text-ink md:text-8xl">
            Food<span className="text-leaf">Bridge</span>
          </h1>
          <p className="mt-8 max-w-2xl text-xl leading-relaxed text-ink/70">
            Eliminating hunger through real-time coordination. Connecting restaurants directly to NGOs using Gemini-powered verification.
          </p>

          <div className="mt-10 flex flex-wrap gap-4">
            {user && role ? (
              <Link href={redirectTo || "/"}
                className="flex items-center gap-2 rounded-xl bg-leaf px-8 py-4 text-lg font-bold text-white shadow-lift transition hover:-translate-y-1 hover:bg-ink">
                Explore App Dashboard <ArrowRight className="size-5" />
              </Link>
            ) : (
              <>
                <Link href="/login"
                  className="flex items-center gap-2 rounded-xl bg-leaf px-8 py-4 text-lg font-bold text-white shadow-lift transition hover:-translate-y-1 hover:bg-ink">
                  Sign In <ArrowRight className="size-5" />
                </Link>
                <Link href="/onboarding/donor"
                  className="flex items-center gap-2 rounded-xl bg-ink px-8 py-4 text-lg font-bold text-paper shadow-lift transition hover:-translate-y-1 hover:bg-ink/90">
                  Register Restaurant
                </Link>
              </>
            )}
          </div>

          <div className="mt-12 grid grid-cols-3 gap-6 border-t border-ink/5 pt-10">
            {[
              { icon: Utensils, text: "10+ Verified Restaurants" },
              { icon: Heart, text: "3 Partner NGOs" },
              { icon: ShieldCheck, text: "Gemini QA Scans" },
            ].map(({ icon: Icon, text }) => (
              <div key={text}>
                <div className="mb-2 flex size-10 items-center justify-center rounded-xl bg-field text-ink">
                  <Icon className="size-5" />
                </div>
                <p className="text-sm font-bold text-ink">{text}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="relative rounded-3xl border border-ink/10 bg-gradient-to-br from-field to-white p-8 shadow-2xl">
          <h3 className="text-2xl font-bold text-ink">Live Impact</h3>
          <p className="mt-1 text-sm text-ink/50">Real-time redistribution metrics</p>
          <ImpactStats impact={impact} />
          <div className="mt-6 rounded-2xl bg-ink p-5 text-center text-paper">
            <p className="text-xs font-bold uppercase tracking-widest text-paper/40">Live Modules</p>
            <p className="mt-3 text-sm text-paper/80">
              Donor, NGO, Volunteer, Super Admin, and Municipal dashboards are now connected to live backend data.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
