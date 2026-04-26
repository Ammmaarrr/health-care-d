# Databricks notebook source
# MAGIC %md
# MAGIC # 06 - Genie Space Setup Helper
# MAGIC
# MAGIC Genie is interactive — there is no public API to programmatically
# MAGIC create a Genie space yet — so this notebook just verifies the
# MAGIC underlying Delta tables exist, prints a checklist, and registers
# MAGIC the prompt pack as an MLflow artifact for traceability.
# MAGIC
# MAGIC See `docs/GENIE_PROMPTS.md` for the actual setup walkthrough and
# MAGIC the seven canned demo prompts.

# COMMAND ----------

import mlflow

dbutils.widgets.text("catalog", "workspace", "Unity Catalog catalog")
dbutils.widgets.text("schema", "healthmap_agent", "Unity Catalog schema")
dbutils.widgets.text("experiment_name", "/Shared/healthmap-agent", "MLflow experiment")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
experiment_name = dbutils.widgets.get("experiment_name")

mlflow.set_tracking_uri("databricks")
mlflow.set_registry_uri("databricks")
mlflow.set_experiment(experiment_name)

REQUIRED_TABLES = [
    "facilities_clean",
    "capabilities_extracted",
    "trust_scores",
    "validator_findings",
    "medical_deserts_by_state",
    "medical_deserts_by_pin",
    "crisis_zones_top_pin",
]
OPTIONAL_TABLES = ["capabilities_extracted_llm"]

# COMMAND ----------

print("Tables required for the Genie space:\n")
status: dict[str, bool] = {}
for tbl in REQUIRED_TABLES + OPTIONAL_TABLES:
    name = f"{catalog}.{schema}.{tbl}"
    try:
        cnt = spark.table(name).count()
        ok = True
        print(f"  [OK]    {name}  ({cnt:,} rows)")
    except Exception as e:
        ok = False
        marker = "WARN" if tbl in OPTIONAL_TABLES else "MISS"
        print(f"  [{marker}]  {name}  -> {e}")
    status[tbl] = ok

missing_required = [t for t in REQUIRED_TABLES if not status.get(t)]
if missing_required:
    print(f"\nMissing required tables: {missing_required}.")
    print("Run notebooks 00, 01, 02, 05 first.")
else:
    print("\nAll required tables present. You can now create the Genie space:")
    print("  Databricks left nav -> Genie -> New Genie space")
    print(f"  -> add tables from {catalog}.{schema}")
    print("  -> paste the instructions block from docs/GENIE_PROMPTS.md")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Register the prompt pack with MLflow for traceability

# COMMAND ----------

prompt_pack_text = """\
GENIE PROMPT PACK — see docs/GENIE_PROMPTS.md in the repo.

3.1 Multi-attribute (rural Bihar surgery + part-time doctors)
3.2 Specialised deserts (oncology by state, with Wilson CIs)
3.3 Truth-gap audit (surgery without anesthesiologist)
3.4 Crisis hotspot PINs (worst ICU deserts)
3.5 Regex vs LLM extractor disagreement
3.6 Validator HIGH findings by state
3.7 Confidence-aware ranking (wilson_lower > 0.5)
"""

with mlflow.start_run(run_name="genie_prompt_pack"):
    mlflow.log_param("catalog", catalog)
    mlflow.log_param("schema", schema)
    mlflow.log_dict(
        {"required_tables": REQUIRED_TABLES, "optional_tables": OPTIONAL_TABLES, "status": status},
        "genie_table_check.json",
    )
    mlflow.log_text(prompt_pack_text, "genie_prompt_pack.txt")
print("Prompt pack registered. See MLflow run.")
