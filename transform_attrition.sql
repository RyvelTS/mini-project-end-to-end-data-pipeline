SET search_path TO ai_engineer;

-- =================================================================
-- Post-load SQL transforms (EXERCISE VERSION)
-- Instruksi: Isi bagian yang ditandai TODO
-- Nama tabel "raw_attrition" akan diganti otomatis oleh pipeline.py
-- =================================================================

-- 1. Rata-rata gaji per departemen
-- TODO 11: Tulis query untuk menghitung AVG dari MonthlyIncome per Department
-- Hint: SELECT "Department", ROUND(AVG(???)::numeric, 2) AS avg_income
--       FROM raw_attrition GROUP BY ???
SELECT
    "Department",
    ROUND(AVG("MonthlyIncome")::numeric, 2) AS avg_income,
    COUNT(*) AS jumlah_karyawan
FROM raw_attrition
GROUP BY "Department"
ORDER BY avg_income DESC;


-- 2. Attrition rate per departemen
-- TODO 12: Hitung berapa persen karyawan yang keluar per departemen
-- Hint: COUNT(*) FILTER (WHERE "Attrition" = 'Yes') / COUNT(*)
SELECT
    "Department",
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE "Attrition" = 'Yes') AS yang_keluar,
    ROUND(
        COUNT(*) FILTER (WHERE "Attrition" = 'Yes')::numeric / COUNT(*), 3
    ) AS attrition_rate
FROM raw_attrition
GROUP BY "Department"
ORDER BY attrition_rate DESC;


-- 3. Tenure bucket vs attrition
-- TODO 13: Buat kategori masa kerja menggunakan CASE WHEN
-- Hint: CASE WHEN "YearsAtCompany" < 2 THEN 'new' ...
SELECT
    CASE
        WHEN "YearsAtCompany" < 2 THEN '1. new (<2y)'
        WHEN "YearsAtCompany" < 5 THEN '2. mid (2-5y)'
        ELSE '3. veteran (5y+)'
    END AS tenure_bucket,
    COUNT(*) AS total_karyawan,
    COUNT(*) FILTER (WHERE "Attrition" = 'Yes') AS yang_keluar
FROM raw_attrition
GROUP BY tenure_bucket
ORDER BY tenure_bucket;


-- 4. Overtime vs attrition (cross-tab)
-- TODO 14: Cross-tab antara OverTime dan Attrition
-- Hint: GROUP BY dua kolom sekaligus
SELECT
    "OverTime",
    "Attrition",
    COUNT(*) AS jumlah
FROM raw_attrition
GROUP BY "OverTime", "Attrition"
ORDER BY "OverTime", "Attrition";


-- 5. Ranking gaji dalam departemen (window function)
-- TODO 15: Gunakan RANK() OVER (PARTITION BY ... ORDER BY ...)
-- untuk membuat ranking gaji tertinggi per departemen
SELECT
    "EmployeeNumber",
    "Department",
    "JobRole",
    "MonthlyIncome",
    RANK() OVER (
        PARTITION BY "Department"
        ORDER BY "MonthlyIncome" DESC
    ) AS income_rank
FROM raw_attrition
ORDER BY "Department", income_rank
LIMIT 20;
