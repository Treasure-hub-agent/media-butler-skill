<div align="center">

# 🎬 media-butler

> **A CLI for managing your local video library · built for AI agents**

**Turns a pile of messy media filenames into a named, sorted, catalogued library.**

🌐 [中文](README.md) ｜ **English**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-orange.svg)](CHANGELOG.md)

No service to deploy, no account to register, no config file required to start: parse filenames → look up public metadata → normalize naming → sort by type → maintain a local catalogue.
Search and retrieval are provided by **pluggable adapters** — the repository bundles no site-specific adapter, and everything can be switched off for fully offline use.

</div>

---

## ✨ What It Does

**media-butler** is a purely local CLI for managing video files, shipped with an agent operating spec (`SKILL.md`). Use it directly from the shell, or let an AI agent load the skill and drive the whole flow for you.

What it handles for you:

- 🧩 **Filename parsing**: extract title, year, season/episode, and Chinese-subtitle markers from names like `Some.Movie.2019.1080p.WEB-DL.简繁中字.mkv` — pure rules, no guessing, no network
- 📚 **Public metadata lookup**: map a Chinese title to a searchable Latin name (international indexes mostly only match Latin script) and produce multi-script search candidates
- 🗂 **Normalized naming and sorted archiving**: `Movies / Title (Year) / Title (Year).mkv`, `TV / Show (Year) / Season 01 / Show S01E03.mkv`, with automatic classification into four folders (Movies / TV / Anime / Other)
- 📋 **Local library catalogue**: SQLite as the internal index plus dual-track `library.json` / `LIBRARY.md` readable catalogues that both agents and humans can read; the index can be rebuilt from disk
- 🔍 **Missing-episode audit**: compare the episodes you actually have per season and get back exactly which numbers are missing
- 🩺 **Read-only inspection**: source reachability, library file integrity, and target-directory filesystem capabilities (hardlink support) in one pass
- 🔌 **Pluggable extensions (optional)**: search, subtitles, and the download engine are all adapter-based; one failing source never blocks the rest — a custom source is a single class

**Design principle**: the LLM does the understanding, the CLI does the deterministic work. Sizes, seed counts, hashes, and paths are always produced by the CLI — never estimated by a model.

---

## 📌 What's New (v0.1.0 · first public release)

> This section covers only the current version; full history is in [CHANGELOG.md](CHANGELOG.md).

**🧩 Parsing and metadata**

- Resource-name parsing: title, year, season/episode, batch/complete markers, and Chinese-subtitle markers in one JSON output
- Metadata lookup: Chinese/English/native name mapping with several searchable spellings generated automatically
- Token gate: a result title must match a query token, filtering out source-side semantic pollution

**🗂 Archiving and catalogues**

- Normalized naming and classification (Movies / TV / Anime / Other), with episodes landing in `Season NN/`
- Path-escape protection: filenames originating from remote inputs are realpath-asserted before being joined into the library; escapes are refused outright
- Three-tier hardlink fallback: `rename → link → copy`, and when it falls back to copying, large files must be explicitly allowed — **it never silently copies**
- Dual-track catalogue: SQLite as the index, `library.json` / `LIBRARY.md` for agents and humans; the index rebuilds losslessly from disk

**🩺 Read-only inspection**

- Source reachability, missing library files, zero-byte leftovers, orphaned subtitles
- Filesystem capability probe: actually creates a temp file in the target directory and tries `link()` once — more reliable than consulting a table, and cleaned up immediately after

**🔌 Search and retrieval (pluggable, conservative by default)**

- Three-tier source structure: aggregator adapter, generic skeleton, and user-supplied sources
- Chinese-subtitle-first ranking; token gate against pollution; a failing source is skipped silently and reported by the inspector
- Downloads always start asynchronously so they never block an agent's tool call
- Chinese subtitles: local sidecar detection first, then a subtitle site when nothing local matches (including cleanup of returned content)

**⚙️ Engineering**

- **Zero third-party Python dependencies**: standard library only (BT downloads rely on the external `aria2c`, which is not a Python dependency)
- Every write operation that touches the media library supports `--dry-run` (`ingest` / `grab` / `subs` / `config` / `index rebuild`), and a dry run never writes anything; runtime state is written only under the user's home directory, never into the skill directory

---

## Why You Need It

The pain of media file management is that the mess comes from downloading, while organizing is all manual:

| ❌ Without it | ✅ With it |
|---|---|
| A download folder full of `[Group]Title.2019.1080p.x265.简繁中字.mkv` and no idea what is what | `parse` gives you structured JSON in one command: title / year / season-episode / subtitle marks |
| Chinese titles return nothing on international indexes, so you hunt for an English name yourself | `meta` produces Latin search-name candidates and supports cross-language lookup |
| Renaming by hand and creating `Season 01` folders by hand — dozens of episodes per show | `ingest --dry-run` shows the plan first, then archives everything in one confirmed command |
| A slip puts a movie in the TV folder, or an episode gets treated as a movie | Media type is inferred from filename clues, so each file lands in the right folder; `--type` can force it |
| "Do I already have this episode?" means counting files in a folder | `index missing --title <show> --season 1 --expect 24` returns the missing episode numbers |
| A script silently copies 40GB and your disk fills up | Large copies must be explicitly allowed; by default they are refused with the reason reported honestly |
| Move or copy? Will deleting the source lose data? Nobody can say | Default is `move` (instant and space-free on the same disk); nothing is overwritten or deleted by default |
| A machine migration wipes the catalogue | The index rebuilds losslessly from the directory structure, so catalogues can be re-exported anytime |

**What it does not do**: media servers (no Jellyfin/Emby/Plex playback integration), subscriptions or auto-following (no unattended loops), streaming/DRM capabilities, and site scraping or self-hosted index services.

---

## 🚀 Quick Start

### 1. Get the code

Option 1 — install as an agent skill (includes `SKILL.md`, so the agent follows the spec automatically):

```bash
npx skills add Treasure-hub-agent/media-butler-skill
```

Option 2 — clone it and use it as a plain CLI:

```bash
git clone https://github.com/Treasure-hub-agent/media-butler-skill.git
cd media-butler-skill
```

> To use it as a skill, put the repository directory into your agent's skills directory (anything that can read `SKILL.md` works). Hermes users can also run `hermes skills tap add Treasure-hub-agent/media-butler-skill`.

**Requirements**: Python 3.8+ (standard library only, nothing to pip install). `aria2c` is optional and only needed when downloading.

### 2. Check the CLI

```bash
python3 scripts/media.py --version
python3 scripts/media.py --help
```

### 3. Point it at your library and download folders

```bash
python3 scripts/media.py config \
  --set library_root=/data/media \
  --set download_root=/data/downloads
```

Running `config` with no arguments prints the full current configuration (including the state directory):

```bash
python3 scripts/media.py config
```

### 4. Archive files (preview first, then commit)

```bash
# Preview: prints the plan only, writes nothing
python3 scripts/media.py ingest /data/downloads --type movie --dry-run

# Once it looks right, commit it
python3 scripts/media.py ingest /data/downloads
```

`--type` can be omitted; the type is inferred from filename and folder clues (anime > TV > movie).

### 5. Look at the library

```bash
python3 scripts/media.py index stats
python3 scripts/media.py index list
python3 scripts/media.py index export          # writes library.json / LIBRARY.md
```

That is a complete offline workflow already: **parse → name → archive → catalogue**.

---

## Core Capabilities

| Command | Purpose | When to use it | Key options |
|---|---|---|---|
| `parse <filename>` | Parse a resource name into structured JSON | Unsure what a file is, or whether it has Chinese subs | — |
| `meta <title>` | Look up public metadata and generate multi-script search names | A Chinese title returns nothing and you want Latin candidates | — |
| `search <title>` | Multi-source search (Chinese-subtitle-first ranking) | You want to see available versions | `--limit` |
| `grab <magnet>` | Start a download asynchronously | You picked a source and want to hand it to the downloader | `--dest` `--select` `--dry-run` `--allow-direct` |
| `status` | Check download progress | You want to know how far along it is | `--dest` `--lines` |
| `subs <title｜file>` | Fetch Chinese subtitles | A foreign title is missing Chinese subs | `--file` `--dest` `--dry-run` |
| `ingest <dir>` | Name + classify + archive into the library | Downloads are done and files need putting away | `--library` `--type` `--dry-run` |
| `index list｜stats｜export｜missing｜rebuild` | Catalogue query, stats, export, missing episodes, rebuild | Auditing the library, finding gaps | `--library` `--title` `--season` `--expect` |
| `doctor sources｜library｜fs｜regrab` | **Read-only** inspection | Diagnosing unreachable sources, lost files, hardlink support | `--library` `--src` `--dest` |
| `config` | Read/write configuration | Setting library, download dir, proxy | `--set k=v` `--dry-run` |

---

## Usage Guide

### Organizing a messy download folder

```bash
# 1. See how it intends to place things
python3 scripts/media.py ingest /data/downloads --dry-run

# 2. Mixed content (movies + episodes) also sorts itself out — no need to split batches
python3 scripts/media.py ingest /data/downloads

# 3. Results are written to the index and readable catalogues refresh automatically
python3 scripts/media.py index export
```

The resulting layout:

```
library root/
├── 电影/        Title (Year)/Title (Year).mkv
├── 剧集/        Show (Year)/Season 01/Show S01E03.mkv
├── 动漫/        Anime (Year)/Season 01/Anime S01E03.mkv
└── 其他/        Anything unclear goes here — never guessed
```

**Archiving defaults**: existing files are not overwritten (reported as `skipped-exists`), source files are not deleted (unless `move` is doing the moving), and file contents are never modified. Re-running an ingest is idempotent and will not create duplicate records.

### Dealing with a filename only a scene group could love

```bash
python3 scripts/media.py parse "Some.Movie.2019.1080p.WEB-DL.简繁中字.mkv"
```

Output (abridged):

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

A non-empty `marks` means Chinese-subtitle markers were found; `is_batch: true` means a complete season or collection.

### Auditing which episodes are missing

```bash
python3 scripts/media.py index rebuild --library /data/media   # rebuild if the index was lost
python3 scripts/media.py index missing --title "Some Show" --season 1 --expect 24
```

The output is an array of missing episode numbers, e.g. `[3, 7, 12]`. Without `--expect`, the highest indexed episode is used as the upper bound.

### Adding Chinese subtitles

```bash
# First check for a local sidecar (if found, the path is returned and no request is made)
python3 scripts/media.py subs --file /data/media/电影/Some\ Movie\ \(2019\)/Some\ Movie\ \(2019\).mkv

# If nothing local matches, list candidates (no download)
python3 scripts/media.py subs "Some Movie 2019" --dry-run
```

**Honest caveat**: subtitles may not match your specific release's timing; if nothing matches, it reports "not found" rather than pretending to succeed.

### Inspection: check the ground before you build

```bash
python3 scripts/media.py doctor fs        # can the target directory hardlink? (real probe, not a table lookup)
python3 scripts/media.py doctor library   # does the index point at files that no longer exist?
python3 scripts/media.py doctor sources    # source reachability (reported honestly as unreachable when offline)
```

`doctor` is **entirely read-only**: it writes no persistent files, changes no configuration, and performs no retrieval. The filesystem probe creates a temp file in the target directory and tries `link()` once, then cleans up immediately. Source reachability checks only probe whether a public endpoint is online and do not involve any search content.

### Search and retrieval (optional, pluggable)

> ⚠️ This section is an extension capability, not the tool's main story. The repository contains **no site-specific adapter**, only a single **aggregator adapter** (the server-side fetches upstream public indexes on your behalf), which is enabled by default; user-supplied sources must be added by you.

```bash
python3 scripts/media.py meta "Some Show"
python3 scripts/media.py search "Some Show" --limit 10
python3 scripts/media.py grab "magnet:?xt=..." --dry-run    # see the exact command line first
python3 scripts/media.py grab "magnet:?xt=..."
python3 scripts/media.py status --lines 20
```

**One command back to fully offline mode** (disables all third-party sources; organizing, archiving, and cataloguing are unaffected):

```bash
python3 scripts/media.py config --set sources_enabled=
python3 scripts/media.py doctor sources     # should print an empty list
```

**Before you use this, you should know**:

- Adding or enabling any third-party source is taken as **your own confirmation that you are entitled to access it**, and you accept the consequences
- Downloading uses the BT network, so **your IP is exposed to other peers in the swarm**; the tool does not hide that from you
- Magnet links and `info_hash` values go only to the downloader and to DHT/trackers — never to any third-party metadata API
- Seeding is off by default (`--seed-time=0`)
- No telemetry, no automatic callbacks, and no uploading of your catalogue or source health data

To add your own sources (a private tracker, a self-hosted middleware service, etc.), see `references/sources.md`.

### Storage, permissions, and privacy

| Item | Location / notes |
|---|---|
| State directory | Linux/macOS: `~/.media-butler/`; Windows: `%APPDATA%\media-butler\` |
| Override | Set `MEDIA_BUTLER_HOME` to any directory |
| Contents | `config.json` (config, written with mode `0600` since it may hold proxy credentials), `library.db` (SQLite index), `library.json` / `LIBRARY.md` (readable catalogues) |
| Permissions | The state directory and index files follow your system `umask`; on multi-user hosts, tightening to `0700` / `0600` is recommended |
| Least privilege | Run as a non-root user and mount only the download and media directories — never all of `$HOME` |
| Network behavior | Outbound requests happen only when you explicitly invoke search/subtitle commands; parsing, archiving, and cataloguing are fully offline |
| Agent context | When used by an agent, titles enter the conversation context and are sent to your configured model provider — an exposure surface specific to the agent layer; evaluate it accordingly |

### The two hard constraints of hardlinks

This section is irrelevant if you mostly move files; it matters only when you set `archive_action=hardlink` to keep a download copy:

- Source and target must be **on the same filesystem** *and* **under the same mount point**. Two Docker bind mounts are still cross-device inside the container even if they share a filesystem on the host, and `link()` returns `EXDEV`.
- The fix is to mount a single common parent (the `/data` pattern):

```yaml
volumes:
  - /srv/data:/data          # downloads and library share one mount
```

```bash
python3 scripts/media.py config --set library_root=/data/media \
                                --set download_root=/data/downloads
```

- Subvolumes and datasets (Btrfs subvolumes, ZFS datasets — a very common layout on Synology/QNAP) count as different filesystems by `st_dev`, which breaks hardlinks
- SMB/CIFS mounts generally do not support hardlinks; NFS depends on server-side configuration
- On Windows, only NTFS on the same volume supports them; FAT32/exFAT does not
- Multiple paths point at the same data: deleting one path **frees no space**

When in doubt, run the capability probe first:

```bash
python3 scripts/media.py doctor fs
```

---

## FAQ

**Q: Does it need a network connection?**
No. Parsing, naming, archiving, cataloguing, and missing-episode detection are fully offline, as are `doctor fs` and `doctor library`. Only `meta` / `search` / `subs` / `grab` need a network or a downloader.

**Q: What dependencies do I need?**
Python 3.8+ and its standard library — no third-party Python packages at all. Only actual downloading needs the external `aria2c`; without it, `grab` prints the magnet link plus installation hints instead of failing.

**Q: Can it lose my files?**
Not quietly. Nothing is overwritten, deleted, or modified by default; every write operation that touches the media library supports `--dry-run`; archiving failures are recorded rather than aborting, with each result reported honestly (`skipped-exists` / `error:...` / `refused-large-copy`).

**Q: Why would archiving "refuse" to copy a large file?**
When there is no way to hardlink across filesystems, copying is the only option left. Silently copying a multi-gigabyte file would fill a disk with no indication of the cause, so anything above the threshold (2GiB by default) must be explicitly allowed.

**Q: Chinese titles return nothing — what now?**
Use `meta` to get Latin search names first. Latin coverage on international indexes is far higher than for Chinese names.

**Q: Will `doctor` modify my library?**
No. `doctor` is entirely read-only. Even its "regrab candidates" subcommand only produces a candidate list; acting on it requires your confirmation and a separate `grab` call.

**Q: What if I delete the index database?**
`index rebuild --library <root>` rebuilds it from the directory structure, depending only on local facts like filenames and folder layout.

**Q: Windows / macOS support?**
Paths go through `pathlib` / `os.path`, and the state directory resolves per platform to `%APPDATA%` or `~/.media-butler`. Note that NTFS and APFS are case-insensitive by default while ext4 is case-sensitive — keep that in mind when syncing a library across platforms.

**Q: Can it auto-follow new episodes and download them?**
No, deliberately: there are no subscription features and no unattended loops.

---

## Disclaimer

- This tool is a **CLI for managing video files**: it parses filenames, queries public metadata, normalizes naming, sorts by type, and maintains a local catalogue.
  It does **not host, index, or scrape** any video content, and the repository contains neither video content nor links to specific works.
- Search capability is provided by **pluggable adapters**; the repository bundles no site-specific adapter and everything can be switched off for fully offline use.
- Please use it only for content you own the rights to or are licensed to access, works in the public domain, and personal backups of media you have purchased. Confirming the authorization status of what you obtain is your responsibility.
- This project is **free, ad-free, accepts no donations, and has no paid unlocks**; the authors derive no income from it.
- Full terms (including rights-holder and takedown response, and the kinds of contributions that are not accepted) are in **[DISCLAIMER.md](DISCLAIMER.md)**.

> One line of self-reflection: **a disclaimer does not grant immunity.** What actually matters is the structural choices — no bundled sources, no self-built index, no automatic retrieval, no monetization, no promotion.

---

## Contributing

Bug fixes, tests, and documentation improvements are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) first — it explicitly lists the **kinds of contributions that are not accepted**.

---

## License

[MIT License](LICENSE) © media-butler-skill contributors

Maintained under a pseudonym; not promoted on domestic (China) platforms. The repository name, the directory name, and the `name` field in `SKILL.md` are kept identical (`media-butler-skill`) to avoid platform recognition issues.
