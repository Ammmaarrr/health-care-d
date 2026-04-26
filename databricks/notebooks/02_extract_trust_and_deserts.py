# Databricks notebook source
# MAGIC %md
# MAGIC # 02 - Extract, Trust Score, Validate, And Map Deserts
# MAGIC
# MAGIC Creates the judge-visible Databricks tables for the MVP plus stretch goals:
# MAGIC
# MAGIC - `capabilities_extracted`            unstructured -> 15 capability tristates with evidence
# MAGIC - `trust_scores`                      per-facility trust score with breakdown and flags
# MAGIC - `validator_findings`                self-correction findings with severity (stretch #2)
# MAGIC - `medical_deserts_by_state`          per-state gap ratios with Wilson 95% CIs (research item)
# MAGIC - `medical_deserts_by_pin`            per-PIN gaps with centroids + risk + Wilson CIs
# MAGIC
# MAGIC Each stage is wrapped with `@mlflow.trace` so the agent's thought process is
# MAGIC visible in MLflow 3 Tracing (stretch #1). Falls back to plain functions on
# MAGIC older runtimes so the notebook stays portable.

# COMMAND ----------

import math
import re
from functools import wraps

import mlflow
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    StringType,
    StructField,
    StructType,
)

dbutils.widgets.text("catalog", "workspace", "Unity Catalog catalog")
dbutils.widgets.text("schema", "healthmap_agent", "Unity Catalog schema")
dbutils.widgets.text("experiment_name", "/Shared/healthmap-agent", "MLflow experiment")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
experiment_name = dbutils.widgets.get("experiment_name")

spark.sql(f"USE `{catalog}`.`{schema}`")
mlflow.set_tracking_uri("databricks")
mlflow.set_registry_uri("databricks")
mlflow.set_experiment(experiment_name)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Tracing helper
# MAGIC
# MAGIC `@trace_step` uses `mlflow.trace` if the runtime exposes it (MLflow 3),
# MAGIC otherwise it is a no-op decorator so the notebook still runs on older runtimes.

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

# MAGIC %md
# MAGIC ## Capability vocabulary
# MAGIC
# MAGIC Covers the MVP-required capabilities (ICU, emergency, surgery, anesthesiology,
# MAGIC oxygen) plus the high-acuity capabilities the challenge calls out (oncology,
# MAGIC dialysis, neonatal, trauma) and infrastructure indicators (24x7, blood bank,
# MAGIC lab, x-ray, dental, pharmacy).

# COMMAND ----------

YES_PATTERNS = {
    "has_icu": re.compile(r"\b(icu|intensive\s+care|critical\s+care|ventilator)\b", re.I),
    "has_emergency": re.compile(r"\b(emergency|casualty|er\b|ambulance)\b", re.I),
    "has_surgery": re.compile(r"\b(surgery|surgical|operation\s+theatre|\bot\b|appendectomy|laparoscopy|c[- ]?section)\b", re.I),
    "has_anesthesiologist": re.compile(r"\b(anesthesiologist|anaesthesiologist|anesthesia|anaesthesia)\b", re.I),
    "has_oxygen": re.compile(r"\b(oxygen|o2|oxygen\s+concentrator|oxygen\s+supply|oxygen\s+cylinder)\b", re.I),
    "has_oncology": re.compile(r"\b(oncology|onco|cancer|chemotherapy|chemo|radiation\s+therapy|tumou?r)\b", re.I),
    "has_dialysis": re.compile(r"\b(dialysis|haemodialysis|hemodialysis|nephrology|renal)\b", re.I),
    "has_neonatal": re.compile(r"\b(neonatal|nicu|newborn|premature|paediatric\s+icu|pediatric\s+icu)\b", re.I),
    "has_trauma": re.compile(r"\b(trauma|accident\s+ward|polytrauma|critical\s+injury)\b", re.I),
    "has_24x7": re.compile(r"\b(24\s*[/x-]?\s*7|24\s*hours?|round[\s-]+the[\s-]+clock|twenty[\s-]+four\s+hours?)\b", re.I),
    "has_blood_bank": re.compile(r"\b(blood\s+bank|transfusion|blood\s+donation)\b", re.I),
    "has_lab": re.compile(r"\b(laboratory|\blab\b|pathology|microbiology|biochemistry|haematology|hematology)\b", re.I),
    "has_xray": re.compile(r"\b(x[\s-]?ray|radiograph|radiology|imaging|ct\s+scan|cat\s+scan|mri|ultrasound|sonograph)\b", re.I),
    "has_dental": re.compile(r"\b(dental|dentist|orthodontic|endodontic|prosthodontic)\b", re.I),
    "has_pharmacy": re.compile(r"\b(pharmacy|drug\s+store|chemist|dispensary)\b", re.I),
}

CAPABILITY_NAMES = list(YES_PATTERNS.keys())
EVIDENCE_FIELDS = [f"{c.removeprefix('has_')}_evidence" for c in CAPABILITY_NAMES]

NEGATION = re.compile(r"\b(no|not\s+available|without|unavailable|lack(?:s|ing)?|missing|absent)\b", re.I)
PART_TIME = re.compile(r"\b(part[\s-]?time|visiting|on[\s-]?call|consultant)\b", re.I)
FULL_TIME = re.compile(r"\b(full[\s-]?time|resident|in[\s-]?house|on[\s-]?staff)\b", re.I)


@trace_step("split_sentences")
def split_sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


@trace_step("sentence_with_pattern")
def sentence_with(pattern: re.Pattern, text: str) -> str | None:
    for sentence in split_sentences(text):
        if pattern.search(sentence):
            return sentence[:500]
    return None


@trace_step("classify_tristate")
def tristate(pattern: re.Pattern, text: str) -> str:
    evidence = sentence_with(pattern, text)
    if not evidence:
        return "uncertain"
    if NEGATION.search(evidence):
        return "no"
    return "yes"


@trace_step("classify_doctor_type")
def doctor_type(text: str) -> str:
    text = text or ""
    if PART_TIME.search(text):
        return "part-time"
    if FULL_TIME.search(text):
        return "full-time"
    return "unknown"


# COMMAND ----------

extract_schema = StructType(
    [StructField(c, StringType()) for c in CAPABILITY_NAMES]
    + [StructField("doctor_type", StringType())]
    + [StructField(f, StringType()) for f in EVIDENCE_FIELDS]
)


@F.udf(returnType=extract_schema)
def extract_capabilities(notes: str):
    notes = notes or ""
    record = {name: tristate(pattern, notes) for name, pattern in YES_PATTERNS.items()}
    record["doctor_type"] = doctor_type(notes)
    for cap, field in zip(CAPABILITY_NAMES, EVIDENCE_FIELDS):
        record[field] = sentence_with(YES_PATTERNS[cap], notes)
    return record

# COMMAND ----------

# MAGIC %md
# MAGIC ## Trust scoring
# MAGIC
# MAGIC Trust = `0.15 base + 0.05 per yes - 0.04 per no - 0.02 per uncertain`,
# MAGIC then penalised when high-acuity claims contradict supporting capabilities
# MAGIC (e.g. surgery without anesthesiologist, ICU without oxygen, oncology without
# MAGIC lab/imaging, dialysis without lab, trauma without emergency).

# COMMAND ----------

CONTRADICTION_RULES = [
    ("surgery_without_anesth", "has_surgery", "has_anesthesiologist", 0.20, "high",
     "Claims surgery but anesthesiologist is not verified"),
    ("icu_without_oxygen", "has_icu", "has_oxygen", 0.15, "high",
     "Claims ICU but oxygen support is not verified"),
    ("trauma_without_emergency", "has_trauma", "has_emergency", 0.10, "medium",
     "Claims trauma care but no emergency capability"),
    ("oncology_without_lab", "has_oncology", "has_lab", 0.10, "medium",
     "Claims oncology but no laboratory capability"),
    ("oncology_without_imaging", "has_oncology", "has_xray", 0.10, "medium",
     "Claims oncology but no imaging or radiology"),
    ("dialysis_without_lab", "has_dialysis", "has_lab", 0.08, "medium",
     "Claims dialysis but no supporting laboratory"),
    ("neonatal_without_oxygen", "has_neonatal", "has_oxygen", 0.10, "medium",
     "Claims neonatal/NICU but no oxygen capability"),
    ("nicu_without_paediatrics", "has_neonatal", "has_emergency", 0.05, "low",
     "Claims neonatal but no emergency or 24/7 capability"),
]


@F.udf(returnType=DoubleType())
def trust_score_udf(*values):
    capability_values = list(values[: len(CAPABILITY_NAMES)])
    doctor = values[len(CAPABILITY_NAMES)]
    yes = sum(1 for v in capability_values if v == "yes")
    no = sum(1 for v in capability_values if v == "no")
    uncertain = sum(1 for v in capability_values if v == "uncertain")
    score = 0.15 + 0.05 * yes - 0.04 * no - 0.02 * uncertain

    by_name = dict(zip(CAPABILITY_NAMES, capability_values))
    for _id, claim, support, penalty, _sev, _msg in CONTRADICTION_RULES:
        if by_name.get(claim) == "yes" and by_name.get(support) != "yes":
            score -= penalty
    if doctor == "part-time":
        score -= 0.03
    return float(max(0.0, min(1.0, score)))


@F.udf(returnType=StringType())
def trust_flags_udf(*values):
    capability_values = list(values[: len(CAPABILITY_NAMES)])
    doctor = values[len(CAPABILITY_NAMES)]
    by_name = dict(zip(CAPABILITY_NAMES, capability_values))
    flags = []
    for _id, claim, support, _penalty, _sev, message in CONTRADICTION_RULES:
        if by_name.get(claim) == "yes" and by_name.get(support) != "yes":
            flags.append(message)
    if doctor == "part-time":
        flags.append("Relies on part-time/visiting doctors")
    return "; ".join(flags)


validator_finding_schema = StructType([
    StructField("rule_id", StringType()),
    StructField("capability", StringType()),
    StructField("severity", StringType()),
    StructField("message", StringType()),
])


@F.udf(returnType=StructType([StructField("findings", StringType())]))
def _placeholder_findings_udf(*_args):
    return {"findings": ""}


# Build the validator UDF programmatically so it returns ARRAY<STRUCT>.
def _make_validator_udf():
    array_struct = f"array<struct<rule_id:string,capability:string,severity:string,message:string>>"

    @F.udf(returnType=array_struct)
    def _validate(*values):
        capability_values = list(values[: len(CAPABILITY_NAMES)])
        by_name = dict(zip(CAPABILITY_NAMES, capability_values))
        out = []
        for rule_id, claim, support, _penalty, severity, message in CONTRADICTION_RULES:
            if by_name.get(claim) == "yes" and by_name.get(support) != "yes":
                out.append({"rule_id": rule_id, "capability": claim, "severity": severity, "message": message})
        return out

    return _validate


validator_udf = _make_validator_udf()


# COMMAND ----------

# MAGIC %md
# MAGIC ## Run extraction + scoring + validation

# COMMAND ----------

with mlflow.start_run(run_name="databricks_rule_extraction"):
    facilities = spark.table(f"`{catalog}`.`{schema}`.facilities_clean")
    extracted = facilities.withColumn("extracted", extract_capabilities(F.col("notes"))).select(
        "facility_id", "name", "state", "district", "pin", "rural", "latitude", "longitude",
        "facility_type", "phone", "email", "notes", "extracted.*",
    )

    score_inputs = [F.col(c) for c in CAPABILITY_NAMES] + [F.col("doctor_type")]
    trusted = extracted.withColumn("trust_score", trust_score_udf(*score_inputs)) \
        .withColumn("flags", trust_flags_udf(*score_inputs)) \
        .withColumn("validator_findings", validator_udf(*[F.col(c) for c in CAPABILITY_NAMES]))

    extracted.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
        f"`{catalog}`.`{schema}`.capabilities_extracted"
    )
    trusted.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
        f"`{catalog}`.`{schema}`.trust_scores"
    )

    findings_df = trusted.select("facility_id", "name", "state", "district", "pin",
                                 F.explode_outer("validator_findings").alias("finding")) \
        .filter(F.col("finding").isNotNull()) \
        .select("facility_id", "name", "state", "district", "pin",
                "finding.rule_id", "finding.capability", "finding.severity", "finding.message")
    findings_df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
        f"`{catalog}`.`{schema}`.validator_findings"
    )

    mlflow.log_metric("facilities_processed", trusted.count())
    mlflow.log_metric("validator_findings", findings_df.count())
    mlflow.log_metric(
        "high_severity_findings",
        findings_df.filter(F.col("severity") == "high").count(),
    )

display(spark.table(f"`{catalog}`.`{schema}`.trust_scores").orderBy(F.desc("trust_score")).limit(25))

# COMMAND ----------

display(spark.table(f"`{catalog}`.`{schema}`.validator_findings").orderBy(F.desc("severity")).limit(50))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Medical deserts with Wilson 95% confidence intervals
# MAGIC
# MAGIC `gap_ratio` = fraction of facilities lacking a verified `yes` for a capability.
# MAGIC We attach a Wilson 95% confidence interval so NGO planners can distinguish
# MAGIC truly under-served regions from regions whose data is just sparse.

# COMMAND ----------

Z = 1.96
WILSON_DENOM = lambda n: (1.0 + (Z * Z) / n)
WILSON_CENTRE = lambda p, n: (p + (Z * Z) / (2 * n)) / WILSON_DENOM(n)
WILSON_HALF = lambda p, n: (Z * F.sqrt(p * (1 - p) / n + (Z * Z) / (4 * n * n))) / WILSON_DENOM(n)


def add_wilson_ci(df, ratio_col: str = "gap_ratio", count_col: str = "missing_or_uncertain", total_col: str = "total"):
    n = F.col(total_col).cast("double")
    p = F.col(count_col).cast("double") / F.when(n > 0, n).otherwise(F.lit(1.0))
    centre = (p + (Z * Z) / (2 * n)) / (1 + (Z * Z) / n)
    half = (Z * F.sqrt(p * (1 - p) / n + (Z * Z) / (4 * n * n))) / (1 + (Z * Z) / n)
    return df.withColumn("wilson_lower", F.greatest(F.lit(0.0), centre - half)) \
             .withColumn("wilson_upper", F.least(F.lit(1.0), centre + half))


trusted = spark.table(f"`{catalog}`.`{schema}`.trust_scores")
state_gaps = None
pin_gaps = None
for cap in CAPABILITY_NAMES:
    by_state = trusted.groupBy("state").agg(
        F.count("*").alias("total"),
        F.sum(F.when(F.col(cap) != "yes", 1).otherwise(0)).alias("missing_or_uncertain"),
    ).withColumn("capability", F.lit(cap)).withColumn(
        "gap_ratio", F.col("missing_or_uncertain") / F.col("total")
    )
    by_state = add_wilson_ci(by_state)
    state_gaps = by_state if state_gaps is None else state_gaps.unionByName(by_state)

    by_pin = trusted.groupBy("pin", "state").agg(
        F.count("*").alias("total"),
        F.sum(F.when(F.col(cap) != "yes", 1).otherwise(0)).alias("missing_or_uncertain"),
        F.avg("latitude").alias("centroid_lat"),
        F.avg("longitude").alias("centroid_lng"),
    ).withColumn("capability", F.lit(cap)).withColumn(
        "risk", F.col("missing_or_uncertain") / F.col("total")
    )
    by_pin = add_wilson_ci(by_pin, ratio_col="risk")
    pin_gaps = by_pin if pin_gaps is None else pin_gaps.unionByName(by_pin)

state_gaps.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.medical_deserts_by_state"
)
pin_gaps.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.medical_deserts_by_pin"
)

display(spark.table(f"`{catalog}`.`{schema}`.medical_deserts_by_state").orderBy(F.desc("gap_ratio")).limit(60))
