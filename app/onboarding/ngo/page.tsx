import { NgoOnboarding } from "@/components/NgoOnboarding";
import { PageHeader } from "@/components/PageHeader";

export default function NgoOnboardingPage() {
  return (
    <main className="min-h-screen">
      <PageHeader eyebrow="NGO onboarding" title="Coordinator Approval" description="NGO Darpan, Aadhaar, beneficiary profile, dietary preferences, and pending Super Admin review." />
      <div className="mx-auto max-w-7xl px-5 py-6">
        <NgoOnboarding />
      </div>
    </main>
  );
}
