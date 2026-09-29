"""
Cleaner

Cleans scraped data (RSS + books + quotes) BEFORE loading to DB.
This is the "Transform" step of the ETL path.

Instruksi: Isi bagian yang ditandai TODO
"""

import logging
from typing import List, Dict

import pandas as pd

log = logging.getLogger(__name__)


def clean_articles(raw_records: List[Dict]) -> pd.DataFrame:
    """Clean scraped data. Returns DataFrame ready for DB insert."""
    if not raw_records:
        return pd.DataFrame(columns=["title", "url", "source", "content", "published_at"])

    df = pd.DataFrame(raw_records)
    initial = len(df)
    log.info("Mulai cleaning: %d record", initial)

    # TODO 6: Drop duplikat berdasarkan kolom URL
    # Hint: df.drop_duplicates(subset=[???])
    df = df.drop_duplicates(subset=['url'])
    log.info("Setelah drop duplikat URL: %d record (-%d)", len(df), initial - len(df))

    # TODO 7: Buang baris yang tidak punya title atau URL (null)
    # Hint: df.dropna(subset=[???])
    before = len(df)
    df = df.dropna(subset=['title','url'])
    if len(df) < before:
        log.info("Drop baris tanpa title/url: -%d", before - len(df))

    # TODO 8: Normalisasi teks
    #   - title: strip whitespace
    #   - url: strip whitespace
    #   - source: strip whitespace + lowercase
    #   - content: isi NaN dengan "" lalu strip whitespace
    df["title"] = df["title"].str.strip()
    df["url"] = df["url"].str.strip()
    df["source"] = df["source"].str.strip().str.lower()
    df["content"] = df["content"].fillna("").str.strip()

    # TODO 9: Konversi published_at ke datetime
    # Hint: pd.to_datetime(..., errors="coerce", utc=True)
    #       lalu dt.tz_localize(None) untuk menghapus timezone info
    df["published_at"] = pd.to_datetime(df["published_at"],errors="coerce",utc=True)
    df["published_at"] = df["published_at"].dt.tz_localize(None)

    # TODO 10: Buang baris dengan konten terlalu pendek (< 20 karakter)
    # Hint: df[df["content"].str.len() >= ???]
    before2 = len(df)
    df = df[df["content"].str.len() >= 20]
    if len(df) < before2:
        log.info("Drop konten pendek (<20 char): -%d", before2 - len(df))

    # Hanya kolom yang masuk DB
    df = df[["title", "url", "source", "content", "published_at"]]
    df = df.reset_index(drop=True)

    log.info("Cleaning selesai: %d -> %d record", initial, len(df))
    return df
