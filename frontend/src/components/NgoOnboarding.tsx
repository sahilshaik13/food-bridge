"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { HandHeart, Send, Loader2, AlertCircle } from "lucide-react";
import { createUserWithEmailAndPassword } from "firebase/auth";
import { firebaseAuth } from "@/lib/firebase";
import { apiSend } from "@/lib/api";
import { useAuth } from "@/lib/AuthProvider";

export function NgoOnboarding() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    const fd = new FormData(e.currentTarget);
    const email = fd.get("email") as string;
    const password = fd.get("password") as string;
    
    try {
      // 1. Create Firebase Auth user
      const userCred = await createUserWithEmailAndPassword(firebaseAuth, email, password);
      
      // Wait a tiny bit for AuthProvider to sync the token
      await new Promise(resolve => setTimeout(resolve, 500));
      
      // Force token refresh and set globally so api.ts can use it
      const token = await userCred.user.getIdToken(true);
      (window as any).__fbToken = token;

      // 2. Call backend to create pending profile
      const res: any = await apiSend("/auth/onboarding/ngo", {
        name: fd.get("name"),
        area: fd.get("area"),
        focus: fd.get("focus") || "hunger relief",
        ngo_darpan_id: fd.get("ngo_darpan_id"),
        beneficiary_count: parseInt(fd.get("beneficiary_count") as string) || 100,
        coordinator_name: fd.get("coordinator_name"),
        coordinator_phone: fd.get("coordinator_phone"),
        email: email,
        address: fd.get("address"),
      });

      await userCred.user.getIdToken(true);
      
      // Redirect to a pending screen, or just admin queue
      router.replace(res.redirect_to || "/");

    } catch (err: any) {
      if (err.code === "auth/email-already-in-use") {
        setError("Email is already registered. Please sign in.");
      } else {
        setError(err.message || "Failed to submit NGO application.");
      }
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="mx-auto max-w-2xl rounded-2xl border border-ink/10 bg-white p-8 shadow-lift">
      <div className="mb-6 flex items-start justify-between gap-4 border-b border-ink/5 pb-6">
        <div>
          <p className="text-xs font-bold uppercase tracking-wide text-civic">Step 1 of 1</p>
          <h2 className="mt-1 font-display text-3xl">NGO Application</h2>
          <p className="mt-1 text-sm text-ink/60">Submit your NGO Darpan details for Admin verification.</p>
        </div>
        <div className="rounded-xl bg-civic/10 p-3 text-civic"><HandHeart className="size-6" /></div>
      </div>

      <div className="grid gap-5 sm:grid-cols-2">
        <label className="grid gap-1.5 text-sm font-bold text-ink/70 sm:col-span-2">
          NGO Registered Name
          <input name="name" required placeholder="Akshaya Patra Foundation"
            className="rounded-xl border border-ink/15 bg-paper px-4 py-3 font-normal outline-none focus:border-civic" />
        </label>

        <label className="grid gap-1.5 text-sm font-bold text-ink/70">
          Email Address (Login ID)
          <input name="email" type="email" required placeholder="coordinator@ngo.org"
            className="rounded-xl border border-ink/15 bg-paper px-4 py-3 font-normal outline-none focus:border-civic" />
        </label>

        <label className="grid gap-1.5 text-sm font-bold text-ink/70">
          Password
          <input name="password" type="password" required placeholder="Min. 6 characters" minLength={6}
            className="rounded-xl border border-ink/15 bg-paper px-4 py-3 font-normal outline-none focus:border-civic" />
        </label>

        <label className="grid gap-1.5 text-sm font-bold text-ink/70">
          NGO Darpan ID
          <input name="ngo_darpan_id" required placeholder="TS/2024/000123"
            className="rounded-xl border border-ink/15 bg-paper px-4 py-3 font-normal outline-none focus:border-civic" />
        </label>

        <label className="grid gap-1.5 text-sm font-bold text-ink/70">
          Estimated Beneficiary Count
          <input name="beneficiary_count" type="number" required placeholder="150"
            className="rounded-xl border border-ink/15 bg-paper px-4 py-3 font-normal outline-none focus:border-civic" />
        </label>

        <label className="grid gap-1.5 text-sm font-bold text-ink/70">
          Coordinator Name
          <input name="coordinator_name" required placeholder="Aditi Verma"
            className="rounded-xl border border-ink/15 bg-paper px-4 py-3 font-normal outline-none focus:border-civic" />
        </label>

        <label className="grid gap-1.5 text-sm font-bold text-ink/70">
          Coordinator Phone
          <input name="coordinator_phone" required placeholder="+91 90000 00000"
            className="rounded-xl border border-ink/15 bg-paper px-4 py-3 font-normal outline-none focus:border-civic" />
        </label>

        <label className="grid gap-1.5 text-sm font-bold text-ink/70 sm:col-span-2">
          Focus Area
          <input name="focus" required placeholder="Orphanage / Slum Relief"
            className="rounded-xl border border-ink/15 bg-paper px-4 py-3 font-normal outline-none focus:border-civic" />
        </label>

        <label className="grid gap-1.5 text-sm font-bold text-ink/70">
          Area / Neighborhood
          <input name="area" required placeholder="Gachibowli"
            className="rounded-xl border border-ink/15 bg-paper px-4 py-3 font-normal outline-none focus:border-civic" />
        </label>

        <label className="grid gap-1.5 text-sm font-bold text-ink/70">
          Full Address
          <input name="address" required placeholder="Plot 12, Gachibowli, Hyderabad"
            className="rounded-xl border border-ink/15 bg-paper px-4 py-3 font-normal outline-none focus:border-civic" />
        </label>
      </div>

      {error && (
        <div className="mt-6 flex items-center gap-2 rounded-xl bg-chili/10 p-4 text-sm font-bold text-chili">
          <AlertCircle className="size-5" /> {error}
        </div>
      )}

      <button
        disabled={loading}
        type="submit"
        className="mt-8 flex w-full items-center justify-center gap-2 rounded-xl bg-civic py-4 font-bold text-white shadow-line transition hover:bg-ink disabled:opacity-50"
      >
        {loading ? <Loader2 className="size-5 animate-spin" /> : <Send className="size-5" />}
        {loading ? "Submitting Application…" : "Submit NGO Application"}
      </button>
    </form>
  );
}
