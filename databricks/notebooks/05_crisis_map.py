# Databricks notebook source
# MAGIC %md
# MAGIC # 05 - Dynamic Crisis Map (Stretch Goal #3)
# MAGIC
# MAGIC Builds the judge-facing dashboard tables and renders maps directly in
# MAGIC Databricks for the highest-risk medical deserts:
# MAGIC
# MAGIC - `crisis_zones_top_pin`        top 200 highest-risk PIN x capability cells
# MAGIC - Map view per high-acuity capability (ICU, surgery, oncology, dialysis,
# MAGIC   neonatal, trauma)

# COMMAND ----------

from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "workspace", "Unity Catalog catalog")
dbutils.widgets.text("schema", "healthmap_agent", "Unity Catalog schema")
dbutils.widgets.text("min_total", "5", "Minimum facilities per PIN before risk is reported")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
min_total = int(dbutils.widgets.get("min_total"))

spark.sql(f"USE `{catalog}`.`{schema}`")

# COMMAND ----------

deserts = spark.table(f"`{catalog}`.`{schema}`.medical_deserts_by_pin") \
    .filter(F.col("total") >= F.lit(min_total)) \
    .filter(F.col("centroid_lat").isNotNull() & F.col("centroid_lng").isNotNull())

high_acuity = ["has_icu", "has_emergency", "has_surgery", "has_oncology",
               "has_dialysis", "has_neonatal", "has_trauma"]

top_zones = deserts.filter(F.col("capability").isin(high_acuity)) \
    .orderBy(F.desc("risk"), F.desc("total")) \
    .limit(200)

top_zones.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.crisis_zones_top_pin"
)

display(top_zones)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Map view - drill down per capability
# MAGIC
# MAGIC Click each capability cell, switch the cell visualization to **Map** in
# MAGIC Databricks (lat/lng centroids), and use `risk` as the colour scale.

# COMMAND ----------

display(deserts.filter(F.col("capability") == "has_icu").orderBy(F.desc("risk")).limit(500))

# COMMAND ----------

display(deserts.filter(F.col("capability") == "has_surgery").orderBy(F.desc("risk")).limit(500))

# COMMAND ----------

display(deserts.filter(F.col("capability") == "has_oncology").orderBy(F.desc("risk")).limit(500))

# COMMAND ----------

display(deserts.filter(F.col("capability") == "has_dialysis").orderBy(F.desc("risk")).limit(500))

# COMMAND ----------

display(deserts.filter(F.col("capability") == "has_neonatal").orderBy(F.desc("risk")).limit(500))

# COMMAND ----------

display(deserts.filter(F.col("capability") == "has_trauma").orderBy(F.desc("risk")).limit(500))
