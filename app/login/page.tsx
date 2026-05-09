"use client";

import { useState, useEffect, Suspense } from "react";
import { signInWithEmailAndPassword, createUserWithEmailAndPassword } from "firebase/auth";
import { firebaseAuth } from "@/lib/firebase";
import { useAuth } from "@/lib/AuthProvider";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2, LogIn, Globe, ArrowRight } from "lucide-react";
import Link from "next/link";

function LoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { user, role, redirectTo, loading: authLoading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next");

  useEffect(() => {
    if (!authLoading && user && role && redirectTo) {
      router.replace(next || redirectTo);
    }
  }, [user, role, redirectTo, authLoading, router, next]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await signInWithEmailAndPassword(firebaseAuth, email, password);
    } catch (err: any) {
      const code = err.code;
      if (code === "auth/user-not-found" || code === "auth/wrong-password" || code === "auth/invalid-credential" || code === "auth/invalid-login-credentials") {
        setError("Invalid email or password.");
      } else if (code === "auth/too-many-requests") {
        setError("Too many attempts. Please wait a few minutes and try again.");
      } else {
        setError("Sign in failed. Please try again.");
      }
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleLogin} className="rounded-2xl border border-ink/10 bg-white p-8 shadow-lift">
      <div className="grid gap-5">
        <label className="grid gap-1.5 text-sm font-bold text-ink/70">
          Email Address
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="manager@restaurant.com"
            required
            autoComplete="email"
            className="rounded-xl border border-ink/15 bg-paper px-4 py-3 text-sm outline-none transition focus:border-leaf focus:ring-2 focus:ring-leaf/10"
          />
        </label>

        <label className="grid gap-1.5 text-sm font-bold text-ink/70">
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            required
            autoComplete="current-password"
            className="rounded-xl border border-ink/15 bg-paper px-4 py-3 text-sm outline-none transition focus:border-leaf focus:ring-2 focus:ring-leaf/10"
          />
        </label>

        {error && (
          <div className="rounded-xl bg-chili/10 px-4 py-3 text-sm font-bold text-chili">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="flex items-center justify-center gap-2 rounded-xl bg-leaf py-3.5 font-bold text-white shadow-line transition hover:bg-ink disabled:opacity-50"
        >
          {loading ? <Loader2 className="size-5 animate-spin" /> : <LogIn className="size-5" />}
          {loading ? "Verifying…" : "Sign In to Dashboard"}
        </button>
      </div>
    </form>
  );
}

export default function LoginPage() {
  const { loading: authLoading } = useAuth();

  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-paper">
        <Loader2 className="size-8 animate-spin text-leaf" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-paper">
      <nav className="border-b border-ink/8 px-5 py-3">
        <Link href="/" className="flex w-fit items-center gap-2 font-bold text-leaf">
          <Globe className="size-5" />
          FoodBridge
        </Link>
      </nav>

      <div className="mx-auto flex min-h-[calc(100vh-56px)] max-w-md flex-col justify-center px-5 py-12">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-ink">Welcome back</h1>
          <p className="mt-2 text-ink/60">Sign in to your FoodBridge dashboard</p>
        </div>

        <Suspense fallback={<div className="flex items-center justify-center py-12"><Loader2 className="size-8 animate-spin text-leaf" /></div>}>
          <LoginForm />
        </Suspense>

        <p className="mt-6 text-center text-sm text-ink/50">
          New restaurant?{" "}
          <Link href="/onboarding/donor" className="font-bold text-leaf hover:underline">
            Register here <ArrowRight className="inline size-3" />
          </Link>
        </p>
        <p className="mt-2 text-center text-sm text-ink/50">
          Invited volunteer?{" "}
          <Link href="/volunteer/register" className="font-bold text-leaf hover:underline">
            Complete invite registration
          </Link>
        </p>
      </div>
    </div>
  );
}
