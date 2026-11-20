"""正文解析 + 归档导出 mock 测试（不发真实网络请求）。"""
import sys
from core import content, exporter, store

SAMPLE = """<html><head><title>测试文章标题</title></head><body>
<div id="js_content">
<p>这是第一段正文。</p>
<p>这是第二段，包含 <strong>加粗</strong> 内容。</p>
<img data-src="https://mmbiz.qpic.cn/aaa/0" />
<p>第三段。</p>
<script>var x='不应出现';</script>
</div></body></html>"""

def main():
    info = content.parse_article_html(SAMPLE)
    assert info["title"] == "测试文章标题", info["title"]
    assert "这是第一段正文" in info["text"], info["text"]
    assert "不应出现" not in info["text"], "script 未过滤"
    assert len(info["images"]) == 1, info["images"]
    print("1. 正文解析 OK, text=", repr(info["text"][:60]))
    # fetch_article 带 headers 与重试的新签名可调用
    assert callable(content.fetch_article) and callable(content.fetch_articles)

    # 造两条已归档数据测试导出
    store.init_db()
    aid = store.get_or_create_account("MOCK_BIZ_ARCHIVE", "测试号")
    arts = [
        {"title":"文章A","digest":"","author":"x","cover":"","url":"https://x/1",
         "publish_time":"2026-01-01","publish_ts":1,"source_url":""},
        {"title":"文章B","digest":"","author":"x","cover":"","url":"https://x/2",
         "publish_time":"2026-01-02","publish_ts":2,"source_url":""},
    ]
    ids = store.save_articles_and_get_ids(aid, arts) if hasattr(store, "save_articles_and_get_ids") else None
    # 用现有接口入库后取 id
    store.save_articles(aid, arts)
    rows = store.list_articles()
    target = [r for r in rows if r["url"] in ("https://x/1","https://x/2")]
    assert len(target) == 2
    for i, r in enumerate(target):
        store.save_content(r["id"], f"正文内容第{i+1}篇\n第二行", ok=True)
    archived = store.list_archived()
    assert len(archived) >= 2
    print("2. 正文存储 OK, archived=", len(archived))

    hp = exporter.export_archive_html(archived, "测试归档")
    zp = exporter.export_archive_md_zip(archived, "测试归档")
    import pathlib
    assert pathlib.Path(hp).exists() and pathlib.Path(zp).exists()
    html_txt = pathlib.Path(hp).read_text(encoding="utf-8")
    assert "文章A" in html_txt and "正文内容第" in html_txt
    print("3. 归档导出 OK:", hp, "|", zp)

    # 只清理本测试造的 mock 数据，绝不清空真实采集结果
    import sqlite3
    from core.config import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("DELETE FROM articles WHERE url IN ('https://x/1','https://x/2')")
    conn.execute("DELETE FROM accounts WHERE biz='MOCK_BIZ_ARCHIVE'")
    conn.commit()
    conn.close()
    print("4. mock 数据清理完成（真实采集数据不受影响）")

if __name__ == "__main__":
    main()
