# Frontend prompt — paste into Lovable or v0

The frontend lives in a separate repo: https://github.com/Ammmaarrr/nexus-health-intel

Use this verbatim when you have credits.

---

```
Build a Next.js + Tailwind app called "Healthcare Intelligence Agent".

## Behavior
- Single page. Reads NEXT_PUBLIC_BACKEND_URL from env.
- If env var is missing OR the backend errors, fall back to mock data
  in /lib/mock.ts so the UI is always demoable.

## API contract (do not invent fields)
POST {BACKEND_URL}/query
Request:  {
  "query": string,
  "origin_lat"?: number,         // optional — enables "nearest" ranking
  "origin_lng"?: number,
  "use_llm_validator"?: boolean  // default true; toggle off for fast demos
}
Response: {
  "results": [{
    "facility_id": string,
    "name": string,
    "location": { "state": string, "district": string, "pin": string,
                  "rural": boolean, "latitude": number|null,
                  "longitude": number|null },
    "meta": { "facility_type": string|null },
    "capabilities": {
      "has_icu":             "yes" | "no" | "uncertain",
      "has_emergency":       "yes" | "no" | "uncertain",
      "has_surgery":         "yes" | "no" | "uncertain",
      "has_anesthesiologist":"yes" | "no" | "uncertain",
      "has_oxygen":          "yes" | "no" | "uncertain",
      "has_oncology":        "yes" | "no" | "uncertain",
      "has_dialysis":        "yes" | "no" | "uncertain",
      "has_neonatal":        "yes" | "no" | "uncertain",
      "has_trauma":          "yes" | "no" | "uncertain",
      "has_lab":             "yes" | "no" | "uncertain",
      "has_imaging":         "yes" | "no" | "uncertain",
      "doctor_type":         "full-time" | "part-time" | "unknown"
    },
    "trust_score": number,        // 0..1
    "trust_breakdown": {
      "completeness": number, "consistency": number,
      "validator": number, "evidence_strength": number
    },
    "flags": string[],
    "evidence": { [capability: string]: string },  // verbatim from notes
    "reasoning": string,
    "phone": string|null,
    "email": string|null,
    "distance_km": number|null    // only when origin_lat/lng was sent
  }],
  "trace": {
    "parsed_query": object,       // includes doctor_preference
    "retrieved_ids": string[],
    "validator_findings": object[],
    "trust_breakdown": object,
    "steps": string[],
    "cost": {
      "prompt_tokens": number, "completion_tokens": number,
      "calls": number, "estimated_cost_usd": number
    }
  }
}

GET {BACKEND_URL}/desert-map?min_total=20&capability=oncology
  -> { gaps: [{ state, capability, missing_or_uncertain, total,
                gap_ratio, wilson_lower, wilson_upper }] }

GET {BACKEND_URL}/desert-map/pins?capability=icu&top=40
  -> { zones: [{ pin, state, capability, total, missing_or_uncertain,
                 risk, wilson_lower, wilson_upper,
                 centroid_lat, centroid_lng }] }

GET {BACKEND_URL}/health -> { ok: true }

## UI
1. Header: "Healthcare Intelligence Agent" / "Find reliable medical care
   using AI reasoning". Subtle gradient background, soft shadow.
2. Search bar (large, centered). Placeholder:
   "Find emergency surgery hospital in rural Bihar with part-time doctors".
   Submit on Enter or button click.
3. While loading: skeleton cards + text "Analyzing 10,000 hospital records..."
4. Each result = card with:
   - Hospital name + location chip + (if `distance_km` present) "X km" pill
   - Trust score as a circular gauge:
       >= 0.75 green, 0.5-0.75 amber, < 0.5 red
   - Capability badges for ALL 11 capabilities + doctor_type:
       green=yes, gray=uncertain, red=no, with icons
   - Flags shown as warning rows with a triangle icon (only if non-empty)
   - Two collapsible sections:
       "View evidence" — list each evidence sentence, capability label on left
       "Why this result?" — render `reasoning` as the body text
5. Trust breakdown: small bar chart of the four sub-scores
   (completeness, consistency, validator, evidence_strength).
6. Below results, a "View reasoning trace" drawer (right-side slide-over)
   showing the raw `trace` JSON pretty-printed with syntax highlighting,
   plus a footer line "Cost this query: $0.0021 (320 prompt, 180 completion)".
7. Tab "Medical desert map":
   - Capability dropdown: ICU, Emergency, Surgery, Anesthesiologist,
     Oxygen, Oncology, Dialysis, Neonatal, Trauma, Lab, Imaging
   - State view (desert-map): choropleth, color = gap_ratio,
     tooltip shows Wilson 95% CI [wilson_lower .. wilson_upper]
   - PIN view (desert-map/pins): react-leaflet, marker per PIN at
     (centroid_lat, centroid_lng), color = risk

## Style
Modern AI SaaS. Inter font. Rounded-2xl. Soft shadows. Light mode default,
dark mode supported. No emojis except a triangle icon for flags.
```

---

Once Lovable produces the project:

1. Set `NEXT_PUBLIC_BACKEND_URL` in Vercel project settings to your HF Space URL.
2. The HF Space URL will look like `https://<username>-healthmap-agent.hf.space`.
3. Add `https://<your-vercel-app>.vercel.app` to the backend's `CORS_ORIGINS` env var on the Space.
