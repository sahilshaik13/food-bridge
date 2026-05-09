import { MapPin, Navigation, RadioTower } from "lucide-react";

export function RoleMap({ role }: { role: "donor" | "ngo" | "volunteer" | "municipal" | "admin" }) {
  const labels = {
    donor: ["Own restaurant pin", "All NGO pins", "Emergency broadcast CTA"],
    ngo: ["Own NGO pin", "Nearby donors", "Private accepted routes"],
    volunteer: ["Pickup pin", "Drop pin", "Navigation route only"],
    municipal: ["All donors", "All NGOs", "Surplus/demand heatmap"],
    admin: ["All entities", "All routes", "Review flags"]
  }[role];

  return (
    <section className="overflow-hidden rounded-lg border border-ink/12 bg-white/75 shadow-line">
      <div className="map-grid relative h-80">
        <span className="absolute left-[18%] top-[34%] rounded-full bg-leaf px-3 py-1 text-xs font-bold text-white shadow-lift">
          Donor
        </span>
        <span className="absolute right-[22%] top-[27%] rounded-full bg-civic px-3 py-1 text-xs font-bold text-white shadow-lift">
          NGO
        </span>
        <span className="absolute bottom-[25%] left-[45%] rounded-full bg-saffron px-3 py-1 text-xs font-bold text-ink shadow-lift">
          Route
        </span>
        {(role === "municipal" || role === "admin") && (
          <span className="absolute right-[12%] bottom-[18%] rounded-full bg-chili px-3 py-1 text-xs font-bold text-white shadow-lift">
            Gap zone
          </span>
        )}
      </div>
      <div className="grid gap-2 p-4 md:grid-cols-3">
        {labels.map((label, index) => {
          const Icon = index === 0 ? MapPin : index === 1 ? RadioTower : Navigation;
          return (
            <div key={label} className="flex items-center gap-2 rounded-md bg-field/70 p-3 text-sm font-semibold">
              <Icon className="size-4 text-leaf" />
              {label}
            </div>
          );
        })}
      </div>
    </section>
  );
}
