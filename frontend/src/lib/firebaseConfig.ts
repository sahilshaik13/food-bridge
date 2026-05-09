export type FirebaseWebConfig = {
  apiKey: string;
  authDomain: string;
  databaseURL: string;
  projectId: string;
  storageBucket: string;
  messagingSenderId: string;
  appId: string;
  measurementId?: string;
};

const requiredEnv = (name: string, fallback?: string): string => {
  const value = process.env[name] || fallback;
  if (!value) {
    console.error(`Missing required environment variable: ${name}`);
    return ""; 
  }
  return value;
};

export const firebaseConfig: FirebaseWebConfig = {
  apiKey: requiredEnv("NEXT_PUBLIC_FIREBASE_API_KEY"),
  authDomain: requiredEnv("NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN", "foodbridge-4f96f.firebaseapp.com"),
  databaseURL: requiredEnv("NEXT_PUBLIC_FIREBASE_DATABASE_URL", "https://foodbridge-4f96f-default-rtdb.asia-southeast1.firebasedatabase.app"),
  projectId: requiredEnv("NEXT_PUBLIC_FIREBASE_PROJECT_ID", "foodbridge-4f96f"),
  storageBucket: requiredEnv("NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET", "foodbridge-4f96f.firebasestorage.app"),
  messagingSenderId: requiredEnv("NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID", "507153921282"),
  appId: requiredEnv("NEXT_PUBLIC_FIREBASE_APP_ID", "1:507153921282:web:be29c2125697ffb7a0be1b"),
  measurementId: process.env.NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID || "G-ZMNS60LNVL",
};
