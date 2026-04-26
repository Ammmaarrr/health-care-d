import type { QueryResponse } from "./types";

/** Shown when NEXT_PUBLIC_BACKEND_URL is missing or the API errors. */
export const MOCK_QUERY_RESPONSE: QueryResponse = {
  results: [
    {
      facility_id: "mock-1",
      name: "Demo District Hospital (mock data)",
      location: {
        state: "Bihar",
        district: "Patna",
        pin: "800001",
        rural: true,
        latitude: 25.6,
        longitude: 85.1,
      },
      meta: { facility_type: "hospital" },
      capabilities: {
        has_icu: "uncertain",
        has_emergency: "yes",
        has_surgery: "yes",
        has_anesthesiologist: "uncertain",
        has_oxygen: "yes",
        has_oncology: "uncertain",
        has_dialysis: "uncertain",
        has_neonatal: "uncertain",
        has_trauma: "uncertain",
        has_lab: "uncertain",
        has_imaging: "uncertain",
        doctor_type: "part-time",
      },
      trust_score: 0.62,
      trust_breakdown: {
        completeness: 0.6,
        consistency: 0.7,
        validator: 0.55,
        evidence_strength: 0.65,
      },
      flags: [
        "Set NEXT_PUBLIC_BACKEND_URL in Vercel to call the real /query API (HF Space).",
      ],
      evidence: {
        emergency: "24x7 emergency services mentioned in facility notes (mock).",
        surgery: "Surgical services listed; verify current staffing.",
      },
      reasoning:
        "This is static mock data for UI demos. Connect your configured Hugging Face Space URL in Vercel project settings to load live results.",
      phone: null,
      email: null,
      distance_km: 12.4,
    },
  ],
  trace: {
    steps: ["mock: no backend reach"],
    cost: { estimated_cost_usd: 0, prompt_tokens: 0, completion_tokens: 0, calls: 0 },
  },
};
