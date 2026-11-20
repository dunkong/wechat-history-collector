"""管理 mitmproxy 抓包进程 + 凭证文件监听 + 系统代理开关（仅本机）。

安全设计（防止断网）：
1. 只有 mitmproxy 真正监听端口成功后，才开启系统代理。
2. 守护线程每秒检查：代理开着但抓包进程死了 → 立即自动关闭代理。
3. 服务启动时自动清理"指向本工具端口但进程未运行"的残留代理。
"""
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from .config import AUTH_PATH, MITM_HOST, MITM_PORT, ROOT, PROFILE_HOME

# Windows 系统代理（注册表 HKCU，无需管理员）
import winreg

PROXY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
PROXY_SERVER = f"{MITM_HOST}:{MITM_PORT}"

_state = {
    "proc": None,
    "proxy_on": False,
    "last_error": "",
    "auto_recovered": "",  # 记录自动回滚事件，便于前端提示
}


def _reg_get(name, default=None):
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, PROXY_KEY)
        v, _ = winreg.QueryValueEx(k, name)
        winreg.CloseKey(k)
        return v
    except Exception:
        return default


def _port_open(host=MITM_HOST, port=MITM_PORT, timeout=0.4):
    """抓包端口是否真的有人监听（ mitmproxy 是否活着）。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def proxy_is_enabled():
    return _reg_get("ProxyEnable", 0) == 1


def proxy_points_to_us():
    server = _reg_get("ProxyServer", "") or ""
    return PROXY_SERVER in server


def _reg_set(name, value, vtype=winreg.REG_SZ):
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, PROXY_KEY, 0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, name, 0, vtype, value)
    winreg.CloseKey(key)


def enable_system_proxy():
    # 保险：抓包端口没监听就绝不开代理，否则整机会断网
    if not _port_open():
        return False, "抓包端口未就绪，已阻止开启系统代理（避免断网）。请确认 mitmproxy 已启动。"
    try:
        _reg_set("ProxyEnable", 1, winreg.REG_DWORD)
        _reg_set("ProxyServer", PROXY_SERVER)
        _state["proxy_on"] = True
        return True, "系统代理已开启 → " + PROXY_SERVER
    except Exception as e:
        return False, f"开启代理失败（可手动设置）：{e}"


def disable_system_proxy():
    try:
        _reg_set("ProxyEnable", 0, winreg.REG_DWORD)
        _state["proxy_on"] = False
        return True, "系统代理已关闭"
    except Exception as e:
        return False, f"关闭代理失败：{e}"


def start_mitm():
    """后台启动 mitmdump，并等待端口真正可连接才返回成功。"""
    if _state["proc"] and _state["proc"].poll() is None and _port_open():
        return True, "抓包进程已在运行"
    addon = ROOT / "mitm_addon.py"
    # mitmproxy v12 正确入口是 mitmproxy.tools.main:mitmdump。
    # 旧的 -m mitmproxy.tools.dump 在 v12 无 main()，会静默 code=0 退出。
    cmd = [sys.executable, "-c",
           "from mitmproxy.tools.main import mitmdump; mitmdump()",
           "--listen-host", MITM_HOST, "--listen-port", str(MITM_PORT),
           "-s", str(addon)]
    try:
        # 关键：日志句柄必须保存到进程生命周期结束，否则函数返回后被 GC 关闭，
        # 子进程写入已关闭的句柄会立即崩溃（这是之前"秒退"的根因）。
        if _state.get("log_handle") is None:
            _state["log_handle"] = open(ROOT / "data" / "mitm.log", "a", encoding="utf-8")
        _state["proc"] = subprocess.Popen(
            cmd, stdout=_state["log_handle"], stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        # 轮询等待端口就绪（最多 12 秒），比单纯 sleep 更可靠
        for _ in range(24):
            if _state["proc"].poll() is not None:
                code = _state["proc"].returncode
                return False, f"抓包进程启动后立即退出(code={code})，请看 data/mitm.log"
            if _port_open():
                return True, "抓包进程已启动且端口就绪"
            time.sleep(0.5)
        return False, "抓包进程启动超时，端口未就绪，请看 data/mitm.log"
    except Exception as e:
        return False, f"抓包进程启动失败：{e}"


def stop_mitm():
    if _state["proc"] and _state["proc"].poll() is None:
        _state["proc"].terminate()
        try:
            _state["proc"].wait(timeout=3)
        except Exception:
            _state["proc"].kill()
    _state["proc"] = None
    if _state.get("log_handle") is not None:
        try:
            _state["log_handle"].close()
        except Exception:
            pass
        _state["log_handle"] = None
    return True, "抓包进程已停止"


def clear_auth():
    try:
        AUTH_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def read_auth():
    if not AUTH_PATH.exists():
        return None
    try:
        data = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
        if data.get("auth", {}).get("key"):
            return data
    except Exception:
        pass
    return None


def is_auth_fresh(max_age_sec=1800):
    """凭证是否新鲜（默认 30 分钟内）。"""
    data = read_auth()
    if not data:
        return False, None
    age = time.time() - data.get("captured_at", 0)
    return age <= max_age_sec, data


def build_profile_url(biz):
    return PROFILE_HOME.format(biz=biz)


def status():
    proc = _state["proc"]
    return {
        # 以端口是否监听为准：服务重启后即使 _state 丢失，只要抓包进程还活着就算运行中
        "mitm_running": _port_open(),
        "proxy_on": proxy_is_enabled(),
        "proxy_points_to_us": proxy_points_to_us(),
        "port_open": _port_open(),
        "auth_captured": read_auth() is not None,
        "auto_recovered": _state.get("auto_recovered", ""),
    }


def _watchdog():
    """守护线程：代理开着但抓包进程死了/端口不通 → 自动关代理，防止断网。"""
    while True:
        time.sleep(1.5)
        try:
            enabled = proxy_is_enabled()
            ours = proxy_points_to_us()
            alive = _port_open()
            # 只回滚"我们设置的、指向本工具端口"的代理，不碰用户自己的代理设置
            if enabled and ours and not alive:
                _reg_set("ProxyEnable", 0, winreg.REG_DWORD)
                _state["proxy_on"] = False
                _state["auto_recovered"] = (
                    "检测到抓包进程已停止但系统代理仍开启，已自动关闭代理以恢复网络。")
                print("[WATCHDOG] 自动关闭残留代理，网络已恢复")
        except Exception:
            pass


def init_safety():
    """服务启动时：清理残留代理 + 启动守护线程。"""
    # 如果上次异常退出留下"指向本工具端口"的代理但进程没跑，立即清掉
    if proxy_is_enabled() and proxy_points_to_us() and not _port_open():
        try:
            _reg_set("ProxyEnable", 0, winreg.REG_DWORD)
            _state["auto_recovered"] = "启动时检测到残留代理可能导致断网，已自动关闭。"
            print("[INIT] 已清理残留代理")
        except Exception:
            pass
    t = threading.Thread(target=_watchdog, daemon=True)
    t.start()


init_safety()
