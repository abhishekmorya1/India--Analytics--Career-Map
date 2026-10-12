"""
Phase 5 prep - export two clean tables for Power BI.
Input : db/analytics_jobs.db
Output: dashboard/data/jobs.csv         one row per analytics posting (4,508)
        dashboard/data/job_skills.csv   one row per (posting, skill), common skills only

Usage (project root):  python python/export_for_powerbi.py [db_path]
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

DB = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("db/analytics_jobs.db")
OUT = Path("dashboard/data")
OUT.mkdir(parents=True, exist_ok=True)

ROLE_ORDER = ["BI / MIS / Reporting", "Data Analyst", "Business Analyst", "Data Engineer", "Data Scientist / ML"]
ROLE_SHORT = {"BI / MIS / Reporting": "BI / MIS", "Data Analyst": "Data Analyst",
              "Business Analyst": "Business Analyst", "Data Engineer": "Data Engineer",
              "Data Scientist / ML": "Data Scientist / ML"}
BAND_ORDER = {"0-2": 1, "3-5": 2, "6-8": 3, "9-12": 4, "13+": 5, "Unknown": 6}
CORE = ["sql", "python", "power bi", "tableau", "excel", "aws", "azure", "spark", "machine learning", "snowflake"]
MIN_SKILL_POSTINGS = 20

con = sqlite3.connect(DB)
jobs = pd.read_sql("SELECT * FROM jobs", con)
skills = pd.read_sql("SELECT job_id, skill, skill_category FROM job_skills", con)

# ---- jobs ------------------------------------------------------------------
jobs["role_short"] = jobs["role"].map(ROLE_SHORT)
jobs["role_order"] = jobs["role"].map({r: i + 1 for i, r in enumerate(ROLE_ORDER)})
jobs["exp_band_order"] = jobs["exp_band"].map(BAND_ORDER)
# blank unless the salary is usable -> Power BI MEDIAN()/COUNT() then ignore the rest automatically
jobs["salary_lpa_ok"] = jobs["salary_lpa"].where(jobs["salary_flag"] == "ok")
company = jobs["company_name"].fillna("Unknown")
jobs["company_clean"] = company.where(~company.str.lower().str.startswith("purview"), "Purview (all entities)")
vol = jobs["company_clean"].value_counts()
jobs["high_volume_poster"] = jobs["company_clean"].map(vol >= 50).map({True: "Yes", False: "No"})

cols = ["job_id", "title", "role", "role_short", "role_order", "company_clean", "high_volume_poster",
        "city", "metro_group", "work_mode_hint", "exp_min", "exp_band", "exp_band_order",
        "salary_lpa_ok", "skills_count", "rating", "reviews_count"]
jobs[cols].to_csv(OUT / "jobs.csv", index=False)

# ---- skills ----------------------------------------------------------------
sk = skills[skills["skill_category"] != "Other"].copy()          # drop the long tail of vague tags
sk = sk[sk["job_id"].isin(jobs["job_id"])].drop_duplicates(["job_id", "skill"])
n = sk.groupby("skill")["job_id"].nunique()
sk = sk[sk["skill"].isin(n[n >= MIN_SKILL_POSTINGS].index)]
sk["is_core"] = sk["skill"].isin(CORE).map({True: "Yes", False: "No"})
sk.to_csv(OUT / "job_skills.csv", index=False)

print(f"jobs.csv: {len(jobs):,} rows, {int(jobs['salary_lpa_ok'].notna().sum()):,} with usable salary")
print(f"job_skills.csv: {len(sk):,} rows, {sk['skill'].nunique()} distinct skills (each in >= {MIN_SKILL_POSTINGS} postings)")
print(f"high-volume posters (>= 50 postings): {(vol >= 50).sum()} companies")
