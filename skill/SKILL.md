# /handover — Household Handover Report Generator

Generate a household weekly check-in report using Claude's native vision. No external API needed.

## How to trigger
User types `/handover`

---

## Household config
Default pair: **Leonie** ↔ **Martin**
If a new name appears, treat them as the inspector and ask who they're checking after.

---

## Workflow

### Step 0 — Identify the inspector

Use **AskUserQuestion**:
- Question: "今天是谁在做检查？"
- Header: "身份确认"
- Options:
  - "Leonie" — Leonie 检查 Martin 的工作
  - "Martin" — Martin 检查 Leonie 的工作
  - "Other" — 其他人（会追加提问）

Set `inspector` = chosen name.
Set `reportee` = the other person in the default pair.
If "Other": ask for their name (text), then ask who they're checking after (text).

These map to: `incoming` = inspector (写报告的人), `outgoing` = reportee (被检查的人).

---

### Step 1 — Scan & convert photos

Run:
```bash
python3 /Users/yueouli/code/handover/prep.py
```

Parse the JSON. If `photos` is empty, tell the user "No photos found in ~/Desktop/交接照片/ — add photos and try again." and stop.

Show the user the photo list: "Found X photos: [filenames]"

**Duplicate check:** If `duplicates` in the JSON is non-empty, show each group before proceeding:

```
⚠️ 发现疑似重复照片（感知哈希检测）：
  组 1: A.jpg 和 B.jpg
  组 2: C.jpg、D.jpg、E.jpg
```

Use **AskUserQuestion**:
- Question: "检测到疑似重复照片，怎么处理？"
- Header: "重复照片"
- Options:
  - "每组只保留第一张" — 自动去掉每组里后面的
  - "全部保留" — 都分析，报告里可能有重复内容
  - "我来手动选" — 逐组提问（文本输入：输入要保留的文件名）

Apply the user's choice to the `photos` list before Step 2.

---

### Step 2 — Verbal description

Use **AskUserQuestion**:
- Question: "有口头描述要补充吗？描述问题可以帮我更准地分类照片。"
- Header: "口头描述"
- Options:
  - "跳过" — 直接分析照片
  - "我来说一下" — 我想补充描述

If "跳过": `verbal_context` is empty, proceed.
If "我来说一下": ask the user to type their description; save as `verbal_context`.

---

### Step 3 — Read all photos in parallel, then batch-analyze

**Token-efficient approach: fire all Read tool calls in one go, then analyze everything in a single pass.**

Read ALL converted photos simultaneously using parallel Read tool calls (one call per photo, all in the same response).

> If there are more than 12 photos, process in batches of 12.

Once all images are loaded, produce ALL analyses in ONE response — do not analyze photo-by-photo.

Produce one JSON object per photo:
```json
{
  "filename": "IMG_6639.jpg",
  "area": "kitchen",
  "location": "Coffee Corner",
  "state": "issue",
  "issue_title": "Coffee machine area needs a wipe",
  "description": "Coffee grounds scattered around the machine with milk foam buildup — looks like it hasn't been wiped after use in a while.",
  "severity": "urgent",
  "next_step": "Wipe the drip tray and machine surface after each use — takes under a minute!"
}
```

Field rules:
- `area`: `"fridge"` | `"kitchen"` | `"sink"` | `"bathroom"` | `"living_room"` | `"bedroom"` | `"laundry"` | `"upstairs"` | `"other"`
- `location`: specific spot shown in the card sub-label (e.g. `"Coffee Corner"`, `"Bathroom · Shower"`, `"Bedroom · Chair"`)
- `state`: `"highlight"` (something done well — praise it!) | `"issue"` (messy/dirty/needs action) | `"after_clean"` (reference photo of desired clean state)
- `issue_title`: short title; for highlights make it celebratory (e.g. "The wooden board looks amazing!")
- `severity`: issues only — `"urgent"` (health/safety or really bad) | `"next"` (needs doing soon) | `"minor"` (quick fix); `null` for highlights and after_clean
- `next_step`: issues only — one short actionable sentence starting with a verb (e.g. `"Empty all bins before handover."`); `null` for highlights

If `verbal_context` is not empty, use it to match and classify photos — reflect the user's phrasing in titles and descriptions where it fits.

After producing all photo analyses, also produce a **summary object**:
```json
{
  "highlights": "short phrase listing the good things (e.g. 'wooden board, 3D-printed cup holder')",
  "action_today": "urgent items needing same-day action (e.g. 'expired meat in fridge, SodaStream mould')",
  "habits": "recurring small issues that suggest a weekly habit (e.g. 'wipe coffee machine after use, empty bins at handover')",
  "discuss": "structural issues that need a conversation (e.g. 'where does the suitcase live?')"
}
```
If a category has nothing to report, use `"—"`.

Display each result as you go:
```
📷 IMG_6639.jpg → ☕ kitchen · Coffee Corner | ⚠️ urgent | "Coffee machine area needs a wipe"
```

---

### Step 4 — Confirm with the user

Show a numbered summary of all analyses. Then use **AskUserQuestion**:
- Question: "这些分析看起来对吗？"
- Header: "确认分析"
- Options:
  - "全部确认 ✅" — 直接生成报告
  - "跳过某几张" — 从报告里排除几张
  - "编辑某张" — 修改某张的字段

If "跳过某几张": ask "跳过哪几张？（输入编号，如 1 3）" (text input); remove those from the list.
If "编辑某张": ask "编辑第几张？" (text input), then ask which field to change — title / description / location / severity / next_step — and apply the change. After editing, re-show the summary and ask the same AskUserQuestion again.

---

### Step 5 — Generate report

Get today's date:
```bash
python3 -c "from datetime import date; print(date.today().isoformat())"
```

Build this JSON and write it to `/tmp/handover_analysis.json` using a bash heredoc:
```json
{
  "today": "...",
  "outgoing": "...(reportee)",
  "incoming": "...(inspector)",
  "summary": { ...summary object from Step 3... },
  "analyses": [ ...all confirmed analysis dicts... ],
  "originals": [ ...list of original photo paths from prep.py output... ],
  "tmp_dir": "...tmp_dir from prep.py output..."
}
```

Then run:
```bash
python3 /Users/yueouli/code/handover/report.py --input /tmp/handover_analysis.json
```

Parse the output JSON for `markdown` and `html` paths.

> **HTML is always editable:** `report.py` generates HTML with `contenteditable="true"` on all text fields (titles, descriptions, next steps, summary values). Do NOT change this — it's a permanent user preference.

---

### Step 6 — Done

Tell the user:
```
✅ 报告生成完毕！
  📝 Markdown: [md_path]
  🌐 HTML: [html_path]
  原始照片已移至 交接照片/done/
```

Use **AskUserQuestion**:
- Question: "在浏览器里打开 HTML 报告？"
- Header: "打开报告"
- Options:
  - "是，打开 🌐"
  - "否，完成"

If "是，打开 🌐": run `open [html_path]`.
