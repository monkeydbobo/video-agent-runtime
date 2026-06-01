---
name: manga-workflow
description: 将小说转换为短视频的端到端工作流编排器。当用户提到做视频、创建项目、继续项目、查看进度时必须使用此 skill。触发场景包括但不限于："帮我把小说做成视频"、"开个新项目"、"继续"、"下一步"、"看看项目进度"、"从头开始"、"拆集"、"自动跑完流程"等。即使用户只说了简短的"继续"或"下一步"，只要当前上下文涉及视频项目，就应该触发。不要用于单个资产生成（如只重画某张分镜图或只重新生成某个角色设计图——那些有专门的 skill）。
---
<!-- mode: marketing -->

# 视频工作流编排

你（主 agent）是编排中枢。你**不直接**处理小说原文或生成剧本，而是：
1. 检测项目状态 → 2. 决定下一阶段 → 3. dispatch 合适的 subagent → 4. 展示结果 → 5. 获取用户确认 → 6. 循环

**核心约束**：
- 产品简报/脚本原文**永远不加载到主 agent context**，由 subagent 自行读取
- 每次 dispatch 只传**文件路径和关键参数**，不传大块内容
- 每个 subagent 完成一个聚焦任务就返回，主 agent 负责阶段间衔接

> 三种生成模式（图生视频 / 宫格生视频 / 参考生视频）的数据路径与阶段分支详见 `.claude/references/generation-modes.md`。

---

## 阶段 0：项目设置

**重要**：项目目录的创建由 Web 端 `POST /api/v1/projects` 触发 `ProjectManager.create_project()` 完成（包括所有子目录与 `project.json`、按 content_mode 物化对应的 agent profile）。**主 agent 不创建目录、不写入 project.json 初始字段**——session 启动时 cwd 已绑定到已存在的项目根。

### 新项目

1. 提示用户在 Web 端先创建项目，**创建时指定 content_mode=marketing**；session 启动后 cwd 已绑定到对应项目根
2. 使用 Read 工具读取 `project.json`，确认 `title`、`content_mode`、`generation_mode` 字段（本 session 当前 content_mode 为 `marketing`，创建后不可变更）
3. 若 `generation_mode` 未在创建时指定，默认 storyboard；可在 Web 端补齐
4. 请用户将产品简报/广告脚本放入 `source/`（若只有商品图、无文字简报，可跳过——见阶段 2.3 会从商品图自动生成简报）
5. 如果用户选择“爆款复刻”：
   - 将爆款参考视频放入 `reference_videos/`（支持 `.mp4` / `.mov` / `.webm`）
   - 将商品图（产品图）放入 `product_images/`（支持 `.png` / `.jpg` / `.jpeg` / `.webp`，可多张）
6. **上传后自动生成项目概述**（synopsis、genre、theme、world_setting）

> 标准项目子目录由 `create_project()` 自动建好：`source/`、`scripts/`、`drafts/`、`characters/`、`scenes/`、`props/`、`storyboards/`、`grids/`、`videos/`、`reference_videos/`、`product_images/`、`thumbnails/`、`output/`。

### 现有项目

1. session cwd 已经绑定到目标项目根
2. 通过 Read `project.json` + Glob 文件系统判定状态摘要
3. 从上次未完成的阶段继续

---

## 状态检测

进入工作流后，使用 Read 读取 `project.json`，使用 Glob 检查文件系统。按顺序检查，遇到第一个缺失项即确定当前阶段：

1. `product_images/` 中存在商品图，且 `drafts/episode_{N}/step0_product_brief.md` 不存在？ → **阶段 2.3**（商品图内容理解；会写出 `source/episode_{N}.txt` 并把产品写入 characters 桶、绑定 `reference_image`）
2. characters / scenes / props 中**任一**为空（定义缺失）？ → **阶段 1**
3. 目标集 source/episode_{N}.txt 不存在？ → **阶段 2**
4. `reference_videos/` 中存在爆款参考视频，且 `drafts/episode_{N}/step0_viral_analysis.md` 不存在？ → **阶段 2.5**
5. 目标集 drafts/ 中间文件不存在？ → **阶段 3**
   - content_mode == marketing: `drafts/episode_{N}/step1_ad_units.md`
   - generation_mode == reference_video: `drafts/episode_{N}/step1_reference_units.md`
   - 其它 narration: `drafts/episode_{N}/step1_segments.md`
6. scripts/episode_{N}.json 不存在？ → **阶段 4**
7. 任一类资产仍有缺 sheet 项（character 缺 character_sheet / scene 缺 scene_sheet / prop 缺 prop_sheet）？ → **阶段 5**（三类并行）
8. **storyboard / grid 模式**：有场景缺少分镜图？ → **阶段 6**（reference_video 模式跳过）
9. 有场景/unit 缺少视频？ → **阶段 7**
10. 全部完成 → 工作流结束，引导用户在 Web 端导出剪映草稿

**确定目标集数**：如果用户未指定，找到最新的未完成集，或询问用户。

---

## 阶段间确认协议

**每个 subagent 返回后**，主 agent 执行：

1. **展示摘要**：将 subagent 返回的摘要展示给用户
2. **获取确认**：使用 AskUserQuestion 提供选项：
   - **继续下一阶段**（推荐）
   - **重做此阶段**（附加修改要求后重新 dispatch）
   - **跳过此阶段**
3. **根据用户选择行动**

---

## 阶段 1：全局角色/场景/道具提取

**触发**：project.json 中 characters / scenes / props 中**任一**为空（定义缺失）

**dispatch `analyze-assets` subagent**：

```
项目名称：{project_name}
分析范围：{整部小说 / 用户指定的范围}
已有角色：{已有角色名列表，或"无"}
已有场景：{已有场景名列表，或"无"}
已有道具：{已有道具名列表，或"无"}

请分析小说原文，提取角色 / 场景 / 道具信息，写入 project.json，返回摘要。
```

> **marketing 注意**：阶段 2.3 已把商品图绑定到各产品（characters 桶）的 `reference_image`。
> 阶段 1 对已存在的产品必须**合并**而非覆盖——保留其 `reference_image`，只补充缺失的 scenes / props 与产品描述，
> 避免清掉商品图绑定导致阶段 5 失去以图生图的输入参考。

---

## 阶段 2：分集规划

**触发**：目标集的 `source/episode_{N}.txt` 不存在

每次只切分当前需要制作的那一集。**主 agent 直接执行**（不 dispatch subagent）：

1. 确定源文件：`source/_remaining.txt` 存在则使用，否则用原始小说文件
2. 询问用户目标字数（如 1000 字/集）
3. 调用 `peek_split_point.py` 展示切分点附近上下文：
   ```bash
   python .claude/skills/manage-project/scripts/peek_split_point.py --source {源文件} --target {目标字数}
   ```
4. 分析 nearby_breakpoints，建议自然断点
5. 用户确认后，先 dry run 验证：
   ```bash
   python .claude/skills/manage-project/scripts/split_episode.py --source {源文件} --episode {N} --target {目标字数} --anchor "{锚点文本}" --dry-run
   ```
6. 确认无误后实际执行（去掉 `--dry-run`）

---

## 阶段 2.3：商品图内容理解（可选，爆款复刻用）

**触发**：`product_images/` 下存在 `.png` / `.jpg` / `.jpeg` / `.webp`，但目标集缺少 `drafts/episode_{N}/step0_product_brief.md`

**dispatch `analyze-product-images` subagent**：

```
项目名称：{project_name}
项目路径：{project_path}
集数：{N}
商品图：{product_images/ 下的图片路径列表；未指定时取全部}

请对商品图做内容理解，产出结构化产品简报，写入 drafts/episode_{N}/step0_product_brief.md，
同步写 source/episode_{N}.txt，并把每个产品的 reference_image 绑定到对应商品图，返回摘要。
```

**约束**：
- 只基于商品图可见信息与项目概述推断，不虚构图中不存在的功能或参数
- 产品简报会兼作 `source/episode_{N}.txt`（满足阶段 2 的源文件条件），并把产品写入 characters 桶、绑定 `reference_image`，供阶段 5 以图生图渲染产品三视图
- 完成后，若 scenes / props 仍为空，再走阶段 1 从简报补充提取

---

## 阶段 2.5：爆款视频内容理解（可选）

**触发**：`reference_videos/` 下存在 `.mp4` / `.mov` / `.webm`，但目标集缺少 `drafts/episode_{N}/step0_viral_analysis.md`

**dispatch `analyze-viral-reference` subagent**：

```
项目名称：{project_name}
项目路径：{project_path}
集数：{N}
参考视频：{reference_videos/ 下的爆款视频路径；未指定时选择最近上传的视频}

请分析爆款参考视频，提取可复刻的镜头结构、节奏、口播/字幕结构与 CTA 模板，
写入 drafts/episode_{N}/step0_viral_analysis.md，返回摘要。
```

**约束**：
- 只复刻结构、节奏、卖点展开方式，不复制原视频的人物、品牌、logo、音乐名或可识别台词
- 内容理解结果只作为后续 `split-marketing-ad-units` 的参考，不直接替代本项目产品简报

---

## 阶段 3：单集预处理

**触发**：目标集的 drafts/ 中间文件不存在

根据 `effective_mode(project, episode)` 选择 subagent：

- `generation_mode == reference_video` → dispatch `split-reference-video-units`
- content_mode == marketing → dispatch `split-marketing-ad-units`

dispatch prompt 通用参数：项目名称、项目路径、集数、本集小说文件路径。

（两个预处理 subagent 会自行读 project.json + 调用
`mcp__arcreel__get_video_capabilities({})`
拿到模型能力与用户偏好；主 agent 不需要预先注入角色/场景/道具列表或
`supported_durations` / `max_duration` / `max_reference_images` / `default_duration` 等数据。）

---

## 阶段 4：JSON 剧本生成

**触发**：scripts/episode_{N}.json 不存在

**dispatch `create-episode-script` subagent**：传入项目名称、项目路径、集数。

---

## 阶段 5：资产设计（character / scene / prop 三类并行）

**前置条件**：三类资产的定义（characters / scenes / props）均已通过阶段 1 写入 project.json。若任一类定义为空（数组缺失），应回到阶段 1 补提取，而非停留在阶段 5。

**触发**：三类资产中任一类存在缺 sheet 项：
- character 缺 character_sheet
- scene 缺 scene_sheet
- prop 缺 prop_sheet

**调度规则（显式条件判断，按类型独立决定）**：

```
对于 type ∈ {character, scene, prop}:
  若该类存在缺 *_sheet 项 → dispatch 对应的 `generate-assets` subagent
  若该类均已齐全         → 跳过，不 dispatch

三类判断彼此独立，结果可能 dispatch 0~3 个 subagent。
所有 dispatch 的 subagent 返回后，合并摘要展示给用户，进入阶段间确认。
```

下面三个 dispatch 块是模板，只实例化满足上述条件的那几个：

### subagent — 产品三视图

**触发**：有产品（characters 桶）缺少 character_sheet

```
dispatch `generate-assets` subagent：
  任务类型：character（API 仍为 character，语义为产品）
  项目名称：{project_name}
  待生成项：{缺失产品名列表}
  工具调用：
    mcp__arcreel__generate_assets({"type": "character"})
  验证方式：重新读取 project.json，检查对应角色的 character_sheet 字段
```

### subagent — 场景设计

**触发**：有场景缺少 scene_sheet

```
dispatch `generate-assets` subagent：
  任务类型：scene
  项目名称：{project_name}
  待生成项：{缺失场景名列表}
  工具调用：
    mcp__arcreel__generate_assets({"type": "scene"})
  验证方式：重新读取 project.json，检查对应场景的 scene_sheet 字段
```

### subagent — 道具设计

**触发**：有道具缺少 prop_sheet

```
dispatch `generate-assets` subagent：
  任务类型：prop
  项目名称：{project_name}
  待生成项：{缺失道具名列表}
  工具调用：
    mcp__arcreel__generate_assets({"type": "prop"})
  验证方式：重新读取 project.json，检查对应道具的 prop_sheet 字段
```

---

## 阶段 6：分镜图生成（仅 storyboard / grid 模式）

**触发**：有场景缺少分镜图；**参考生视频模式跳过此阶段**

检查 `effective_mode(project, episode)`：

- `"storyboard"` → dispatch `generate-assets`，调 `mcp__arcreel__generate_storyboards`
- `"grid"` → dispatch `generate-assets`，调 `mcp__arcreel__generate_grid`
- `"reference_video"` → 不触发，直接跳到阶段 7

### storyboard 模式（默认）

**dispatch `generate-assets` subagent**：

```
dispatch `generate-assets` subagent：
  任务类型：storyboard
  项目名称：{project_name}
  工具调用：
    mcp__arcreel__generate_storyboards({"script": "episode_{N}.json"})
  验证方式：重新读取 scripts/episode_{N}.json，检查各场景的 storyboard_image 字段
```

### grid 模式

**dispatch `generate-assets` subagent**：

```
dispatch `generate-assets` subagent：
  任务类型：storyboard
  项目名称：{project_name}
  工具调用：
    mcp__arcreel__generate_grid({"script": "episode_{N}.json"})
  验证方式：重新读取 scripts/episode_{N}.json，检查各场景的 storyboard_image 字段
```

---

## 阶段 7：视频生成

**触发**：有场景缺少视频

**dispatch `generate-assets` subagent**：

```
dispatch `generate-assets` subagent：
  任务类型：video
  项目名称：{project_name}
  工具调用：
    mcp__arcreel__generate_video_episode({"script": "episode_{N}.json"})
  验证方式：重新读取 scripts/episode_{N}.json，检查各场景的 video_clip 字段
```

---

## 灵活入口

工作流**不强制从头开始**。根据状态检测结果，自动从正确的阶段开始：

- "分析小说角色" → 只执行阶段 1
- "创建第2集剧本" → 从阶段 2 开始（如果角色已有）
- "继续" → 状态检测找到第一个缺失项
- 指定具体阶段（如"生成分镜图"）→ 直接跳到该阶段

---

## 数据分层

- 角色 / 场景 / 道具完整定义**只存 project.json**，剧本中仅引用名称
- 统计字段（scenes_count、status、progress）**读时计算**，不存储
- 剧集元数据在剧本保存时**写时同步**
