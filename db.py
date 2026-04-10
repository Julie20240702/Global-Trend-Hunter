import sqlite3
import json
from pathlib import Path
from typing import Dict, Any

DB_PATH = Path(__file__).parent / "trend_hunter.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trend_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT,
            title TEXT,
            platform TEXT,
            url TEXT,
            trend_score REAL,
            analysis_json TEXT,
            localization_json TEXT,
            script_json TEXT,
            safety_json TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_record(record: Dict[str, Any]):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO trend_reports
        (video_id, title, platform, url, trend_score, analysis_json, localization_json, script_json, safety_json, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record["video_id"],
            record["title"],
            record["platform"],
            record["url"],
            float(record["trend_score"]),
            json.dumps(record["analysis"], ensure_ascii=False),
            json.dumps(record["localized"], ensure_ascii=False),
            json.dumps(record["script"], ensure_ascii=False),
            json.dumps(record["safety"], ensure_ascii=False),
            record["status"],
        )
    )
    conn.commit()
    conn.close()
