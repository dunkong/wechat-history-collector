"""抓取公众号文章正文。纯标准库实现，零新增依赖。"""
import re
import time
from html.parser import HTMLParser

import requests

UA_WECHAT = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0")


class _ContentParser(HTMLParser):
    """提取 id=js_content 节点内的正文文本与图片。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.parts = []
        self.images = []
        self._in_title = False
        self._in_content = False
        self._div_depth = 0
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag == "div" and d.get("id") == "js_content" and not self._in_content:
            self._in_content = True
            self._div_depth = 1
            return
        if not self._in_content:
            return
        if tag == "div":
            self._div_depth += 1
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "img":
            src = d.get("data-src") or d.get("src") or ""
            if src.startswith("http"):
                self.images.append(src)
                self.parts.append(f"[图片 {len(self.images)}]")
        if tag in ("p", "br", "section", "div", "h1", "h2", "h3", "li", "blockquote"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if not self._in_content:
            return
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        if tag == "div":
            self._div_depth -= 1
            if self._div_depth <= 0:
                self._in_content = False
                return
        if tag in ("p", "section", "div", "h1", "h2", "h3", "li", "blockquote"):
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title and not self.title:
            t = data.strip()
            if t:
                self.title = t
        if self._in_content and not self._skip:
            t = data.strip()
            if t:
                self.parts.append(t)

    def text(self):
        lines = []
        for p in self.parts:
            if p.startswith("[图片"):
                lines.append(p)
                continue
            s = p.strip()
            if s:
                lines.append(s)
        # 合并连续图片标注到同一行
        out = []
        for ln in lines:
            if ln.startswith("[图片") and out and out[-1].startswith("[图片"):
                out[-1] += " " + ln
            else:
                out.append(ln)
        return "\n".join(out)


def parse_article_html(raw_html):
    p = _ContentParser()
    p.feed(raw_html)
    return {"title": p.title, "text": p.text(), "images": p.images}


def fetch_article(url, timeout=20, headers=None, retries=2):
    """抓取单篇文章正文。返回 {ok, title, text, images, error}。
    带重试：微信偶尔返回空壳/验证页，重试可显著提高成功率。"""
    if not url:
        return {"ok": False, "error": "空链接"}
    h = dict(headers) if headers else {"User-Agent": UA_WECHAT}
    last_err = "未知错误"
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=h, timeout=timeout)
            raw = r.text
        except Exception as e:
            last_err = f"请求失败：{e}"
            time.sleep(0.6)
            continue
        head = raw[:3000]
        if "环境异常" in head or "去验证" in head:
            last_err = "触发微信验证"
            time.sleep(0.8)
            continue
        info = parse_article_html(raw)
        if info["text"]:
            info["ok"] = True
            return info
        if "js_content" in raw.lower():
            last_err = "正文节点存在但无文本（可能为纯图片/视频文章）"
            break  # 这类文章重试无意义
        last_err = "未找到正文节点（空壳页，重试中）"
        time.sleep(0.8)
    return {"ok": False, "error": last_err}


def fetch_articles(articles, progress=None, delay=0.5, headers=None, control=None):
    """批量抓取。articles=[{'id','url'}]. 进度回调 progress(done,total,ok)。
    control 可选，含 is_stopped()/wait_if_paused()。返回 (results, stopped)。"""
    results = {}
    total = len(articles)
    stopped = False
    for i, art in enumerate(articles, 1):
        if control:
            if control.is_stopped():
                stopped = True
                break
            control.wait_if_paused()
            if control.is_stopped():
                stopped = True
                break
        res = fetch_article(art.get("url", ""), headers=headers)
        results[art["id"]] = res
        if progress:
            progress(i, total, res.get("ok", False))
        if i < total:
            time.sleep(delay)
    return results, stopped
