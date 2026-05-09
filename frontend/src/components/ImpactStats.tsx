import { BadgeIndianRupee, Leaf, Utensils } from "lucide-react";

type ImpactStatsType = {
  meals_served: number;
  kg_saved: number;
  co2_offset_kg: number;
};

export function ImpactStats({ impact }: { impact: ImpactStatsType | null | undefined }) {
  if (!impact) {
    return (
      <section className="grid gap-3 md:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-24 animate-pulse rounded-lg bg-ink/10" />
        ))}
      </section>
    );
  }

  const stats = [
    { label: "Meals served", value: (impact.meals_served || 0).toLocaleString("en-IN"), icon: Utensils },
    { label: "Food saved", value: `${((impact.kg_saved || 0) / 1000).toFixed(1)} t`, icon: Leaf },
    { label: "CO₂ offset", value: `${((impact.co2_offset_kg || 0) / 1000).toFixed(1)} t`, icon: BadgeIndianRupee }
  ];

  return (
    <section className="grid gap-3 md:grid-cols-3">
      {stats.map((stat) => (
        <div key={stat.label} className="rounded-lg border border-ink/12 bg-ink p-4 text-paper shadow-lift">
          <div className="flex items-center justify-between">
            <span className="text-sm text-paper/70">{stat.label}</span>
            <stat.icon className="size-4 text-saffron" />
          </div>
          <strong className="mt-3 block font-display text-3xl font-normal">{stat.value}</strong>
        </div>
      ))}
    </section>
  );
}
