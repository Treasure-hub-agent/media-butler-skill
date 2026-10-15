<div align="center">

# 🎬 media-butler

> **影视文件管理 CLI · 给 agent 用的本地媒体库管家**

**把「一堆混乱的影视文件名」变成「按规范命名、分好类、带清单的媒体库」。**

🌐 **中文** ｜ [English](README.en.md)

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-orange.svg)](CHANGELOG.md)

不部署服务、不注册账号、不写配置文件也能用：解析文件名 → 查公开元数据 → 规范化命名 → 按类型归档 → 维护本地清单。
检索与获取能力由**可插拔适配器**提供：仓库内不含任何具体站点的适配器，只带一个**聚合器适配器**（由其服务端代为访问上游公开索引），可一键关闭回到纯离线模式。

</div>

---

## ✨ 功能简介

**media-butler** 是一个纯本地的影视文件管理工具，配套一份 agent 操作规范（`SKILL.md`）。你可以直接当命令行工具用，也可以让 AI agent 装载 skill 后替你跑完整流程。

它替你解决这些事：

- 🧩 **文件名解析**：从 `Some.Movie.2019.1080p.WEB-DL.简繁中字.mkv` 这类资源名里提取片名、年份、季集号、中文字幕标记——纯正则与规则，不猜、不联网
- 📚 **公开元数据查询**：把中文片名映射成可检索的拉丁名（国际索引源普遍只认拉丁名），产出多语种检索候选词
- 🗂 **规范化命名与分类归档**：`电影 / 影片名 (年份) / 影片名 (年份).mkv`、`剧集 / 剧名 (年份) / Season 01 / 剧名 S01E03.mkv`，四类目录（电影 / 剧集 / 动漫 / 其他）自动判定
- 📋 **本地媒体库清单**：SQLite 内部索引 + `library.json` / `LIBRARY.md` 双轨文本清单，agent 与人都能直接读；索引删了还能从磁盘重建
- 🔍 **缺集盘点**：按季比对已入库集号，直接给出缺哪几集
- 🩺 **只读巡检**：源可达性、库文件完整性、目标目录的文件系统能力（是否支持硬链接）一次查清
- 🔌 **可插拔扩展（可选）**：检索、字幕、下载引擎全部适配器化，单源挂掉不影响主流程；自定义源只需实现一个类

**设计原则**：LLM 做理解，CLI 做确定性。体积、种子数、哈希、路径一律由 CLI 输出，模型不心算。

---

## 📌 版本动态（v0.1.0 · 首个公开版本）

> 本栏目只保留当前版本的变化；完整历史见 [CHANGELOG.md](CHANGELOG.md)。

**🧩 文件解析与元数据**

- 资源名解析：片名、年份、季集号、合集/整季、中文字幕标记一次提取，输出 JSON
- 元数据查询：中英日三语名映射，自动生成多个可检索写法
- 词元校验闸门：结果标题必须命中查询词元，挡掉源侧语义污染

**🗂 归档与清单**

- 规范化命名 + 按类型分类（电影 / 剧集 / 动漫 / 其他），剧集自动落 `Season NN/`
- 路径越界防护：远端来的文件名拼进媒体库前做 realpath 断言，越界直接拒绝
- 硬链接三级回退：`rename → link → copy`，回退到复制时大文件必须显式放行，**绝不静默复制**
- 双轨清单：SQLite 当索引，`library.json` / `LIBRARY.md` 给 agent 与人读；索引可从磁盘无损重建

**🩺 只读巡检**

- 源可达性、库内丢文件、零字节残留、孤立字幕
- 文件系统能力探针：在目标目录真建临时文件试一次 `link()`，比查表可靠；探完即清理

**🔌 检索与获取（可插拔，默认收敛）**

- 三层源结构：聚合器适配器 + 通用骨架 + 用户自备源
- 中字优先排序；词元闸门防污染；单源失败静默跳过并由巡检上报
- 下载一律异步启动，不阻塞 agent 的工具调用
- 中文字幕：本地外挂检测优先，缺失时走字幕站补齐（含返回内容清洗）

**⚙️ 工程**

- **零第三方 Python 依赖**：纯标准库（BT 下载靠外部 `aria2c`，不算 Python 依赖）
- 会改动媒体库的写操作都带 `--dry-run`（`ingest` / `grab` / `subs` / `config` / `index rebuild`），预演绝不落盘；写状态只落用户家目录，不碰 skill 目录

---

## 为什么需要它

影视文件管理的痛点是「杂乱来自下载，而整理全靠手工」：

| ❌ 没有它 | ✅ 有了它 |
|---|---|
| 下载目录里一堆 `[组名]片名.2019.1080p.x265.简繁中字.mkv`，认不出是什么片 | `parse` 一条命令出结构化 JSON：片名 / 年份 / 季集 / 中字标记 |
| 中文片名在国际索引源上搜不到，只能自己想办法找英文名 | `meta` 自动产出拉丁检索名候选，中英互查 |
| 手工重命名、手工建 `Season 01` 目录，一部剧几十集重命名到崩溃 | `ingest --dry-run` 先给计划，确认后一条命令全部归档到位 |
| 手滑把电影塞进「剧集」目录，或者剧集被当成电影 | 按文件名线索自动判类型，四类目录各归各位；也可 `--type` 强制指定 |
| 「我到底有没有这一集？」只能靠翻文件夹数文件 | `index missing --title <剧名> --season 1 --expect 24` 直接给缺集号 |
| 归档时脚本默默复制了 40GB，硬盘突然满了 | 大文件复制必须显式放行，默认拒绝并如实上报原因 |
| 「移动」还是「复制」？删源会不会丢数据？没人说得清 | 默认 `move`（同盘瞬时、不占额外空间）；默认不覆盖、不删除 |
| 媒体库换机器后清单全丢 | 索引可从磁盘目录结构无损重建，清单随时重新导出 |

**它不做**：媒体服务器（不接 Jellyfin/Emby/Plex 播放）、订阅追新（无无人值守循环）、流媒体/DRM 相关能力、抓站与自建索引服务。

---

## 🚀 快速开始

### 1. 取得代码

方式一，作为 agent skill 安装（含 `SKILL.md`，agent 会自动按规范操作）：

```bash
npx skills add Treasure-hub-agent/media-butler-skill
```

方式二，手动克隆当普通 CLI 用：

```bash
git clone https://github.com/Treasure-hub-agent/media-butler-skill.git
cd media-butler-skill
```

> 作为 skill 使用时，把仓库目录放进你的 agent 技能目录即可（只要能读取 `SKILL.md`）。Hermes 用户也可以走 `hermes skills tap add Treasure-hub-agent/media-butler-skill`。

**运行要求**：Python 3.8+（纯标准库，无需 pip 安装任何包）。`aria2c` 为可选，仅在需要下载时使用。

### 2. 确认 CLI 可用

```bash
python3 scripts/media.py --version
python3 scripts/media.py --help
```

### 3. 设置媒体库与下载目录

```bash
python3 scripts/media.py config \
  --set library_root=/data/media \
  --set download_root=/data/downloads
```

`config` 不带参数时打印当前全部配置（含状态目录路径）：

```bash
python3 scripts/media.py config
```

### 4. 归档入库（先预演，再落地）

```bash
# 预演：只打印计划，绝不落盘
python3 scripts/media.py ingest /data/downloads --type movie --dry-run

# 确认无误后执行
python3 scripts/media.py ingest /data/downloads
```

`--type` 可省略，默认按文件名与目录线索自动判定（动漫 > 剧集 > 电影）。

### 5. 查看媒体库清单

```bash
python3 scripts/media.py index stats
python3 scripts/media.py index list
python3 scripts/media.py index export          # 导出 library.json / LIBRARY.md
```

至此，一条完全不联网的整理链路已经跑通：**解析 → 命名 → 归档 → 清单**。

---

## 核心能力

| 命令 | 作用 | 何时用 | 关键参数 |
|---|---|---|---|
| `parse <文件名>` | 解析资源名，输出结构化 JSON | 不确定某个文件是什么片、有没有中字 | — |
| `meta <片名>` | 查公开元数据 + 生成多语种检索名 | 中文名搜不到，想要拉丁名候选 | — |
| `search <片名>` | 多源检索（中字优先排序） | 想看看有哪些可选版本 | `--limit` |
| `grab <磁力>` | 异步加入下载 | 已选定片源，交给下载器 | `--dest` `--select` `--dry-run` `--allow-direct` |
| `status` | 查看下载进度 | 想知道下到哪了 | `--dest` `--lines` |
| `subs <片名｜文件>` | 获取中文字幕 | 外国片缺中字 | `--file` `--dest` `--dry-run` |
| `ingest <目录>` | 命名 + 分类 + 归档入库 | 下载完，想把文件摆正 | `--library` `--type` `--dry-run` |
| `index list｜stats｜export｜missing｜rebuild` | 清单查询、统计、导出、缺集、重建 | 盘点库、找缺集 | `--library` `--title` `--season` `--expect` |
| `doctor sources｜library｜fs｜regrab` | **只读**巡检 | 排查不可达/丢文件/能否硬链接 | `--library` `--src` `--dest` |
| `config` | 配置读写 | 设置媒体库、下载目录、代理 | `--set k=v` `--dry-run` |

---

## 使用指南

### 整理一个混乱的下载目录

```bash
# 1. 先看它打算怎么摆
python3 scripts/media.py ingest /data/downloads --dry-run

# 2. 混合内容（电影 + 剧集）也会各自归位，不需要分批
python3 scripts/media.py ingest /data/downloads

# 3. 归档结果逐条写入索引，并自动刷新可读清单
python3 scripts/media.py index export
```

归档后的目录结构：

```
媒体库根/
├── 电影/        影片名 (年份)/影片名 (年份).mkv
├── 剧集/        剧名 (年份)/Season 01/剧名 S01E03.mkv
├── 动漫/        番剧名 (年份)/Season 01/番剧名 S01E03.mkv
└── 其他/        归属不清的都放这里，绝不猜测
```

**归档默认姿态**：不覆盖已存在的文件（报 `skipped-exists`）、不删除源文件（除非用 `move` 移动）、不改文件内容。重复入库是幂等的，不会产生重复记录。

### 处理一个非 1080p 就认不出的文件名

```bash
python3 scripts/media.py parse "Some.Movie.2019.1080p.WEB-DL.简繁中字.mkv"
```

输出（节选）：

```json
{
  "title": "Some Movie",
  "year": 2019,
  "season": null,
  "episode": null,
  "is_batch": false,
  "marks": ["中字", "简繁", "繁中"],
  "groups": []
}
```

`marks` 非空即表示识别到中文字幕标记，`is_batch` 为 `true` 表示整季/合集。

### 盘点库里缺了哪几集

```bash
python3 scripts/media.py index rebuild --library /data/media   # 索引丢失时重建
python3 scripts/media.py index missing --title "Some Show" --season 1 --expect 24
```

输出缺集号数组，例如 `[3, 7, 12]`。不给 `--expect` 时按已入库最大集号推断。

### 补中文字幕

```bash
# 先看本地是不是已经有外挂字幕（有就直接返回路径，不发任何请求）
python3 scripts/media.py subs --file /data/media/电影/Some\ Movie\ \(2019\)/Some\ Movie\ \(2019\).mkv

# 本地没有时，列出候选（不下载）
python3 scripts/media.py subs "Some Movie 2019" --dry-run
```

**如实提示**：字幕与片源的版本可能时间轴不匹配；找不到就该报「未找到」，工具不会假装成功。

### 巡检：先确认地基，再动手

```bash
python3 scripts/media.py doctor fs        # 目标目录能否硬链接（真探针，非查表）
python3 scripts/media.py doctor library   # 库里有没有记录指向不存在的文件
python3 scripts/media.py doctor sources    # 源可达性（离线时如实报不可达）
```

`doctor` **全程只读**：不写任何持久文件、不改配置、不执行任何获取动作；文件系统探针会在目标目录建一个临时文件试一次 `link()`，探完立即清理。源可达性巡检只探测公开接口是否在线，不涉及检索内容。

### 检索与获取（可选，可插拔）

> ⚠️ 这一段属于扩展能力，不是本工具的主叙事。仓库内**不含任何具体站点的适配器**，只有一个**聚合器适配器**（服务端代为访问上游公开索引），它默认处于启用状态；用户自备源需要自己接入。

```bash
python3 scripts/media.py meta "Some Show"
python3 scripts/media.py search "Some Show" --limit 10
python3 scripts/media.py grab "magnet:?xt=..." --dry-run    # 先看将执行的命令行
python3 scripts/media.py grab "magnet:?xt=..."
python3 scripts/media.py status --lines 20
```

**一键回到纯离线模式**（关闭全部第三方源，整理/归档/清单不受影响）：

```bash
python3 scripts/media.py config --set sources_enabled=
python3 scripts/media.py doctor sources     # 应输出空列表
```

**使用前你必须知道**：

- 接入或启用任何第三方源，都视为**你自行确认有权访问该源**，并自行承担相应后果
- 下载会走 BT 网络，**你的 IP 会暴露给 swarm 中的其他节点**；工具不会替你隐藏这一点
- 磁力链接与 `info_hash` 只会交给下载器与 DHT/tracker，不会发给任何第三方元数据接口
- 不默认做种（`--seed-time=0`）
- 不采集任何遥测、不自动回连、不上传你的清单或源健康数据

自备源（自有 PT 站、自建中间层等）的接入方式见 `references/sources.md`。

### 存储、权限与隐私

| 项 | 位置 / 说明 |
|---|---|
| 状态目录 | Linux/macOS：`~/.media-butler/`；Windows：`%APPDATA%\media-butler\` |
| 覆盖方式 | 环境变量 `MEDIA_BUTLER_HOME` 指定任意目录 |
| 目录内容 | `config.json`（配置，写入时权限固定 `0600`，因为可能含代理凭据）、`library.db`（SQLite 索引）、`library.json` / `LIBRARY.md`（可读清单） |
| 权限建议 | 状态目录与索引文件的权限遵循系统 `umask`；多用户主机上建议自行收紧到 `0700` / `0600` |
| 最小权限 | 建议以非 root 用户运行，只挂载下载目录与媒体目录，不要给出整个 `$HOME` |
| 网络行为 | 仅在你显式调用检索/字幕命令时出网；整理、归档、清单这一半完全离线可用 |
| agent 场景 | 使用 agent 时，片名会进入会话上下文并发送给你所配置的模型提供方——这是 agent 层特有的信息暴露面，请自行评估 |

### 硬链接的两个硬约束

以移动（`rename`）为主时无需关心这一节；只有当你用 `archive_action=hardlink` 保留下载副本时，才需要：

- 要求源与目标**在同一文件系统**，并且**在同一挂载点**。Docker 下两个 bind mount 即使用宿主机上同一文件系统，容器内仍是跨设备，`link()` 会返回 `EXDEV`。
- 解法是只挂一个共同父目录（`/data` 模式）：

```yaml
volumes:
  - /srv/data:/data          # 下载与媒体库同挂载
```

```bash
python3 scripts/media.py config --set library_root=/data/media \
                                --set download_root=/data/downloads
```

- 子卷 / dataset（Btrfs subvolume、ZFS dataset、Synology/QNAP 常见分区方式）在 `st_dev` 意义上算不同文件系统，会破坏硬链接
- SMB/CIFS 挂载基本不支持硬链接；NFS 视服务器端配置而定
- Windows 仅 NTFS 同卷内可用，FAT32/exFAT 不支持
- 多个路径指向同一份数据：删掉其中一个路径**不会释放空间**

不确定时先跑一次能力探针：

```bash
python3 scripts/media.py doctor fs
```

---

## 常见问题

**Q：需要联网吗？**
不需要。解析、命名、归档、清单、缺集检测全部离线可用，`doctor fs` / `doctor library` 也是纯本地。只有 `meta` / `search` / `subs` / `grab` 需要网络或下载器。

**Q：需要安装什么依赖？**
Python 3.8+ 标准库即可，没有任何第三方 Python 包。只有真正要下载时才需要外部的 `aria2c`；没有它时 `grab` 会输出磁力链接并给出安装建议，而不是报错退出。

**Q：会弄丢我的文件吗？**
不会偷偷弄丢。默认不覆盖、不删除、不改内容；会改动媒体库的写操作都支持 `--dry-run`；归档失败只记录不中断，逐条如实上报结果（`skipped-exists` / `error:...` / `refused-large-copy`）。

**Q：为什么归档会「拒绝」复制大文件？**
跨文件系统又无法硬链接时只剩复制一条路。静默复制一个几十 GB 的文件会让用户硬盘突然爆掉、却不知道是谁干的，所以超过阈值（默认 2GiB）必须显式放行。

**Q：中文片名搜不到怎么办？**
用 `meta` 先拿拉丁检索名。国际索引源的拉丁名覆盖率远高于中文名。

**Q：`doctor` 会改我的库吗？**
不会。`doctor` 全程只读。它的「换源候选」子命令也只产出候选清单，实际获取需要你确认后另行走 `grab`。

**Q：索引数据库删了怎么办？**
`index rebuild --library <库根>` 从磁盘目录结构重建，只依赖文件名与目录结构这些本地事实。

**Q：支持 Windows / macOS 吗？**
路径处理用 `pathlib` / `os.path`，状态目录按平台落到 `%APPDATA%` 或 `~/.media-butler`。注意 NTFS 与 APFS 默认大小写不敏感、ext4 敏感，跨平台同步媒体库时留意命名撞车。

**Q：能不能自动追新、自动下载新集？**
不能，这是刻意不做：本工具没有任何订阅或无人值守循环。

---

## 免责声明

- 本工具是一个**影视文件管理 CLI**：解析文件名、查询公开元数据、规范化命名、按类型归档、维护本地清单。
  它**不托管、不索引、不抓取**任何影视内容，仓库内不含任何影视内容或指向具体作品的链接。
- 检索能力由**可插拔适配器**提供；仓库内不含任何具体站点的适配器，且可一键关闭回到纯离线模式。
- 请仅用于：你拥有合法权利或已获授权的内容、公共领域作品、以及你已购置媒介的个人备份。
  你需要自行确认所获取内容的授权状态。
- 本项目**免费、无广告、不接受捐赠、无付费解锁**；作者不从中获取任何收益。
- 完整条款（含权利人与下架响应、不接受的贡献类型）见 **[DISCLAIMER.md](DISCLAIMER.md)**。

> 一句话自省：**免责声明不产生免疫。** 真正起作用的是结构选择——不内置源、不自建索引、不自动获取、不营利、不宣传。

---

## 参与贡献

欢迎修 bug、补测试、改进文档。请先读 [CONTRIBUTING.md](CONTRIBUTING.md)（其中明确列出了**不接受的贡献类型**）。

---

## 版权

[MIT License](LICENSE) © media-butler-skill contributors

本项目以笔名维护，不在国内平台推广。仓库名、目录名与 `SKILL.md` 的 `name` 字段保持一致（均为 `media-butler-skill`），以免平台识别异常。
