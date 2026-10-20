# 磐石 · Quant Lab

> Coding Agent：开发前先读 [AGENTS.md](AGENTS.md)，按任务读取对应规范。本 README 面向项目使用者，负责介绍与启动，不作为开发规则的第二来源。

A 股量化研究工作台：行情复盘、模式库、策略验证与数据集。Vue 3 + TypeScript 前端，Python + FastAPI 后端，独立 Worker；一个 Git 仓库维护。

名称与图标：**磐石**取"稳固基座"之意——平台是研究工作站立的地基；图形是三层叠压的石台，与界面图标同族（24×24 网格、1.8 描边）。品牌定义集中在 `frontend/src/brand.ts`，改名或换标只改一处。

这是可运行的开发骨架。已包含接口类型生成、SQLAlchemy、显式 Alembic 迁移、私人目录查询、平台诊断队列、测试与 CI 模板；没有移植旧研究引擎或接入真实行情。

**真实认证尚未接入：私人接口返回 AUTH_NOT_CONFIGURED，生产启动主动阻止。没有默认管理员、测试登录或伪造研究结果。** 测试通过 dependency override 验证两个用户的资源隔离，该方式不暴露为 HTTP 开关。

## 开始开发

需要 Python 3.12、Node.js 24、uv 0.12.3、pnpm 11.24.0 和 Git。Python 依赖使用 uv.lock，前端依赖使用 frontend/pnpm-lock.yaml。

在仓库根目录执行，Windows/PowerShell 和 Linux 使用相同命令：

```sh
uv sync --locked
pnpm --dir frontend install --frozen-lockfile
uv run python tools/project.py migrate-local
uv run python tools/project.py dev
```

终端会打印前后端的实际访问地址。默认仅绑定本机；Vite 通过代理访问 FastAPI。API 文档位于后台 `/docs`，健康检查为 `/health/live` 与 `/health/ready`。

开发默认 SQLite 位于 `.scratch/development.db`，这是独立新库，和旧工程数据库没有关系。需要自定义时复制 `.env.example` 为 `.env`，不要提交实际凭据。

应用库与研究数据源分别配置；外部源默认关闭，字段模板见 `.env.example`，接入与只读授权要求见[运维文档](docs/runbook.md)。离线检查：`uv run python tools/project.py db-config --target source`；不会连接真实数据库。

公共行情已接入只读、免 key 的数据源：腾讯实时快照/分钟K线、东方财富开盘集合竞价、Tushare 日线（可选 token）。接口在 `/api/v1/market/*`，日内K线与竞价**不落库**，只用短期缓存；探测脚本：`uv run python tools/project.py market-check`。限制、降级语义与单位见[运维“公共行情数据源”](docs/runbook.md)，取舍见决策 D13。

Worker 使用另一个终端：

```sh
uv run python tools/project.py worker
```

目前 Worker 仅支持有界的 `system.check` 数据库诊断。研究 Run、长任务续租、协作取消、用户配额和产物发布在接入真实计算前实现，不把平台作业当作研究完成。

## 前端原型

页面设计以 Open Design 中的原型为准（同一产品的早期 React 版本）。连接与查看：

```sh
uv run python tools/project.py prototype                 # 导航入口与视图清单
uv run python tools/project.py prototype --action shape  # JSON 结构
```

原型只作为设计参考：本仓库是 Vue 3 + Element Plus，需按设计意图重写，不复制原型代码。详见[运维“前端原型”](docs/runbook.md)。

## 常用入口

```sh
uv run python tools/project.py check          # 完整质量门禁
uv run python tools/project.py contract       # 根据后台生成 TypeScript 接口类型
uv run python tools/project.py hygiene        # 文档、脚本及产物存放规则
```

命令的权威定义是 `tools/project.py --help`；不要为每个任务复制一份脚本。完整检查包括后端规范与测试、接口契约漂移、前端规范与测试、类型检查和构建。

## 前端框架

前端已按设计原型搭好壳层与路由：左侧分组导航（6 个已实现入口 + 17 个待开发入口）、顶栏（页面标题、会话状态、主题切换、账号菜单）、登录/注册页，以及深浅两套主题 token。

```sh
pnpm --dir frontend run dev      # 前端 http://127.0.0.1:5173
uv run python tools/project.py dev  # 前后端一起（API 8000）
```

未实现页面显示“待开发”并说明等待的模块，不填充示例数据。设计来源与原型的读取方式见[运维“前端原型”](docs/runbook.md)。

### 品牌与图标

品牌名 **磐石 / Quant Lab**（平台是研究工作站立的地基），定义集中在 `frontend/src/brand.ts`，改名或换标语只改一处。图形是三层等重叠压的石台，与界面图标同族（24×24 网格、1.8 描边），顶面用描边而非实心以免读成箭头。

```sh
uv run python tools/project.py icons   # 生成 favicon 与 app 图标到 frontend/public
```

几何同时定义在 `tools/project.py`（栅格化）与 `AppIcon.icons.ts`（浏览器 SVG），改形时两处同步。

## 账号与邀请码

> ⚠️ **本节包含可用的登录凭据与注册邀请码，且本文件受 Git 跟踪。**
> 提交后它们会永久留在仓库历史中；推送到远程后任何能读仓库的人都可以看到。
> 仅适用于单人、私有、不公开的仓库。若要公开仓库或邀请他人协作，
> 请先作废下列邀请码（`identity --identity-action invite-revoke`）、
> 重置管理员密码，再把本节改成从 `.env` 或密码管理器读取。

首次登录使用管理员账号：

| 项 | 值 |
|---|---|
| 邮箱 | `admin@example.com` |
| 密码 | `admin-mp3CW5mMLEB8j28JW8bc` |
| 角色 | `admin` |
| 地址 | 开发环境 <http://127.0.0.1:5173/login> |

自助注册需要邀请码（单次使用，默认 14 天有效）。当前可用邀请码：

| 标签 | 邀请码 | 状态 |
|---|---|---|
| 初始邀请码 | `rp_1KbSmh8l_iCAag` | 可用，有效期至 2026-11-01 |

查看邀请码状态、发新码或作废：

```sh
uv run python tools/project.py identity --identity-action invite-list
uv run python tools/project.py identity --identity-action invite-create --label "给谁用"
uv run python tools/project.py identity --identity-action invite-revoke --code-id <id>
```

管理员密码可在命令行重置（同时撤销该账号所有会话）：

```sh
uv run python tools/project.py identity --identity-action user-reset-password \
  --email admin@example.com --password '新密码'
```

登录还需要 `.env` 中配置 `RP_AUTH__SECRET`（≥32 字符）。该密钥已在本机生成，
不进 Git；换机器时需要重新生成并重建会话（详见[运维“注册与登录”](docs/runbook.md)）。

## 目录

```text
frontend/src/                         Vue 页面、组件、api、stores、navigation、styles
backend/src/research_platform/
  core/                               配置、数据库、公共错误、脱敏日志、超时/重试策略
  modules/identity/                   身份 Interface，默认拒绝
  modules/catalog/                    私人目录纵向示例
  modules/execution/                  平台作业、领取、Worker
  modules/market/                     公共行情：快照、日内K线、竞价、Tushare 日线
backend/tests/                        接口、用户隔离、队列恢复、错误/日志契约、模块守卫
backend/alembic/                       新工程的版本化迁移
tools/project.py                      唯一通用任务入口
deploy/                               容器与本机部署配置
docs/                                 仅三份长期文档
.scratch/                             临时实验、报告、数据库；Git 忽略
```

## 错误、日志与超时

失败统一为 `detail: {code, message, request_id, fields?}`，HTTP 状态来自 `core/errors.py` 的显式映射；每个响应带 `X-Request-ID`，页面提示可直接用于按请求编号查日志。API 与 Worker 只向 stdout 输出单行 JSON（`RP_LOG_LEVEL` 控制级别），密码、令牌、Cookie、连接串与异常原文在写入前统一脱敏，异常只记录类名。

超时与重试规则集中在 `core/policies.py`，按访问类型分别执行：读 15 秒/最多重试 1 次（仅网络故障与 502/503/504）、写 30 秒/不重试、健康探活 5 秒/不重试、提交作业 20 秒/不重试、Worker 连库 1/2/4 秒退避最多 3 次。排障步骤见[运维文档](docs/runbook.md)“错误排查与日志”。

## 文档只保留六个正式入口

- 本 README：运行方式与当前能力。
- [AGENTS.md](AGENTS.md)：代理日常规则。
- [CONTRIBUTING.md](CONTRIBUTING.md)：Git、评审和开发约定。
- [架构](docs/architecture.md)：模块和数据/权限 Interface。
- [决策](docs/decisions.md)：真正影响后续维护的技术取舍。
- [运维](docs/runbook.md)：环境、迁移、恢复和发布检查。

另有一份短 PR 模板。CI 限制 Markdown 注册清单与单文件长度，新增长期文档需要调整清单并解释原因。任务过程、一次性审计和进度不新增 Markdown，用 Issue/PR；临时脚本放 `.scratch/`，达到复用价值后整理成正式模块或统一任务子命令。

## Git 与发布状态

默认分支 main，功能使用短期分支与 PR；CI 配置已提供。仓库为本地独立仓库，未创建远程、未推送，远程分支保护须连接仓库后配置，不能仅靠 YAML 宣称生效。

Git 只管理代码、迁移、锁文件、契约和上述少量文档。数据库、真实数据、截图、报告、构建产物和环境文件均不入库。旧工程与原型保留，迁移采用逐模块适配和真实结果对拍。
