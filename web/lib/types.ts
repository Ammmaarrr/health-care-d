export type TriState = "yes" | "no" | "uncertain";
export type DoctorType = "full-time" | "part-time" | "unknown";

export type Capabilities = {
  has_icu: TriState;
  has_emergency: TriState;
  has_surgery: TriState;
  has_anesthesiologist: TriState;
  has_oxygen: TriState;
  has_oncology: TriState;
  has_dialysis: TriState;
  has_neonatal: TriState;
  has_trauma: TriState;
  has_lab: TriState;
  has_imaging: TriState;
  doctor_type: DoctorType;
};

export type HospitalResult = {
  facility_id: string;
  name: string;
  location: {
    state: string;
    district: string;
    pin: string;
    rural: boolean;
    latitude: number | null;
    longitude: number | null;
  };
  meta: { facility_type: string | null };
  capabilities: Capabilities;
  trust_score: number;
  trust_breakdown: {
    completeness: number;
    consistency: number;
    validator: number;
    evidence_strength: number;
  };
  flags: string[];
  evidence: Record<string, string | undefined>;
  reasoning: string;
  phone: string | null;
  email: string | null;
  distance_km: number | null;
};

export type QueryResponse = {
  results: HospitalResult[];
  trace: Record<string, unknown>;
};
