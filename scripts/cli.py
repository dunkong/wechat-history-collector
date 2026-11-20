#!/usr/bin/env python3
"""公众号历史文章采集器 · 命令行入口。

为 AI 自动调用/自动化设计：所有命令输出单行 JSON，便于程序解析。
用法见 README 或 `python scripts/cli.py --help`。
"""
import argparse
import json
import sys
import time
from pathlib import Path

# 让脚本从任意目录运行都能 import core
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import capture, collector, content as content_mod, exporter, seed, store  # noqa: E402


def out(obj):
    print(json.dumps(obj, ensure_ascii=False))


def cmd_seed(args):
    biz, err = seed.extract_biz(args.url)
    if err:
        out({"ok": False, "error": err})
        return 1
    aid = store.get_or_create_account(biz, args.name)
    out({"ok": True, "biz": biz, "account_id": aid,
         "profile_url": capture.build_profile_url(biz)})
    return 0


def cmd_capture_start(args):
    capture.clear_auth()
    ok1, m1 = capture.start_mitm()
    if not ok1:
        out({"ok": False, "stage": "mitm", "message": m1})
        return 1
    ok2, m2 = capture.enable_system_proxy()
    out({"ok": ok2, "stage": "proxy", "message": m2,
         "profile_url": capture.build_profile_url(args.biz) if args.biz else "",
         "hint": "把 profile_url 复制到微信电脑版文件传输助手并点开，凭证会自动捕获"})
    return 0 if ok2 else 1


def cmd_capture_status(args):
    st = capture.status()
    fresh, auth = capture.is_auth_fresh()
    st["auth_fresh"] = fresh
    if auth:
        st["biz"] = auth["auth"].get("biz", "")
    out(st)
    return 0


def cmd_capture_stop(args):
    _, m1 = capture.disable_system_proxy()
    _, m2 = capture.stop_mitm()
    out({"ok": True, "message": f"{m1}；{m2}"})
    return 0


def cmd_network_reset(args):
    capture.stop_mitm()
    ok, msg = capture.disable_system_proxy()
    out({"ok": True, "message": "系统代理已强制关闭，网络应已恢复。" + ("" if ok else f" ({msg})")})
    return 0


def cmd_collect(args):
    auth = capture.read_auth()
    if not auth:
        out({"ok": False, "error": "未捕获到凭证，请先执行 capture start 并在微信里点开主页链接"})
        return 1
    fresh, _ = capture.is_auth_fresh()
    if not fresh and not args.force:
        out({"ok": False, "error": "凭证可能已过期（>30分钟），建议重新抓包；确要继续请加 --force"})
        return 1
    biz = args.biz or auth["auth"].get("biz", "")
    if not biz:
        out({"ok": False, "error": "缺少 biz，请用 --biz 指定"})
        return 1
    aid = store.get_or_create_account(biz, args.name)
    max_pages = 3000 if args.pages <= 0 else args.pages
    res = collector.collect(auth, aid, max_pages=max_pages)
    out({"ok": not bool(res["error"]), "pages": res["pages"], "new_count": res["new_count"],
         "reached_end": res["reached_end"], "stopped": res["stopped"],
         "error": res["error"], "total_in_db": store.count_all()})
    return 0


def cmd_content(args):
    if args.all:
        rows = store.list_articles()
        ids = [r["id"] for r in rows if not r.get("content_status") == "ok"]
    else:
        ids = args.ids
    if not ids:
        out({"ok": False, "error": "没有待抓取正文的文章"})
        return 1
    arts = store.get_articles_by_ids(ids)
    auth = capture.read_auth()
    headers = None
    if auth:
        headers = {"User-Agent": auth.get("user_agent") or content_mod.UA_WECHAT,
                   "Cookie": auth.get("cookie", ""), "Referer": "https://mp.weixin.qq.com/"}
    results, _ = content_mod.fetch_articles(arts, headers=headers, delay=args.delay)
    ok_n = 0
    for aid, res in results.items():
        good = res.get("ok", False)
        ok_n += 1 if good else 0
        store.save_content(aid, res.get("text", ""), ok=good, error=res.get("error", ""))
    out({"ok": True, "attempted": len(arts), "success": ok_n})
    return 0


def cmd_export(args):
    rows = store.list_articles()
    if not rows:
        out({"ok": False, "error": "暂无文章"})
        return 1
    paths = exporter.export_all(rows, args.name or "wechat_articles")
    out({"ok": True, "files": paths})
    return 0


def cmd_archive(args):
    rows = store.list_archived(args.keyword)
    if not rows:
        out({"ok": False, "error": "暂无已归档正文，请先执行 content 抓取正文"})
        return 1
    name = args.name or "wechat_articles"
    out({"ok": True, "html": exporter.export_archive_html(rows, name),
         "zip": exporter.export_archive_md_zip(rows, name), "count": len(rows)})
    return 0


def cmd_status(args):
    out({"total": store.count_all(), "accounts": store.list_accounts()})
    return 0


def main():
    p = argparse.ArgumentParser(description="公众号历史文章采集器 CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("seed", help="解析种子链接得到 biz")
    ps.add_argument("url"); ps.add_argument("--name", default=""); ps.set_defaults(fn=cmd_seed)

    pc = sub.add_parser("capture", help="抓包控制")
    pc.add_argument("action", choices=["start", "status", "stop"])
    pc.add_argument("--biz", default=""); pc.set_defaults(fn=lambda a: {
        "start": cmd_capture_start, "status": cmd_capture_status, "stop": cmd_capture_stop}[a.action](a))

    sub.add_parser("reset", help="一键恢复网络（关闭代理）").set_defaults(fn=cmd_network_reset)

    pco = sub.add_parser("collect", help="翻页采集历史文章")
    pco.add_argument("--biz", default=""); pco.add_argument("--name", default="")
    pco.add_argument("--pages", type=int, default=0, help="0=尽量拉全")
    pco.add_argument("--force", action="store_true", help="凭证过期时仍继续")
    pco.set_defaults(fn=cmd_collect)

    pct = sub.add_parser("content", help="抓取正文")
    g = pct.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="抓所有未归档文章")
    g.add_argument("--ids", type=int, nargs="+", help="指定文章 ID")
    pct.add_argument("--delay", type=float, default=0.4); pct.set_defaults(fn=cmd_content)

    pe = sub.add_parser("export", help="导出元数据多格式")
    pe.add_argument("--name", default=""); pe.set_defaults(fn=cmd_export)

    pa = sub.add_parser("archive", help="导出正文归档")
    pa.add_argument("--name", default=""); pa.add_argument("--keyword", default=""); pa.set_defaults(fn=cmd_archive)

    sub.add_parser("status", help="查看入库统计").set_defaults(fn=cmd_status)

    args = p.parse_args()
    try:
        code = args.fn(args)
    except Exception as e:
        out({"ok": False, "error": f"{type(e).__name__}: {e}"})
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    main()
