# Genie Prompt Pack

[Genie](https://docs.databricks.com/en/genie/index.html) is the Databricks
natural-language-to-SQL surface. Once notebooks 00-02 have built the
Delta tables, you can stand up a Genie Space against them and let
judges / NGO planners ask questions in English. This file is the
copy-paste prompt pack for the demo.

## 1. Stand up the Genie Space (one-time)

1. Databricks left nav -> **Genie** -> **New Genie space**.
2. Name: `Healthmap India 10k`.
3. Catalog / schema: `workspace.healthmap_agent` (or whatever you used).
4. Add these tables:
   - `facilities_clean`
   - `capabilities_extracted`            (regex extractor, notebook 02)
   - `capabilities_extracted_llm`        (LLM extractor, notebook 02b — optional)
   - `trust_scores`
   - `validator_findings`
   - `medical_deserts_by_state`
   - `medical_deserts_by_pin`
   - `crisis_zones_top_pin`
5. Paste the **Instructions** block below into the space's instructions.
6. Save and share the read link.

## 2. Genie Space instructions (paste verbatim)

```
You are an analyst for a healthcare NGO using the India 10k facilities
dataset. Always answer with concrete numbers and SQL queries against the
tables in this space. Prefer the `trust_scores` table when the question
involves capability claims, because it has the validator flags column.
Use `medical_deserts_by_state` and `medical_deserts_by_pin` when the
question is about regional gaps or crisis zones. The Wilson 95% CIs
(`wilson_lower`, `wilson_upper`) measure how confident the gap_ratio is;
quote them whenever you call out a "desert" so the user knows whether
the gap is statistically established or just sparse data. Capability
columns are tristates: yes / no / uncertain. Treat both `no` and
`uncertain` as "missing" when computing deserts.
```

## 3. Headline demo prompts

Run these in the Genie space for the live demo. The expected SQL is
inline (Genie should produce something close to it; if it does not, you
can paste the SQL into the chat).

### 3.1 The brief's headline query
> Which facilities in rural Bihar can perform an emergency appendectomy
> and typically use part-time doctors? Sort by trust score.

```sql
SELECT name, district, pin, trust_score, flags,
       has_surgery, has_emergency, has_anesthesiologist, doctor_type
FROM trust_scores
WHERE LOWER(state) LIKE '%bihar%'
  AND rural = TRUE
  AND has_surgery IN ('yes', 'uncertain')
  AND has_emergency IN ('yes', 'uncertain')
  AND doctor_type = 'part-time'
ORDER BY trust_score DESC
LIMIT 25;
```

### 3.2 Specialised deserts
> Which states have the worst gap for oncology, with at least 30
> facilities reporting?

```sql
SELECT state, total, missing_or_uncertain, gap_ratio,
       wilson_lower, wilson_upper
FROM medical_deserts_by_state
WHERE capability = 'has_oncology'
  AND total >= 30
ORDER BY gap_ratio DESC
LIMIT 20;
```

### 3.3 Truth gap audit
> List facilities that claim surgery but have no anesthesiologist
> verified — these are the "advanced surgery, no anesthesia" cases the
> brief warned about.

```sql
SELECT facility_id, name, state, district, pin,
       has_surgery, has_anesthesiologist, trust_score, flags
FROM trust_scores
WHERE has_surgery = 'yes'
  AND has_anesthesiologist <> 'yes'
ORDER BY trust_score ASC
LIMIT 50;
```

### 3.4 Crisis hotspot map seed
> Top 20 PIN codes with the worst ICU desert risk where we have at
> least 5 facilities reporting.

```sql
SELECT pin, state, total, missing_or_uncertain, risk,
       wilson_lower, wilson_upper, centroid_lat, centroid_lng
FROM medical_deserts_by_pin
WHERE capability = 'has_icu'
  AND total >= 5
ORDER BY risk DESC, total DESC
LIMIT 20;
```

### 3.5 Self-correction discrepancies
> Where do the regex and LLM extractors disagree on `has_surgery`?
> Useful when both notebook 02 and 02b have run.

```sql
WITH r AS (SELECT facility_id, has_surgery AS regex_surgery FROM capabilities_extracted),
     l AS (SELECT facility_id, has_surgery AS llm_surgery FROM capabilities_extracted_llm)
SELECT r.facility_id, regex_surgery, llm_surgery
FROM r JOIN l USING (facility_id)
WHERE regex_surgery <> llm_surgery
LIMIT 100;
```

### 3.6 Validator findings by severity
> How many facilities have at least one HIGH-severity validator finding,
> grouped by state?

```sql
SELECT state, COUNT(DISTINCT facility_id) AS facilities_with_high_findings
FROM validator_findings
WHERE severity = 'high'
GROUP BY state
ORDER BY facilities_with_high_findings DESC
LIMIT 25;
```

### 3.7 Confidence-aware desert ranking (Areas of Research § 4)
> Show me the worst dialysis deserts but only where the Wilson lower
> bound is above 0.5 — i.e. we are 95% confident the gap_ratio is more
> than a coin flip.

```sql
SELECT state, total, missing_or_uncertain, gap_ratio,
       wilson_lower, wilson_upper
FROM medical_deserts_by_state
WHERE capability = 'has_dialysis'
  AND wilson_lower > 0.5
ORDER BY wilson_lower DESC
LIMIT 20;
```

## 4. Tips for the live demo

- Run prompt 3.1 first so judges see multi-attribute reasoning live.
- Then prompt 3.3 to show the trust-gap audit (the brief's flagship
  example: "Advanced Surgery but no Anesthesiologist").
- Then prompt 3.7 to show the confidence-aware desert ranking that
  answers Areas of Research § 4.
- Genie shows the generated SQL inline; combine with the MLflow tracing
  view from `03_query_demo_with_mlflow.py` to demonstrate end-to-end
  agentic traceability.
