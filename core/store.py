"""SQLite 增量存储，按 URL 去重。"""
import sqlite3
from .config import DB_PATH


def _conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            biz TEXT UNIQUE NOT NULL,
            name TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            url TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            digest TEXT DEFAULT '',
            author TEXT DEFAULT '',
            cover TEXT DEFAULT '',
            publish_time TEXT DEFAULT '',
            publish_ts INTEGER DEFAULT 0,
            source_url TEXT DEFAULT '',
            content TEXT DEFAULT '',
            content_status TEXT DEFAULT '',
            content_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(account_id) REFERENCES accounts(id)
        )
    """)
    # 兼容已有数据库：缺列则追加
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(articles)").fetchall()}
    for col, ddl in (("content", "TEXT DEFAULT ''"),
                     ("content_status", "TEXT DEFAULT ''"),
                     ("content_at", "TIMESTAMP")):
        if col not in cols:
            conn.execute(f"ALTER TABLE articles ADD COLUMN {col} {ddl}")
    conn.commit()
    conn.close()


def get_or_create_account(biz, name=""):
    conn = _conn()
    conn.execute("INSERT OR IGNORE INTO accounts(biz,name) VALUES(?,?)", (biz, name))
    if name:
        conn.execute("UPDATE accounts SET name=? WHERE biz=?", (name, biz))
    row = conn.execute("SELECT id FROM accounts WHERE biz=?", (biz,)).fetchone()
    conn.commit()
    conn.close()
    return row["id"]


def save_articles(account_id, articles):
    conn = _conn()
    new = 0
    for art in articles:
        cur = conn.execute("""
            INSERT OR IGNORE INTO articles
            (account_id,url,title,digest,author,cover,publish_time,publish_ts,source_url)
            VALUES(?,?,?,?,?,?,?,?,?)
        """, (account_id, art["url"], art["title"], art["digest"], art["author"],
              art["cover"], art["publish_time"], art["publish_ts"], art["source_url"]))
        new += cur.rowcount
    conn.commit()
    conn.close()
    return new


def list_articles(account_id=None, keyword=""):
    conn = _conn()
    sql = "SELECT * FROM articles WHERE 1=1"
    params = []
    if account_id:
        sql += " AND account_id=?"
        params.append(account_id)
    if keyword:
        sql += " AND (title LIKE ? OR digest LIKE ?)"
        params += [f"%{keyword}%", f"%{keyword}%"]
    sql += " ORDER BY publish_ts DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_accounts():
    conn = _conn()
    rows = conn.execute("SELECT a.*, COUNT(ar.id) AS n FROM accounts a LEFT JOIN articles ar ON ar.account_id=a.id GROUP BY a.id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_content(article_id, text, ok=True, error=""):
    conn = _conn()
    from datetime import datetime
    status = "ok" if ok else ("fail:" + error[:80])
    conn.execute("UPDATE articles SET content=?, content_status=?, content_at=? WHERE id=?",
                 (text or "", status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), article_id))
    conn.commit()
    conn.close()


def get_articles_by_ids(ids):
    if not ids:
        return []
    conn = _conn()
    marks = ",".join("?" for _ in ids)
    rows = conn.execute(f"SELECT * FROM articles WHERE id IN ({marks})", ids).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_archived(keyword=""):
    conn = _conn()
    sql = "SELECT * FROM articles WHERE content_status='ok'"
    params = []
    if keyword:
        sql += " AND (title LIKE ? OR content LIKE ?)"
        params += [f"%{keyword}%", f"%{keyword}%"]
    sql += " ORDER BY publish_ts DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_all():
    conn = _conn()
    n = conn.execute("SELECT COUNT(*) AS n FROM articles").fetchone()["n"]
    conn.close()
    return n


def clear_all():
    conn = _conn()
    conn.execute("DELETE FROM articles")
    conn.execute("DELETE FROM accounts")
    conn.commit()
    conn.close()


init_db()
