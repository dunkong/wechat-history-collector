"""用抓到的凭证翻页拉取历史文章列表并入库。"""
import json
import re
import time
from datetime import datetime

import requests

from . import store
from .config import GETMSG_URL, UA

UA_MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0")


def clean_content_url(url):
    if not url:
        return ""
    return url.replace("&amp;", "&")


def parse_msg_list(raw):
    """general_msg_list 是 JSON 字符串，解析为文章 dict 列表（含多图文）。"""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    out = []
    for item in raw.get("list", []):
        ts = item.get("comm_msg_info", {}).get("datetime", 0)
        pub = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else ""
        ext = item.get("app_msg_ext_info")
        if not ext:
            continue  # 非图文消息（图片/视频/纯文本）跳过
        entries = []
        entries.append((ext, 0))
        for sub in ext.get("multi_app_msg_item_list", []) or []:
            entries.append((sub, 1))
        for info, idx in entries:
            url = clean_content_url(info.get("content_url", ""))
            title = (info.get("title") or "").strip()
            if not url or not title:
                continue
            out.append({
                "title": title,
                "digest": (info.get("digest") or "").strip(),
                "author": (info.get("author") or "").strip(),
                "cover": info.get("cover", "") or "",
                "url": url,
                "publish_time": pub,
                "publish_ts": ts,
                "is_multi": idx,
                "source_url": info.get("source_url", "") or "",
            })
    return out


def collect(auth, account_id, max_pages=500, delay=0.6, progress=None, control=None):
    """
    auth: capture.read_auth() 返回结构
    max_pages: 最多翻页数（默认 500，会一直翻到微信返回 continue=0 为止）
    progress: 进度回调 fn(page, got, total)
    control: 可选控制对象，含 is_stopped()/wait_if_paused() 方法
    返回 {articles, pages, new_count, error, reached_end, stopped}
    """
    a = auth["auth"]
    biz = a.get("biz") or ""
    headers = {
        "User-Agent": auth.get("user_agent") or UA_MOBILE,
        "Cookie": auth.get("cookie", ""),
        "Referer": auth.get("referer") or f"https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz={biz}",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
    }
    params = {
        "action": "getmsg",
        "__biz": biz,
        "f": "json",
        "offset": 0,
        "count": 20,
        "is_ok": 1,
        "scene": 124,
        "uin": a.get("uin", ""),
        "key": a.get("key", ""),
        "pass_ticket": a.get("pass_ticket", ""),
        "x5": 0,
    }
    all_articles = []
    pages = 0
    error = None
    reached_end = False
    empty_streak = 0
    try:
        max_pages = max(1, min(int(max_pages), 3000))
    except (TypeError, ValueError):
        max_pages = 500

    sess = requests.Session()
    stopped = False
    for page in range(max_pages):
        # 暂停/停止控制：每页开始前检查
        if control:
            if control.is_stopped():
                stopped = True
                break
            control.wait_if_paused()
            if control.is_stopped():
                stopped = True
                break
        try:
            r = sess.get(GETMSG_URL, params=params, headers=headers, timeout=20)
            data = r.json()
        except Exception as e:
            error = f"第 {page+1} 页请求失败：{e}"
            break

        ret = data.get("ret", -1)
        if ret != 0:
            error = f"第 {page+1} 页返回异常 ret={ret}：{data.get('errmsg','')}（凭证可能已过期）"
            break

        arts = parse_msg_list(data.get("general_msg_list", ""))
        all_articles.extend(arts)
        pages += 1
        if progress:
            progress(page + 1, len(arts), len(all_articles))

        can_continue = int(data.get("can_msg_continue", 0))
        if not can_continue:
            reached_end = True
            break
        if not arts:
            empty_streak += 1
            if empty_streak >= 3:
                error = "连续 3 页无文章，判定已到历史底部，自动停止"
                reached_end = True
                break
        else:
            empty_streak = 0
        nxt = data.get("next_offset")
        params["offset"] = int(nxt) if str(nxt).isdigit() else (params["offset"] + 20)
        time.sleep(delay)
    else:
        # for 循环自然走完（没 break）→ 触及页数上限但微信仍说有更多
        error = f"达到设定的 {max_pages} 页上限（微信仍显示有更多），可增大页数后再次采集（会自动去重）"

    new_count = store.save_articles(account_id, all_articles)
    if stopped:
        error = None  # 用户主动停止不算错误
    return {
        "articles": all_articles,
        "pages": pages,
        "new_count": new_count,
        "error": error,
        "reached_end": reached_end,
        "stopped": stopped,
    }
