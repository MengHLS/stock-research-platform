# 运行与发布

## 本地开发

按 README 安装锁定依赖和启动。统一入口自动建立 .scratch；migrate-local 只允许此目录中的新 SQLite 数据库，不允许它误连旧 MySQL/TiDB。

数据库版本查看使用 Alembic current。初始迁移无旧库导入，downgrade 明确拒绝删除数据；需要回退时采用备份恢复或经过评审的前向修复。

接口修改后运行 contract 并提交生成的 schema.d.ts。check 会独立重新生成到忽略目录并比较，不悄悄覆盖已提交的契约。

## 可选本机构建容器

deploy/compose.yaml 是本机 MySQL 开发模板，端口只绑定 127.0.0.1；不会自动迁移数据库。

在忽略的 deploy/.env 中提供 MYSQL_PASSWORD 和 MYSQL_ROOT_PASSWORD 后，在 deploy 目录执行：

此开发模板把 MYSQL_PASSWORD 放入连接 URL，因此密码使用随机生成的 URL 安全字符（字母、数字、下划线或连字符）；含 @、:、/ 等字符的凭据不能直接代入该模板，正式配置应分别传值并通过 URL.create 构造。

```sh
docker compose build
docker compose up -d db
docker compose run --rm api alembic -c backend/alembic.ini upgrade head
docker compose up -d
```

这组迁移命令仅适用于模板创建的新 research 数据库；现有生产库必须先做基线、备份和迁移评审。开发数据卷会保留；删除卷会丢数据，不在清理命令里自动执行。

当前环境未安装 Docker；本模板尚未实际运行，不能据此宣称 MySQL 兼容或容器部署验收通过。

## 面向独立服务器的发布门槛

1. 选定 Python 认证实现，完成邀请/会话/注销/禁用和私人资源双用户验证。
2. 生产配置检查、MySQL 迁移、备份恢复演练通过；研究执行器和对象存储访问分别验收。
3. 前后端静态资源/API 同域 HTTPS；接入 Caddy 或现有网关。数据库和存储管理口不公开。
4. CI 类型/测试/构建及目标环境冒烟通过后，才正式解除当前生产启动阻断。
5. 使用不可变镜像；保留上一版配置及恢复方案。禁止生产自动升级依赖或启动时自动生成 DDL。

## 故障处理

- liveness 失败：检查进程和启动日志；production 阻断是有意行为。
- readiness 失败：检查新库迁移和数据库可达性；不要用空数组冒充健康。
- AUTH_NOT_CONFIGURED：真实身份尚未接入，不创建临时管理员绕过。
- Worker 无待处理项：空闲正常；未知 handler 会显式失败。
- 作业租约耗尽：最多三次后 LEASE_EXHAUSTED；保留记录调查原因，不覆盖旧终态。
- 清理：只处理自己创建的 .scratch 内容，确认实际路径和用途；真实研究证据另有保留策略。

日志不输出连接串、密码或会话令牌。磁盘、任务失败、队列等待和备份状态接入正式监控后再开放远程试用。
