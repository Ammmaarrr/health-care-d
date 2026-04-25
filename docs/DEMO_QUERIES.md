# Suggested demo queries

Use these in your Lovable UI's example pills, or just to verify the
backend after deploy.

## The "trust gap" query (the headline demo)
> Find emergency surgery hospital in rural Bihar

What to point at on screen:
- **Top result has trust ~0.65** because anesthesiologist is verified.
- **Lower results have trust ~0.23** with the flag *"Surgery is claimed
  but anesthesiologist is uncertain"*. This is the whole point of the
  system.

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
```

Returns the worst capability gaps by state, ready to overlay on a map.
