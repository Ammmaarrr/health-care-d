# Suggested demo queries

Use these in your Lovable UI's example pills, or just to verify the
backend after deploy.

## The brief's own headline query (multi-attribute reasoning)
> Find the nearest facility in rural Bihar that can perform an emergency
> appendectomy and typically leverages part-time doctors

Send with `origin_lat` / `origin_lng` set to a Bihar pin (e.g. Patna
25.5941, 85.1376) to enable the proximity bonus. The agent should:
- parse `state=Bihar`, `rural=true`, `required_capabilities=[surgery,
  emergency]`, `doctor_preference=part-time`;
- return `distance_km` per result and rank closer + part-time matches first.

## The "trust gap" query
> Find emergency surgery hospital in rural Bihar

What to point at on screen:
- **Top result has trust ~0.65** because anesthesiologist is verified.
- **Lower results have trust ~0.23** with the flag *"Surgery is claimed
  but anesthesiologist is uncertain"*. This is the whole point of the
  system.

## High-acuity specialty queries (oncology / dialysis / trauma)
> Where can a kidney patient get dialysis in Tamil Nadu?

> Cancer chemotherapy hospital near Pune

> Trauma care for road accident victims in Uttar Pradesh

Each of these exercises the new capability vocabulary. The validator
will flag e.g. "Oncology claimed but laboratory is uncertain."

## ICU + staff query
> Find ICU hospital with full-time doctors near Maharashtra

Shows:
- ICU verified vs uncertain in evidence.
- Doctor type extraction (`full-time` / `part-time` / `unknown`).

## Rural-discovery query
> Nearest hospital with 24/7 emergency care in Uttar Pradesh

Shows:
- Structured filter on state + retrieval over notes for "24/7".
- Several rural facilities surfaced, scored by their evidence.

## Gap discovery (no specific location)
> Hospitals that can perform surgery and have oxygen supply

Shows:
- Cross-capability filter; system flags "Surgery without oxygen".

## Negative-confidence query
> Hospital with neonatal ICU near Bihar

Shows:
- The system is **conservative**: most facilities marked "uncertain"
  for ICU because their notes don't mention neonatal capability.
- Trust scores low across the board → demonstrates the model isn't
  hallucinating capabilities.

## Desert map call (separate endpoint)
```http
GET /desert-map?min_total=30
GET /desert-map?min_total=20&capability=icu
GET /desert-map?min_total=20&capability=oncology
GET /desert-map?min_total=20&capability=dialysis
GET /desert-map?min_total=20&capability=trauma
GET /desert-map/pins?capability=icu&top=40
```

Each `gap` / `zone` now includes `wilson_lower` and `wilson_upper`
fields — a Wilson 95% confidence interval on the gap ratio so NGO
planners can distinguish a truly under-served region from one whose
data is just sparse (Areas-of-Research § 4 in the brief).
