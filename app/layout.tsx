import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "FoodBridge",
  description: "Real-time surplus food coordination for Hyderabad."
};

import { AuthProvider } from "@/lib/AuthProvider";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
