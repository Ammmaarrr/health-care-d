# Databricks notebook source
# MAGIC %md
# MAGIC # 00 - Setup
# MAGIC
# MAGIC Run this first in Databricks. It creates the catalog/schema objects used by
# MAGIC the hackathon notebooks and records the intended dataset location.

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace", "Unity Catalog catalog")
dbutils.widgets.text("schema", "healthmap_agent", "Unity Catalog schema")
dbutils.widgets.text(
    "dataset_path",
    "/Workspace/Users/m.ammar.63.64@gmail.com/healthmap-agent/VF_Hackathon_Dataset_India_Large.xlsx",
    "Path to VF_Hackathon_Dataset_India_Large.xlsx",
)

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
dataset_path = dbutils.widgets.get("dataset_path")

spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema}`")
spark.sql(f"USE `{catalog}`.`{schema}`")

print(f"Using schema: {catalog}.{schema}")
print(f"Expected dataset path: {dataset_path}")

# COMMAND ----------

spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS `{catalog}`.`{schema}`.run_config (
      key STRING,
      value STRING,
      updated_at TIMESTAMP
    )
    USING DELTA
    """
)

spark.sql(f"DELETE FROM `{catalog}`.`{schema}`.run_config WHERE key = 'dataset_path'")
spark.sql(
    f"""
    INSERT INTO `{catalog}`.`{schema}`.run_config
    VALUES ('dataset_path', '{dataset_path.replace("'", "''")}', current_timestamp())
    """
)

display(spark.table(f"`{catalog}`.`{schema}`.run_config"))
