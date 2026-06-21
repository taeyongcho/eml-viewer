"""
EML 뷰어 DB 캐시 (SQLite)
- 헤더 정보(제목/보낸이/날짜 등)를 DB에 저장
- 앱 시작 시 DB에서 즉시 로드
- .eml 파일이 없어진 경우 자동 정리
"""
import sqlite3
import os


DB_PATH = os.path.join(os.path.expanduser("~"), ".eml_viewer_cache.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS emails (
                path      TEXT PRIMARY KEY,
                basename  TEXT NOT NULL,
                subject   TEXT,
                from_     TEXT,
                to_       TEXT,
                cc_       TEXT,
                date_str  TEXT,
                date_ts   REAL,   -- timestamp (float), None 이면 NULL
                added_at  REAL DEFAULT (strftime('%s','now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON emails(date_ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_basename ON emails(basename)")
        conn.commit()


def save_emails(email_list: list):
    """파싱된 이메일 dict 목록을 DB에 저장 (이미 있으면 무시)"""
    rows = []
    for e in email_list:
        date_ts = e["date"].timestamp() if e.get("date") else None
        rows.append((
            e["path"],
            os.path.basename(e["path"]),
            e.get("subject", ""),
            e.get("from_", ""),
            e.get("to", ""),
            e.get("cc", ""),
            e.get("date_str", ""),
            date_ts,
        ))
    with get_conn() as conn:
        conn.executemany("""
            INSERT OR IGNORE INTO emails
                (path, basename, subject, from_, to_, cc_, date_str, date_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()


def load_all() -> list:
    """DB에서 전체 로드. 파일이 실제로 존재하는 것만 반환."""
    import datetime
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM emails ORDER BY date_ts DESC NULLS LAST"
        ).fetchall()

    result = []
    missing = []
    for row in rows:
        path = row["path"]
        if not os.path.exists(path):
            missing.append(path)
            continue
        # date 복원
        date_obj = None
        if row["date_ts"] is not None:
            try:
                date_obj = datetime.datetime.fromtimestamp(
                    row["date_ts"], tz=datetime.timezone.utc
                ).replace(tzinfo=None)  # naive로 통일
            except Exception:
                pass
        result.append({
            "path":     path,
            "subject":  row["subject"] or os.path.basename(path),
            "from_":    row["from_"] or "",
            "to":       row["to_"] or "",
            "cc":       row["cc_"] or "",
            "date_str": row["date_str"] or "",
            "date":     date_obj,
            "body_text":   None,
            "body_html":   None,
            "attachments": None,
            "_raw":        None,   # 클릭 시 파일에서 읽음
        })

    # 없어진 파일 DB에서 제거
    if missing:
        with get_conn() as conn:
            conn.executemany("DELETE FROM emails WHERE path=?", [(p,) for p in missing])
            conn.commit()

    return result


def get_existing_basenames() -> set:
    """DB에 이미 있는 파일명(basename) 집합 반환"""
    with get_conn() as conn:
        rows = conn.execute("SELECT basename FROM emails").fetchall()
    return {row["basename"] for row in rows}


def delete_paths(paths: list):
    """지정한 경로들을 DB에서 삭제"""
    with get_conn() as conn:
        conn.executemany("DELETE FROM emails WHERE path=?", [(p,) for p in paths])
        conn.commit()


def clear_all():
    """DB 전체 초기화"""
    with get_conn() as conn:
        conn.execute("DELETE FROM emails")
        conn.commit()


# 앱 시작 시 초기화
init_db()
