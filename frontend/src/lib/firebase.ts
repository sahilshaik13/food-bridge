import { getApps, initializeApp } from "firebase/app";
import type { FirebaseApp } from "firebase/app";
import { getAuth } from "firebase/auth";
import { getDatabase } from "firebase/database";
import { getFirestore } from "firebase/firestore";
import { getStorage } from "firebase/storage";

import { firebaseConfig } from "./firebaseConfig";

export const firebaseApp: FirebaseApp =
  getApps().length > 0 ? getApps()[0] : initializeApp(firebaseConfig);

export const firebaseAuth = getAuth(firebaseApp);
export const firestore = getFirestore(firebaseApp);
export const realtimeDatabase = getDatabase(firebaseApp);
export const firebaseStorage = getStorage(firebaseApp);
