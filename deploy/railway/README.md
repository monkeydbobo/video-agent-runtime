# Railway 部署

此目录为 ArcReel 在 Railway 上运行所需的最小配置。Railway 从仓库根目录的
`Dockerfile` 构建，并通过 `railway.json` 用 `/health` 检查服务状态。

## Railway 服务设置

1. 创建项目并从 GitHub 导入本仓库的目标分支。
2. 添加 **PostgreSQL** 服务。
3. 为 ArcReel 服务添加一个 Volume，挂载路径设为 `/data`。
4. 在 ArcReel 服务的 Variables 中添加 `deploy/railway/.env.example` 中的变量；
   `DATABASE_URL` 的值设为 `${{Postgres.DATABASE_URL}}`（如果 PostgreSQL 服务改名，
   同步替换引用中的服务名）。
5. 在 Networking 中生成域名，或绑定 `app.oioi.space`。应用会自动读取 Railway
   提供的 `PORT`，无需手填端口。

## 持久化边界

`ARCREEL_DATA_DIR=/data/projects` 使项目、媒体产物和本地运行数据保存在 Volume。
Vertex 凭据会按应用规则写入 `/data/vertex_keys`，因此同一块 Volume 即可保护二者。
PostgreSQL 保存账户、配置、任务和用量等数据库记录。

首次部署成功后，用 `AUTH_USERNAME` / `AUTH_PASSWORD` 登录，进入“设置”配置 AI
助手以及至少一个文本、图像或视频供应商的 API Key。
