# Cleaning log (Phase 1)

- Raw rows: 97,929
- Duplicate jobId rows removed: 250
- Non-INR (USD) rows set aside: 129
- Salary disclosed (any): 33,354
- Salary usable (flag = ok): 32,964  | suspect_low: 375  | suspect_high: 20
- Monthly salaries annualised: 238
- Experience unknown: 571
- Distinct raw location strings: 10,065 -> distinct primary cities: 1,310
- Multi-city postings: 19,194 (19.7%)
- Work-mode hint -> {'Not specified': 89941, 'Hybrid': 5752, 'Remote': 1857}
- Posting age range (days): 0-20; 'Starts ...' rows: 571
- Postings with skills field at the 8-tag cap: 88,233 (90.4%)
- Postings with no skills: 571
- Postings with only ONE salary bound (min or max, not both; no salary_mid): 8
- FINAL rows in jobs_clean.csv: 97,550  | columns: 27
- Rows in job_locations.csv: 131,076
