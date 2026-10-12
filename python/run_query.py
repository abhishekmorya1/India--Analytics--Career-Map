"""
Run a query against db/analytics_jobs.db and print the result - no extra tools needed.

Usage (from the project root):
    python python/run_query.py                       -> list all query names in sql/queries.sql
    python python/run_query.py q03                   -> run the query whose name starts with q03
    python python/run_query.py q04b_salary_role_by_experience
    python python/run_query.py "SELECT role, COUNT(*) AS n FROM jobs GROUP BY role"   -> any SQL you type
"""
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd

DB = Path("db/analytics_jobs.db")
SQL_FILE = Path("sql/queries.sql")

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)
pd.set_option("display.max_rows", 100)

parts = re.split(r"^-- name:\s*(\S+)\s*$", SQL_FILE.read_text(encoding="utf-8"), flags=re.M)
queries = dict(zip(parts[1::2], parts[2::2]))

arg = sys.argv[1].strip() if len(sys.argv) > 1 else ""

if not arg:
    print("Available queries:")
    for name in queries:
        first = next((l[5:].strip() for l in queries[name].splitlines() if l.startswith("-- Q:")), "")
        print(f"  {name:42s} {first}")
    sys.exit()

if re.match(r"(?is)^\s*(select|with)\b", arg):
    sql = arg
else:
    hits = [n for n in queries if n.startswith(arg)]
    if len(hits) != 1:
        sys.exit(f"'{arg}' matches {len(hits)} queries. Run without arguments to see the list.")
    print(f"-- {hits[0]}")
    sql = queries[hits[0]]

con = sqlite3.connect(DB)
print(pd.read_sql_query(sql.strip().rstrip(";"), con).to_string(index=False))
