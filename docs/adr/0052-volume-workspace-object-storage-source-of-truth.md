---
status: accepted
---

# Volume 作媒体工作盘，对象存储作视频持久层，下载地址按需签发

ArcReel 的供应商视频 URL 是临时交付通道，不是平台可控的持久地址；现有 Worker 已把结果下载到
Railway Volume，FFmpeg 成片也写在同一目录，但 Volume 与单个服务实例绑定、容量有限，并且无法
支撑多副本。决定引入私有 S3 兼容对象存储：Volume 继续承担生成、缩略图与 FFmpeg 的低延迟工作盘，
`videos/` 当前视频和 `output/` 成片在完成后以确定性 object key 双写到对象存储。

对象 key 由 `user_id + project_name + 项目内相对路径` 唯一导出，不把供应商临时 URL 或服务器绝对路径
作为对象身份。项目 JSON 继续保存 canonical 相对路径，避免把某家 S3 的 URL/签名生命周期泄漏到领域数据。
对象存储未配置时保持 Volume-only 兼容；配置后，供应商视频上传失败按 best-effort 记录，避免已经计费成功
的生成任务被重跑；可安全重跑的 FFmpeg 成片则要求上传成功后才报告完整成功。

下载仍通过 `media.oioi.bio` 文件级短时令牌进入。Volume 有本地副本时由 Railway CDN 缓存服务响应；
本地副本缺失时，同一路由验证对象存在后 307 跳转到 Bucket 的预签名 URL，避免视频字节继续经过应用服务。
Web 端每次点击成片时调用鉴权接口重新签发 URL，历史成片不再因签名过期而要求重新合成。

对象存储 module 的 interface 只有四项能力：发布项目文件、判断项目文件是否存在、签发项目文件 URL、
列出项目当前媒体文件。
S3 key、MIME、重试、签名参数和路径安全全部藏在 implementation 内；生成、Compose、文件路由只跨这一
seam。现有媒体可通过 `scripts/migrate_media_to_object_storage.py` 幂等回填，迁移阶段不删除 Volume 文件。

## 明确不采用

- **把供应商 OSS URL 当持久地址**：签名与账号由供应商控制，过期后无法由 ArcReel 续签。
- **把所有项目文件立即迁出 Volume**：FFmpeg 与生成链路需要本地随机读写；首版双写降低迁移风险。
- **把 S3 URL写入 project.json**：会把存储 adapter 细节扩散到前端、归档、版本与校验模块。
- **公开 Bucket**：Railway Bucket 本身是私有的；文件访问必须经项目鉴权或短时预签名。

## Consequences

- 新生成视频和成片具备平台控制的持久副本；供应商临时 URL 过期不影响 ArcReel 文件。
- Volume 仍需容量监控；后续可在确认对象上传后增加本地淘汰与按需回源，不改变现有 interface。
- Railway Bucket 不支持对象版本和生命周期规则，版本历史仍由 ArcReel 自身管理。
- Bucket 上传是服务出站流量，浏览器从 Bucket 下载不经过应用服务；CDN 命中路径与回源路径语义一致。
