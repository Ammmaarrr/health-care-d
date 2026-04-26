# Databricks notebook source
# MAGIC %md
# MAGIC # 01 - Ingest Excel To Delta
# MAGIC
# MAGIC Converts the Virtue Foundation Excel file into governed Delta tables:
# MAGIC
# MAGIC - `facilities_raw`
# MAGIC - `facilities_clean`
# MAGIC
# MAGIC This mirrors `backend.pipeline.load.canonicalize`, but stays self-contained so
# MAGIC it can run in a Databricks notebook without packaging the repo first.

# COMMAND ----------

# MAGIC %pip install openpyxl

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import ast
from pathlib import Path

import pandas as pd

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

# COMMAND ----------

URBAN_CITIES = {
    "mumbai", "delhi", "new delhi", "bangalore", "bengaluru", "hyderabad",
    "chennai", "kolkata", "pune", "ahmedabad", "surat", "jaipur", "lucknow",
    "kanpur", "nagpur", "visakhapatnam", "indore", "thane", "bhopal",
    "patna", "vadodara", "ghaziabad", "ludhiana", "coimbatore", "agra",
    "madurai", "nashik", "faridabad", "meerut", "rajkot", "kalyan", "vasai",
    "vijayawada", "jabalpur", "mysore", "mysuru", "gwalior", "aurangabad",
    "ranchi", "howrah", "jodhpur", "raipur", "kota", "guwahati",
    "chandigarh", "dehradun", "noida", "gurgaon", "gurugram", "amritsar",
    "allahabad", "prayagraj", "varanasi", "srinagar", "navi mumbai",
    "ulhasnagar", "tiruchirappalli", "trichy", "salem", "warangal", "kochi",
    "cochin", "thiruvananthapuram", "trivandrum", "kozhikode", "calicut",
    "thrissur",
}


def format_list_field(val: object, label: str) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    if not s or s.lower() == "nan" or s in ("[]", "['']", "[\"\"]"):
        return ""
    try:
        parsed = ast.literal_eval(s)
        if isinstance(parsed, list):
            items = [str(x).strip() for x in parsed if str(x).strip()]
            return f"{label}: " + "; ".join(items) + "." if items else ""
    except (ValueError, SyntaxError):
        pass
    return f"{label}: {s}."


def build_notes(row: pd.Series) -> str:
    parts = []
    desc = str(row.get("description") or "").strip()
    if desc and desc.lower() != "nan":
        parts.append(f"Description: {desc}")
    parts.append(format_list_field(row.get("specialties"), "Specialties"))
    parts.append(format_list_field(row.get("procedure"), "Procedures"))
    parts.append(format_list_field(row.get("equipment"), "Equipment"))
    parts.append(format_list_field(row.get("capability"), "Capabilities listed"))
    for source, label in (("facilityTypeId", "Facility type"), ("operatorTypeId", "Operator type")):
        value = row.get(source)
        if value and str(value).strip().lower() != "nan":
            parts.append(f"{label}: {value}.")
    return " ".join(p for p in parts if p)


def is_rural(city: object) -> bool | None:
    if city is None or (isinstance(city, float) and pd.isna(city)):
        return None
    return str(city).strip().lower() not in URBAN_CITIES


def normalize_phone_token(s: str) -> str | None:
    s = s.strip()
    if not s:
        return None
    if s.startswith("+"):
        return s
    digits = "".join(c for c in s if c.isdigit())
    if len(digits) == 10:
        return "+91" + digits
    if len(digits) >= 10:
        return "+" + digits
    return None


def first_from_phone_numbers(val: object) -> str | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return None
    try:
        parsed = ast.literal_eval(s)
        if isinstance(parsed, list) and parsed:
            return normalize_phone_token(str(parsed[0]))
    except (ValueError, SyntaxError):
        pass
    return normalize_phone_token(s)


def clean_official_phone(val: object) -> str | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        digits = str(int(float(val)))
    except (ValueError, TypeError):
        return None
    if len(digits) < 10:
        return None
    if digits.startswith("91") and len(digits) >= 12:
        return "+" + digits
    if len(digits) == 10:
        return "+91" + digits
    return "+" + digits


def row_phone(row: pd.Series) -> str | None:
    return clean_official_phone(row.get("officialPhone")) or first_from_phone_numbers(row.get("phone_numbers"))


def clean_email(val: object) -> str | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    return s if s and s.lower() != "nan" and "@" in s else None


def canonicalize(raw: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    out["facility_id"] = [f"vf-{i:05d}" for i in range(len(raw))]
    out["name"] = raw["name"].astype(str).str.strip()
    out["state"] = raw["address_stateOrRegion"].astype(str).str.strip()
    out["district"] = raw["address_city"].astype(str).str.strip()
    out["pin"] = raw["address_zipOrPostcode"].astype(str).str.strip().replace({"nan": None})
    out["rural"] = raw["address_city"].apply(is_rural)
    out["latitude"] = pd.to_numeric(raw["latitude"], errors="coerce")
    out["longitude"] = pd.to_numeric(raw["longitude"], errors="coerce")
    out["facility_type"] = raw["facilityTypeId"].astype(str).str.strip().replace({"nan": None})
    out["phone"] = raw.apply(row_phone, axis=1)
    out["email"] = raw["email"].map(clean_email)
    out["notes"] = raw.apply(build_notes, axis=1).str.replace(r"\s+", " ", regex=True).str.strip()
    return out

# COMMAND ----------

raw = pd.read_excel(dataset_path)
clean = canonicalize(raw)

spark.createDataFrame(raw.astype(str)).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.facilities_raw"
)
spark.createDataFrame(clean).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.facilities_clean"
)

print(f"Wrote {len(raw):,} raw rows and {len(clean):,} clean rows.")
display(spark.table(f"`{catalog}`.`{schema}`.facilities_clean").limit(20))
