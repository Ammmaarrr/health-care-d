# Databricks Runbook

This repo now has a Databricks-native path for the Databricks "Serving A Nation"
challenge. The goal is to show judges that the healthcare agent is backed by
Databricks tables, MLflow traces, and an optional Mosaic AI Vector Search index.

## What To Run

Import or sync the files in `databricks/notebooks/` into a Databricks workspace
and run them in order:

1. `00_setup.py`
2. `01_ingest_excel_to_delta.py`
3. **One of:**
   - `02_extract_trust_and_deserts.py` — regex extractor, $0 cost,
     produces `capabilities_extracted` + `trust_scores` +
     `medical_deserts_by_*` Delta tables.
   - `02b_extract_with_agent_bricks.py` — calls a Databricks Foundation
     Model serving endpoint (the brief's recommended Agent Bricks
     stack) for higher-recall extraction, output table
     `capabilities_extracted_llm`. After this you can re-run notebook 02
     after pointing it at the LLM table to refresh trust scores.
4. `03_query_demo_with_mlflow.py` — multi-attribute reasoning demo with
   `@mlflow.trace` spans (Stretch Goal #1).
5. `04_vector_search.py` — programmatic Mosaic AI Vector Search index
   creation (preferred). Falls back to `04_vector_search_sql_template.sql`
   if your workspace lacks Vector Search entitlement.
6. `05_crisis_map.py` — PIN-level deserts + map visualisation
   (Stretch Goal #3).
7. `06_genie_setup.py` — table-existence check + prompt-pack
   registration for the Genie Space (see `docs/GENIE_PROMPTS.md`).

## Dataset Location

Upload `VF_Hackathon_Dataset_India_Large.xlsx` to the same Databricks workspace
folder as the notebooks, then set the notebook widget `dataset_path` to that
file if it is not already set.

Recommended path:

```text
/Workspace/Users/m.ammar.63.64@gmail.com/healthmap-agent/VF_Hackathon_Dataset_India_Large.xlsx
```

If the `workspace` catalog is not writable in your Databricks account, use any
catalog/schema where you have `CREATE TABLE` permission and update the widgets.

## Tables Created

The notebooks create these Delta tables:

- `facilities_raw`
- `facilities_clean`
- `capabilities_extracted`
- `capabilities_extracted_llm` (only when notebook 02b ran)
- `trust_scores`
- `validator_findings`
- `medical_deserts_by_state`
- `medical_deserts_by_pin`
- `crisis_zones_top_pin` (after notebook 05)

These map directly to the challenge criteria:

- Discovery and verification: `capabilities_extracted` (regex) and
  `capabilities_extracted_llm` (Agent Bricks), `trust_scores`,
  `validator_findings`.
- Intelligent document parsing: `facilities_clean.notes` and evidence
  columns + the LLM extraction notebook.
- Social impact: `medical_deserts_by_state`, `medical_deserts_by_pin`
  (each with Wilson 95% CIs).
- Transparency: MLflow run artifacts from `03_query_demo_with_mlflow.py`
  + per-stage `@mlflow.trace` spans in `02_*` and `02b_*`.
- Genie: see `docs/GENIE_PROMPTS.md` for the natural-language demo
  prompts against the same Delta tables.

## Demo Query

Use this query in `03_query_demo_with_mlflow.py`:

```text
Find emergency surgery in rural Bihar with part-time doctors
```

Then show:

1. The ranked output table.
2. The evidence columns.
3. The `flags` column for trust gaps.
4. The MLflow experiment `/Shared/healthmap-agent`.

## Local CLI Commands

The local machine has Python 3.11 and the Databricks Python packages installed.
Once the Databricks CLI is visible in a fresh terminal, authenticate with:

```powershell
databricks auth login --host https://YOUR-WORKSPACE-URL
databricks current-user me
```

After auth, the notebooks can be imported with:

```powershell
databricks workspace mkdirs /Workspace/Users/$env:USERNAME/healthmap-agent
databricks workspace import-dir databricks/notebooks /Workspace/Users/$env:USERNAME/healthmap-agent --overwrite
```

Authentication cannot be completed by code alone because Databricks requires the
user's workspace URL and browser login.
