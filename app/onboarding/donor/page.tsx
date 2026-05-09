import { DonorOnboarding } from "@/components/DonorOnboarding";
import { PageHeader } from "@/components/PageHeader";

export default function DonorOnboardingPage() {
  return (
    <main className="min-h-screen">
      <PageHeader eyebrow="Donor onboarding" title="Restaurant Registration" description="FSSAI-first registration. Telegram is enabled only after the app profile exists." />
      <div className="mx-auto max-w-7xl px-5 py-6">
        <DonorOnboarding />
      </div>
    </main>
  );
}
