"""
Phase 3 - SQLite database + run all queries
Input : data/clean/analytics_jobs.csv, job_skills.csv, job_locations.csv, skills_dim.csv
        sql/queries.sql
Output: db/analytics_jobs.db
        sql/results/<query_name>.csv   (one file per query - use these in Power BI / notebook)

Usage:  python scripts/build_database.py [clean_dir] [sql_file] [db_path]
"""
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd

CLEAN = Path(sys.argv[1] if len(sys.argv) > 1 else "data/clean")
SQL_FILE = Path(sys.argv[2] if len(sys.argv) > 2 else "sql/queries.sql")
DB = Path(sys.argv[3] if len(sys.argv) > 3 else "db/analytics_jobs.db")
RESULTS = SQL_FILE.parent / "results"
DB.parent.mkdir(parents=True, exist_ok=True)
RESULTS.mkdir(parents=True, exist_ok=True)

if DB.exists():
    DB.unlink()  # rebuild from scratch so the script is reproducible
con = sqlite3.connect(DB)

# ---------------------------------------------------------------- load tables
jobs = pd.read_csv(CLEAN / "analytics_jobs.csv")
jobs = jobs[[
    "job_id", "title", "role", "company_name", "city", "metro_group", "n_locations",
    "multi_location", "work_mode_hint", "exp_min", "exp_max", "exp_band",
    "salary_min", "salary_max", "salary_mid", "salary_lpa", "salary_flag",
    "skills_count", "skills_capped", "rating", "reviews_count", "days_ago",
]]
skills = pd.read_csv(CLEAN / "job_skills.csv")
locs = pd.read_csv(CLEAN / "job_locations.csv")
locs = locs[locs["job_id"].isin(jobs["job_id"])]  # keep only analytics jobs

# Raw data spells the same region two ways ("Delhi NCR" and "Delhi / NCR") -> merge
METRO_FIX = {"Delhi / NCR": "Delhi NCR", "NCR": "Delhi NCR", "Delhi/NCR": "Delhi NCR"}
for frame in (jobs, locs):
    frame["metro_group"] = frame["metro_group"].replace(METRO_FIX)
    frame["metro_group"] = frame["metro_group"].fillna("Unknown")

jobs.to_sql("jobs", con, index=False)
skills.to_sql("job_skills", con, index=False)
locs.to_sql("job_locations", con, index=False)

con.executescript("""
CREATE UNIQUE INDEX idx_jobs_id        ON jobs(job_id);
CREATE INDEX idx_jobs_role             ON jobs(role);
CREATE INDEX idx_skills_job            ON job_skills(job_id);
CREATE INDEX idx_skills_skill          ON job_skills(skill);
CREATE INDEX idx_locs_job              ON job_locations(job_id);

-- Only postings with a usable, annualised salary (flag 'ok' = between 1 LPA and 1 Cr)
CREATE VIEW v_salary_jobs AS
SELECT * FROM jobs WHERE salary_flag = 'ok' AND salary_lpa IS NOT NULL;
""")
con.commit()

for t in ["jobs", "job_skills", "job_locations", "v_salary_jobs"]:
    n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"{t}: {n:,} rows")

# ---------------------------------------------------------------- run queries
text = SQL_FILE.read_text(encoding="utf-8")
blocks = re.split(r"^-- name:\s*(\S+)\s*$", text, flags=re.M)
# blocks = [preamble, name1, body1, name2, body2, ...]
failed = []
for name, body in zip(blocks[1::2], blocks[2::2]):
    try:
        df = pd.read_sql_query(body.strip().rstrip(";"), con)
        df.to_csv(RESULTS / f"{name}.csv", index=False)
        print(f"OK   {name}: {len(df)} rows")
    except Exception as e:
        failed.append(name)
        print(f"FAIL {name}: {e}")

con.close()
print(f"\nDatabase: {DB}   Results folder: {RESULTS}")
if failed:
    sys.exit(f"Failed queries: {failed}")
