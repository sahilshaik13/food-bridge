"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { MapPin, Building2, Utensils, CheckCircle2, Clock, Users, BadgeIndianRupee } from "lucide-react";
import { apiGet } from "@/lib/api";
import { MapViewer } from "@/components/MapViewer";

type Donor = {
  id: string;
  name: string;
  area: string;
  type: string;
  fssai_license: string;
  contact_name?: string;
  phone?: string;
  email?: string;
  avg_surplus_kg: string;
  monthly_meals: number;
  verification_status: "pending" | "verified" | "suspended";
  telegram_enabled?: boolean;
  telegram_username?: string;
  location: { lat: number; lng: number; address: string; area: string };
};

export default function DonorProfilePage() {
  const params = useParams();
  const router = useRouter();
  const [donor, setDonor] = useState<Donor | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (params.slug) {
      apiGet<Donor>(`/donors/${params.slug}`).then((data) => {
        setDonor(data);
        setLoading(false);
      }).catch(() => {
        setDonor(null);
        setLoading(false);
      });
    }
  }, [params.slug]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-paper">
        <div className="text-lg text-ink/60">Loading...</div>
      </div>
    );
  }

  if (!donor) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-paper">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-ink">Donor not found</h1>
          <Link href="/donor" className="mt-4 inline-block text-leaf hover:underline">
            Back to Donor dashboard
          </Link>
        </div>
      </div>
    );
  }

  const markers = [
    {
      id: donor.id,
      lat: donor.location.lat,
      lng: donor.location.lng,
      title: donor.name,
      type: "donor" as const,
    },
  ];

  return (
    <div className="min-h-screen bg-paper">
      <nav className="border-b border-ink/8 px-5 py-3">
        <Link href="/donor" className="flex w-fit items-center gap-2 font-bold text-leaf">
          ← Back to Donors
        </Link>
      </nav>

      <div className="mx-auto max-w-4xl px-5 py-10">
        <div className="mb-8">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold text-ink">{donor.name}</h1>
              <p className="mt-1 flex items-center gap-2 text-ink/60">
                <MapPin className="size-4" />
                {donor.area} - {donor.location.address}
              </p>
              <div className="mt-3 flex items-center gap-3">
                {donor.verification_status === "verified" ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-leaf/15 px-3 py-1 text-sm font-semibold text-leaf">
                    <CheckCircle2 className="size-4" />
                    Verified Donor
                  </span>
                ) : donor.verification_status === "pending" ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-saffron/20 px-3 py-1 text-sm font-semibold text-ink">
                    <Clock className="size-4" />
                    Verification Pending
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full bg-chili/15 px-3 py-1 text-sm font-semibold text-chili">
                    <Clock className="size-4" />
                    Suspended
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="grid gap-8 md:grid-cols-2">
          <div className="space-y-6">
            <section className="rounded-xl border border-ink/10 bg-white p-6">
              <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-ink">
                <Building2 className="size-5 text-civic" />
                Business Details
              </h2>
              <div className="space-y-3">
                <div>
                  <p className="text-sm text-ink/50">Type</p>
                  <p className="font-semibold text-ink">{donor.type}</p>
                </div>
                <div>
                  <p className="text-sm text-ink/50">FSSAI License</p>
                  <p className="font-mono text-ink/80">{donor.fssai_license}</p>
                </div>
                {donor.contact_name && (
                  <div>
                    <p className="text-sm text-ink/50">Contact Person</p>
                    <p className="font-semibold text-ink">{donor.contact_name}</p>
                  </div>
                )}
                {donor.phone && (
                  <div>
                    <p className="text-sm text-ink/50">Phone</p>
                    <p className="text-ink">{donor.phone}</p>
                  </div>
                )}
                {donor.email && (
                  <div>
                    <p className="text-sm text-ink/50">Email</p>
                    <p className="text-ink">{donor.email}</p>
                  </div>
                )}
              </div>
            </section>

            <section className="rounded-xl border border-ink/10 bg-white p-6">
              <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-ink">
                <Utensils className="size-5 text-leaf" />
                Donation Statistics
              </h2>
              <div className="space-y-3">
                <div>
                  <p className="text-sm text-ink/50">Avg. Surplus per Day</p>
                  <p className="text-2xl font-display font-normal text-ink">{donor.avg_surplus_kg}</p>
                </div>
                <div>
                  <p className="text-sm text-ink/50">Monthly Meals Donated</p>
                  <p className="text-2xl font-display font-normal text-ink">{donor.monthly_meals.toLocaleString("en-IN")}</p>
                </div>
              </div>
            </section>

            {donor.telegram_enabled && (
              <section className="rounded-xl border border-ink/10 bg-white p-6">
                <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-ink">
                  <BadgeIndianRupee className="size-5 text-saffron" />
                  Telegram Integration
                </h2>
                <p className="text-ink/60">
                  Enabled for quick donations
                </p>
                {donor.telegram_username && (
                  <p className="mt-2 font-semibold text-ink">
                    @{donor.telegram_username}
                  </p>
                )}
              </section>
            )}
          </div>

          <div className="space-y-6">
            <section className="rounded-xl border border-ink/10 bg-white p-6">
              <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-ink">
                <MapPin className="size-5 text-saffron" />
                Location
              </h2>
              <div className="h-80 overflow-hidden rounded-lg border border-ink/10">
                <MapViewer markers={markers} center={donor.location} zoom={14} />
              </div>
              <p className="mt-3 text-sm text-ink/60">
                {donor.location.address}
              </p>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
