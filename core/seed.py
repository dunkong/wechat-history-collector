"""从种子文章链接提取公众号 __biz 标识。

关键：__biz 是 base64 字符串（如 MzA5MDMwMTIyNQ==）。
微信页面里常出现 ${window.biz} 之类的 JS 占位符，必须校验拒绝，
否则会把模板变量当成账号标识。
"""
import re
import requests
from urllib.parse import urlparse, parse_qs, unquote

from .config import UA

# 真实 __biz：base64 字符集，长度通常 16~24（至少 8）。
# 用 [A-Za-z0-9=_\-] 覆盖微信实际值，且能排除 ${} / 引号 / 空格 等占位符。
BIZ_RE = re.compile(r"^[A-Za-z0-9=_\-]{8,}$")

# 按优先级排列：越靠前越可能是真实定义
BIZ_PATTERNS = [
    r'var\s+biz\s*=\s*["\']([^"\']+)["\']',
    r'window\.__biz\s*=\s*["\']([^"\']+)["\']',
    r'window\.biz\s*=\s*["\']([^"\']+)["\']',
    r'["\']?__biz["\']?\s*[:=]\s*["\']([^"\']+)["\']',
    r'"biz"\s*:\s*"([^"]+)"',
]


def valid_biz(value: str) -> bool:
    """校验是否为合法的 __biz。拒绝 ${...} 模板占位符等非法值。"""
    if not value:
        return False
    v = unquote(value).strip()
    return bool(BIZ_RE.fullmatch(v))


def extract_biz_from_html(html: str):
    """从文章 HTML 中提取第一个合法的 __biz；找不到返回 None。"""
    for pat in BIZ_PATTERNS:
        for m in re.finditer(pat, html):
            cand = m.group(1)
            if valid_biz(cand):
                return unquote(cand).strip()
    return None


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    return url


def extract_biz(url: str, timeout: int = 15):
    """
    返回 (biz, error)。
    优先从 URL 参数取；否则抓取文章 HTML 提取。
    """
    url = normalize_url(url)
    host = urlparse(url).netloc
    if "weixin.qq.com" not in host and "wechat.com" not in host:
        return None, "这不是微信文章链接（需 mp.weixin.qq.com）"

    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    for key in ("__biz", "biz"):
        if key in qs and qs[key][0]:
            cand = qs[key][0]
            if valid_biz(cand):
                return unquote(cand).strip(), None
            # URL 里是非法的占位符，继续尝试 HTML

    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
        html = resp.text
    except Exception as e:
        return None, f"抓取文章页失败：{e}"

    biz = extract_biz_from_html(html)
    if biz:
        return biz, None

    # 应对被验证页拦截 / 纯占位符页面：给出可操作的兜底提示
    if "${" in html or "window.biz" in html:
        return None, "页面只含动态占位符（如 ${window.biz}），未能取到真实 __biz。请在微信里打开文章，从链接参数中复制 __biz 手动填入。"
    if "验证" in html or "环境异常" in html or len(html) < 2000:
        return None, "文章页触发了微信验证，无法自动提取 __biz。请在微信里打开文章，从链接参数中复制 __biz 手动填入。"
    return None, "未在文章页找到合法 __biz，请换一篇该号的文章作为种子链接，或手动填入 __biz"
