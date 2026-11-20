"""路径与常量配置。所有数据只存本机。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "articles.db"
AUTH_PATH = DATA_DIR / "captured_auth.json"
EXPORT_DIR = DATA_DIR / "exports"

MITM_HOST = "127.0.0.1"
MITM_PORT = 8898
WEB_PORT = 8899

PROFILE_HOME = "https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz={biz}&scene=124#wechat_redirect"
GETMSG_URL = "https://mp.weixin.qq.com/mp/profile_ext"

# 普通浏览器 UA 即可；抓包时以微信内置浏览器发出的请求为准
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 MicroMessenger/8.0")

for p in (DATA_DIR, EXPORT_DIR):
    p.mkdir(parents=True, exist_ok=True)
