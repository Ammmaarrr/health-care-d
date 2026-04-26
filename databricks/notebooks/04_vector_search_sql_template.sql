-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 04 - Mosaic AI Vector Search Template
-- MAGIC
-- MAGIC This is the optional judge-facing Vector Search path. Run notebooks 00-02
-- MAGIC first so `facilities_clean` exists as a Delta table.
-- MAGIC
-- MAGIC Free Edition usually allows one Vector Search endpoint. If your workspace
-- MAGIC does not expose Vector Search, keep the FAISS/local retriever and demo the
-- MAGIC Delta + MLflow notebooks instead.

-- COMMAND ----------

-- Replace these names if you changed the widgets in the Python notebooks.
USE CATALOG workspace;
USE SCHEMA healthmap_agent;

-- COMMAND ----------

-- If your workspace has Mosaic AI Vector Search enabled, create a Delta Sync
-- index from `facilities_clean` in the Databricks UI:
--
-- 1. Left nav: Compute or Search -> Vector Search.
-- 2. Create endpoint: healthmap-vector-search.
-- 3. Create index from table: workspace.healthmap_agent.facilities_clean.
-- 4. Primary key: facility_id.
-- 5. Text column: notes.
-- 6. Sync columns: name, state, district, pin, rural, facility_type.
--
-- The exact SQL/API differs by workspace entitlement, so this file is kept as a
-- durable checklist rather than a brittle command.

-- COMMAND ----------

SELECT
  facility_id,
  name,
  state,
  district,
  pin,
  rural,
  substr(notes, 1, 500) AS notes_preview
FROM facilities_clean
LIMIT 20;
