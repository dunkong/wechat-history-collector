"""模拟 getmsg 分页响应，测试 collector.collect 完整翻页流程（mock HTTP，不发真实请求）"""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# 用临时数据库，避免污染真实采集数据
_tmpdb = Path(tempfile.gettempdir()) / "wxc_test_collect.db"
_tmpdb.unlink(missing_ok=True)
from core import config as _cfg  # noqa: E402
_cfg.DB_PATH = _tmpdb
from core import store as _store  # noqa: E402
_store.DB_PATH = _tmpdb
import sqlite3 as _sqlite3  # noqa: E402
def _tmp_conn():
    c = _sqlite3.connect(str(_tmpdb))
    c.row_factory = _sqlite3.Row
    return c
_store._conn = _tmp_conn
_tmpdb.parent.mkdir(parents=True, exist_ok=True)
_c = _sqlite3.connect(str(_tmpdb))
_c.execute("""CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY AUTOINCREMENT,
    biz TEXT UNIQUE NOT NULL, name TEXT DEFAULT '', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
_c.execute("""CREATE TABLE IF NOT EXISTS articles (id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL, url TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
    digest TEXT DEFAULT '', author TEXT DEFAULT '', cover TEXT DEFAULT '',
    publish_time TEXT DEFAULT '', publish_ts INTEGER DEFAULT 0, source_url TEXT DEFAULT '',
    content TEXT DEFAULT '', content_status TEXT DEFAULT '', content_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
_c.commit(); _c.close()

from core import collector  # noqa: E402
store = _store

aid = store.get_or_create_account("MzTestBiz==", "分页测试号")

# 造 3 页数据：第1页2篇，第2页2篇，第3页1篇后结束
def make_page(offset, count, more):
    lst = []
    for i in range(count):
        n = offset + i + 1
        lst.append({
            "comm_msg_info": {"datetime": 1700000000 + n * 3600, "type": 49},
            "app_msg_ext_info": {
                "title": f"文章{n}", "digest": f"摘要{n}", "author": "作者",
                "content_url": f"https://mp.weixin.qq.com/s?__biz=X&mid={n}&idx=1&sn=s{n}",
                "cover": "", "multi_app_msg_item_list": [],
            },
        })
    return {
        "ret": 0, "errmsg": "ok",
        "general_msg_list": json.dumps({"list": lst}, ensure_ascii=False),
        "next_offset": offset + count,
        "can_msg_continue": 1 if more else 0,
    }

pages = [make_page(0, 2, True), make_page(2, 2, True), make_page(4, 1, False)]

class FakeResp:
    def __init__(self, data): self._data = data
    def json(self): return self._data

calls = {"n": 0}
offsets_seen = []
def fake_get(self, url, params=None, headers=None, timeout=None):
    offsets_seen.append(params["offset"])
    data = pages[calls["n"] % len(pages)]
    calls["n"] += 1
    return FakeResp(data)

auth = {
    "captured_at": 9999999999,
    "auth": {"key": "fakekey", "pass_ticket": "fakept", "uin": "1", "biz": "MzTestBiz=="},
    "cookie": "fake=1", "referer": "", "user_agent": "UA",
}

with patch.object(collector.requests.Session, "get", fake_get):
    res = collector.collect(auth, aid, max_pages=10, delay=0)

print("pages fetched:", res["pages"])
print("offsets:", offsets_seen)
print("articles parsed:", len(res["articles"]))
print("new in db:", res["new_count"])
print("error:", res["error"])

assert res["pages"] == 3, res
assert offsets_seen == [0, 2, 4], offsets_seen
assert len(res["articles"]) == 5, len(res["articles"])
assert res["new_count"] == 5, res
assert res["error"] is None
assert store.count_all() == 5
print("\nPAGINATION TEST PASSED ✓")

_tmpdb.unlink(missing_ok=True)
