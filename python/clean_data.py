"""
Phase 1 - Cleaning
Raw job-postings export (Sept 2025 snapshot, all roles) -> tidy tables.

Usage:
    python scripts/clean_data.py [raw_xlsx_path] [output_dir]

Outputs (in output_dir, default data/clean):
    jobs_clean.csv          one row per job posting (INR only, de-duplicated)
    job_locations.csv       one row per (job, city) - handles multi-city postings
    jobs_usd_excluded.csv   USD postings set aside (not comparable with INR)
    cleaning_log.md         what was changed and how many rows were affected
"""
import html
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path(sys.argv[1] if len(sys.argv) > 1 else "data/raw/indian-job-market-dataset-2025.xlsx")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "data/clean")
OUT.mkdir(parents=True, exist_ok=True)

log = []


def note(msg):
    print(msg)
    log.append(msg)


def ws(s):
    """Collapse whitespace; keep NaN as NaN."""
    return re.sub(r"\s+", " ", str(s)).strip() if pd.notna(s) else np.nan


# --------------------------------------------------------------------------
# 0. Load
# --------------------------------------------------------------------------
df = pd.read_excel(RAW)
note(f"Raw rows: {len(df):,}")

# --------------------------------------------------------------------------
# 1. Duplicates - same jobId appearing more than once; keep first occurrence
# --------------------------------------------------------------------------
n0 = len(df)
df = df.drop_duplicates("jobId", keep="first")
note(f"Duplicate jobId rows removed: {n0 - len(df):,}")

# --------------------------------------------------------------------------
# 2. Currency - keep INR only; USD rows saved separately
# --------------------------------------------------------------------------
usd = df[df.currency != "INR"]
df = df[df.currency == "INR"].copy()
usd.to_csv(OUT / "jobs_usd_excluded.csv", index=False)
note(f"Non-INR (USD) rows set aside: {len(usd):,}")

# --------------------------------------------------------------------------
# 3. Text fields
# --------------------------------------------------------------------------
df["title"] = df["title"].map(ws)
df["company_name"] = df["companyName"].map(ws)


def strip_html(s):
    if pd.isna(s):
        return np.nan
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>", " ", str(s))
    s = re.sub(r"<[^>]+>", " ", s)
    return ws(html.unescape(s))


df["description"] = df["jobDescription"].map(strip_html)

# --------------------------------------------------------------------------
# 4. Salary
#    - 0 in min/max means "Not disclosed" -> NULL
#    - "5,000/month" rows have no numeric min/max -> annualise (x12), flagged
#    - "Unpaid" -> NULL, basis = unpaid
#    - implausible values are FLAGGED, not deleted (filter on salary_flag = 'ok')
# --------------------------------------------------------------------------
sal = df["salary"].fillna("")
df["salary_min"] = df["minimumSalary"].where(df["minimumSalary"] > 0)
df["salary_max"] = df["maximumSalary"].where(df["maximumSalary"] > 0)
df["salary_basis"] = np.where(df["salary_min"].notna(), "annual", "none")

monthly = (
    sal.str.extract(r"^([\d,]+)\s*/\s*month", flags=re.I)[0]
    .str.replace(",", "", regex=False)
    .astype(float)
)
m = monthly.notna() & df["salary_min"].isna()
df.loc[m, "salary_min"] = monthly[m] * 12
df.loc[m, "salary_max"] = monthly[m] * 12
df.loc[m, "salary_basis"] = "monthly_x12"
df.loc[sal.eq("Unpaid"), "salary_basis"] = "unpaid"

df["salary_mid"] = (df["salary_min"] + df["salary_max"]) / 2
df["salary_lpa"] = (df["salary_mid"] / 1e5).round(2)  # lakhs per annum
df["has_variable_pay"] = sal.str.contains("Variable", case=False)

flag = pd.Series("ok", index=df.index)
flag[df["salary_mid"].isna()] = "none"
flag[df["salary_max"] < 100_000] = "suspect_low"      # < 1 LPA: likely monthly/stipend mislabelled
flag[df["salary_max"] > 10_000_000] = "suspect_high"  # > 1 Cr: outlier / possible entry error
df["salary_flag"] = flag
note(f"Salary disclosed (any): {df['salary_mid'].notna().sum():,}")
note(f"Salary usable (flag = ok): {(flag == 'ok').sum():,}  | "
     f"suspect_low: {(flag == 'suspect_low').sum():,}  | suspect_high: {(flag == 'suspect_high').sum():,}")
note(f"Monthly salaries annualised: {m.sum():,}")

# --------------------------------------------------------------------------
# 5. Experience - use numeric columns; bands keyed on minimum experience
#    13+ band is kept but has very few salary points (exclude from salary charts)
# --------------------------------------------------------------------------
df["exp_min"] = df["minimumExperience"]
df["exp_max"] = df["maximumExperience"]
df["exp_band"] = (
    pd.cut(df["exp_min"], [-0.1, 2, 5, 8, 12, 100], labels=["0-2", "3-5", "6-8", "9-12", "13+"])
    .astype(object)
    .fillna("Unknown")
)
note(f"Experience unknown: {(df['exp_band'] == 'Unknown').sum():,}")

# --------------------------------------------------------------------------
# 6. Location
#    - strip "Hybrid - " prefix and locality in brackets: "Kolkata(Chinar Park)" -> "Kolkata"
#    - one posting may list several cities -> job_locations table (exploded)
#    - city = first listed city; multi_location flags the ambiguity
#    - metro_group merges satellite cities (Gurugram/Noida -> Delhi NCR, etc.)
#    - work_mode_hint: ONLY what the location text says; no "onsite" label exists in the data
# --------------------------------------------------------------------------
ALIAS = {
    "Bangalore": "Bengaluru", "Gurgaon": "Gurugram", "Delhi": "New Delhi",
    "Bombay": "Mumbai", "Madras": "Chennai", "Calcutta": "Kolkata",
}
METRO = {}
for metro, cities in {
    "Bengaluru": ["Bengaluru", "Bangalore Rural"],
    "Delhi NCR": ["New Delhi", "Gurugram", "Noida", "Greater Noida", "Ghaziabad", "Faridabad"],
    "Mumbai MMR": ["Mumbai", "Navi Mumbai", "Thane", "Mumbai Suburban", "Kalyan", "Dombivli", "Vasai", "Bhiwandi"],
    "Pune": ["Pune", "Pimpri-Chinchwad"],
    "Hyderabad": ["Hyderabad", "Secunderabad"],
}.items():
    for c in cities:
        METRO[c] = metro


def split_locations(raw):
    x = re.sub(r"(?i)^hybrid\s*-\s*", "", str(raw))
    parts = [re.sub(r"\(.*?\)", "", p).strip() for p in x.split(",")]
    parts = [ALIAS.get(p, p) for p in parts if p]
    return list(dict.fromkeys(parts))  # de-duplicate, keep order


locs = df["location"].map(split_locations)
df["location_raw"] = df["location"].map(ws)
df["city"] = locs.map(lambda l: l[0] if l else np.nan)
df["metro_group"] = df["city"].map(lambda c: METRO.get(c, c))
df["n_locations"] = locs.map(len)
df["multi_location"] = df["n_locations"] > 1
low = df["location"].str.lower()
df["work_mode_hint"] = np.select(
    [low.str.startswith("hybrid"), low.str.contains("remote")],
    ["Hybrid", "Remote"],
    default="Not specified",
)
note(f"Distinct raw location strings: {df['location'].nunique():,} -> distinct primary cities: {df['city'].nunique():,}")
note(f"Multi-city postings: {df['multi_location'].sum():,} ({df['multi_location'].mean():.1%})")
note(f"Work-mode hint -> {df['work_mode_hint'].value_counts().to_dict()}")

job_locations = (
    pd.DataFrame({"job_id": df["jobId"], "city": locs}).explode("city").dropna(subset=["city"])
)
job_locations["metro_group"] = job_locations["city"].map(lambda c: METRO.get(c, c))
job_locations.to_csv(OUT / "job_locations.csv", index=False)

# --------------------------------------------------------------------------
# 7. Posting age - raw text is relative ("6 Days Ago"); convert to number of days
#    "Starts in ..." rows are internship/start-date strings -> days_ago NULL, flagged
# --------------------------------------------------------------------------
def days_ago(s):
    s = str(s).strip().lower()
    if s in ("just now", "few hours ago", "today"):
        return 0
    mm = re.match(r"(\d+)\s+days?\s+ago", s)
    return int(mm.group(1)) if mm else np.nan


df["days_ago"] = df["jobUploaded"].map(days_ago)
df["future_start"] = df["jobUploaded"].str.lower().str.startswith("starts")
note(f"Posting age range (days): {int(df['days_ago'].min())}-{int(df['days_ago'].max())}; "
     f"'Starts ...' rows: {df['future_start'].sum():,}")

# --------------------------------------------------------------------------
# 8. Skills - lower-case, trim, de-duplicate; '|' separated
#    The source field is capped at 8 tags -> flag it (skill counts are undercounts)
# --------------------------------------------------------------------------
raw_n = df["tagsAndSkills"].fillna("").map(lambda s: len([t for t in s.split(",") if t.strip()]))


def clean_skills(s):
    if pd.isna(s):
        return ""
    out = []
    for t in str(s).split(","):
        t = ws(t)
        t = t.lower() if isinstance(t, str) else ""
        if t and t not in out:
            out.append(t)
    return "|".join(out)


df["skills"] = df["tagsAndSkills"].map(clean_skills)
df["skills_count"] = df["skills"].map(lambda s: len(s.split("|")) if s else 0)
df["skills_capped"] = raw_n.eq(8)
note(f"Postings with skills field at the 8-tag cap: {df['skills_capped'].sum():,} ({df['skills_capped'].mean():.1%})")
note(f"Postings with no skills: {(df['skills_count'] == 0).sum():,}")

# --------------------------------------------------------------------------
# 9. Final columns + sanity checks
# --------------------------------------------------------------------------
out = df.rename(columns={
    "jobId": "job_id", "companyId": "company_id",
    "ReviewsCount": "reviews_count", "AggregateRating": "rating",
})[[
    "job_id", "title", "company_name", "company_id",
    "location_raw", "city", "metro_group", "n_locations", "multi_location", "work_mode_hint",
    "exp_min", "exp_max", "exp_band",
    "salary_min", "salary_max", "salary_mid", "salary_lpa", "salary_basis", "salary_flag", "has_variable_pay",
    "skills", "skills_count", "skills_capped",
    "days_ago", "future_start", "reviews_count", "rating", "description",
]]

both = out["salary_min"].notna() & out["salary_max"].notna()
one_sided = out["salary_min"].notna() ^ out["salary_max"].notna()
note(f"Postings with only ONE salary bound (min or max, not both; no salary_mid): {one_sided.sum():,}")

assert out["job_id"].is_unique, "job_id not unique"
assert (out.loc[both, "salary_min"] <= out.loc[both, "salary_max"]).all(), "salary_min > salary_max"
assert np.nanmin(out[["salary_min", "salary_max"]].to_numpy(dtype=float)) > 0, "non-positive salary left"

# Descriptions are the bulk of the file size -> separate table (join on job_id when needed)
out[["job_id", "description"]].to_csv(OUT / "job_descriptions.csv", index=False)
out = out.drop(columns=["description"])
out.to_csv(OUT / "jobs_clean.csv", index=False)
note(f"FINAL rows in jobs_clean.csv: {len(out):,}  | columns: {out.shape[1]}")
note(f"Rows in job_locations.csv: {len(job_locations):,}")

(OUT / "cleaning_log.md").write_text(
    "# Cleaning log (Phase 1)\n\n" + "\n".join(f"- {l}" for l in log) + "\n", encoding="utf-8"
)
