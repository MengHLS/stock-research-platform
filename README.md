# 研究工作台

Vue 3 + TypeScript 前端，Python + FastAPI 后端，独立 Worker；一个 Git 仓库维护。

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

Worker 使用另一个终端：

```sh
uv run python tools/project.py worker
```

目前 Worker 仅支持有界的 `system.check` 数据库诊断。研究 Run、长任务续租、协作取消、用户配额和产物发布在接入真实计算前实现，不把平台作业当作研究完成。

## 常用入口

```sh
uv run python tools/project.py check          # 完整质量门禁
uv run python tools/project.py contract       # 根据后台生成 TypeScript 接口类型
uv run python tools/project.py hygiene        # 文档、脚本及产物存放规则
```

命令的权威定义是 `tools/project.py --help`；不要为每个任务复制一份脚本。完整检查包括后端规范与测试、接口契约漂移、前端规范与测试、类型检查和构建。

## 目录

```text
frontend/src/                         Vue 页面、组件、api、stores
backend/src/research_platform/
  core/                               配置、数据库、公共错误
  modules/identity/                   身份 Interface，默认拒绝
  modules/catalog/                    私人目录纵向示例
  modules/execution/                  平台作业、领取、Worker
backend/tests/                        接口、用户隔离、队列恢复、模块守卫
backend/alembic/                       新工程的版本化迁移
tools/project.py                      唯一通用任务入口
deploy/                               容器与本机部署配置
docs/                                 仅三份长期文档
.scratch/                             临时实验、报告、数据库；Git 忽略
```

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
