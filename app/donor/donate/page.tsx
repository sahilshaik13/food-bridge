import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { DonationForm } from "@/components/DonationForm";
import { PageHeader } from "@/components/PageHeader";

export default function DonorDonatePage() {
  return (
    <main className="min-h-screen">
      <PageHeader eyebrow="Donor only" title="Post Donation" description="Photo upload, food type, quantity, Gemini scan result, and retake path for first photo failure." />
      <div className="mx-auto max-w-3xl px-5 py-6">
        <Link href="/donor" className="mb-4 inline-flex items-center gap-2 text-sm font-bold text-leaf hover:underline">
          <ArrowLeft className="size-4" />
          Back to donor dashboard
        </Link>
        <DonationForm mode="standalone" />
      </div>
    </main>
  );
}
