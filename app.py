"""本地网页服务：种子解析 / 抓包控制 / 翻页采集 / 查看导出。仅监听 127.0.0.1。"""
import json
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, send_file

from core import capture, collector, content as content_mod, exporter, seed, store
from core.control import TaskControl
from core.config import ROOT, WEB_PORT, EXPORT_DIR

app = Flask(__name__, static_folder=None)
WEB = ROOT / "web"

_progress = {"running": False, "page": 0, "got": 0, "total": 0, "done": False, "error": "", "reached_end": False, "paused": False, "stopped": False}
_content_progress = {"running": False, "done": 0, "total": 0, "ok": 0, "fail": 0, "finished": False, "paused": False, "stopped": False}
_current = {"biz": "", "name": ""}
_list_control = TaskControl()   # 列表采集控制器
_content_control = TaskControl()  # 正文抓取控制器


@app.route("/")
def index():
    return send_from_directory(str(WEB), "index.html")


@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(str(WEB), path)


@app.route("/api/seed", methods=["POST"])
def api_seed():
    url = request.json.get("url", "")
    biz, err = seed.extract_biz(url)
    if err:
        return jsonify({"ok": False, "error": err})
    _current["biz"] = biz
    aid = store.get_or_create_account(biz)
    return jsonify({"ok": True, "biz": biz, "account_id": aid})


@app.route("/api/account/name", methods=["POST"])
def api_account_name():
    name = request.json.get("name", "").strip()
    if _current["biz"] and name:
        store.get_or_create_account(_current["biz"], name)
        _current["name"] = name
    return jsonify({"ok": True})


@app.route("/api/capture/start", methods=["POST"])
def api_capture_start():
    capture.clear_auth()
    ok1, msg1 = capture.start_mitm()
    # 抓包进程没起来绝不开代理（否则断网）
    if not ok1:
        return jsonify({"ok": False, "mitm": msg1, "proxy": "已跳过开启代理（避免断网）",
                        "profile_url": ""})
    ok2, msg2 = capture.enable_system_proxy()
    return jsonify({"ok": ok1 and ok2, "mitm": msg1, "proxy": msg2,
                    "profile_url": capture.build_profile_url(_current["biz"]) if _current["biz"] else ""})


@app.route("/api/network/reset", methods=["POST"])
def api_network_reset():
    """一键急救：强制关闭指向本工具端口的代理，恢复网络。"""
    capture.stop_mitm()
    ok, msg = capture.disable_system_proxy()
    capture._state["auto_recovered"] = "已手动执行网络急救，代理强制关闭。"
    return jsonify({"ok": True, "msg": "系统代理已强制关闭，网络应已恢复。" + ("" if ok else f" ({msg})")})


@app.route("/api/capture/status")
def api_capture_status():
    st = capture.status()
    fresh, auth = capture.is_auth_fresh()
    st["auth_fresh"] = fresh
    st["biz"] = _current.get("biz", "")
    st["profile_url"] = capture.build_profile_url(_current["biz"]) if _current.get("biz") else ""
    if auth:
        st["biz"] = auth["auth"].get("biz", "") or st["biz"]
    return jsonify(st)


@app.route("/api/capture/stop", methods=["POST"])
def api_capture_stop():
    _, m1 = capture.disable_system_proxy()
    _, m2 = capture.stop_mitm()
    return jsonify({"ok": True, "msg": f"{m1}；{m2}"})


def _run_collect(max_pages):
    global _progress
    auth = capture.read_auth()
    if not auth:
        _progress.update(running=False, error="未捕获到凭证")
        return
    def prog(page, got, total):
        _progress.update(page=page, got=got, total=total)
    def state_poll():
        # 后台轮询暂停状态，写入 progress 供前端显示
        while _progress.get("running"):
            _progress["paused"] = _list_control.is_paused()
            time.sleep(0.3)
    threading.Thread(target=state_poll, daemon=True).start()
    try:
        res = collector.collect(auth, store.get_or_create_account(_current["biz"] or auth["auth"].get("biz", "")),
                                max_pages=max_pages, progress=prog, control=_list_control)
        _progress.update(running=False, done=True, error=res["error"] or "", paused=False,
                         page=res["pages"], total=res["new_count"], reached_end=res.get("reached_end", False),
                         stopped=res.get("stopped", False))
    except Exception as e:
        _progress.update(running=False, error=str(e), paused=False)


@app.route("/api/collect", methods=["POST"])
def api_collect():
    global _progress
    fresh, _ = capture.is_auth_fresh()
    if not fresh:
        return jsonify({"ok": False, "error": "凭证未捕获或已过期，请先完成抓包步骤"})
    try:
        max_pages = int((request.json or {}).get("max_pages", 500))
    except (TypeError, ValueError):
        max_pages = 500
    if max_pages <= 0:
        max_pages = 3000  # 0 = 尽量拉全
    _list_control.reset()
    _progress = {"running": True, "page": 0, "got": 0, "total": 0, "done": False, "error": "", "reached_end": False,
                 "paused": False, "stopped": False}
    threading.Thread(target=_run_collect, args=(max_pages,), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/collect/pause", methods=["POST"])
def api_collect_pause():
    if not _progress.get("running"):
        return jsonify({"ok": False, "error": "当前没有进行中的采集"})
    if _list_control.is_paused():
        _list_control.resume()
        return jsonify({"ok": True, "action": "resumed"})
    _list_control.pause()
    return jsonify({"ok": True, "action": "paused"})


@app.route("/api/collect/stop", methods=["POST"])
def api_collect_stop():
    _list_control.stop()
    return jsonify({"ok": True, "msg": "正在停止，已采集的数据会保留入库"})


@app.route("/api/progress")
def api_progress():
    return jsonify(_progress)


@app.route("/api/articles")
def api_articles():
    kw = request.args.get("keyword", "")
    return jsonify(store.list_articles(keyword=kw))


@app.route("/api/accounts")
def api_accounts():
    return jsonify(store.list_accounts())


@app.route("/api/stats")
def api_stats():
    return jsonify({"total": store.count_all()})


@app.route("/api/export", methods=["POST"])
def api_export():
    fmt = request.json.get("format", "xlsx")
    rows = store.list_articles()
    if not rows:
        return jsonify({"ok": False, "error": "暂无文章"})
    name = _current["name"] or "wechat_articles"
    paths = exporter.export_all(rows, name)
    if fmt not in paths:
        return jsonify({"ok": False, "error": "未知格式"})
    return jsonify({"ok": True, "file": paths[fmt], "all": paths})


def _run_fetch_content(ids):
    global _content_progress
    arts = store.get_articles_by_ids(ids)
    def prog(done, total, ok):
        _content_progress.update(done=done, total=total, ok=_content_progress["ok"] + (1 if ok else 0),
                                 fail=_content_progress["fail"] + (0 if ok else 1))
    def state_poll():
        while _content_progress.get("running"):
            _content_progress["paused"] = _content_control.is_paused()
            time.sleep(0.3)
    threading.Thread(target=state_poll, daemon=True).start()
    try:
        # 带上抓包凭证的 Cookie/UA，模拟微信内置浏览器，提高正文页抓取成功率
        auth = capture.read_auth()
        headers = None
        if auth:
            headers = {"User-Agent": auth.get("user_agent") or content_mod.UA_WECHAT,
                       "Cookie": auth.get("cookie", ""),
                       "Referer": "https://mp.weixin.qq.com/"}
        results, stopped = content_mod.fetch_articles(arts, progress=prog, headers=headers, control=_content_control)
        for aid, res in results.items():
            store.save_content(aid, res.get("text", ""), ok=res.get("ok", False), error=res.get("error", ""))
        _content_progress.update(running=False, finished=True, paused=False, stopped=stopped)
    except Exception as e:
        _content_progress.update(running=False, finished=True, paused=False, fail=_content_progress["fail"] + 1)
        app.logger.error(f"fetch content error: {e}")


@app.route("/api/content/fetch", methods=["POST"])
def api_content_fetch():
    global _content_progress
    ids = (request.json or {}).get("ids", [])
    arts = store.get_articles_by_ids(ids)
    if not arts:
        return jsonify({"ok": False, "error": "未选中任何文章"})
    _content_control.reset()
    _content_progress = {"running": True, "done": 0, "total": len(arts), "ok": 0, "fail": 0, "finished": False,
                         "paused": False, "stopped": False}
    threading.Thread(target=_run_fetch_content, args=([a["id"] for a in arts],), daemon=True).start()
    return jsonify({"ok": True, "total": len(arts)})


@app.route("/api/content/progress")
def api_content_progress():
    return jsonify(_content_progress)


@app.route("/api/content/pause", methods=["POST"])
def api_content_pause():
    if not _content_progress.get("running"):
        return jsonify({"ok": False, "error": "当前没有进行中的正文抓取"})
    if _content_control.is_paused():
        _content_control.resume()
        return jsonify({"ok": True, "action": "resumed"})
    _content_control.pause()
    return jsonify({"ok": True, "action": "paused"})


@app.route("/api/content/stop", methods=["POST"])
def api_content_stop():
    _content_control.stop()
    return jsonify({"ok": True, "msg": "正在停止，已抓取的正文会保留"})


@app.route("/api/archived")
def api_archived():
    kw = request.args.get("keyword", "")
    return jsonify(store.list_archived(kw))


@app.route("/api/export/archive", methods=["POST"])
def api_export_archive():
    kw = (request.json or {}).get("keyword", "")
    rows = store.list_archived(kw)
    if not rows:
        return jsonify({"ok": False, "error": "暂无已归档正文，请先勾选文章抓取正文"})
    name = _current["name"] or "wechat_articles"
    return jsonify({"ok": True,
                    "html": exporter.export_archive_html(rows, name),
                    "zip": exporter.export_archive_md_zip(rows, name)})


@app.route("/api/download")
def api_download():
    p = request.args.get("path", "")
    fp = Path(p)
    if not fp.exists() or EXPORT_DIR.resolve() not in fp.resolve().parents:
        return "file not found", 404
    return send_file(str(fp), as_attachment=True)


if __name__ == "__main__":
    print(f"\n  公众号历史文章采集  →  http://127.0.0.1:{WEB_PORT}\n")
    app.run(host="127.0.0.1", port=WEB_PORT, debug=False)
