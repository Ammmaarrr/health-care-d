# Databricks notebook source
# MAGIC %md
# MAGIC # 03 - Agentic Query Demo With MLflow Tracing
# MAGIC
# MAGIC Multi-attribute reasoning over the Delta tables produced by `02`. Each agent
# MAGIC step is wrapped with `@mlflow.trace` (with a safe fallback) so judges can see
# MAGIC the full chain of thought in MLflow Tracing.
# MAGIC
# MAGIC Default query covers the challenge example:
# MAGIC `Find the nearest facility in rural Bihar that can perform an emergency
# MAGIC appendectomy and typically leverages part-time doctors.`

# COMMAND ----------

import math

import mlflow
from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "workspace", "Unity Catalog catalog")
dbutils.widgets.text("schema", "healthmap_agent", "Unity Catalog schema")
dbutils.widgets.text("experiment_name", "/Shared/healthmap-agent", "MLflow experiment")
dbutils.widgets.text(
    "query",
    "Find the nearest facility in rural Bihar that can perform an emergency appendectomy and typically leverages part-time doctors",
    "Natural-language query",
)
dbutils.widgets.text("origin_lat", "", "Optional anchor latitude (for nearest)")
dbutils.widgets.text("origin_lng", "", "Optional anchor longitude (for nearest)")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
experiment_name = dbutils.widgets.get("experiment_name")
query = dbutils.widgets.get("query")
origin_lat_raw = dbutils.widgets.get("origin_lat").strip()
origin_lng_raw = dbutils.widgets.get("origin_lng").strip()
origin_lat = float(origin_lat_raw) if origin_lat_raw else None
origin_lng = float(origin_lng_raw) if origin_lng_raw else None

spark.sql(f"USE `{catalog}`.`{schema}`")
mlflow.set_tracking_uri("databricks")
mlflow.set_registry_uri("databricks")
mlflow.set_experiment(experiment_name)

# COMMAND ----------

def _resolve_trace_decorator():
    candidate = getattr(mlflow, "trace", None)
    if candidate is None:
        return None
    try:
        @candidate
        def _probe():
            return None

        _probe()
        return candidate
    except Exception:
        return None


_trace = _resolve_trace_decorator()


def trace_step(name: str | None = None):
    def decorator(fn):
        if _trace is None:
            return fn
        try:
            return _trace(fn) if name is None else _trace(name=name)(fn)
        except TypeError:
            return _trace(fn)

    return decorator


# COMMAND ----------

CAPABILITY_KEYWORDS = {
    "has_icu": ["icu", "intensive care", "critical care", "ventilator"],
    "has_emergency": ["emergency", "casualty", "ambulance", "trauma"],
    "has_surgery": ["surgery", "surgical", "operation", "appendectomy", "laparoscopy", "c-section", "csection"],
    "has_anesthesiologist": ["anesth", "anaesth"],
    "has_oxygen": ["oxygen", "o2"],
    "has_oncology": ["oncology", "cancer", "chemotherapy", "chemo", "radiation", "tumor", "tumour"],
    "has_dialysis": ["dialysis", "hemodialysis", "haemodialysis", "kidney", "nephrology", "renal"],
    "has_neonatal": ["neonatal", "nicu", "newborn", "premature", "paediatric icu"],
    "has_trauma": ["trauma", "polytrauma", "accident ward"],
    "has_24x7": ["24/7", "24x7", "round the clock", "twenty four hour"],
    "has_blood_bank": ["blood bank", "transfusion"],
    "has_lab": ["laboratory", "pathology", "blood test"],
    "has_xray": ["x-ray", "xray", "radiograph", "imaging", "ct scan", "mri", "ultrasound"],
    "has_dental": ["dental", "dentist"],
    "has_pharmacy": ["pharmacy", "chemist", "drug store"],
}

INDIAN_STATES = [
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh", "goa",
    "gujarat", "haryana", "himachal pradesh", "jharkhand", "karnataka", "kerala",
    "madhya pradesh", "maharashtra", "manipur", "meghalaya", "mizoram", "nagaland",
    "odisha", "punjab", "rajasthan", "sikkim", "tamil nadu", "telangana", "tripura",
    "uttar pradesh", "uttarakhand", "west bengal", "delhi", "jammu and kashmir",
    "ladakh", "puducherry", "chandigarh",
]


@trace_step("01_parse_query")
def parse_query(q: str) -> dict:
    ql = q.lower()
    required = []
    for cap, keywords in CAPABILITY_KEYWORDS.items():
        if any(k in ql for k in keywords):
            required.append(cap)

    state = next((s.title() for s in INDIAN_STATES if s in ql), None)

    rural = None
    if "rural" in ql:
        rural = True
    elif "urban" in ql or "tier-1" in ql or "tier 1" in ql:
        rural = False

    doctor = None
    if "part-time" in ql or "part time" in ql or "visiting" in ql:
        doctor = "part-time"
    elif "full-time" in ql or "full time" in ql or "resident" in ql:
        doctor = "full-time"

    return {
        "state": state,
        "rural": rural,
        "doctor_type": doctor,
        "required_capabilities": required,
    }


@trace_step("02_filter_candidates")
def filter_candidates(df, parsed: dict):
    if parsed["state"]:
        df = df.filter(F.lower(F.col("state")).contains(parsed["state"].lower()))
    if parsed["rural"] is not None:
        df = df.filter(F.col("rural") == parsed["rural"])
    return df


@trace_step("03_score_match")
def score_match(df, parsed: dict):
    expr = F.lit(0.0)
    weight = 0.0
    for cap in parsed["required_capabilities"]:
        expr = expr + F.when(F.col(cap) == "yes", F.lit(1.0)) \
                       .when(F.col(cap) == "uncertain", F.lit(0.25)) \
                       .otherwise(F.lit(0.0))
        weight += 1.0
    if parsed.get("doctor_type"):
        expr = expr + F.when(F.col("doctor_type") == parsed["doctor_type"], F.lit(0.5)).otherwise(F.lit(0.0))
        weight += 0.5
    denom = max(1.0, weight)
    return df.withColumn("match_score", expr / F.lit(denom))


@trace_step("04_apply_distance")
def apply_distance(df, lat: float | None, lng: float | None):
    if lat is None or lng is None:
        return df
    lat1 = F.radians(F.lit(lat))
    lng1 = F.radians(F.lit(lng))
    lat2 = F.radians(F.col("latitude"))
    lng2 = F.radians(F.col("longitude"))
    a = (F.sin((lat2 - lat1) / 2) ** 2) + F.cos(lat1) * F.cos(lat2) * (F.sin((lng2 - lng1) / 2) ** 2)
    distance_km = F.lit(2 * 6371.0) * F.asin(F.sqrt(a))
    return df.withColumn("distance_km", distance_km)


@trace_step("05_rank_results")
def rank_results(df, has_origin: bool):
    score_cols = [
        F.lit(0.5) * F.col("match_score"),
        F.lit(0.4) * F.col("trust_score"),
    ]
    if has_origin:
        proximity = F.when(F.col("distance_km").isNull(), F.lit(0.0)) \
            .otherwise(F.greatest(F.lit(0.0), F.lit(1.0) - F.col("distance_km") / F.lit(500.0)))
        score_cols.append(F.lit(0.1) * proximity)
    combined = score_cols[0]
    for c in score_cols[1:]:
        combined = combined + c
    return df.withColumn("combined_score", combined).orderBy(F.desc("combined_score"), F.desc("trust_score"))


# COMMAND ----------

with mlflow.start_run(run_name="databricks_query_demo"):
    parsed = parse_query(query)
    mlflow.log_param("query", query)
    mlflow.log_dict(parsed, "parsed_query.json")
    if origin_lat is not None and origin_lng is not None:
        mlflow.log_param("origin_lat", origin_lat)
        mlflow.log_param("origin_lng", origin_lng)

    facilities = spark.table(f"`{catalog}`.`{schema}`.trust_scores")
    candidates = filter_candidates(facilities, parsed)
    candidates = apply_distance(candidates, origin_lat, origin_lng)
    candidates = score_match(candidates, parsed)
    ranked = rank_results(candidates, has_origin=origin_lat is not None and origin_lng is not None)

    select_cols = [
        "facility_id", "name", "state", "district", "pin", "rural",
        "trust_score", "match_score", "combined_score", "flags",
    ]
    if origin_lat is not None and origin_lng is not None:
        select_cols.append("distance_km")
    select_cols.extend([c for c in CAPABILITY_KEYWORDS.keys()])
    select_cols.extend([
        "icu_evidence", "emergency_evidence", "surgery_evidence",
        "anesthesiologist_evidence", "oxygen_evidence",
        "oncology_evidence", "dialysis_evidence", "neonatal_evidence", "trauma_evidence",
    ])

    results = ranked.select(*select_cols).limit(10)
    rows = [row.asDict(recursive=True) for row in results.collect()]

    mlflow.log_metric("candidate_count", candidates.count())
    mlflow.log_metric("returned_count", len(rows))
    mlflow.log_dict({"query": query, "parsed": parsed, "results": rows}, "agent_trace.json")

display(results)
