# Databricks notebook source
# MAGIC %md
# MAGIC # 04 - Mosaic AI Vector Search (Programmatic)
# MAGIC
# MAGIC Creates the Mosaic AI Vector Search endpoint + Delta-Sync index that the
# MAGIC FastAPI `retrieval_agent` and the Databricks query notebook can both
# MAGIC point at. Uses the official `databricks-vectorsearch` Python SDK.
# MAGIC
# MAGIC Requires Vector Search entitlement on the workspace. Free Edition
# MAGIC typically allows one endpoint. If your workspace does not expose
# MAGIC Vector Search, run `04_vector_search_sql_template.sql` and create the
# MAGIC index from the UI, or stay with the FAISS local retriever.

# COMMAND ----------

# MAGIC %pip install -U databricks-vectorsearch

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import time
from databricks.vector_search.client import VectorSearchClient

dbutils.widgets.text("catalog", "workspace", "Unity Catalog catalog")
dbutils.widgets.text("schema", "healthmap_agent", "Unity Catalog schema")
dbutils.widgets.text("source_table", "facilities_clean", "Source Delta table")
dbutils.widgets.text("endpoint_name", "healthmap-vector-search", "VS endpoint name")
dbutils.widgets.text("index_suffix", "_vs_index", "Index name suffix")
dbutils.widgets.text(
    "embedding_endpoint",
    "databricks-bge-large-en",
    "FM endpoint serving embeddings (Agent Bricks)",
)

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
source_table = dbutils.widgets.get("source_table")
endpoint_name = dbutils.widgets.get("endpoint_name")
index_suffix = dbutils.widgets.get("index_suffix")
embedding_endpoint = dbutils.widgets.get("embedding_endpoint")

source_full = f"{catalog}.{schema}.{source_table}"
index_full = f"{catalog}.{schema}.{source_table}{index_suffix}"

print(f"Source table: {source_full}")
print(f"Index name:   {index_full}")
print(f"Endpoint:     {endpoint_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Enable Change Data Feed on the source Delta table
# MAGIC Required for Delta-Sync indexes.

# COMMAND ----------

spark.sql(
    f"ALTER TABLE {source_full} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Create the Vector Search endpoint (idempotent)

# COMMAND ----------

client = VectorSearchClient()

existing = {e["name"] for e in client.list_endpoints().get("endpoints", [])}
if endpoint_name not in existing:
    client.create_endpoint(name=endpoint_name, endpoint_type="STANDARD")
    print(f"Created endpoint {endpoint_name}; waiting for it to come online...")
    for _ in range(40):
        ep = client.get_endpoint(endpoint_name)
        if ep.get("endpoint_status", {}).get("state") == "ONLINE":
            break
        time.sleep(15)
else:
    print(f"Endpoint {endpoint_name} already exists.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Create the Delta-Sync index
# MAGIC
# MAGIC We let Databricks compute embeddings via the Agent Bricks BGE
# MAGIC endpoint. Primary key is `facility_id`, embedded text is `notes`.

# COMMAND ----------

existing_indexes = {
    i["name"]
    for i in (client.list_indexes(name=endpoint_name) or {}).get("vector_indexes", [])
}
if index_full not in existing_indexes:
    client.create_delta_sync_index(
        endpoint_name=endpoint_name,
        index_name=index_full,
        source_table_name=source_full,
        pipeline_type="TRIGGERED",  # explicit sync; switch to "CONTINUOUS" if you have budget
        primary_key="facility_id",
        embedding_source_column="notes",
        embedding_model_endpoint_name=embedding_endpoint,
    )
    print(f"Created index {index_full}")
else:
    print(f"Index {index_full} already exists.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Trigger a sync and wait for the index to be queryable

# COMMAND ----------

idx = client.get_index(endpoint_name=endpoint_name, index_name=index_full)
idx.sync()

for _ in range(40):
    desc = idx.describe()
    state = (desc or {}).get("status", {}).get("ready", False)
    if state:
        break
    time.sleep(15)

print("Index ready:", desc.get("status"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Smoke test — multi-attribute query
# MAGIC The same query the brief calls out, but routed through Mosaic AI VS.

# COMMAND ----------

response = idx.similarity_search(
    query_text="emergency surgery in rural Bihar with part-time doctors",
    columns=["facility_id", "name", "state", "district", "pin", "rural", "facility_type"],
    num_results=10,
    filters={"state": "Bihar", "rural": True},
)
display(spark.createDataFrame(response.get("result", {}).get("data_array", []),
                              schema=[c["name"] for c in response.get("manifest", {}).get("columns", [])]))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Connect the FastAPI backend
# MAGIC
# MAGIC In your `.env` (or HF Space secrets) set:
# MAGIC
# MAGIC ```
# MAGIC VECTOR_SEARCH_ENDPOINT=healthmap-vector-search
# MAGIC VECTOR_SEARCH_INDEX=workspace.healthmap_agent.facilities_clean_vs_index
# MAGIC DATABRICKS_HOST=https://<workspace>.cloud.databricks.com
# MAGIC DATABRICKS_TOKEN=<PAT or OAuth token>
# MAGIC ```
# MAGIC
# MAGIC `backend/agents/retrieval_agent.py` will detect those env vars and
# MAGIC route every `/query` call through Mosaic AI Vector Search instead of
# MAGIC the local FAISS index. If the SDK call fails it falls back to FAISS
# MAGIC automatically so the API never goes down.
