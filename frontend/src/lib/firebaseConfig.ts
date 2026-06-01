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

const requiredEnv = (name: string, value?: string, fallback?: string): string => {
  const resolved = value || fallback;
  if (!resolved) {
    console.error(`Missing required environment variable: ${name}`);
    return "";
  }
  return resolved;
};

const firebaseApiKey = requiredEnv(
  "NEXT_PUBLIC_FIREBASE_API_KEY",
  process.env.NEXT_PUBLIC_FIREBASE_API_KEY
);
const firebaseAuthDomain = requiredEnv(
  "NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN",
  process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  "foodbridge-4f96f.firebaseapp.com"
);
const firebaseDatabaseUrl = requiredEnv(
  "NEXT_PUBLIC_FIREBASE_DATABASE_URL",
  process.env.NEXT_PUBLIC_FIREBASE_DATABASE_URL,
  "https://foodbridge-4f96f-default-rtdb.asia-southeast1.firebasedatabase.app"
);
const firebaseProjectId = requiredEnv(
  "NEXT_PUBLIC_FIREBASE_PROJECT_ID",
  process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  "foodbridge-4f96f"
);
const firebaseStorageBucket = requiredEnv(
  "NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET",
  process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  "foodbridge-4f96f.firebasestorage.app"
);
const firebaseMessagingSenderId = requiredEnv(
  "NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID",
  process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  "507153921282"
);
const firebaseAppId = requiredEnv(
  "NEXT_PUBLIC_FIREBASE_APP_ID",
  process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
  "1:507153921282:web:fb3739f1e8e01adba0be1b"
);

export const firebaseConfig: FirebaseWebConfig = {
  apiKey: firebaseApiKey,
  authDomain: firebaseAuthDomain,
  databaseURL: firebaseDatabaseUrl,
  projectId: firebaseProjectId,
  storageBucket: firebaseStorageBucket,
  messagingSenderId: firebaseMessagingSenderId,
  appId: firebaseAppId,
  measurementId: process.env.NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID || "G-N37VKGNTKJ",
};
