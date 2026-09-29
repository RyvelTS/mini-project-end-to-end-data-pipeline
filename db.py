from typing import Optional, List, Dict
from sqlalchemy import create_engine, text
from pydantic_settings import BaseSettings, SettingsConfigDict
import pandas as pd
import math
import logging

log = logging.getLogger(__name__)

class DBSettings(BaseSettings):
    database_url: str
    student_name: str

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=False, extra="ignore"
    )

settings = DBSettings()
engine = create_engine(settings.database_url)

SCHEMA = "ai_engineer"
ARTICLES_TABLE = f'"{SCHEMA}".articles_{settings.student_name}'
ATTRITION_TABLE_NAME = f"raw_attrition_{settings.student_name}"
ATTRITION_TABLE = f'"{SCHEMA}".{ATTRITION_TABLE_NAME}'

def init_db():
    """Create tables and indexes if they don't exist."""
    ddl = f"""
    CREATE TABLE IF NOT EXISTS {ARTICLES_TABLE} (
        id           SERIAL PRIMARY KEY,
        title        TEXT NOT NULL,
        url          TEXT UNIQUE NOT NULL,
        source       TEXT NOT NULL,
        content      TEXT,
        published_at TIMESTAMP,
        scraped_at   TIMESTAMP DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_articles_source
        ON {ARTICLES_TABLE}(source);
    CREATE INDEX IF NOT EXISTS idx_articles_published
        ON {ARTICLES_TABLE}(published_at DESC);
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))
    log.info("Database ready. Table: %s", ARTICLES_TABLE)

def save_articles(df: pd.DataFrame) -> int:
    """Insert articles with ON CONFLICT — safe to re-run."""
    if df.empty:
        log.warning("DataFrame kosong, tidak ada yang di-insert.")
        return 0

    inserted = 0
    with engine.begin() as conn:
        for _, row in df.iterrows():
            result = conn.execute(
                text(f"""
                    INSERT INTO {ARTICLES_TABLE}
                        (title, url, source, content, published_at)
                    VALUES
                        (:title, :url, :source, :content, :published_at)
                    ON CONFLICT (url) DO NOTHING
                """),
                {
                    "title": row["title"],
                    "url": row["url"],
                    "source": row["source"],
                    "content": row["content"],
                    "published_at": row["published_at"]
                    if pd.notna(row["published_at"])
                    else None,
                },
            )
            inserted += result.rowcount

    log.info("Insert selesai: %d baru dari %d record.", inserted, len(df))
    return inserted

def count_articles() -> int:
    """Count total articles in DB."""
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT COUNT(*) FROM {ARTICLES_TABLE}"))
        return result.scalar()

def count_articles_by_source() -> Dict[str, int]:
    """
    Hitung jumlah artikel per source.
    Return contoh: {"bbc": 50, "nytimes": 30, "books.toscrape": 200}
    """
    # TODO 18: Tulis query SELECT source, COUNT(*) ... GROUP BY source
    #          Lalu convert hasil ke dictionary {source: count}
    with engine.connect() as conn:
        rows = conn.execute(text(
            f"SELECT source, COUNT(*) as cnt FROM {ARTICLES_TABLE}"
            f" GROUP BY source ORDER BY cnt DESC"
        )).mappings().all()
    return {row["source"]: row["cnt"] for row in rows}

def get_articles(
    source: Optional[str] = None,
    title: Optional[str] = None,
    limit: int = 20,
) -> List[Dict]:
    """
    Cari articles dengan optional filter source dan title.

    Contoh pemanggilan:
      get_articles(source="bbc", limit=5)           → artikel BBC saja
      get_articles(title="python", limit=10)         → judul mengandung "python"
      get_articles(source="bbc", title="AI", limit=5) → BBC + judul ada "AI"
    """
    # TODO 19: Bangun query SELECT secara dinamis berdasarkan parameter
    #
    # Hint:
    #   - Mulai dengan: query = f"SELECT * FROM {ARTICLES_TABLE} WHERE 1=1"
    #   - Jika source ada:   tambah " AND source = :source"
    #   - Jika title ada:    tambah " AND title ILIKE :title"
    #     (ILIKE = case-insensitive LIKE di PostgreSQL)
    #     params["title"] = f"%{title}%"   ← wildcard di kedua sisi
    #   - Akhiri dengan: ORDER BY published_at DESC NULLS LAST LIMIT :limit
    #   - Execute dengan parameterized query (JANGAN string format untuk values!)
    #   - Return list of dicts: [dict(r) for r in rows]
    query = f"SELECT * FROM {ARTICLES_TABLE} WHERE 1=1"
    params: dict = {}

    if source:
        query += " AND source = :source"
        params["source"] = source.lower()

    if title:
        query += " AND title ILIKE :title"
        params["title"] = f"%{title}%"

    query += " ORDER BY published_at DESC NULLS LAST LIMIT :limit"
    params["limit"] = limit

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()
    return [dict(r) for r in rows]

def get_article_by_id(article_id: int) -> Optional[Dict]:
    """Get single article by ID. Return None jika tidak ditemukan."""
    # TODO 20: SELECT * FROM ... WHERE id = :id
    #
    # Hint:
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT * FROM {ARTICLES_TABLE} WHERE id = :id"),
            {"id": article_id},
        ).mappings().first()
    return dict(row) if row else None

def get_attrition_summary() -> Dict:
    """
    Overall stats: total karyawan, jumlah & rate attrition.
    Return contoh: {"total_employees": 1470, "attrition_yes": 237, ...}
    """
    # TODO 21: Hitung total karyawan dan jumlah yang Attrition = 'Yes'
    with engine.connect() as conn:
        row = conn.execute(text(f"""
            SELECT 
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE "Attrition" = 'Yes') AS attrition_yes
            FROM {ATTRITION_TABLE}
        """)).mappings().one()
        total = row["total"]
        attrition_yes = row["attrition_yes"]
    return {
        "total_employees": total,
        "attrition_yes": attrition_yes,
        "attrition_no": total - attrition_yes,
        "attrition_rate": round(attrition_yes / total, 4) if total > 0 else 0.0,
    }

def search_articles(
    source: Optional[str] = None,
    title: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
    per_page: int = 10,
) -> Dict:
    """
    Search articles dengan filter dinamis dan pagination.
    """
    offset = (page - 1) * per_page

    where_clauses = ["1=1"]
    params: dict = {}

    if source:
        where_clauses.append("source = :source")
        params["source"] = source.lower()

    if title:
        where_clauses.append("title ILIKE :title")
        params["title"] = f"%{title}%"

    if date_from:
        where_clauses.append("published_at >= :date_from")
        params["date_from"] = date_from

    if date_to:
        where_clauses.append("published_at <= :date_to")
        params["date_to"] = date_to

    where_sql = " AND ".join(where_clauses)

    with engine.connect() as conn:
        # Hitung total artikel yang cocok dengan filter
        count_query = f"SELECT COUNT(*) FROM {ARTICLES_TABLE} WHERE {where_sql}"
        total_items = conn.execute(text(count_query), params).scalar() or 0

        # Ambil data dengan LIMIT dan OFFSET
        data_query = f"""
            SELECT * FROM {ARTICLES_TABLE}
            WHERE {where_sql}
            ORDER BY published_at DESC NULLS LAST
            LIMIT :limit OFFSET :offset
        """
        data_params = {**params, "limit": per_page, "offset": offset}
        rows = conn.execute(text(data_query), data_params).mappings().all()

    total_pages = math.ceil(total_items / per_page) if total_items > 0 else 0

    return {
        "data": [dict(r) for r in rows],
        "page": page,
        "per_page": per_page,
        "total_items": total_items,
        "total_pages": total_pages,
    }

def get_attrition_by_department() -> List[Dict]:
    """
    Attrition rate + avg income per department.
    Ini gabungan query 1 & 2 dari transform_attrition.sql Session 9.
    """
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT
                "Department",
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE "Attrition" = 'Yes') AS attrition_count,
                ROUND(
                    COUNT(*) FILTER (WHERE "Attrition" = 'Yes')::numeric / COUNT(*), 3
                ) AS attrition_rate,
                ROUND(AVG("MonthlyIncome")::numeric, 2) AS avg_income
            FROM {ATTRITION_TABLE}
            GROUP BY "Department"
            ORDER BY attrition_rate DESC
        """)).mappings().all()
    return [dict(r) for r in rows]

def get_attrition_by_tenure() -> List[Dict]:
    """
    Attrition by tenure bucket.
    Ini query 3 dari transform_attrition.sql Session 9.
    """
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT
                CASE
                    WHEN "YearsAtCompany" < 2 THEN '1. new (<2y)'
                    WHEN "YearsAtCompany" < 5 THEN '2. mid (2-5y)'
                    ELSE '3. veteran (5y+)'
                END AS tenure_bucket,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE "Attrition" = 'Yes') AS attrition_count,
                ROUND(
                    COUNT(*) FILTER (WHERE "Attrition" = 'Yes')::numeric / COUNT(*), 3
                ) AS attrition_rate
            FROM {ATTRITION_TABLE}
            GROUP BY tenure_bucket
            ORDER BY tenure_bucket
        """)).mappings().all()
    return [dict(r) for r in rows]


def get_attrition_by_overtime() -> List[Dict]:
    """
    Attrition by overtime status.
    Ini query 4 dari transform_attrition.sql Session 9.
    """
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT
                "OverTime",
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE "Attrition" = 'Yes') AS attrition_count,
                ROUND(
                    COUNT(*) FILTER (WHERE "Attrition" = 'Yes')::numeric / COUNT(*), 3
                ) AS attrition_rate
            FROM {ATTRITION_TABLE}
            GROUP BY "OverTime"
            ORDER BY "OverTime"
        """)).mappings().all()
    return [dict(r) for r in rows]


def get_top_earners_by_department(limit_per_dept: int = 5) -> List[Dict]:
    """
    Top earners per department menggunakan RANK() window function.
    Ini query 5 dari transform_attrition.sql Session 9.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT *
                FROM (
                    SELECT
                        "EmployeeNumber",
                        "Department",
                        "JobRole",
                        "MonthlyIncome",
                        "Attrition",
                        RANK() OVER (
                            PARTITION BY "Department"
                            ORDER BY "MonthlyIncome" DESC
                        ) AS income_rank
                    FROM {ATTRITION_TABLE}
                ) ranked
                WHERE income_rank <= :limit_per_dept
                ORDER BY "Department", income_rank
            """),
            {"limit_per_dept": limit_per_dept},
        ).mappings().all()
    return [dict(r) for r in rows]
