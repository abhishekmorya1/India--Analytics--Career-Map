-- ============================================================================
-- India Analytics Career Map - SQL queries (SQLite)
-- Each block starts with "-- name: <id>" so build_database.py can run and export it.
-- You can also copy any block into DB Browser for SQLite and run it by hand.
--
-- Tables : jobs, job_skills, job_locations      View: v_salary_jobs
-- NOTE   : SQLite has no MEDIAN(), so medians use the ROW_NUMBER() trick:
--          pick the middle row (or average the two middle rows) per group.
-- NOTE   : "usable salary" = salary_flag = 'ok'  (see cleaning_log.md)
-- ============================================================================


-- name: q01_role_demand
-- Q: Which analytics roles are hired for the most?
SELECT role,

       COUNT(*)                                              AS postings,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)    AS pct_of_analytics_postings
FROM jobs
GROUP BY role
ORDER BY postings DESC;


-- name: q02_salary_coverage
-- Q: How much salary data do we actually have per role? (data-quality check)
SELECT role,
       COUNT(*)                                                       AS postings,
       SUM(salary_flag = 'ok')                                        AS with_usable_salary,
       ROUND(100.0 * SUM(salary_flag = 'ok') / COUNT(*), 1)           AS pct_with_salary
FROM jobs
GROUP BY role
ORDER BY with_usable_salary DESC;


-- name: q03_salary_by_role
-- Q: What is the median salary (LPA) for each role?
WITH ranked AS (
    SELECT role, salary_lpa,
           ROW_NUMBER() OVER (PARTITION BY role ORDER BY salary_lpa) AS rn,
           COUNT(*)     OVER (PARTITION BY role)                      AS n
    FROM v_salary_jobs
)
SELECT role,
       MAX(n)                     AS n_salaries,
       ROUND(AVG(salary_lpa), 1)  AS median_lpa
FROM ranked
WHERE rn IN ((n + 1) / 2, (n + 2) / 2)
GROUP BY role
ORDER BY median_lpa DESC;


-- name: q04a_salary_by_experience
-- Q: How does salary grow with experience? (all analytics roles together)
--    13+ and Unknown are left out: too few salary points.
WITH ranked AS (
    SELECT exp_band, salary_lpa,
           ROW_NUMBER() OVER (PARTITION BY exp_band ORDER BY salary_lpa) AS rn,
           COUNT(*)     OVER (PARTITION BY exp_band)                     AS n
    FROM v_salary_jobs
    WHERE exp_band IN ('0-2', '3-5', '6-8', '9-12')
)
SELECT exp_band,
       MAX(n)                     AS n_salaries,
       ROUND(AVG(salary_lpa), 1)  AS median_lpa
FROM ranked
WHERE rn IN ((n + 1) / 2, (n + 2) / 2)
GROUP BY exp_band
ORDER BY CASE exp_band WHEN '0-2' THEN 1 WHEN '3-5' THEN 2 WHEN '6-8' THEN 3 ELSE 4 END;


-- name: q04b_salary_role_by_experience
-- Q: Same, split by role. Cells with fewer than 8 salaries are dropped.
WITH ranked AS (
    SELECT role, exp_band, salary_lpa,
           ROW_NUMBER() OVER (PARTITION BY role, exp_band ORDER BY salary_lpa) AS rn,
           COUNT(*)     OVER (PARTITION BY role, exp_band)                     AS n
    FROM v_salary_jobs
    WHERE exp_band IN ('0-2', '3-5', '6-8', '9-12')
)
SELECT role, exp_band,
       MAX(n)                     AS n_salaries,
       ROUND(AVG(salary_lpa), 1)  AS median_lpa
FROM ranked
WHERE rn IN ((n + 1) / 2, (n + 2) / 2)
GROUP BY role, exp_band
HAVING MAX(n) >= 8
ORDER BY role, CASE exp_band WHEN '0-2' THEN 1 WHEN '3-5' THEN 2 WHEN '6-8' THEN 3 ELSE 4 END;


-- name: q05_demand_by_metro
-- Q: Which metros have the most analytics postings?
--    Uses job_locations, so a posting listing Bengaluru + Hyderabad counts in BOTH
--    (percentages therefore add up to more than 100).
SELECT l.metro_group,
       COUNT(DISTINCT l.job_id)                                              AS postings,
       ROUND(100.0 * COUNT(DISTINCT l.job_id) / (SELECT COUNT(*) FROM jobs), 1) AS pct_of_postings
FROM job_locations l
GROUP BY l.metro_group
ORDER BY postings DESC
LIMIT 12;


-- name: q06_salary_by_metro
-- Q: Where do analytics jobs pay more? (primary listed city; metros with 20+ salaries)
WITH ranked AS (
    SELECT metro_group, salary_lpa,
           ROW_NUMBER() OVER (PARTITION BY metro_group ORDER BY salary_lpa) AS rn,
           COUNT(*)     OVER (PARTITION BY metro_group)                     AS n
    FROM v_salary_jobs
)
SELECT metro_group,
       MAX(n)                     AS n_salaries,
       ROUND(AVG(salary_lpa), 1)  AS median_lpa
FROM ranked
WHERE rn IN ((n + 1) / 2, (n + 2) / 2)
GROUP BY metro_group
HAVING MAX(n) >= 20
ORDER BY median_lpa DESC;


-- name: q07_top_skills_overall
-- Q: Which skills are most in demand across all analytics roles?
--    "Other" (long tail of rare/ambiguous tags) is excluded.
SELECT s.skill,
       s.skill_category,
       COUNT(DISTINCT s.job_id)                                                    AS postings,
       ROUND(100.0 * COUNT(DISTINCT s.job_id) / (SELECT COUNT(*) FROM jobs), 1)    AS pct_of_postings
FROM job_skills s
WHERE s.skill_category <> 'Other'
GROUP BY s.skill, s.skill_category
ORDER BY postings DESC
LIMIT 20;


-- name: q08_top_skills_per_role
-- Q: What are the top 8 skills inside each role?
WITH role_n AS (
    SELECT role, COUNT(*) AS n FROM jobs GROUP BY role
),
cnt AS (
    SELECT j.role, s.skill, COUNT(DISTINCT s.job_id) AS postings
    FROM job_skills s
    JOIN jobs j ON j.job_id = s.job_id
    WHERE s.skill_category <> 'Other'
    GROUP BY j.role, s.skill
),
ranked AS (
    SELECT role, skill, postings,
           ROW_NUMBER() OVER (PARTITION BY role ORDER BY postings DESC) AS skill_rank
    FROM cnt
)
SELECT r.role, r.skill_rank, r.skill, r.postings,
       ROUND(100.0 * r.postings / n.n, 1) AS pct_of_role_postings
FROM ranked r
JOIN role_n n ON n.role = r.role
WHERE r.skill_rank <= 8
ORDER BY r.role, r.skill_rank;


-- name: q09_core_tools_by_role
-- Q: SQL vs Python vs Power BI vs Tableau vs Excel - who needs what?
SELECT j.role,
       COUNT(*) AS postings,
       ROUND(100.0 * SUM(EXISTS (SELECT 1 FROM job_skills s WHERE s.job_id = j.job_id AND s.skill = 'sql'))      / COUNT(*), 1) AS sql_pct,
       ROUND(100.0 * SUM(EXISTS (SELECT 1 FROM job_skills s WHERE s.job_id = j.job_id AND s.skill = 'python'))   / COUNT(*), 1) AS python_pct,
       ROUND(100.0 * SUM(EXISTS (SELECT 1 FROM job_skills s WHERE s.job_id = j.job_id AND s.skill = 'power bi')) / COUNT(*), 1) AS power_bi_pct,
       ROUND(100.0 * SUM(EXISTS (SELECT 1 FROM job_skills s WHERE s.job_id = j.job_id AND s.skill = 'tableau'))  / COUNT(*), 1) AS tableau_pct,
       ROUND(100.0 * SUM(EXISTS (SELECT 1 FROM job_skills s WHERE s.job_id = j.job_id AND s.skill = 'excel'))    / COUNT(*), 1) AS excel_pct
FROM jobs j
GROUP BY j.role
ORDER BY postings DESC;


-- name: q10_skill_pairs
-- Q: Which skills are asked for together? (self-join on job_id, core skills only)
WITH c AS (
    SELECT DISTINCT job_id, skill
    FROM job_skills
    WHERE skill IN ('sql', 'python', 'power bi', 'tableau', 'excel', 'aws', 'azure', 'gcp',
                    'spark', 'snowflake', 'databricks', 'etl', 'machine learning')
)
SELECT a.skill AS skill_1, b.skill AS skill_2, COUNT(*) AS postings
FROM c a
JOIN c b ON a.job_id = b.job_id AND a.skill < b.skill
GROUP BY a.skill, b.skill
ORDER BY postings DESC
LIMIT 15;


-- name: q11_skill_salary_premium_within_role
-- Q: Does having a skill go with higher pay AFTER controlling for role?
--    Compares median salary of postings WITH vs WITHOUT the skill, inside the same role.
--    Only groups with 15+ salaries on each side. This is association, not causation.
WITH core(skill) AS (
    VALUES ('sql'), ('python'), ('power bi'), ('tableau'), ('excel'), ('aws'), ('azure'), ('spark')
),
grid AS (
    SELECT b.role, c.skill, b.salary_lpa,
           EXISTS (SELECT 1 FROM job_skills s WHERE s.job_id = b.job_id AND s.skill = c.skill) AS has_skill
    FROM v_salary_jobs b
    CROSS JOIN core c
),
ranked AS (
    SELECT role, skill, has_skill, salary_lpa,
           ROW_NUMBER() OVER (PARTITION BY role, skill, has_skill ORDER BY salary_lpa) AS rn,
           COUNT(*)     OVER (PARTITION BY role, skill, has_skill)                     AS n
    FROM grid
),
med AS (
    SELECT role, skill, has_skill, MAX(n) AS n, AVG(salary_lpa) AS median_lpa
    FROM ranked
    WHERE rn IN ((n + 1) / 2, (n + 2) / 2)
    GROUP BY role, skill, has_skill
)
SELECT w.role, w.skill,
       w.n                            AS n_with_skill,
       ROUND(w.median_lpa, 1)         AS median_with,
       wo.n                           AS n_without_skill,
       ROUND(wo.median_lpa, 1)        AS median_without,
       ROUND(w.median_lpa - wo.median_lpa, 1) AS diff_lpa
FROM med w
JOIN med wo ON wo.role = w.role AND wo.skill = w.skill AND wo.has_skill = 0
WHERE w.has_skill = 1 AND w.n >= 15 AND wo.n >= 15
ORDER BY w.role, diff_lpa DESC;


-- name: q12_top_hiring_companies
-- Q: Who posts the most analytics jobs? (staffing/bulk posters are visible here -
--    flag them manually in the README instead of calling them "top employers")
SELECT company_name,
       COUNT(*)                                                        AS postings,
       COUNT(DISTINCT city)                                            AS cities,
       COUNT(DISTINCT role)                                            AS roles,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM jobs), 1)        AS pct_of_postings
FROM jobs
GROUP BY company_name
ORDER BY postings DESC
LIMIT 15;


-- name: q13_work_mode_hint
-- Q: Hybrid / remote mentions by role. Only what the location text says;
--    "Not specified" does NOT mean onsite.
SELECT role,
       COUNT(*)                                                            AS postings,
       ROUND(100.0 * SUM(work_mode_hint = 'Hybrid') / COUNT(*), 1)         AS hybrid_pct,
       ROUND(100.0 * SUM(work_mode_hint = 'Remote') / COUNT(*), 1)         AS remote_pct,
       ROUND(100.0 * SUM(work_mode_hint = 'Not specified') / COUNT(*), 1)  AS not_specified_pct
FROM jobs
GROUP BY role
ORDER BY postings DESC;
