# 部署补充说明

本文档补充 [`getting-started.md`](getting-started.md) 未覆盖的部署细节，主要面向已经能够通过 Docker / 本地启动 ArcReel 的运维与开发者。

## Agent 沙箱依赖

ArcReel 启动会进行严格的安全检查 — sandbox 工具缺失即拒绝启动。

| 环境 | 工具 | 安装 |
|---|---|---|
| macOS | `sandbox-exec` | 系统自带，无需额外安装 |
| Linux 本地开发 | `bwrap` + `socat` | `sudo apt install bubblewrap socat` (Ubuntu/Debian) / `sudo dnf install bubblewrap socat` (Fedora) / `sudo pacman -S bubblewrap socat` (Arch) |
| Docker | `bwrap` + `socat` | Dockerfile 已包含 |

启动失败时 server 会输出明确错误信息，按提示安装即可。

**.env 迁移说明**：sandbox 设计要求父进程 `os.environ` 不含任何 provider 密钥。
请把 `.env` 中的下列 key 移到 WebUI 系统配置页：

- `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL` 等 ANTHROPIC_*
- `ARK_API_KEY` / `XAI_API_KEY` / `GEMINI_API_KEY` / `VIDU_API_KEY` / `DASHSCOPE_API_KEY` / `MINIMAX_API_KEY` / `OPENAI_API_KEY`
- `GOOGLE_APPLICATION_CREDENTIALS`（vertex 凭据继续放 `vertex_keys/` 目录）

启动检测发现这些 key 仍存在于 env 时，server 会拒绝启动并提示需要清理。

## Railway 媒体存储

生产环境建议同时使用 Railway Volume 和私有 S3 兼容 Bucket：

- Volume 挂载到项目目录，作为视频生成与 FFmpeg 的工作盘；
- Bucket 保存 `videos/` 当前片段和 `output/` 成片的持久副本；
- `ARCREEL_PUBLIC_MEDIA_BASE_URL` 指向独立媒体域名（例如 `https://media.example.com`）；
- Web 端按需申请文件级短时链接，本地副本不存在时服务会 307 跳转至 Bucket 预签名地址。

Bucket 服务变量映射如下：

```env
ARCREEL_OBJECT_STORAGE_ENDPOINT=${{arcreel-media.ENDPOINT}}
ARCREEL_OBJECT_STORAGE_BUCKET=${{arcreel-media.BUCKET}}
ARCREEL_OBJECT_STORAGE_ACCESS_KEY_ID=${{arcreel-media.ACCESS_KEY_ID}}
ARCREEL_OBJECT_STORAGE_SECRET_ACCESS_KEY=${{arcreel-media.SECRET_ACCESS_KEY}}
ARCREEL_OBJECT_STORAGE_REGION=${{arcreel-media.REGION}}
ARCREEL_OBJECT_STORAGE_PREFIX=media
ARCREEL_OBJECT_STORAGE_PRESIGN_SECONDS=300
```

变量引用中的 `arcreel-media` 是 Bucket 服务名，可按实际名称替换。Bucket 必须保持私有，不要把访问密钥或
Bucket 预签名地址写进 `project.json`。

升级已有部署后，先执行 dry-run，再幂等回填 Volume 上的既有视频：

```bash
uv run python scripts/migrate_media_to_object_storage.py --dry-run
uv run python scripts/migrate_media_to_object_storage.py
```

迁移不会删除 Volume 文件。完整设计和失败语义见
[`ADR 0052`](adr/0052-volume-workspace-object-storage-source-of-truth.md)。
