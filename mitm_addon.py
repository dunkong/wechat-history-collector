"""
mitmproxy addon：截获微信内置浏览器的临时凭证与 Cookie。

捕获公众号主页请求（profile_ext?action=home），拿到
key / pass_ticket / uin / biz，写入凭证文件供翻页采集使用。
"""
import json
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

DATA_DIR = Path(__file__).resolve().parent / "data"
AUTH_PATH = DATA_DIR / "captured_auth.json"

UA_FALLBACK = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 MicroMessenger/8.0")


def _read():
    try:
        return json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write(payload: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AUTH_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _merge_auth(new_auth: dict, meta: dict):
    """合并进现有凭证：只填空缺字段，不覆盖已有的有效值。"""
    data = _read()
    old_auth = dict(data.get("auth", {}))
    for k, v in new_auth.items():
        if v and not old_auth.get(k):
            old_auth[k] = v
    data["auth"] = old_auth
    for k, v in meta.items():
        if v and not data.get(k):
            data[k] = v
    # cookie / ua 用最新的（更可能有效）
    if meta.get("cookie"):
        data["cookie"] = meta["cookie"]
    if meta.get("user_agent"):
        data["user_agent"] = meta["user_agent"]
    data["captured_at"] = time.time()
    _write(data)
    return data


def request(flow):
    url = flow.request.pretty_url
    if "mp.weixin.qq.com" not in url:
        return

    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    cookie = flow.request.headers.get("Cookie", "")
    ua = flow.request.headers.get("User-Agent", UA_FALLBACK)
    meta = {"url": url, "cookie": cookie, "user_agent": ua}

    # 公众号主页：key / pass_ticket / uin / biz
    if "/mp/profile_ext" in url and params.get("action", [""])[0] == "home":
        key = params.get("key", [""])[0]
        if not key:
            return
        _merge_auth({
            "key": key,
            "pass_ticket": params.get("pass_ticket", [""])[0],
            "uin": params.get("uin", [""])[0],
            "biz": params.get("__biz", [""])[0],
        }, {"referer": flow.request.headers.get("Referer", ""), **meta})
        print("\n[AUTH CAPTURED] 主页凭证 key=%s... cookie=%s" % (key[:16], "YES" if cookie else "NO"))
