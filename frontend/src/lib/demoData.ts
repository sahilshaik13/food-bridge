export type DonationStatus =
  | "draft"
  | "pending_match"
  | "notified"
  | "accepted"
  | "declined"
  | "assigned"
  | "completed"
  | "expired"
  | "needs_review"
  | "escalated_radius_2"
  | "escalated_radius_3"
  | "wasted";

export type Donation = {
  id: string;
  donor_id: string;
  donor_name: string;
  food_type: string;
  quantity_kg: number;
  meal_count: number;
  status: DonationStatus;
  location: { area: string; address: string; lat: number; lng: number };
  photo_url?: string;
  notes?: string;
  scan: {
    passed: boolean;
    confidence: number;
    reason: string;
    detected_food_type: string;
    freshness_window_minutes: number;
  };
  ngo_queue: Array<{
    ngo_id: string;
    ngo_name: string;
    distance_km: number;
    total_score: number;
    proximity_score: number;
    food_type_score: number;
    nutrition_score: number;
    reason: string;
  }>;
  assigned_ngo_id?: string;
  assigned_ngo_name?: string;
  volunteer_name?: string;
  pickup_photo_url?: string;
  completed_meals_served?: number;
  created_at: string;
  expires_at: string;
  updated_at: string;
  current_radius_km: number;
  escalation_level: number;
  notified_ngo_ids: string[];
  last_escalation_at?: string;
};

export type ImpactStats = {
  meals_served: number;
  kg_saved: number;
  co2_offset_kg: number;
  active_donations: number;
  completed_donations: number;
};

export type Prediction = {
  id: string;
  donor_id: string;
  donor_name: string;
  area: string;
  food_type: string;
  predicted_time: string;
  probability: number;
  nearby_ngos: number;
};

export type Notification = {
  id: string;
  donation_id?: string;
  recipient_role: "donor" | "ngo_coordinator" | "ngo_volunteer" | "municipal_admin" | "super_admin";
  recipient_id: string;
  title: string;
  body: string;
  channel: "dashboard" | "fcm" | "telegram";
  read: boolean;
  created_at: string;
};

export type Donor = {
  id: string;
  name: string;
  area: string;
  type: string;
  fssai_license: string;
  contact_name?: string;
  phone?: string;
  email?: string;
  location: { area: string; address: string; lat: number; lng: number };
  avg_surplus_kg: string;
  monthly_meals: number;
  verification_status: "pending" | "verified" | "suspended";
  telegram_enabled: boolean;
  telegram_chat_id?: string;
  telegram_username?: string;
  created_at: string;
};

export type Ngo = {
  id: string;
  name: string;
  area: string;
  focus: string;
  ngo_darpan_id: string;
  beneficiary_count: number;
  food_preferences: string[];
  dietary_restrictions: string[];
  location: { area: string; address: string; lat: number; lng: number };
  verification_status: "pending" | "verified" | "suspended";
  aadhaar_document_url?: string;
  meal_time_schedule?: string;
  coordinator_name?: string;
  coordinator_phone?: string;
};

export type CommunicationMessage = {
  id: string;
  donation_id: string;
  sender_role: "donor" | "ngo_coordinator" | "ngo_volunteer" | "municipal_admin" | "super_admin";
  sender_id: string;
  recipient_role: "donor" | "ngo_coordinator" | "ngo_volunteer" | "municipal_admin" | "super_admin";
  recipient_id: string;
  body: string;
  created_at: string;
};

export type UserProfile = {
  id: string;
  role: "super_admin" | "municipal_admin" | "donor" | "ngo_coordinator" | "ngo_volunteer";
  display_name: string;
  status: "pending" | "verified" | "active" | "rejected" | "suspended";
  entity_id?: string;
  duplicate_flag: boolean;
  created_at: string;
};

export type EmergencyRequest = {
  id: string;
  ngo_id: string;
  ngo_name: string;
  food_type: string;
  quantity_goal_kg: number;
  pledged_kg: number;
  status: "open" | "partial_accepted" | "cancelled" | "fulfilled";
  donor_targets: string[];
  created_at: string;
  deadline_at: string;
  notes?: string;
};

export type HeatmapFeature = {
  type: "Feature";
  properties: {
    kind: "surplus" | "demand";
    weight: number;
    name: string;
  };
  geometry: {
    type: "Point";
    coordinates: [number, number];
  };
};

export type HeatmapData = {
  generated_at: string;
  surplus: {
    type: "FeatureCollection";
    features: HeatmapFeature[];
  };
  demand: {
    type: "FeatureCollection";
    features: HeatmapFeature[];
  };
  coverage_gaps: Array<{
    area: string;
    severity: "high" | "medium" | "low";
    reason: string;
  }>;
};
