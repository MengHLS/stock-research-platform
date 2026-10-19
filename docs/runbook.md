# 运行与发布

## 本地开发

按 README 安装锁定依赖和启动。统一入口自动建立 .scratch；migrate-local 只允许此目录中的新 SQLite 数据库，不允许它误连旧 MySQL/TiDB。

数据库版本查看使用 Alembic current。初始迁移无旧库导入，downgrade 明确拒绝删除数据；需要回退时采用备份恢复或经过评审的前向修复。

接口修改后运行 contract 并提交生成的 schema.d.ts。check 会独立重新生成到忽略目录并比较，不悄悄覆盖已提交的契约。

## 错误排查与日志

API 与 Worker 只向 stdout/stderr 输出单行 JSON；`RP_LOG_LEVEL` 取 DEBUG/INFO/WARNING/ERROR，默认 INFO。不按模块写日志文件，轮转与收集交给运行环境。

```json
{"ts":"2026-10-18T02:14:06.074Z","level":"INFO","role":"api","event":"request.completed","request_id":"4a74…","method":"GET","route":"/api/v1/catalog","status":503,"duration_ms":8.2,"error_code":"AUTH_NOT_CONFIGURED"}
```

- 用户报错时先取页面显示的 `request_id`（等同响应头 `X-Request-ID` 与错误体 `detail.request_id`），再按该值过滤 `request.completed`；同一请求的全部事件带同一编号。
- 未处理异常记录 `request.failed`（`error_type` 只含类名，不含消息与堆栈）和固定的 500 安全文案；不要用日志中的类名反推用户输入。
- `route` 是路由模板，未匹配为 `unmatched`；日志中不会出现具体资源 ID、查询串、Cookie、Authorization、密码、连接串或租约 token。字段名命中敏感词或值形似带凭据 URL 时输出 `[redacted]`/`[redacted-url]`，未知对象只写类名。
- Worker 事件为 `worker.started`、`job.claimed`、`job.completed`（含 `outcome`、`duration_ms`、`error_code`）、`worker.connect_retry`、`worker.fatal`、`worker.stopped`；用 `job_id`+`attempt` 关联，不能用租约 token 检索。
- 错误分类、事件字段与脱敏规则见架构“统一错误与日志”；新增业务错误码必须先在 `core/errors.py` 的 `ERROR_SPECS` 登记状态与安全文案，未登记会落兜底 400 并暴露评审缺口。

超时与重试以 `core/policies.py` 为准：read 15 秒/最多 1 次（仅网络与 502/503/504）、write 30 秒/不重试、diagnostic 5 秒/不重试、submit 20 秒/不重试、worker-connect 10 秒/最多 3 次（1/2/4 秒）。排障时先确认失败属于超时、取消还是业务错误，不要通过放大 HTTP 超时掩盖慢查询；耗时计算应提交后台作业。

## 研究知识库

本机使用已安装的 Obsidian，在既有「投资」vault 内新增专区，不另建或移动整个笔记库：

- vault：`F:/Users/A/Desktop/Obsidian-workspace/stock/投资`
- 首页：`研究工作台/研究入口.md`；主题：`研究工作台/主题/`；模板：`研究工作台/模板/研究主题.md`；索引：`研究工作台/研究索引.base`
- 使用既有核心 Templates/Bases，无社区插件；新建 templates.json 指向专区模板目录，未覆盖旧模板配置。客户端未加载时重启 Obsidian，或直接复制模板到主题目录。

Agent 开始研究前先读首页并搜索主题目录；已有主题就更新主结论与简短证据，新问题才创建 research-topic 笔记。模板保留运行、数据/代码版本、配置、结果位置和局限，初始为草稿，人工复核后才可标已复核。索引是动态视图，不维护第二份手工清单；模板和首页不计入研究条目。

文件可直接读取/更新，无需开放 REST 插件或本机端口。当前未导入旧研究文档，未配置/验证云同步、独立备份、多用户权限或图表集成；更换机器时重新确认 vault 路径。知识库不在仓库内，不纳入 Git 或 .scratch；备份须单独落实。

## 数据库配置与数据源接入

配置模板是根目录 `.env.example`。本地复制为被 Git 忽略的 `.env` 后填写；部署通过服务端环境变量注入，优先级为进程环境高于 .env，高于默认值。模板中的可选 MySQL 配置均为注释，默认不访问外部网络。禁止把配置或校验错误中的原始输入整体输出。

日志级别用 `RP_LOG_LEVEL`（DEBUG/INFO/WARNING/ERROR，默认 INFO）配置，API 与 Worker 共用同一取值；它只影响输出量，不改变错误分类与脱敏规则。

| 角色 | 配置 | 用途与权限 |
|---|---|---|
| 应用库 app | 默认 `RP_DATABASE_URL` 指向本工程 SQLite；MySQL 使用 `RP_DATABASE_MYSQL__*` | 新系统业务数据，API/Worker/Alembic 共用；按运行/迁移职责最小授权 |
| 研究源 source | `RP_SOURCE_MYSQL__*`，未配置即关闭 | 现有 MySQL/TiDB 的研究输入，必须使用数据库端专用 SELECT-only 账号；不绑定应用 ORM 或 Alembic |

两套 MySQL 配置均含 HOST、PORT、DATABASE、USERNAME、PASSWORD、TLS、可选 CA_FILE、CONNECT_TIMEOUT 和 READ_TIMEOUT。PASSWORD 保持原值，由 URL.create 构造连接参数；无需手工拼接或 URL 转义。dotenv 中带 #、空格等字符的密码应加引号，容器环境变量则传原值。完整字段以 `.env.example` 和 Settings 为准。

默认 TLS=verify，校验证书链及主机名；CA_FILE 未设时用系统信任根，而 verify_ca 必须显式指定 CA_FILE（留空即启动报配置错误）。TLS=verify_ca 用固定的 CA_FILE 校验证书链但**不校验主机名**（等价 MySQL VERIFY_CA），用于 MySQL 8 自动生成的服务器证书：这类证书没有 subjectAltName，主机名校验永远不可能通过；而 disabled 明文连接实测被服务器以 1045 拒绝（具体机制未逐层验证），因此该模式是这类库唯一可用选项。它仍强制加密、校验失败即断连，不降级为不校验连接，因此不是被拒绝的“prefer”模式。自签发 CA 通过服务端私有路径配置，挂载示例见 `deploy/compose.server.yaml`。TLS=disabled 仅用于隔离的本机开发环境，不得用于公网 TiDB。

结构化应用 MySQL 启用时移除 RP_DATABASE_URL；相同主机/端口/库名的应用与源配置会被拒绝，但 DNS 别名、转发地址等仍需人工核实。旧式应用 URL 为兼容保留，远程 MySQL 应迁到结构化配置以统一 TLS/超时控制。角色检查不是数据库访问权限证明。本机开发曾临时豁免“独立库 + SELECT-only 账号”两条约束（复用旧工程同库及 `app` 全权账号），仅由用户明确同意，恢复条件见决策 D09“本机临时豁免”；工具输出不因豁免而放松判断。

统一任务入口（在项目根目录执行）：

```sh
uv run python tools/project.py db-config --target app
uv run python tools/project.py db-config --target source
uv run python tools/project.py db-check --target app
# 仅在专用账号就绪且获准连接后，才执行 source 的 db-check：
# uv run python tools/project.py db-check --target source
```

db-config 仅离线校验与输出脱敏状态，不连库；db-check 是显式 SELECT 1 连通检查，不建表、不扫描业务数据，也不证明只读授权、表结构或研究语义正确。源库权限由管理员核实实际授权及继承角色；不能通过尝试写生产表验证只读。TiDB 的普通 READ ONLY 事务声明并非可靠写保护，见[官方说明](https://docs.pingcap.com/tidbcloud/sql-statement-set-transaction/)。

旧项目使用 DATABASE_URL、TUSHARE_TOKEN 及 MINIO_*，它们不自动继承；旧 Node mysql URL 的 ssl JSON 参数不能直接搬给 PyMySQL：旧工程用 `ssl={"rejectUnauthorized":false}`（加密但不校验证书），本工程对应应选 verify_ca 并固定其 CA，选 verify 会因主机名不匹配而失败。历史复盘只读 `index_daily`（交易日/四指数）、`limit_up_records`（涨停记录）、`stock_daily_prices`（梯队行情）和 `market_data`（成交额/两融，旧源亿元口径），不绑定应用 ORM、不迁移旧表。

源库首次接入前需确认真实库位置与上述表范围、独立只读账号、TLS/CA、网络白名单和快照版本；只做授权的连通/结构检查。登录后总览页调用 `context`（默认日/前后日）、`dates`（区间≤366 日）、`overview`、`indices`、`limit-up` 与 `stock-series`（窗口≤120 交易日）；`RP_REVIEW__*` 控制缓存、窗口和连板回溯。源库未配时接口返回 `SOURCE_NOT_CONFIGURED`。覆盖 `available/completeness=presence_only` 只表示源中存在行；无涨停行、前一日缺口、连板链触顶或个股日线缺失时相关值为 null 并带稳定 issue，不填 0。坏数据 502 `MARKET_REVIEW_SOURCE_BAD_DATA`，SQL/表不可用 503 `MARKET_REVIEW_SOURCE_UNAVAILABLE`，非交易日 404。当前页面已用本地假数据完成视觉与交互检查；四张旧表的真实表结构、行数及日期极值已核实（逐表基线见[决策 D15](decisions.md#d15--历史复盘首版只读旧源并显式表达缺失)，各表日期范围不同且不保证区间完整），但只读权限（本机为临时豁免的全权账号）、数据完整性、性能与采集补数仍未验收。

## 公共行情数据源

腾讯分钟K线/竞价与东方财富竞价**无需配置**，只读、无 key；Tushare 日线可选，需 `RP_TUSHARE__TOKEN`。字段见 `.env.example`；`RP_UPSTREAM__*` 控制超时、重试、按源最小间隔与缓存秒数，`enabled=false` 时接口返回 `MARKET_SOURCE_DISABLED` 且不发任何外网请求。

| 接口 | 来源 | 说明 |
|---|---|---|
| `GET /api/v1/market/quote` | 腾讯 | 实时快照：最新价/昨收/涨跌停/行情时间；覆盖沪深北与指数，盘前竞价时段也可读 |
| `GET /api/v1/market/global/overview` | 新浪/雅虎/腾讯/Naver + 应用库 | 登录后读取跨市场概览，`window=20|60|120`；应用库优先，过期时刷新，失败回退最近快照并标记 `stale` |
| `GET /api/v1/market/intraday` | 腾讯 | `symbol`、`period=m1|m5|m15|m30|m60`、`limit<=800`；无北交所 |
| `GET /api/v1/market/auction` | 东财曲线 + 新浪成交 | 09:15–09:25 虚拟撮合曲线来自东财（`push2`/`push2his` 多主机轮换）；09:25 实际成交优先东财，降级时来自新浪（沪深北/科创/ETF/指数全覆盖、股数精确）。全部失败时 `degraded=true`、`snapshots=[]`，前端必须显示降级状态 |
| `GET /api/v1/market/daily` | Tushare | `symbol`、可选 `start`/`end`（YYYY-MM-DD） |
| `GET /api/v1/market/sources` | 本服务 | 各源是否配置；不触发外网请求 |
| `GET /api/v1/market/session` | 本服务 | 当前时段标签，按时钟判断，不代表交易日历 |

标的写法：**规范形态为后缀式 `600519.SH` / `000001.SZ` / `920982.BJ`**，返回的 `symbol` 一律是该形态；入参同时接受 `600519`、`sh600519`、`sh.600519`、`SH600519`、`600519.sh` 等变体，统一折叠为规范形态。上证指数号段（`000001`/`000010`/`000016`/`000300`/`000688`/`000852`/`000905`）与深市股票同时使用 `000xxx`，深市指数 `399001`/`399106` 也需区分，这些**必须带交易所前缀**；裸代码一律 400 `MARKET_SYMBOL_INVALID`，不做猜测。北交所（`bj` 前缀）无腾讯分钟线，返回 `MARKET_DATA_UNAVAILABLE` 而不是空数组。日内K线与日线的成交量均换算为股（`volume_shares`）；腾讯快照因股票/ETF/指数口径不一致，字段为 `volume_lots` 并附 `volume_note`。时间对外为 UTC ISO 8601，另附 `trading_day` 交易日。

失败码：`MARKET_SYMBOL_INVALID`(400)、`MARKET_DATA_UNAVAILABLE`(404)、`MARKET_SOURCE_UNAVAILABLE`(503)、`MARKET_SOURCE_BAD_RESPONSE`(502)、`MARKET_SOURCE_NOT_CONFIGURED`/`MARKET_SOURCE_DISABLED`(503)、`MARKET_SOURCE_PERMISSION_DENIED`(503)、`MARKET_SOURCE_RATE_LIMITED`(429)；复盘另有 400 区间码、404 日期码及 502/503 源码。供应商原始报文、连接串与 Tushare token 不写日志、不回前端。

Tushare 侧需自行确认账号权限：本机继承的旧 token 实测 `daily`、`daily_basic`、`trade_cal` 可用，`stk_mins` 限每小时 1 次，`stk_auction`、`rt_k`、`fund_daily` 无权限，因此竞价与日内不走 Tushare。新账号开通后无需改代码即可用 `daily`；`stk_auction` 若要接入需新增 provider 与对拍，不能直接假定字段一致。

竞价降级判定：`provider=eastmoney` 表示拿到完整 09:15–09:25 曲线；`provider=sina` 且 `degraded=true` 表示东财曲线不可用、只有 09:25 成交（新浪覆盖全部板块且股数精确）；`provider=tencent` 是新浪也失败时的最后兜底（科创板股数取 09:30 分钟线校正）。降级时 `matched_time`/`matched_volume_shares`/`matched_amount` 仍有效但 `snapshots` 为空，`limits` 里写明降级原因。

时间字段一律 UTC（`...Z` 或 `+00:00`），`trading_day` 单独给交易日。若返回的竞价属于**早于当前交易所日期**的交易日（盘前或非交易日读到的上一交易日数据），`limits` 会明确写“不是今日竞价”，前端必须据此标注而不能当今日数据展示。上游 429 映射为 `MARKET_SOURCE_RATE_LIMITED`(429)，与 `MARKET_SOURCE_UNAVAILABLE`(503) 区分。

验证：`uv run python tools/project.py market-check` 只读探测上述公共源并输出各自状态（不发写请求、不写库）。当前未验收的部分：真实网络抖动下的重试/超时、供应商限流阈值、代理环境（本机走 HTTP 代理时 httpx2 的 `trust_env` 关闭策略需在部署环境确认）、盘前 09:15–09:25 实时轮询（离线只能验证已收盘交易日的曲线与降级路径），以及历史日内数据的冻结快照。东财曲线在本地代理环境下的失败原因（已定位，2026-10-18）：本机 Clash 类代理以 **fake-ip** 模式应答 DNS，`push2.eastmoney.com` 被解析为 `198.18.0.166`、`push2his.eastmoney.com` 为 `198.18.0.163`（`198.18.0.0/15` 是保留测试段），代理未能完成到东财的 TLS 隧道；同时东财服务端要求 TLS 重协商，Windows schannel 与 Python/OpenSSL 均拒绝。**直连真实 IP 可正常取得完整曲线**（`ssl_verify_result=0`，连续 6 次 200）。

因此 `/auction` 现在有两层兜底，无需改代码：
1. **多主机轮换** `push2` → `push2his`（同一 endpoint、同一报文）；
2. **可选地址固定** `RP_UPSTREAM__HOST_ADDRESSES`，为被 fake-ip 拦截的主机指定已核实真实地址。实现是**逐请求**改写目标地址并保留 `Host` 头与 TLS `sni_hostname`，证书仍按域名校验；不修改进程全局解析器（早期版本用 `socket.getaddrinfo` 补丁，并发请求会互相覆盖并污染后续所有 DNS 解析，已废弃）。

排查步骤：`curl -4 --noproxy "*" https://push2his.eastmoney.com/...` 能通说明是代理 DNS 问题；把解析到的真实 IP 填进 `RP_UPSTREAM__HOST_ADDRESSES` 即可。也可临时退出代理直连验证。

## 注册与登录

自建认证，不依赖外部 OAuth。启用前必须在环境中设置签名密钥：

```sh
python -c "import secrets;print(secrets.token_urlsafe(48))"   # 生成后填入 RP_AUTH__SECRET
```

| 接口 | 说明 |
|---|---|
| `POST /api/v1/auth/register` | 注册并自动登录；`invite` 模式需带 `invitation_code` |
| `POST /api/v1/auth/login` | 登录，写入 HttpOnly 会话 cookie |
| `POST /api/v1/auth/logout` | 服务端撤销会话并清 cookie（`Max-Age=0`） |
| `GET /api/v1/auth/session` | 当前登录用户；未登录返回 **204 无正文**（不是 200 空对象） |
| `POST /api/v1/auth/password` | 修改密码，撤销该用户全部会话并清 cookie |

前端契约：任何接口 401 时请求层统一通知会话 store 并跳回登录页；未登录探测返回 204，前端据此区分“已询问且未登录”和“尚未询问”。

安全语义：密码用标准库 `scrypt`（参数随哈希编码可升级）；库中只存**会话令牌的 SHA-256**，泄露库也无法重放；登录失败与账号不存在同码，不泄露邮箱是否注册；连续失败达 `RP_AUTH__MAX_FAILED_LOGINS` 后锁定；cookie 为 `HttpOnly` + `SameSite=Lax`，生产强制 `Secure`。生产启动按凭据阻断：缺 `RP_AUTH__SECRET` 或 `COOKIE_SECURE=false` 时报错退出。

### 邀请码注册（少量用户的审核方式）

前期只有一两个用户，用邀请码代替人工审核流程：拿到有效邀请码即视为已批准，注册后直接可用，不需要再改账号状态。

```sh
# 发码（明文只显示这一次，数据库只存哈希）
uv run python tools/project.py identity --identity-action invite-create --label "张三"
# 查看所有码及状态（usable / spent / revoked）
uv run python tools/project.py identity --identity-action invite-list
# 作废未使用的码
uv run python tools/project.py identity --identity-action invite-revoke --code-id <id>
```

模式用 `RP_AUTH__REGISTRATION` 切换：`invite`（默认）/ `closed`（只能命令行建号）/ `open`（仅限私有可信部署）。命令行账号管理：`identity --identity-action user-create|user-list|user-disable|user-reset-password`，参数见 `tools/project.py --help`。

邀请码语义：单次使用、可设有效期（默认 14 天）、只存哈希；注册失败（如邮箱已存在）**不会**消耗邀请码；停用账号会同时撤销其全部会话。

未实现：邮箱验证、密码重置邮件、多因素、SSO、审计查询界面。旧项目的 OAuth（Manus 平台）未沿用，其 `users` 表只存 openId，无法迁移密码。

## 前端原型（Open Design）

前端设计原型在 Open Design 桌面应用维护，与本仓库同产品的早期 React 版本。已安装的 Open Design 提供本地 MCP，可读取原型和发起设计优化；默认使用 Open Design Cloud，切换 Local Codex 或 secure BYOK 需用户明确选择，生成失败时不得自动换模式。只读盘点仍可使用数据目录工具：

```sh
uv run python tools/project.py prototype                 # 列出导航入口与视图
uv run python tools/project.py prototype --action shape  # 输出导航/视图 JSON
uv run python tools/project.py prototype --action copy --to .scratch/prototype.html
```

工具按 `stock-limit-up-analyzer` / `stock-research-platform` 字样定位项目，不硬编码项目 ID；找不到或匹配多个时明确报错。当前原型：13 个已实现入口、9 个待开发入口、22 个视图、13 份设计文档。登录/注册另有一份 `auth.html`（左右分栏：左品牌陈列、右表单），本仓库登录页按其布局实现，但示例行情预览、演示账号与验证码均未移植（后端无对应能力），改为渲染真实 `/health/live` 与 `/api/v1/market/sources`。

**原型是设计参考，不是代码来源**：本仓库为 Vue 3 + Element Plus + openapi-fetch，原型来源项目为 React 19 + shadcn + tRPC，页面须按设计意图重写，不能复制移植。实施前确认目标视图、数据来源（`/api/v1/market/*` 等）与原型示例数据的差异；模拟数据与未实现入口不得当成本仓库已有能力。未验证项：字段对齐、浅色主题对比度、移动端布局，需逐页验收。

## 可选本机构建容器

deploy/compose.yaml 是本机 MySQL 开发模板，端口只绑定 127.0.0.1，不会自动迁移数据库；在忽略的 deploy/.env 中提供 MYSQL_PASSWORD 与 MYSQL_ROOT_PASSWORD 后，在 deploy 目录执行：

```sh
docker compose build && docker compose up -d db
docker compose run --rm api alembic -c backend/alembic.ini upgrade head
docker compose up -d
```

模板把密码作为独立环境变量传给应用，不拼接连接 URL，但需注意 Compose 的 .env 插值与 `$` 转义；容器内仅为开发 MySQL 关闭 TLS，不挂载或连接旧研究源。迁移命令仅适用于模板新建的 research 库，现有生产库须先基线、备份和评审；数据卷删除会丢数据。当前环境未安装 Docker，本模板尚未实际运行，不能据此宣称容器部署验收通过。

## dev 分支服务器部署（ECS + ACR + GitHub Actions）

dev 站点是内部验证环境：公网 IP + HTTP，不满足下文发布门槛第 3 条，不能当生产用。设计与取舍见 D14。

| 组件 | 位置 | 说明 |
|---|---|---|
| GitHub Actions / GHCR | GitHub | 门禁、构建并推送 SHA 标签镜像、SSH 部署、远端冒烟 |
| Docker Compose | ECS | `deploy/compose.server.yaml`；只有 web 发布端口（默认 80） |
| db | ECS（既有） | 复用既有 MySQL 实例的 `research` 库与账号，不新建容器 |

`deploy/compose.yaml`（本机）与 `compose.server.yaml`（服务器）互不覆盖，服务器不构建镜像。初始化：ECS 装 Docker 与 git，安全组只放行 80 与 SSH；克隆仓库切到 dev；`cp deploy/env.server.example deploy/.env && chmod 600 deploy/.env` 后填 `IMAGE_PREFIX`、既有 MySQL 的 `MYSQL_*` 与 `RP_AUTH__SECRET`；首版 `bash deploy/deploy.sh --tag <SHA>`。首个账号在镜像内用 `python tools/project.py identity --identity-action user-create --email you@example.com --role admin` 创建。

GitHub 配置：Secret `ECS_HOST`/`ECS_USER`/`ECS_SSH_KEY`；Variable `DEPLOY_PATH`/`WEB_PORT`。镜像仓库用仓库内置 `GITHUB_TOKEN`，无需额外凭据。

发布：推送 `dev` 触发门禁 → 构建 → SSH 部署（拉取、迁移、启动、健康检查）→ 冒烟 `/health/live` 与 `/health/ready`，同分支串行。健康检查失败自动回到上一版，状态在 `deploy/.state/`；手工回滚 `bash deploy/deploy.sh --rollback`。迁移在启动前单独执行，容器不跑迁移。未验收：本地无 Docker，编排、脚本与流水线尚未实际运行；ECS 首次部署、ACR 拉取与回滚演练待执行，通过前不得宣称可用。

## 进程生命周期（目标约定，待实施）

以下是加固规格，不是当前脚本已具备的能力。当前本地子进程清理较简易，Worker 尚无 SIGTERM/协作停止及完整退避处理，API 需补初始化失败和异常退出释放路径。

| 进程 | 启动与运行 | 收到停止/发生失败 |
|---|---|---|
| 本地 dev | 校验配置与所需工具；API/前端分别建受控进程组，在 try/finally 内逐个启动；监听实际启动结果，不以 Popen 成功当服务就绪 | 任一启动失败或意外退出，停止本次启动的另一进程；返回明确失败码。Ctrl+C 协作停止，最多 10 秒后清理所属进程树；不杀同端口未知进程或其他项目 |
| API | 校验配置、建立应用连接并检查必要迁移状态；资源按生命周期持有；liveness 表示进程存活，readiness 表示可接流量，研究源可用性另算 | SIGTERM/Ctrl+C 停止接新请求并退出就绪状态，最多 15 秒排空在途请求，再释放连接与日志；异常路径同样释放资源，不在启动/退出时执行迁移 |
| Worker | 校验配置与应用库；空闲轮询可被停止信号唤醒；配置/缺迁移直接失败退出，临时连接错误有限退避，不伪造任务成功 | 收到停止立即停止领取；短任务最多 30 秒完成，期间须仍持有效租约。结束后释放 session/engine；超过期限不提交假终态，交由租约与恢复规则处理 |

宽限期为首版默认值，配置项在实现时统一加入 Settings。容器 stop_grace_period 须大于内部宽限期并留缓冲，反向代理/HTTP/数据库超时按用途协调。后台计算不占用长 HTTP 请求；不能用延长网关超时代替后台任务。

Worker 临时连接失败首版最多连续重试 3 次（退避 1/2/4 秒，可被停止唤醒），恢复后清零；耗尽后非零退出，由运行环境按有界重启策略处理。任务的 attempts/租约重试与进程连库重试分别计数，不能把进程重启视为一次新研究。日志只留错误分类、重试次数与安全标识。

未来长任务执行器必须支持停止信号、周期续租、产物临时区和原子发布；失去租约立即禁止发布/写入终态。只有确认旧执行已停止，才能主动释放租约供其他 Worker 接管；否则等待租约过期并由 token 阻止旧 Worker 交付。外部计算未停止时不能声称取消完成。

Windows 使用受控进程组的协作退出方式并保留进程树强停兜底；Linux 向本次创建的进程组发停止信号，超时再强停。实现时记录所属 PID/进程组，不按名称广杀；父进程意外消失的清理由部署监督器或受控作业机制承担，不能只依赖 finally。

验收分场景执行一次：正常启动/停止、端口占用、第二个进程启动失败、子进程意外退出、DB 不可用、API 在途请求、Worker 空闲/执行中停止及宽限期耗尽。检查无本次残留进程、退出码正确、资源释放、租约终态未被越权覆盖；不能靠强杀一次就宣称优雅退出完成。

## 面向独立服务器的发布门槛

1. 选定认证实现，完成邀请/会话/注销/禁用与私人资源双用户验证。
2. 生产配置检查、MySQL 迁移、备份恢复演练通过；研究执行器与对象存储分别验收。
3. 前后端静态资源/API 同域 HTTPS 并接入网关；数据库与存储管理口不公开。
4. CI 类型/测试/构建及目标环境冒烟通过后解除生产启动阻断；使用不可变镜像，保留上一版配置与恢复方案，禁止自动升级依赖或启动时生成 DDL。

## 故障处理

- liveness 失败：查进程与启动日志；production 阻断是有意行为。
- readiness 失败：查新库迁移与数据库可达性；不要用空数组冒充健康。
- AUTH_NOT_CONFIGURED：身份未接入，不建临时管理员绕过。
- Worker 无待处理项属正常；未知 handler 显式失败；租约耗尽最多三次后 LEASE_EXHAUSTED，保留记录不覆盖旧终态。
- 清理只处理自己创建的 .scratch，确认真实路径用途；真实研究证据另有保留策略。

日志不输出连接串、密码或会话令牌。磁盘、任务失败、队列等待与备份状态接入正式监控后再开放远程试用。
