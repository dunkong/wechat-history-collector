---
name: wechat-history-collector
description: 采集微信公众号全部历史文章并在本地归档。用户通常只需说一句话（如"采集这个公众号的历史文章"并附上文章链接），AI 即可自动完成解析、抓包引导、翻页采集、导出与正文归档。当用户提供一篇公众号文章链接（种子链接），希望批量拉取该号历史文章、导出 Excel/CSV/HTML/JSON、或抓取正文做离线归档（离线 HTML / Markdown ZIP）时使用本技能。纯本机运行，通过微信电脑版抓包获取临时登录凭证，不调用任何付费接口，数据只存本机。触发词：公众号历史文章、采集公众号、抓取公众号文章、公众号文章归档、导出公众号文章。
agent_created: true
---

# 公众号历史文章采集器

## 用途

给一篇公众号文章链接，采集该公众号的历史文章列表（标题、摘要、作者、封面、发布时间、原文链接），存入本地 SQLite，去重后导出多格式文件；可选抓取正文做离线归档。全程本机运行，不依赖任何付费接口，数据不上传。

## 何时使用

- 用户给出 `mp.weixin.qq.com` 文章链接，想采集该号的历史文章。
- 用户想导出公众号文章到 Excel / CSV / HTML / JSON。
- 用户想把已采集文章的正文归档成可离线阅读的 HTML 或 Markdown。

不适用：不装微信电脑版、不愿抓包、或要求"零配置凭空拿全量"的场景——微信历史列表非公开接口，必须本机抓包拿到临时凭证。

## 关键约束（务必先向用户说明）

- **需要用户配合**：首次要安装 mitmproxy 的本地 CA 证书，采集时要在微信电脑版里点一次主页链接（约 30 分钟内凭证有效）。
- **数量**：默认翻到微信返回"没有更多"为止，一般可拉数百至上千篇；`getmsg` 翻页有平台上限，极老账号不保证从建号至今全量，可反复采集自动去重补全。
- **断网防护**：抓包会临时改写 Windows 系统代理。本工具内置三道保险（端口就绪才开代理、守护线程自动回滚、启动自清理）。若用户反馈断网，立即执行 `python scripts/cli.py reset` 或双击 `reset_network.bat`。
- **合规**：仅采集公开文章供个人存档研究，遵守微信协议与版权。

## 环境

- Windows + 微信电脑版（已登录）。
- Python 3.9+，依赖见 `requirements.txt`（Flask / requests / openpyxl / mitmproxy）。

首次安装：双击 `install.bat`（或 `python -m pip install -r requirements.txt`）。证书：启动抓包后浏览器打开 <http://mitm.it> 安装 Windows 证书（受信任的根证书颁发机构）。

## 用户怎么用：一句话即可

用户不需要记任何命令，也不必了解内部流程。加载本技能后，直接对 AI 说一句话即可，例如：

- "采集这个公众号的全部历史文章：<文章链接>"
- "把这个号的文章导出成 Excel"
- "抓取已采集文章的正文，归档成离线 HTML"

AI 收到请求后应自动跑完下面的流程；全程只有一步需要用户亲自操作——在微信电脑版里点开链接完成抓包，其余步骤由 AI 自行推进。

## AI 执行流程

收到请求后按以下顺序执行，尽量不打断用户，仅在需要用户点微信链接时提示：

1. 解析种子：`python scripts/cli.py seed "<文章链接>" --name "<公众号名>"`，取返回的 `biz` 与 `profile_url`。
2. 启动抓包：`python scripts/cli.py capture start --biz "<biz>"`；把 `profile_url` 交给用户，请其粘贴到微信电脑版"文件传输助手"并点开。
3. 等待凭证：轮询 `python scripts/cli.py capture status`，直到 `auth_fresh=true`。
4. 采集：`python scripts/cli.py collect --biz "<biz>" --pages 0`。
5. 按用户需要导出：`export`（元数据）/ `content`（抓正文）/ `archive`（正文归档）。
6. 收尾：`python scripts/cli.py capture stop`；若用户反馈断网，立即 `python scripts/cli.py reset`。

所有命令输出单行 JSON，直接解析字段判断成败。完整命令与字段见 `references/workflow.md`。

## 手动方式（无 AI 参与时）

- **网页**：双击 `start.bat`（自动打开 <http://127.0.0.1:8899>），按页面 4 步操作：① 粘贴种子链接 → ② 抓包获取凭证 → ③ 采集历史文章 → ④ 查看与导出 / 正文归档。列表、正文任务均支持暂停/继续/停止，已抓数据实时保留。
- **命令行**：直接按上面"AI 执行流程"的命令顺序执行即可。

## 前端/后端 API（网页模式）

Flask 服务只监听 `127.0.0.1:8899`。主要路由：`/api/seed`、`/api/capture/*`、`/api/collect`(`/pause`/`/stop`)、`/api/progress`、`/api/articles`、`/api/export`、`/api/content/*`、`/api/export/archive`、`/api/download`、`/api/network/reset`。详见 `references/workflow.md`。

## 资源清单

- `scripts/cli.py` —— 命令行/自动化统一入口（JSON 输出）。
- `references/workflow.md` —— 完整工作流、CLI 命令、HTTP API、数据库字段。
- `references/troubleshooting.md` —— 抓包、证书、断网、凭证过期等问题排查。
- `app.py` + `core/` + `web/` + `mitm_addon.py` —— 网页模式应用主体。
- `start.bat` / `install.bat` / `reset_network.bat` —— Windows 一键脚本。

## 目录约定

所有运行时数据只写 `data/`（数据库、凭证、导出、日志）。`data/` 已被 `.gitignore` 排除，不会进入版本库。
