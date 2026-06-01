"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { onIdTokenChanged, signOut as firebaseSignOut, User } from "firebase/auth";
import { firebaseAuth } from "./firebase";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "https://foodbridge-api-aqg35pktda-el.a.run.app";

function requireApiBase(): string {
  if (!API_BASE) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL is required and must point to backend.");
  }
  return API_BASE;
}

export interface AuthProfile {
  id: string;
  role: string;
  display_name?: string;
  name?: string;
  status?: string;
  entity_id?: string;
  telegram_enabled?: boolean;
  fssai_license?: string;
  telegram_username?: string;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  role: string | null;
  profile: AuthProfile | null;
  idToken: string | null;
  signOut: () => Promise<void>;
  refreshProfile: () => Promise<void>;
  redirectTo: string | null;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  role: null,
  profile: null,
  idToken: null,
  signOut: async () => {},
  refreshProfile: async () => {},
  redirectTo: null,
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [role, setRole] = useState<string | null>(null);
  const [profile, setProfile] = useState<AuthProfile | null>(null);
  const [idToken, setIdToken] = useState<string | null>(null);
  const [redirectTo, setRedirectTo] = useState<string | null>(null);

  const refreshProfile = async () => {
    if (!user) return;
    try {
      const base = requireApiBase();
      const token = await user.getIdToken(true);
      setIdToken(token);
      const response = await fetch(`${base}/auth/verify`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });

      if (response.ok) {
        const data = await response.json();
        setRole(data.role);
        setProfile(data.profile);
        setRedirectTo(data.redirect_to);
      } else {
        const errorText = await response.text();
        console.error("Profile refresh /auth/verify failed:", response.status, errorText);
        setRole(null);
        setProfile(null);
        setRedirectTo(null);
      }
    } catch (err) {
      console.error("Profile refresh failed:", err);
      setRole(null);
      setProfile(null);
      setRedirectTo(null);
    }
  };

  useEffect(() => {
    return onIdTokenChanged(firebaseAuth, async (currentUser) => {
      setUser(currentUser);

      if (currentUser) {
        try {
          const base = requireApiBase();
          const token = await currentUser.getIdToken(true);
          setIdToken(token);
          // Make token available globally for api.ts
          if (typeof window !== "undefined") {
            (window as any).__fbToken = token;
          }

          const response = await fetch(`${base}/auth/verify`, {
            method: "POST",
            headers: {
              Authorization: `Bearer ${token}`,
              "Content-Type": "application/json",
            },
          });

          if (response.ok) {
            const data = await response.json();
            setRole(data.role);
            setProfile(data.profile);
            setRedirectTo(data.redirect_to);
          } else {
            const errorText = await response.text();
            console.error("Auth verification /auth/verify failed:", response.status, errorText);
            setRole(null);
            setProfile(null);
            setRedirectTo(null);
          }
        } catch (err) {
          console.error("Auth verification failed:", err);
          setRole(null);
          setProfile(null);
          setRedirectTo(null);
        }
      } else {
        // Logged out — clear everything
        if (typeof window !== "undefined") {
          (window as any).__fbToken = null;
        }
        setIdToken(null);
        setRole(null);
        setProfile(null);
        setRedirectTo(null);
      }
      setLoading(false);
    });
  }, []);

  const signOut = async () => {
    await firebaseSignOut(firebaseAuth);
  };

  return (
    <AuthContext.Provider value={{ user, loading, role, profile, idToken, signOut, refreshProfile, redirectTo }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
