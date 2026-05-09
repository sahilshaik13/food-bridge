import { AdminUsersPanel } from "@/components/AdminUsersPanel";
import { PageHeader } from "@/components/PageHeader";

export default function AdminUsersPage() {
  return (
    <main className="min-h-screen">
      <PageHeader eyebrow="Super admin" title="Users & Approvals" description="Pending verification queue, document previews, duplicate flags, and approve/reject/suspend controls." />
      <div className="mx-auto max-w-7xl px-5 py-6">
        <AdminUsersPanel />
      </div>
    </main>
  );
}
