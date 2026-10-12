"""
Phase 2 - Role classification + skills tables
Input : data/clean/jobs_clean.csv, data/clean/job_descriptions.csv   (from clean_data.py)
Output: data/clean/analytics_jobs.csv     in-scope postings + `role`
        data/clean/job_skills.csv         one row per (job, canonical skill, source)
        data/clean/skills_dim.csv         skill -> category
        data/clean/role_audit_sample.csv  100 postings for manual accuracy check
        data/clean/phase2_log.md

Usage:  python scripts/build_roles_skills.py [clean_dir]
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

D = Path(sys.argv[1] if len(sys.argv) > 1 else "data/clean")
log = []


def note(msg):
    print(msg)
    log.append(msg)


jobs = pd.read_csv(D / "jobs_clean.csv")
desc = pd.read_csv(D / "job_descriptions.csv")

# --------------------------------------------------------------------------
# 1. ROLE CLASSIFICATION  (title-based, first match wins, order matters)
#    Scope = the five roles below. Everything else is "out of scope".
#    Known limit: title-only rules miss roles with generic titles
#    ("Software Engineer" doing data work) -> recall is imperfect by design.
# --------------------------------------------------------------------------
RULES = [
    ("Data Engineer",
     r"data engineer|\betl\b|big ?data|data (solution )?architect|data model+er|data platform|dataops"
     r"|analytics engineer|data warehouse|\bdwh\b|data pipeline|databricks|snowflake"),
    ("Data Scientist / ML",
     r"data scien|machine learning|\bml\b|\bai ?/ ?ml\b|\bai engineer|genai|gen ai|generative ai"
     r"|\bllm\b|\bnlp\b|deep learning|computer vision|applied scientist"),
    ("Data Analyst",
     r"data analy|analytics (analyst|associate|specialist|executive|consultant)|insights? analyst"
     r"|product analyst|decision sci"),
    ("Business Analyst", r"business analy|business systems analy|\bba\b"),
    ("BI / MIS / Reporting",
     r"power ?bi|\bbi\b|business intelligence|tableau|\bmis\b|reporting analy|report(ing)? developer"
     r"|reporting specialist|dashboard|qlik|looker"),
]
EXCLUDE = (r"data entry|\bseo\b|digital marketing|trainer|annotation|tutor|teacher|faculty|sales"
           r"|counsell?or|recruit|volunteer|product marketing")


def classify(title):
    s = str(title).lower()
    if re.search(EXCLUDE, s):
        return None
    for name, pat in RULES:
        if re.search(pat, s):
            return name
    return None


jobs["role"] = jobs["title"].map(classify)
a = jobs[jobs["role"].notna()].copy()
note(f"In-scope analytics postings: {len(a):,} of {len(jobs):,} ({len(a)/len(jobs):.1%})")
for r, n in a["role"].value_counts().items():
    ok = ((a["role"] == r) & (a["salary_flag"] == "ok")).sum()
    note(f"  - {r}: {n:,} postings, {ok:,} with usable salary")

# Audit sample: 20 per role, fixed seed -> fill `is_correct` by hand
audit = (pd.concat([a[a["role"] == r].sample(min(20, (a["role"] == r).sum()), random_state=7)
                    for r in a["role"].unique()])[["job_id", "title", "role"]]
           .rename(columns={"role": "assigned_role"}))
audit["is_correct"] = ""
audit["correct_role_if_wrong"] = ""
audit.sample(frac=1, random_state=7).to_csv(D / "role_audit_sample.csv", index=False)

# --------------------------------------------------------------------------
# 2. SKILLS - canonical names (regex, applied to the WHOLE tag via fullmatch)
#    Generic/ambiguous tags are deliberately NOT merged (e.g. "machine", "warehouse").
# --------------------------------------------------------------------------
CANON = [
    (r"(ms |microsoft )?power ?-?bi( desktop| reports?| dashboards?| developer| service)?", "power bi"),
    (r"tableau( desktop| server| development| administration| reporting| public| pulse)?", "tableau"),
    (r"qlik( ?view| ?sense)?", "qlik"),
    (r"looker( studio)?|(google )?data studio", "looker"),
    (r"((advanced|ms|microsoft) )*excel( sheets?| reports?| reporting| report preparation| formulas?)?"
     r"|vlookup|hlookup|pivot tables?|conditional formatting|excel macros?", "excel"),
    (r"sql( queries| server| programming| development| scripting| tuning)?|ms sql( server)?"
     r"|t-?sql|pl ?/ ?sql|plsql|pl-sql", "sql"),
    (r"python( development| coding| programming| scripting| framework| basics| data)?|python3", "python"),
    (r"(py)?spark( sql| streaming| programming)?|apache spark", "spark"),
    (r"aws( [a-z0-9 ]+)?|amazon web services", "aws"),
    (r"(microsoft )?azure( cloud| platform| services?)?", "azure"),
    (r"(gcp|google cloud)( cloud| platforms?)?", "gcp"),
    (r"(azure )?data ?bricks", "databricks"),
    (r"(amazon |aws )?redshift( aws)?", "redshift"),
    (r"machine learning( algorithms| models?)?|ml( algorithms| models?)?|ai ?/ ?ml|aiml", "machine learning"),
    (r"nlp|natural language processing", "nlp"),
    (r"llms?|large language models?", "llm"),
    (r"gen ?ai|genai|generative( ai)?", "generative ai"),
    (r"ai|artificial intelligence", "artificial intelligence"),
    (r"bi|business intelligence", "business intelligence"),
    (r"data visuali[sz]ation|dashboards?|visuali[sz]ation", "data visualization"),
    (r"mis( reporting| reports?)?", "mis reporting"),
    (r"etl( process| pipelines?| development| tools?| developer)?", "etl"),
    (r"data model+ing", "data modeling"),
    (r"data warehous(e|ing)|dwh", "data warehousing"),
    (r"business analysis|business analyst", "business analysis"),
    (r"ci ?/ ?cd|continuous integration", "ci/cd"),
    (r"r|r programming|r language", "r"),
    (r"statistics|statistical (analysis|modeling|modelling)", "statistics"),
]
CANON = [(re.compile(p, re.I), c) for p, c in CANON]

CATEGORY = {
    "Programming & Query": ["sql", "python", "r", "scala", "java", "javascript", "c++", "sas", "nosql", "mysql", "postgresql"],
    "BI & Visualization": ["power bi", "tableau", "qlik", "looker", "dax", "data visualization", "business intelligence"],
    "Spreadsheets": ["excel", "macros", "vba"],
    "Data Engineering": ["spark", "hadoop", "hive", "kafka", "airflow", "etl", "data modeling", "data warehousing",
                         "snowflake", "databricks", "bigquery", "redshift", "azure data factory", "informatica",
                         "dbt", "big data", "data engineering", "data architecture", "data pipelines"],
    "Cloud": ["aws", "azure", "gcp", "cloud", "azure synapse", "azure data lake"],
    "ML & AI": ["machine learning", "deep learning", "nlp", "llm", "generative ai", "artificial intelligence",
                "tensorflow", "pytorch", "scikit-learn", "computer vision", "statistics", "mlops", "data science"],
    "DevOps & Tools": ["git", "github", "docker", "kubernetes", "jenkins", "ci/cd", "devops", "jira", "linux", "unix"],
    "Business & Process": ["business analysis", "project management", "agile", "scrum", "stakeholder management",
                           "requirement gathering", "gap analysis", "mis reporting", "reporting",
                           "presentation skills", "consulting"],
    "Analytics (generic)": ["data analysis", "data analytics", "analytics", "business analytics", "analytical",
                            "data management", "data quality", "data governance", "data mining"],
}
CAT_OF = {s: c for c, ss in CATEGORY.items() for s in ss}


def canonical(tag):
    tag = re.sub(r"\s+", " ", tag.strip().lower())
    for rx, name in CANON:
        if rx.fullmatch(tag):
            return name
    return tag


# tags -> long table
a["_tags"] = a["skills"].fillna("").map(lambda s: [t for t in s.split("|") if t])
tag_rows = a[["job_id", "_tags"]].explode("_tags").dropna(subset=["_tags"])
uniq = {t: canonical(t) for t in tag_rows["_tags"].unique()}
tag_rows["skill"] = tag_rows["_tags"].map(uniq)
tag_rows = tag_rows[["job_id", "skill"]].drop_duplicates()
tag_rows["in_tags"] = True
note(f"Distinct raw skill tags in scope: {len(uniq):,} -> distinct canonical skills: {tag_rows['skill'].nunique():,}")

# --------------------------------------------------------------------------
# 3. DESCRIPTION-BASED EXTRACTION for core skills (title + description text)
#    Why: the source tags are capped at 8 per posting, so tags UNDERCOUNT skills.
#    Descriptions are short snippets, so this is a partial cross-check, not ground truth.
# --------------------------------------------------------------------------
CORE = {
    "sql": r"\bsql\b",
    "python": r"\bpython\b",
    "power bi": r"power ?-?bi\b",
    "tableau": r"\btableau\b",
    "excel": r"\b(?:ms|microsoft|advanced) excel\b|\bexcel (?:sheets?|reports?|formulas?|macros?)\b|\bvlookup\b|\bpivot tables?\b",
    "aws": r"\baws\b|amazon web services",
    "azure": r"\bazure\b",
    "gcp": r"\bgcp\b|google cloud",
    "spark": r"\bpyspark\b|apache spark|spark sql|spark streaming",
    "snowflake": r"\bsnowflake\b",
    "databricks": r"\bdata ?bricks\b",
    "airflow": r"\bairflow\b",
    "kafka": r"\bkafka\b",
    "hadoop": r"\bhadoop\b",
    "dbt": r"\bdbt\b",
    "looker": r"\blooker\b",
    "qlik": r"\bqlik",
    "machine learning": r"machine learning",
    "tensorflow": r"\btensorflow\b",
    "pytorch": r"\bpytorch\b",
}
text = (a[["job_id", "title"]].merge(desc, on="job_id", how="left")
        .assign(t=lambda d: (d["title"].fillna("") + " " + d["description"].fillna("")).str.lower()))
d_rows = []
for skill, pat in CORE.items():
    hit = text.loc[text["t"].str.contains(pat, regex=True), "job_id"]
    d_rows.append(pd.DataFrame({"job_id": hit, "skill": skill, "in_description": True}))
d_rows = pd.concat(d_rows, ignore_index=True)

js = tag_rows.merge(d_rows, on=["job_id", "skill"], how="outer")
js["in_tags"] = js["in_tags"].fillna(False).astype(bool)
js["in_description"] = js["in_description"].fillna(False).astype(bool)
js["source"] = np.select([js.in_tags & js.in_description, js.in_tags], ["both", "tag"], default="description")
js["skill_category"] = js["skill"].map(CAT_OF).fillna("Other")
js = js[["job_id", "skill", "skill_category", "source"]].sort_values(["job_id", "skill"])

# how much does the 8-tag cap undercount?
note(f"In-scope postings at the 8-tag cap: {a['skills_capped'].mean():.1%}")
note("Core-skill postings: tags only -> tags + description (uplift):")
n = len(a)
for s in ["sql", "python", "power bi", "tableau", "excel", "aws", "azure", "spark", "snowflake"]:
    t_only = js[(js.skill == s) & js.source.isin(["tag", "both"])]["job_id"].nunique()
    union = js[js.skill == s]["job_id"].nunique()
    note(f"  - {s}: {t_only:,} ({t_only/n:.1%}) -> {union:,} ({union/n:.1%})")

# --------------------------------------------------------------------------
# 4. Save
# --------------------------------------------------------------------------
dim = (js[["skill", "skill_category"]].drop_duplicates().sort_values(["skill_category", "skill"]))
dim.to_csv(D / "skills_dim.csv", index=False)
js.to_csv(D / "job_skills.csv", index=False)
a.drop(columns=["_tags"]).to_csv(D / "analytics_jobs.csv", index=False)

assert a["job_id"].is_unique
assert js["job_id"].isin(a["job_id"]).all()
note(f"Saved: analytics_jobs.csv ({len(a):,} rows), job_skills.csv ({len(js):,} rows), skills_dim.csv ({len(dim):,} skills)")
(D / "phase2_log.md").write_text("# Phase 2 log (roles + skills)\n\n" + "\n".join(f"- {l}" if not l.startswith("  -") else l
                                 for l in log) + "\n", encoding="utf-8")
