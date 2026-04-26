# Databricks notebook source
# MAGIC %md
# MAGIC # 02b - LLM Extraction With Databricks Foundation Models (Agent Bricks)
# MAGIC
# MAGIC Alternative to `02_extract_trust_and_deserts.py` for the LLM-driven path.
# MAGIC Where notebook 02 uses regex (zero cost, lower recall), this notebook
# MAGIC uses **Databricks Foundation Model serving** — the partner-recommended
# MAGIC "Agent Bricks" stack — to extract capability tristates + verbatim
# MAGIC evidence sentences from each hospital's free-form notes.
# MAGIC
# MAGIC Output table: `capabilities_extracted_llm` (same schema as
# MAGIC `capabilities_extracted` so downstream notebooks 02 (trust/deserts)
# MAGIC and 03 (query demo) work unchanged when you point them at this table).
# MAGIC
# MAGIC Default endpoint: `databricks-meta-llama-3-1-70b-instruct`
# MAGIC (set the widget to swap it out, e.g. for a smaller / cheaper model).

# COMMAND ----------

# MAGIC %pip install -U mlflow databricks-sdk

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import json
import re
from typing import Iterator

import mlflow
import pandas as pd
from mlflow.deployments import get_deploy_client
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType

dbutils.widgets.text("catalog", "workspace", "Unity Catalog catalog")
dbutils.widgets.text("schema", "healthmap_agent", "Unity Catalog schema")
dbutils.widgets.text("experiment_name", "/Shared/healthmap-agent", "MLflow experiment")
dbutils.widgets.text(
    "endpoint",
    "databricks-meta-llama-3-1-70b-instruct",
    "Foundation Model serving endpoint name",
)
dbutils.widgets.text("max_rows", "0", "0 = process every row in facilities_clean")
dbutils.widgets.text("workers", "8", "Concurrent requests to the FM endpoint")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
experiment_name = dbutils.widgets.get("experiment_name")
endpoint = dbutils.widgets.get("endpoint")
max_rows = int(dbutils.widgets.get("max_rows"))
workers = max(1, int(dbutils.widgets.get("workers")))

spark.sql(f"USE `{catalog}`.`{schema}`")
mlflow.set_tracking_uri("databricks")
mlflow.set_registry_uri("databricks")
mlflow.set_experiment(experiment_name)

print(f"Endpoint: {endpoint}")
print(f"Workers:  {workers}")
print(f"Max rows: {'ALL' if max_rows == 0 else max_rows}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Prompt + JSON parser
# MAGIC
# MAGIC Same conservative extraction prompt as the local FastAPI path
# MAGIC (`backend/core/prompts.py::EXTRACT_PROMPT`). 11 capability tristates
# MAGIC + doctor type + verbatim evidence sentences.

# COMMAND ----------

EXTRACT_PROMPT = """\
You extract structured medical capabilities from a hospital's free-form notes.

Be STRICT and CONSERVATIVE:
- If a capability is not explicitly mentioned -> "uncertain".
- Do NOT infer. If the notes say "general medicine", do NOT mark surgery yes.
- "ICU available" / "intensive care unit" -> has_icu = "yes".
- "no ICU" / "ICU under construction" / "ICU planned" -> has_icu = "no".
- The same yes/no/uncertain rules apply to every capability below.

Capability vocabulary (use exactly these field names):
has_icu, has_emergency, has_surgery, has_anesthesiologist, has_oxygen,
has_oncology, has_dialysis, has_neonatal, has_trauma, has_lab, has_imaging,
doctor_type ("full-time" | "part-time" | "unknown").

Output ONLY valid JSON with shape:
{
  "has_icu": "yes"|"no"|"uncertain",
  "has_emergency": "yes"|"no"|"uncertain",
  "has_surgery": "yes"|"no"|"uncertain",
  "has_anesthesiologist": "yes"|"no"|"uncertain",
  "has_oxygen": "yes"|"no"|"uncertain",
  "has_oncology": "yes"|"no"|"uncertain",
  "has_dialysis": "yes"|"no"|"uncertain",
  "has_neonatal": "yes"|"no"|"uncertain",
  "has_trauma": "yes"|"no"|"uncertain",
  "has_lab": "yes"|"no"|"uncertain",
  "has_imaging": "yes"|"no"|"uncertain",
  "doctor_type": "full-time"|"part-time"|"unknown",
  "evidence": {
    "icu": string, "emergency": string, "surgery": string,
    "anesthesiologist": string, "oxygen": string, "oncology": string,
    "dialysis": string, "neonatal": string, "trauma": string,
    "lab": string, "imaging": string, "doctor_type": string
  }
}

Each evidence value MUST be a verbatim sentence/phrase copied from the notes
that supports your decision, or an empty string if "uncertain"/"unknown".

NOTES:
\"\"\"
{notes}
\"\"\"

JSON:"""

CAPABILITY_NAMES = [
    "has_icu", "has_emergency", "has_surgery", "has_anesthesiologist",
    "has_oxygen", "has_oncology", "has_dialysis", "has_neonatal",
    "has_trauma", "has_lab", "has_imaging",
]
EVIDENCE_KEYS = [c.removeprefix("has_") for c in CAPABILITY_NAMES] + ["doctor_type"]


def _parse_json_loose(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    cleaned = text.lstrip("```json").lstrip("```").rstrip("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return {}
    return {}


def _normalize_tristate(v):
    if not isinstance(v, str):
        return "uncertain"
    s = v.strip().lower()
    return s if s in {"yes", "no", "uncertain"} else "uncertain"


def _normalize_doctor(v):
    if not isinstance(v, str):
        return "unknown"
    s = v.strip().lower()
    return s if s in {"full-time", "part-time", "unknown"} else "unknown"


# COMMAND ----------

# MAGIC %md
# MAGIC ## Read facilities and dispatch to the FM endpoint
# MAGIC
# MAGIC We use a `pandas_udf` so each Spark partition holds a single
# MAGIC connection-pooled `mlflow.deployments` client and dispatches
# MAGIC requests in parallel. The Free Edition serverless cluster handles
# MAGIC the rate limit for us; tune `workers` widget down if you hit 429s.

# COMMAND ----------

result_schema = StructType(
    [StructField(c, StringType()) for c in CAPABILITY_NAMES]
    + [StructField("doctor_type", StringType())]
    + [StructField(f"ev_{k}", StringType()) for k in EVIDENCE_KEYS]
)


def extract_pandas_udf(endpoint_name: str):
    @F.pandas_udf(returnType=result_schema)
    def _udf(notes_series: Iterator[pd.Series]) -> Iterator[pd.DataFrame]:
        client = get_deploy_client("databricks")
        for chunk in notes_series:
            rows = []
            for raw_notes in chunk:
                notes = (raw_notes or "")[:6000]
                if not notes.strip():
                    rows.append(_blank_row())
                    continue
                try:
                    response = client.predict(
                        endpoint=endpoint_name,
                        inputs={
                            "messages": [
                                {"role": "system", "content": "Return only valid JSON. No prose."},
                                {"role": "user", "content": EXTRACT_PROMPT.replace("{notes}", notes)},
                            ],
                            "temperature": 0.0,
                            "max_tokens": 1400,
                        },
                    )
                    content = (response.get("choices") or [{}])[0].get("message", {}).get("content", "")
                except Exception:
                    rows.append(_blank_row())
                    continue
                rows.append(_row_from_json(_parse_json_loose(content)))
            yield pd.DataFrame(rows)
    return _udf


def _blank_row() -> dict:
    out = {c: "uncertain" for c in CAPABILITY_NAMES}
    out["doctor_type"] = "unknown"
    for k in EVIDENCE_KEYS:
        out[f"ev_{k}"] = ""
    return out


def _row_from_json(parsed: dict) -> dict:
    if not isinstance(parsed, dict):
        return _blank_row()
    out: dict = {c: _normalize_tristate(parsed.get(c)) for c in CAPABILITY_NAMES}
    out["doctor_type"] = _normalize_doctor(parsed.get("doctor_type"))
    evidence = parsed.get("evidence") or {}
    if not isinstance(evidence, dict):
        evidence = {}
    for k in EVIDENCE_KEYS:
        v = evidence.get(k)
        out[f"ev_{k}"] = v if isinstance(v, str) else ""
    return out

# COMMAND ----------

with mlflow.start_run(run_name="agent_bricks_llm_extraction"):
    mlflow.log_param("endpoint", endpoint)
    mlflow.log_param("max_rows", max_rows)
    mlflow.log_param("workers", workers)

    facilities = spark.table(f"`{catalog}`.`{schema}`.facilities_clean")
    if max_rows > 0:
        facilities = facilities.limit(max_rows)

    facilities = facilities.repartition(workers)

    extracted = facilities.withColumn(
        "extracted", extract_pandas_udf(endpoint)(F.col("notes"))
    ).select(
        "facility_id", "name", "state", "district", "pin", "rural",
        "latitude", "longitude", "facility_type", "phone", "email", "notes",
        "extracted.*",
    )

    extracted.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
        f"`{catalog}`.`{schema}`.capabilities_extracted_llm"
    )
    mlflow.log_metric("rows_extracted", spark.table(f"`{catalog}`.`{schema}`.capabilities_extracted_llm").count())

display(spark.table(f"`{catalog}`.`{schema}`.capabilities_extracted_llm").limit(20))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next steps
# MAGIC
# MAGIC - Re-run `02_extract_trust_and_deserts.py` pointed at
# MAGIC   `capabilities_extracted_llm` instead of the regex output to get
# MAGIC   trust scores + medical desert tables on top of LLM extractions.
# MAGIC - Compare regex vs LLM extractions in a Databricks SQL dashboard
# MAGIC   for the discovery-and-verification consistency check.
