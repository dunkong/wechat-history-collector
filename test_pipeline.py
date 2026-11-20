"""用模拟的 getmsg 响应测试：解析 → 存储去重 → 导出全链路（不依赖真实抓包）"""
import json
import sys
import tempfile
from pathlib import Path

# 隔离到临时目录：绝不污染真实数据库与导出文件
_TMP = Path(tempfile.mkdtemp(prefix="wxc_test_"))
from core import config as _cfg  # noqa: E402
_cfg.DB_PATH = _TMP / "articles.db"
_cfg.EXPORT_DIR = _TMP / "exports"
_cfg.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
from core import store as _store  # noqa: E402
_store.DB_PATH = _cfg.DB_PATH
import sqlite3 as _sqlite3  # noqa: E402
def _tmp_conn():
    c = _sqlite3.connect(str(_cfg.DB_PATH))
    c.row_factory = _sqlite3.Row
    return c
_store._conn = _tmp_conn
_store.init_db()  # 在临时库建表
from core import exporter as _exporter  # noqa: E402
_exporter.EXPORT_DIR = _cfg.EXPORT_DIR

from core import collector, exporter, seed, store  # noqa: E402

store._conn = _store._conn
store.DB_PATH = _cfg.DB_PATH

print("=" * 50)
print("TEST 1: 种子链接解析 __biz")
ok_biz = "https://mp.weixin.qq.com/s?__biz=MzA5MDMwMTIyNQ==&mid=1&idx=1&sn=abc"
biz, err = seed.extract_biz(ok_biz)
assert biz == "MzA5MDMwMTIyNQ==", (biz, err)
print(f"  PASS  biz={biz}")

print("=" * 50)
print("TEST 2: 解析 general_msg_list（含多图文 + 时间）")
msg_list = {
    "list": [
        {
            "comm_msg_info": {"datetime": 1700000000, "type": 49},
            "app_msg_ext_info": {
                "title": "第一篇文章", "digest": "摘要A", "author": "作者甲",
                "content_url": "https://mp.weixin.qq.com/s?__biz=X&mid=1&idx=1&sn=a&amp;chksm=y",
                "cover": "http://mmbiz.qpic.cn/a.jpg",
                "multi_app_msg_item_list": [
                    {"title": "次条文章", "digest": "摘要B", "author": "作者甲",
                     "content_url": "https://mp.weixin.qq.com/s?__biz=X&mid=1&idx=2&sn=b",
                     "cover": "http://mmbiz.qpic.cn/b.jpg"}
                ],
            },
        },
        {"comm_msg_info": {"datetime": 1699900000, "type": 1}},  # 非图文，应跳过
    ]
}
arts = collector.parse_msg_list(json.dumps(msg_list, ensure_ascii=False))
assert len(arts) == 2, arts
assert arts[0]["title"] == "第一篇文章"
assert "&amp;" not in arts[0]["url"], arts[0]["url"]
assert arts[1]["is_multi"] == 1
assert arts[0]["publish_time"].startswith("2023-"), arts[0]["publish_time"]
print(f"  PASS  解析出 {len(arts)} 篇，URL 已清洗，时间={arts[0]['publish_time']}")

print("=" * 50)
print("TEST 3: 存储去重")
store.clear_all()
aid = store.get_or_create_account(biz, "测试公众号")
n1 = store.save_articles(aid, arts)
n2 = store.save_articles(aid, arts)  # 重复入库
assert n1 == 2, n1
assert n2 == 0, n2
rows = store.list_articles()
assert len(rows) == 2
print(f"  PASS  首次入库 {n1}，重复入库 {n2}，当前共 {len(rows)} 篇")

print("=" * 50)
print("TEST 4: 多格式导出")
paths = exporter.export_all(rows, "测试公众号")
for k, v in paths.items():
    assert __import__('pathlib').Path(v).exists(), v
print(f"  PASS  CSV / XLSX / HTML / JSON 全部生成")
for k, v in paths.items():
    print(f"        {k}: {v}")

print("=" * 50)
print("TEST 5: 关键词搜索")
res = store.list_articles(keyword="次条")
assert len(res) == 1 and res[0]["title"] == "次条文章", res
print(f"  PASS  搜索命中 {len(res)} 篇")

print("=" * 50)
print("ALL TESTS PASSED ✓")
