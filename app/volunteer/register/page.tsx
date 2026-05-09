"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { createUserWithEmailAndPassword } from "firebase/auth";
import { firebaseAuth } from "@/lib/firebase";
import { apiGet, apiSend } from "@/lib/api";
import Link from "next/link";
import { Loader2 } from "lucide-react";

function VolunteerRegisterForm() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token") || "";

  const [loadingInvite, setLoadingInvite] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [invite, setInvite] = useState<any>(null);
  const [password, setPassword] = useState("");

  useEffect(() => {
    const loadInvite = async () => {
      if (!token) {
        setError("Missing invite token.");
        setLoadingInvite(false);
        return;
      }
      try {
        const data = await apiGet<any>(`/volunteers/invite/${token}`);
        setInvite(data);
      } catch (err: any) {
        const message = (err?.message || "").toLowerCase();
        if (message.includes("expired")) setError("Invite expired. Ask your NGO coordinator to resend it.");
        else if (message.includes("used")) setError("Invite already used. Contact your NGO coordinator.");
        else if (message.includes("revoked")) setError("Invite revoked by NGO coordinator.");
        else setError("Invite is invalid, expired, or already used.");
      } finally {
        setLoadingInvite(false);
      }
    };
    loadInvite();
  }, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!invite?.email) {
      setError("Invite email is missing.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      await createUserWithEmailAndPassword(firebaseAuth, invite.email, password);
      await apiSend("/volunteers/register", { token });
      setSuccess("Registration submitted. NGO coordinator approval is pending.");
      setTimeout(() => router.replace("/login"), 1500);
    } catch (err: any) {
      const message = (err?.message || "").toLowerCase();
      if (message.includes("email")) setError("Email mismatch with invite. Use the invited email account.");
      else setError(err.message || "Failed to complete registration.");
    } finally {
      setSubmitting(false);
    }
  };

  if (loadingInvite) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-paper">
        <Loader2 className="size-8 animate-spin text-leaf" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-paper px-4 py-10">
      <div className="mx-auto max-w-lg rounded-2xl border border-ink/10 bg-white p-6 shadow-lift">
        <h1 className="text-2xl font-bold text-ink">Volunteer Registration</h1>
        <p className="mt-1 text-sm text-ink/60">Complete your invited registration for FoodBridge.</p>

        {error && <div className="mt-4 rounded-xl bg-chili/10 px-4 py-3 text-sm font-bold text-chili">{error}</div>}
        {success && <div className="mt-4 rounded-xl bg-leaf/10 px-4 py-3 text-sm font-bold text-leaf">{success}</div>}

        {invite && (
          <form onSubmit={handleSubmit} className="mt-5 grid gap-3">
            <label className="grid gap-1 text-sm font-bold text-ink/70">
              NGO
              <input value={invite.ngo_name || ""} disabled className="rounded-xl border border-ink/15 bg-field px-4 py-2.5" />
            </label>
            <label className="grid gap-1 text-sm font-bold text-ink/70">
              Name
              <input value={invite.name || ""} disabled className="rounded-xl border border-ink/15 bg-field px-4 py-2.5" />
            </label>
            <label className="grid gap-1 text-sm font-bold text-ink/70">
              Email
              <input value={invite.email || ""} disabled className="rounded-xl border border-ink/15 bg-field px-4 py-2.5" />
            </label>
            <label className="grid gap-1 text-sm font-bold text-ink/70">
              Password
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Create your password"
                className="rounded-xl border border-ink/15 bg-paper px-4 py-2.5 outline-none focus:border-leaf"
                required
              />
            </label>
            <button
              type="submit"
              disabled={submitting}
              className="mt-2 rounded-xl bg-leaf py-3 font-bold text-white hover:bg-ink disabled:opacity-50"
            >
              {submitting ? "Submitting..." : "Complete Registration"}
            </button>
          </form>
        )}

        <p className="mt-5 text-sm text-ink/60">
          Already have an account? <Link href="/login" className="font-bold text-leaf hover:underline">Sign in</Link>
        </p>
      </div>
    </div>
  );
}

export default function VolunteerRegisterPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-paper">
          <Loader2 className="size-8 animate-spin text-leaf" />
        </div>
      }
    >
      <VolunteerRegisterForm />
    </Suspense>
  );
}
