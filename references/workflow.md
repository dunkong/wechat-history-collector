# 完整工作流参考

## 原理

微信公众号历史文章列表不是公开接口。仅凭种子链接只能提取账号标识 `__biz`；要拉取列表必须有一份带登录态的临时凭证（`key` / `pass_ticket` / `uin` / `biz` + Cookie）。本工具用本机 mitmproxy 截获微信电脑版访问公众号主页时的这些参数，再调用 `mp/profile_ext` 的 `getmsg` 接口翻页。

链路：`种子链接 → __biz → 微信里点主页链接 → 抓包截获凭证 → getmsg 翻页 → general_msg_list 解析 → SQLite 去重入库 → 导出`。

正文抓取是普通网页请求（带抓包得到的 Cookie/UA），不依赖列表凭证的新鲜度，也不涉及付费接口。

## CLI 命令详解（`scripts/cli.py`）

所有命令向 stdout 输出一行 JSON。退出码 0 成功，1 失败。

| 命令 | 作用 | 关键参数 |
| --- | --- | --- |
| `seed <url>` | 从文章链接解析 `__biz` 并建账号 | `--name` 公众号名 |
| `capture start` | 启动 mitmproxy + 开启系统代理 | `--biz` 用于生成主页链接 |
| `capture status` | 查看抓包进程/代理/凭证状态 | — |
| `capture stop` | 关闭系统代理 + 停止抓包 | — |
| `reset` | 一键强关代理（断网急救） | — |
| `collect` | 翻页采集历史文章 | `--biz` `--pages`(0=拉全) `--force` `--name` |
| `content` | 抓取正文 | `--all` 或 `--ids 1 2 3`，`--delay` |
| `export` | 导出元数据 CSV/Excel/HTML/JSON | `--name` |
| `archive` | 导出正文归档 HTML + Markdown ZIP | `--name` `--keyword` |
| `status` | 查看入库总数与账号列表 | — |

`capture status` 返回字段：`mitm_running` / `proxy_on` / `proxy_points_to_us` / `auth_captured` / `auth_fresh` / `auto_recovered`。判断"可以开始采集"的依据是 `auth_fresh: true`。

`collect` 返回字段：`pages`（翻页数）、`new_count`（本次新增入库）、`reached_end`（是否翻到底）、`error`、`total_in_db`。

## HTTP API（网页模式，127.0.0.1:8899）

- `POST /api/seed` `{url}` → `{ok, biz, account_id}`
- `POST /api/account/name` `{name}`
- `GET|POST /api/capture/start|stop|status`、`POST /api/network/reset`
- `POST /api/collect` `{max_pages}`（0 = 拉全）；`POST /api/collect/pause|stop`；`GET /api/progress`
- `GET /api/articles?keyword=`、`/api/accounts`、`/api/stats`
- `POST /api/export` `{format: xlsx|csv|html|json}`
- `POST /api/content/fetch` `{ids}`；`/api/content/pause|stop`；`GET /api/content/progress`；`GET /api/archived`
- `POST /api/export/archive` `{keyword}` → `{html, zip}`
- `GET /api/download?path=<导出绝对路径>`（仅允许 `data/exports/` 下文件）

三类任务（列表、正文）的暂停/停止由 `core/control.py` 的 `TaskControl` 实现：暂停时后台线程阻塞等待，停止时唤醒并保留已入库数据。

## 数据库字段（`data/articles.db`）

`accounts`：`id, biz(unique), name, created_at`

`articles`：`id, account_id, url(unique), title, digest, author, cover, publish_time, publish_ts, source_url, content, content_status, content_at, created_at`

`content_status` 取值：空（未抓）、`ok`（已归档）、`fail:<原因>`（失败）。

## 凭证文件（`data/captured_auth.json`）

由 `mitm_addon.py` 写入，结构：
```
{ "auth": {"key":..., "pass_ticket":..., "uin":..., "biz":...},
  "cookie": "...", "user_agent": "...", "referer": "...", "captured_at": <unix秒> }
```
`captured_at` 用于判断 30 分钟时效。多人/多号使用时以最近一次抓包为准。
