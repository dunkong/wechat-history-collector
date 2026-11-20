"""导出 CSV / Excel / HTML / JSON。HTML 为自带搜索的离线单文件。"""
import csv
import html
import json
import time
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill

from .config import EXPORT_DIR

FIELDS = ["publish_time", "title", "digest", "author", "url"]


def _safe_name(name):
    return "".join(c for c in (name or "export") if c not in r'\/:*?"<>|').strip()[:40] or "export"


def export_csv(rows, name="articles"):
    path = EXPORT_DIR / f"{_safe_name(name)}.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return str(path)


def export_json(rows, name="articles"):
    path = EXPORT_DIR / f"{_safe_name(name)}.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def export_excel(rows, name="articles"):
    path = EXPORT_DIR / f"{_safe_name(name)}.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "历史文章"
    headers = ["发布时间", "标题", "摘要", "作者", "链接"]
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="305496")
        c.alignment = Alignment(vertical="center")
    for r in rows:
        ws.append([r.get("publish_time", ""), r.get("title", ""), r.get("digest", ""),
                   r.get("author", ""), r.get("url", "")])
    widths = [20, 46, 60, 14, 50]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = w
    ws.freeze_panes = "A2"
    wb.save(path)
    return str(path)


def export_html(rows, name="articles"):
    path = EXPORT_DIR / f"{_safe_name(name)}.html"
    cards = []
    for r in rows:
        t = html.escape(r.get("title", ""))
        d = html.escape(r.get("digest", ""))
        u = html.escape(r.get("url", ""))
        pt = html.escape(r.get("publish_time", ""))
        au = html.escape(r.get("author", ""))
        cards.append(
            f'<article class="card" data-t="{t.lower()}" data-d="{d.lower()}">'
            f'<div class="meta">{pt}　·　{au}</div>'
            f'<h3><a href="{u}" target="_blank" rel="noopener">{t}</a></h3>'
            f'<p>{d}</p>'
            f'<a class="lnk" href="{u}" target="_blank" rel="noopener">阅读原文 →</a>'
            f'</article>')
    doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(name)} · 历史文章</title>
<style>
body{{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;max-width:820px;margin:0 auto;padding:24px;color:#1a1a1a;background:#fafafa}}
h1{{font-size:22px;font-weight:600}}
.bar{{position:sticky;top:0;background:#fafafa;padding:12px 0;z-index:2}}
input{{width:100%;box-sizing:border-box;padding:10px 12px;font-size:14px;border:1px solid #ddd;border-radius:8px}}
.card{{background:#fff;border:1px solid #eee;border-radius:10px;padding:16px 18px;margin-bottom:12px}}
.meta{{color:#888;font-size:12px}}
.card h3{{margin:6px 0;font-size:16px;font-weight:600}}
.card h3 a{{color:#1a1a1a;text-decoration:none}}
.card p{{color:#555;font-size:13px;line-height:1.6;margin:6px 0}}
.lnk{{color:#576b95;font-size:13px;text-decoration:none}}
.count{{color:#888;font-size:13px;margin:8px 0}}
</style></head><body>
<h1>{html.escape(name)} · 历史文章</h1>
<div class="count" id="cnt">共 {len(rows)} 篇 · 生成于 {time.strftime('%Y-%m-%d %H:%M')}</div>
<div class="bar"><input id="q" placeholder="搜索标题或摘要…" oninput="filter()"></div>
<div id="list">{''.join(cards)}</div>
<script>
function filter(){{var q=document.getElementById('q').value.toLowerCase();var cs=document.querySelectorAll('.card');var n=0;
cs.forEach(function(c){{var ok=c.dataset.t.indexOf(q)>=0||c.dataset.d.indexOf(q)>=0;c.style.display=ok?'':'none';if(ok)n++;}});
document.getElementById('cnt').textContent='显示 '+n+' / {len(rows)} 篇';}}
</script></body></html>"""
    path.write_text(doc, encoding="utf-8")
    return str(path)


def export_archive_html(rows, name="正文归档"):
    """离线单文件正文归档：左侧目录 + 右侧全文，自带搜索。"""
    import re
    items = []
    toc = []
    for i, r in enumerate(rows):
        title = html.escape(r.get("title", ""))
        pt = html.escape(r.get("publish_time", ""))
        url = html.escape(r.get("url", ""))
        raw = r.get("content", "") or ""
        body = "<br>".join(html.escape(x) for x in raw.split("\n") if x.strip())
        body = re.sub(r"(\[图片\s*\d+\])", r'<span class="imgtag">\1</span>', body)
        toc.append(f'<a href="#a{i}" class="toc-item" data-t="{title.lower()}">{i+1}. {title}</a>')
        items.append(
            f'<article class="arc" id="a{i}">'
            f'<div class="meta">{pt}</div>'
            f'<h2>{title}</h2>'
            f'<div class="body">{body or "<i>（无正文）</i>"}</div>'
            f'<div class="links"><a href="{url}" target="_blank" rel="noopener">阅读原文 →</a></div>'
            f'</article>')
    doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(name)}</title>
<style>
*{{box-sizing:border-box}}
body{{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;margin:0;color:#1a1a1a;background:#f5f5f5}}
.side{{position:fixed;left:0;top:0;bottom:0;width:290px;background:#fff;border-right:1px solid #e5e5e5;overflow-y:auto;padding:16px}}
.side h1{{font-size:17px;margin:0 0 12px}}
.side input{{width:100%;padding:9px 11px;border:1px solid #ddd;border-radius:7px;font-size:13px;margin-bottom:10px}}
.toc-item{{display:block;padding:6px 8px;color:#333;text-decoration:none;font-size:12.5px;border-radius:5px;line-height:1.4}}
.toc-item:hover{{background:#eef3ff;color:#305496}}
.main{{margin-left:290px;padding:28px 40px;max-width:900px}}
.arc{{background:#fff;border:1px solid #e8e8e8;border-radius:10px;padding:22px 26px;margin-bottom:18px}}
.arc .meta{{color:#999;font-size:12px}}
.arc h2{{font-size:19px;margin:8px 0 14px}}
.arc .body{{font-size:14.5px;line-height:1.9;color:#2b2b2b;white-space:normal}}
.imgtag{{color:#576b95;background:#eef3ff;padding:1px 6px;border-radius:4px;font-size:12px}}
.links{{margin-top:16px}}
.links a{{color:#576b95;font-size:13px;text-decoration:none}}
@media(max-width:760px){{.side{{position:static;width:100%;height:240px}}.main{{margin-left:0;padding:18px}}}}
</style></head><body>
<aside class="side"><h1>{html.escape(name)}</h1>
<div style="color:#999;font-size:12px;margin-bottom:10px">共 {len(rows)} 篇 · {time.strftime('%Y-%m-%d %H:%M')}</div>
<input id="q" placeholder="搜索标题…" oninput="flt()">
<div id="toc">{''.join(toc)}</div></aside>
<main class="main">{''.join(items)}</main>
<script>
function flt(){{var q=document.getElementById('q').value.toLowerCase();
document.querySelectorAll('.toc-item').forEach(function(a){{a.style.display=a.dataset.t.indexOf(q)>=0?'':'none';}});}}
</script></body></html>"""
    path = EXPORT_DIR / f"{_safe_name(name)}_正文归档.html"
    path.write_text(doc, encoding="utf-8")
    return str(path)


def export_archive_md_zip(rows, name="正文归档"):
    """每篇文章一个 Markdown 文件，打包成 ZIP。"""
    import zipfile
    path = EXPORT_DIR / f"{_safe_name(name)}_正文MD.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for i, r in enumerate(rows):
            title = (r.get("title") or f"article_{i+1}").replace("\n", " ")
            safe = "".join(c for c in title if c not in r'\\/:*?"<>|').strip()[:50] or f"article_{i+1}"
            fn = f"{i+1:03d}_{safe}.md"
            content = r.get("content", "") or ""
            md = (f"# {title}\n\n"
                  f"> 发布时间：{r.get('publish_time','')}  \n"
                  f"> 原文：{r.get('url','')}\n\n---\n\n{content}\n")
            z.writestr(fn, md)
    return str(path)


def export_all(rows, name="articles"):
    return {
        "csv": export_csv(rows, name),
        "xlsx": export_excel(rows, name),
        "html": export_html(rows, name),
        "json": export_json(rows, name),
    }
