"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Store, UserPlus, Loader2, AlertCircle } from "lucide-react";
import { createUserWithEmailAndPassword } from "firebase/auth";
import { firebaseAuth } from "@/lib/firebase";
import { apiSend } from "@/lib/api";
import { useAuth } from "@/lib/AuthProvider";

export function DonorOnboarding() {
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

      // 2. Call backend to create profile and set claim
      const res: any = await apiSend("/auth/onboarding/donor", {
        name: fd.get("name"),
        area: fd.get("area"),
        type: "restaurant",
        fssai_license: fd.get("fssai_license"),
        contact_name: fd.get("contact_name"),
        phone: fd.get("phone"),
        email: email,
        address: fd.get("address"),
        avg_surplus_kg: parseFloat(fd.get("avg_surplus_kg") as string) || 10.0,
      });

      // 3. Backend will return redirect_to, but AuthProvider might still be loading
      // the new claim. Force refresh auth state.
      await userCred.user.getIdToken(true);
      
      router.replace(res.redirect_to || "/donor");

    } catch (err: any) {
      if (err.code === "auth/email-already-in-use") {
        setError("Email is already registered. Please sign in.");
      } else {
        setError(err.message || "Failed to register restaurant.");
      }
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="mx-auto max-w-2xl rounded-2xl border border-ink/10 bg-white p-8 shadow-lift">
      <div className="mb-6 flex items-start justify-between gap-4 border-b border-ink/5 pb-6">
        <div>
          <p className="text-xs font-bold uppercase tracking-wide text-leaf">Step 1 of 1</p>
          <h2 className="mt-1 font-display text-3xl">Register Restaurant</h2>
          <p className="mt-1 text-sm text-ink/60">Create your donor account and verify your FSSAI license.</p>
        </div>
        <div className="rounded-xl bg-leaf/10 p-3 text-leaf"><Store className="size-6" /></div>
      </div>

      <div className="grid gap-5 sm:grid-cols-2">
        <label className="grid gap-1.5 text-sm font-bold text-ink/70 sm:col-span-2">
          Restaurant / Entity Name
          <input name="name" required placeholder="Banjara Grand Buffet"
            className="rounded-xl border border-ink/15 bg-paper px-4 py-3 font-normal outline-none focus:border-leaf" />
        </label>

        <label className="grid gap-1.5 text-sm font-bold text-ink/70">
          Email Address (Login ID)
          <input name="email" type="email" required placeholder="manager@banjaragrand.com"
            className="rounded-xl border border-ink/15 bg-paper px-4 py-3 font-normal outline-none focus:border-leaf" />
        </label>

        <label className="grid gap-1.5 text-sm font-bold text-ink/70">
          Password
          <input name="password" type="password" required placeholder="Min. 6 characters" minLength={6}
            className="rounded-xl border border-ink/15 bg-paper px-4 py-3 font-normal outline-none focus:border-leaf" />
        </label>

        <label className="grid gap-1.5 text-sm font-bold text-ink/70">
          FSSAI License Number
          <input name="fssai_license" required pattern="\d{14}" title="14 digit FSSAI number" placeholder="13622011004567"
            className="rounded-xl border border-ink/15 bg-paper px-4 py-3 font-normal outline-none focus:border-leaf" />
        </label>

        <label className="grid gap-1.5 text-sm font-bold text-ink/70">
          Phone Number
          <input name="phone" required placeholder="+91 90000 00000"
            className="rounded-xl border border-ink/15 bg-paper px-4 py-3 font-normal outline-none focus:border-leaf" />
        </label>

        <label className="grid gap-1.5 text-sm font-bold text-ink/70">
          Contact Person
          <input name="contact_name" required placeholder="Rahul Sharma"
            className="rounded-xl border border-ink/15 bg-paper px-4 py-3 font-normal outline-none focus:border-leaf" />
        </label>

        <label className="grid gap-1.5 text-sm font-bold text-ink/70">
          Area / Neighborhood
          <input name="area" required placeholder="Banjara Hills"
            className="rounded-xl border border-ink/15 bg-paper px-4 py-3 font-normal outline-none focus:border-leaf" />
        </label>

        <label className="grid gap-1.5 text-sm font-bold text-ink/70">
          Estimated Daily Surplus (kg)
          <input name="avg_surplus_kg" type="number" required placeholder="10"
            className="rounded-xl border border-ink/15 bg-paper px-4 py-3 font-normal outline-none focus:border-leaf" />
        </label>

        <label className="grid gap-1.5 text-sm font-bold text-ink/70 sm:col-span-2">
          Full Address
          <input name="address" required placeholder="Plot 45, Main Road, Hyderabad"
            className="rounded-xl border border-ink/15 bg-paper px-4 py-3 font-normal outline-none focus:border-leaf" />
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
        className="mt-8 flex w-full items-center justify-center gap-2 rounded-xl bg-leaf py-4 font-bold text-white shadow-line transition hover:bg-ink disabled:opacity-50"
      >
        {loading ? <Loader2 className="size-5 animate-spin" /> : <UserPlus className="size-5" />}
        {loading ? "Verifying & Creating Account…" : "Create Restaurant Account"}
      </button>
    </form>
  );
}
