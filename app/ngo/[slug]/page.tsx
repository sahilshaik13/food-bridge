"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { MapPin, Building2, Users, Utensils, Clock, CheckCircle2, ShieldCheck } from "lucide-react";
import { apiGet } from "@/lib/api";
import { MapViewer } from "@/components/MapViewer";

type Ngo = {
  id: string;
  name: string;
  area: string;
  focus: string;
  ngo_darpan_id: string;
  beneficiary_count: number;
  food_preferences: string[];
  dietary_restrictions: string[];
  meal_time_schedule?: string;
  coordinator_name?: string;
  coordinator_phone?: string;
  verification_status: "pending" | "verified" | "suspended";
  location: { lat: number; lng: number; address: string; area: string };
};

export default function NgoProfilePage() {
  const params = useParams();
  const router = useRouter();
  const [ngo, setNgo] = useState<Ngo | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (params.slug) {
      apiGet<Ngo>(`/ngos/${params.slug}`).then((data) => {
        setNgo(data);
        setLoading(false);
      }).catch(() => {
        setNgo(null);
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

  if (!ngo) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-paper">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-ink">NGO not found</h1>
          <Link href="/ngo" className="mt-4 inline-block text-leaf hover:underline">
            Back to NGO dashboard
          </Link>
        </div>
      </div>
    );
  }

  const markers = [
    {
      id: ngo.id,
      lat: ngo.location.lat,
      lng: ngo.location.lng,
      title: ngo.name,
      type: "ngo" as const,
    },
  ];

  return (
    <div className="min-h-screen bg-paper">
      <nav className="border-b border-ink/8 px-5 py-3">
        <Link href="/ngo" className="flex w-fit items-center gap-2 font-bold text-leaf">
          ← Back to NGOs
        </Link>
      </nav>

      <div className="mx-auto max-w-4xl px-5 py-10">
        <div className="mb-8">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold text-ink">{ngo.name}</h1>
              <p className="mt-1 flex items-center gap-2 text-ink/60">
                <MapPin className="size-4" />
                {ngo.area} - {ngo.location.address}
              </p>
              <div className="mt-3 flex items-center gap-3">
                {ngo.verification_status === "verified" ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-leaf/15 px-3 py-1 text-sm font-semibold text-leaf">
                    <CheckCircle2 className="size-4" />
                    Verified NGO
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full bg-saffron/20 px-3 py-1 text-sm font-semibold text-ink">
                    <Clock className="size-4" />
                    Pending Verification
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
                Organization Details
              </h2>
              <div className="space-y-3">
                <div>
                  <p className="text-sm text-ink/50">NGO Darpan ID</p>
                  <p className="font-mono text-ink/80">{ngo.ngo_darpan_id}</p>
                </div>
                <div>
                  <p className="text-sm text-ink/50">Focus Area</p>
                  <p className="font-semibold text-ink">{ngo.focus}</p>
                </div>
                <div>
                  <p className="text-sm text-ink/50">Beneficiaries Served</p>
                  <p className="text-2xl font-display font-normal text-ink">{ngo.beneficiary_count.toLocaleString("en-IN")}</p>
                </div>
              </div>
            </section>

            <section className="rounded-xl border border-ink/10 bg-white p-6">
              <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-ink">
                <Utensils className="size-5 text-leaf" />
                Food Preferences
              </h2>
              <div className="space-y-3">
                <div>
                  <p className="text-sm text-ink/50">Preferred Foods</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {ngo.food_preferences.map((food) => (
                      <span key={food} className="rounded-full bg-field px-3 py-1 text-sm text-ink">
                        {food}
                      </span>
                    ))}
                  </div>
                </div>
                {ngo.dietary_restrictions.length > 0 && (
                  <div>
                    <p className="text-sm text-ink/50">Dietary Restrictions</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {ngo.dietary_restrictions.map((restriction) => (
                        <span key={restriction} className="rounded-full bg-chili/10 px-3 py-1 text-sm text-chili">
                          {restriction}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {ngo.meal_time_schedule && (
                  <div>
                    <p className="text-sm text-ink/50">Meal Schedule</p>
                    <p className="text-ink">{ngo.meal_time_schedule}</p>
                  </div>
                )}
              </div>
            </section>

            {ngo.coordinator_name && (
              <section className="rounded-xl border border-ink/10 bg-white p-6">
                <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-ink">
                  <ShieldCheck className="size-5 text-civic" />
                  Coordinator
                </h2>
                <p className="font-semibold text-ink">{ngo.coordinator_name}</p>
                {ngo.coordinator_phone && (
                  <p className="text-ink/60">{ngo.coordinator_phone}</p>
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
                <MapViewer markers={markers} center={ngo.location} zoom={14} />
              </div>
              <p className="mt-3 text-sm text-ink/60">
                {ngo.location.address}
              </p>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
