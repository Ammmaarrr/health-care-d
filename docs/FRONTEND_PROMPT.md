# Frontend prompt — paste into Lovable or v0

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
Request:  { "query": string }
Response: {
  "results": [{
    "facility_id": string,
    "name": string,
    "location": { "state": string, "district": string, "pin": string, "rural": boolean },
    "capabilities": {
      "has_icu":            "yes" | "no" | "uncertain",
      "has_emergency":      "yes" | "no" | "uncertain",
      "has_surgery":        "yes" | "no" | "uncertain",
      "has_anesthesiologist":"yes" | "no" | "uncertain",
      "has_oxygen":         "yes" | "no" | "uncertain",
      "doctor_type":        "full-time" | "part-time" | "unknown"
    },
    "trust_score": number,        // 0..1
    "flags": string[],
    "evidence": { [capability: string]: string },
    "reasoning": string
  }],
  "trace": {
    "parsed_query": object,
    "retrieved_ids": string[],
    "validator_findings": object[],
    "trust_breakdown": object,
    "steps": string[]
  }
}

GET {BACKEND_URL}/desert-map → { gaps: [{ state, capability, missing_or_uncertain, total }] }
GET {BACKEND_URL}/health     → { ok: true }

## UI
1. Header: "Healthcare Intelligence Agent" / "Find reliable medical care
   using AI reasoning". Subtle gradient background, soft shadow.
2. Search bar (large, centered). Placeholder:
   "Find emergency surgery hospital in rural Bihar with part-time doctors".
   Submit on Enter or button click.
3. While loading: skeleton cards + text "Analyzing 10,000 hospital records..."
4. Each result = card with:
   - Hospital name + location chip
   - Trust score as a circular gauge:
       >= 0.75 green, 0.5–0.75 amber, < 0.5 red
   - Capability badges: green=yes, gray=uncertain, red=no, with icons
   - Flags shown as warning rows with ⚠ (only if flags non-empty)
   - Two collapsible sections:
       "View evidence" — list each evidence sentence, capability label on left
       "Why this result?" — render `reasoning` as the body text
5. Below results, a "View reasoning trace" drawer (right-side slide-over)
   showing the raw `trace` JSON pretty-printed with syntax highlighting.

## Stretch (only if quick)
- Filter pill: "High trust only" (>= 0.75)
- Tab "Medical desert map" using react-leaflet, marker per state with
  color = (1 - gap_ratio for the worst capability in that state)

## Style
Modern AI SaaS. Inter font. Rounded-2xl. Soft shadows. Light mode default,
dark mode supported. No emojis except ⚠ in flags.
```

---

Once Lovable produces the project:

1. Set `NEXT_PUBLIC_BACKEND_URL` in Vercel project settings to your HF Space URL.
2. The HF Space URL will look like `https://<username>-healthmap-agent.hf.space`.
3. Add `https://<your-vercel-app>.vercel.app` to the backend's `CORS_ORIGINS` env var on the Space.
