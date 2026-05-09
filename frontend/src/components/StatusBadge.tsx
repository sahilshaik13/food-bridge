type DonationStatus =
  | "draft"
  | "pending_match"
  | "notified"
  | "accepted"
  | "declined"
  | "assigned"
  | "completed"
  | "expired"
  | "needs_review"
  | "escalated_radius_2"
  | "escalated_radius_3"
  | "wasted";

const statusStyles: Record<string, string> = {
  draft: "bg-stone-200 text-stone-600 ring-stone-300",
  pending_match: "bg-saffron/20 text-saffron ring-saffron/40",
  notified: "bg-saffron/20 text-ink ring-saffron/40",
  accepted: "bg-leaf/15 text-leaf ring-leaf/30",
  declined: "bg-chili/15 text-chili ring-chili/30",
  assigned: "bg-civic/15 text-civic ring-civic/30",
  completed: "bg-ink text-paper ring-ink",
  expired: "bg-stone-200 text-stone-600 ring-stone-300",
  needs_review: "bg-chili/15 text-chili ring-chili/30",
  escalated_radius_2: "bg-orange-100 text-orange-700 ring-orange-300",
  escalated_radius_3: "bg-red-100 text-red-700 ring-red-300",
  wasted: "bg-stone-300 text-stone-700 ring-stone-400",
};

const statusLabels: Record<string, string> = {
  draft: "Draft",
  pending_match: "Pending Match",
  notified: "Notified",
  accepted: "Accepted",
  declined: "Declined",
  assigned: "Assigned",
  completed: "Completed",
  expired: "Expired",
  needs_review: "Needs Review",
  escalated_radius_2: "Escalated (5km)",
  escalated_radius_3: "Escalated (15km)",
  wasted: "Wasted",
};

export function StatusBadge({ status }: { status: DonationStatus }) {
  const style = statusStyles[status] || "bg-stone-200 text-stone-600 ring-stone-300";
  const label = statusLabels[status] || status.replace("_", " ");

  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${style}`}>
      {label}
    </span>
  );
}
