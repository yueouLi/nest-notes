#!/usr/bin/env python3
"""
Household Handover Report Generator
────────────────────────────────────
1. Drop photos into ~/Desktop/交接照片/
2. Run: python3 handover.py
3. Confirm the AI analysis
4. Markdown + HTML get written to Obsidian automatically

API: DeepSeek (OpenAI-compatible)
  Vision model : deepseek-vl2        (for photo analysis)
  Env var      : DEEPSEEK_API_KEY
"""

from openai import OpenAI
import base64

import json
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from datetime import date
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
VAULT       = Path.home() / "Desktop" / "Obsidian Vault"
ATTACHMENTS = VAULT / "附件"
LOG_DIR     = VAULT / "My Life" / "管家周志"
INBOX       = Path.home() / "Desktop" / "交接照片"
IMAGE_EXTS  = {".heic", ".jpg", ".jpeg", ".png", ".webp"}

# ── Colours for terminal output ───────────────────────────────────────────────
R = "\033[91m"; G = "\033[92m"; Y = "\033[93m"; B = "\033[94m"
M = "\033[95m"; C = "\033[96m"; W = "\033[97m"; X = "\033[0m"; BOLD = "\033[1m"

def h(text):  print(f"\n{BOLD}{C}{'─'*50}{X}")  ;  print(f"{BOLD}{W}{text}{X}")
def ok(text): print(f"  {G}✓{X} {text}")
def info(text): print(f"  {C}→{X} {text}")
def warn(text): print(f"  {Y}!{X} {text}")
def err(text):  print(f"  {R}✗{X} {text}")

# ── Photo helpers ─────────────────────────────────────────────────────────────

def collect_photos() -> list[Path]:
    photos = sorted([p for p in INBOX.iterdir()
                     if p.is_file() and p.suffix.lower() in IMAGE_EXTS])
    return photos


def convert_to_jpg(src: Path, dst_dir: Path) -> Path:
    """Convert to JPG and resize to max 1024px on longest side (keeps API payload small)."""
    out = dst_dir / (src.stem + ".jpg")
    subprocess.run(
        ["sips", "-Z", "1024",                      # resize: longest side ≤ 1024px
         "-s", "format", "jpeg",
         "-s", "formatOptions", "65",               # quality 65 — good enough for analysis
         str(src), "--out", str(out)],
        capture_output=True, check=True
    )
    return out


def encode_image(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode()

# ── DeepSeek analysis ────────────────────────────────────────────────────────

GEMINI_MODEL = "gemini-2.0-flash"

def _analyze_one(jpg: Path, verbal_context: str = "") -> dict:
    """Send a single photo to Gemini Flash and get back one structured dict."""
    from openai import RateLimitError
    client = OpenAI(
        api_key=os.environ.get("GEMINI_API_KEY"),
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    context_block = (
        f"\nThe inspector verbally described the overall situation as follows:\n"
        f"\"\"\"\n{verbal_context.strip()}\n\"\"\"\n"
        f"Use this description to help classify the photo — if it matches something mentioned, "
        f"reflect that in issue_title and description.\n"
    ) if verbal_context.strip() else ""

    for attempt in range(5):
        try:
            msg = client.chat.completions.create(
                model=GEMINI_MODEL,
                max_tokens=400,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{encode_image(jpg)}"}
                        },
                        {
                            "type": "text",
                            "text": f"""Analyze this household inspection photo (filename: {jpg.name}).
{context_block}
Return ONE JSON object:
- "filename": "{jpg.name}"
- "area": "fridge"|"kitchen"|"sink"|"bathroom"|"living_room"|"other"
- "state": "issue" (messy/dirty/wrong) or "after_clean" (tidy reference)
- "issue_title": short title if issue, null if after_clean
- "description": 1-2 friendly casual sentences
- "severity": "yikes"|"messy"|"clean"

ONLY return the JSON object, no markdown."""
                        }
                    ]
                }]
            )
            raw = msg.choices[0].message.content.strip().replace("```json","").replace("```","").strip()
            start, end = raw.find("{"), raw.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
            return {"filename": jpg.name, "area": "other", "state": "issue",
                    "issue_title": "Unclassified", "description": raw, "severity": "messy"}
        except RateLimitError as e:
            wait = 65 * (attempt + 1)
            warn(f"Rate limit hit — waiting {wait}s before retry {attempt+1}/4… ({e})")
            time.sleep(wait)
    err(f"Failed after 5 attempts: {jpg.name}")
    return {"filename": jpg.name, "area": "other", "state": "issue",
            "issue_title": "Rate limit failure", "description": "Could not analyse.", "severity": "messy"}


def analyze_photos(jpgs: list[Path], verbal_context: str = "") -> list[dict]:
    """Send each photo to Gemini Flash individually for vision analysis."""
    results = []
    for i, jpg in enumerate(jpgs):
        info(f"[{i+1}/{len(jpgs)}] {jpg.name}")
        entry = _analyze_one(jpg, verbal_context)
        sev = {"yikes": f"{R}😬{X}", "messy": f"{Y}😤{X}",
               "clean": f"{G}✨{X}"}.get(entry.get("severity","messy"), "")
        print(f"       {sev} {entry.get('issue_title') or 'after clean'} [{entry.get('area','?')}]")
        results.append(entry)
    return results

# ── Confirmation prompt ───────────────────────────────────────────────────────

SEVERITY_ICON = {"yikes": f"{R}😬 yikes{X}", "messy": f"{Y}😤 messy{X}",
                 "clean": f"{G}✨ clean{X}"}
AREA_ICON = {"fridge": "🧊", "kitchen": "🍳", "sink": "🚿",
             "bathroom": "🛁", "living_room": "🛋️", "other": "📦"}

def confirm_analysis(analyses: list[dict]) -> list[dict]:
    """Show Claude's analysis and let user confirm or skip individual photos."""
    print(f"\n{BOLD}{W}Gemini's analysis:{X}")
    for i, a in enumerate(analyses):
        icon = AREA_ICON.get(a.get("area", "other"), "📦")
        sev  = SEVERITY_ICON.get(a.get("severity", "messy"), "")
        state_tag = f"{G}[after]{X}" if a.get("state") == "after_clean" else f"{R}[issue]{X}"
        print(f"\n  {BOLD}Photo {i+1}: {a['filename']}{X}")
        print(f"  {icon} area: {a.get('area','?')}  |  {sev}  |  {state_tag}")
        if a.get("issue_title"):
            print(f"  title: {Y}{a['issue_title']}{X}")
        print(f"  desc:  {a.get('description','')}")

    print(f"\n{BOLD}Does this look right?{X}")
    print("  [enter] = yes, all good")
    print("  [s]     = skip a photo (won't appear in report)")
    print("  [e]     = edit issue title / description for a photo")
    choice = input(f"\n  Your choice: ").strip().lower()

    if choice == "s":
        nums = input("  Skip photo numbers (e.g. 1 3): ").strip().split()
        skip = {int(n) - 1 for n in nums if n.isdigit()}
        analyses = [a for i, a in enumerate(analyses) if i not in skip]
    elif choice == "e":
        num = int(input("  Edit photo number: ").strip()) - 1
        if 0 <= num < len(analyses):
            a = analyses[num]
            new_title = input(f"  New title [{a.get('issue_title','')}]: ").strip()
            new_desc  = input(f"  New desc  [{a.get('description','')}]: ").strip()
            if new_title: a["issue_title"] = new_title
            if new_desc:  a["description"]  = new_desc

    return analyses

# ── Markdown generator ────────────────────────────────────────────────────────

def build_markdown(today: str, outgoing: str, incoming: str,
                   analyses: list[dict]) -> str:
    issues = [a for a in analyses if a.get("state") == "issue"]
    afters = [a for a in analyses if a.get("state") == "after_clean"]

    lines = [
        f"# Handover Report · {today}",
        f"",
        f"> Outgoing: {outgoing}　　Incoming: {incoming}　　Date: {today}",
        f"",
        f"> ⚠️ All issues below were found by {incoming} at handover. They were not present at the start of the previous shift.",
        f"",
        f"---",
        f"",
        f"## 🔍 Issues Found at Handover",
        f"",
    ]

    area_map: dict[str, list[dict]] = {}
    for a in issues:
        area_map.setdefault(a.get("area", "other"), []).append(a)

    for area, items in area_map.items():
        icon = AREA_ICON.get(area, "📦")
        for item in items:
            sev = item.get("severity", "messy")
            lines += [
                f"- [x] **{item.get('issue_title', 'Issue')}** `{sev}`",
                f"  - {item.get('description', '')}",
                f"  - Photo: ![[{item['filename']}]]",
                f"  - Resolution: ✅ ",
                f"",
            ]

    lines += [
        f"---",
        f"",
        f"## ✅ After-Clean Reference Photos",
        f"",
    ]
    for a in afters:
        lines.append(f"![[{a['filename']}]]")
    lines.append("")

    lines += [
        f"---",
        f"",
        f"## ⏭️ Open Items",
        f"",
        f"- [ ] ",
        f"",
        f"---",
        f"",
        f"## 💬 Notes",
        f"",
        f"> ",
    ]

    return "\n".join(lines)

# ── HTML generator ────────────────────────────────────────────────────────────

def severity_tag(sev: str) -> str:
    if sev == "yikes":
        return '<span class="tag tag-oof">yikes!</span>'
    return '<span class="tag tag-meh">messy</span>'


def build_html(today: str, outgoing: str, incoming: str,
               analyses: list[dict]) -> str:
    issues = [a for a in analyses if a.get("state") == "issue"]
    afters = [a for a in analyses if a.get("state") == "after_clean"]

    # ── issue cards HTML ──
    cards_html = ""
    for a in issues:
        icon = {"fridge":"🧊","kitchen":"🍳","sink":"🚿",
                "bathroom":"🛁","living_room":"🛋️"}.get(a.get("area","other"),"📦")
        area_label = a.get("area","other").replace("_"," ").title()
        fname = a["filename"]
        cards_html += f"""
    <div class="icard">
      <div class="icard-top">
        <span class="icard-icon">{icon}</span>
        <div class="icard-meta">
          <div class="icard-area">{area_label}</div>
          <div class="icard-name">{a.get("issue_title","Issue")}</div>
        </div>
        {severity_tag(a.get("severity","messy"))}
        <span class="tag tag-done">✓ fixed</span>
      </div>
      <div class="icard-body">
        <p class="icard-desc">{a.get("description","")}</p>
        <div class="fix-box">✨ resolution: </div>
        <div class="photo-grid">
          <div class="photo-frame" onclick="openLightbox('../../附件/{fname}')">
            <img src="../../附件/{fname}" alt="{a.get('issue_title','')}" loading="lazy">
            <div class="photo-cap">{fname}</div>
          </div>
        </div>
      </div>
    </div>"""

    # ── after gallery HTML ──
    gallery_html = ""
    for a in afters:
        fname = a["filename"]
        gallery_html += f"""
      <div class="gitem" onclick="openLightbox('../../附件/{fname}')">
        <img src="../../附件/{fname}" loading="lazy">
        <div class="gcap">{a.get("area","").replace("_"," ").title()} ✨</div>
      </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Handover Report · {today}</title>
<link href="https://fonts.googleapis.com/css2?family=Nunito:ital,wght@0,400;0,600;0,700;0,800;1,400&family=Nunito+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#fff8f3;--card:#fff;--text:#3a2e28;--soft:#7a6e68;--muted:#b5aba4;--coral:#f07060;--coral-bg:#fff1ee;--mint:#4caf88;--mint-bg:#edf8f3;--peach:#f5a06a;--peach-bg:#fff5ec;--lav-bg:#f5f0ff;--border:#f0e8e0;--shadow:rgba(58,46,40,.07)}}
body{{font-family:'Nunito Sans','Nunito',sans-serif;background:var(--bg);color:var(--text);line-height:1.65;font-size:15px}}
.hero{{background:linear-gradient(135deg,#ffe8dc,#ffd6e8 50%,#dce8ff);padding:56px 40px 48px;text-align:center;position:relative;overflow:hidden}}
.hero::before{{content:'🏠';position:absolute;font-size:180px;opacity:.07;top:-20px;right:-20px;line-height:1}}
.hero-eyebrow{{display:inline-block;background:#fff;color:var(--coral);font-weight:800;font-size:11px;letter-spacing:.12em;text-transform:uppercase;padding:5px 14px;border-radius:100px;margin-bottom:20px;box-shadow:0 2px 8px rgba(240,112,96,.18)}}
.hero-title{{font-family:'Nunito',sans-serif;font-size:clamp(32px,6vw,52px);font-weight:800;line-height:1.15;margin-bottom:10px}}
.hero-title span{{color:var(--coral)}}
.hero-sub{{font-size:14.5px;color:var(--soft);margin-bottom:28px}}
.hero-chips{{display:flex;flex-wrap:wrap;gap:8px;justify-content:center}}
.hchip{{background:#fff;border-radius:100px;padding:6px 16px;font-size:13px;font-weight:600;box-shadow:0 2px 8px var(--shadow)}}
.sticky-note{{background:#fffbe6;border:2px dashed #f5d060;border-radius:16px;padding:18px 24px;margin:32px auto;max-width:860px;font-size:14px;color:#7a6400;display:flex;gap:12px;align-items:flex-start}}
.sticky-icon{{font-size:22px;flex-shrink:0}}
.main{{max-width:860px;margin:0 auto;padding:12px 40px 72px}}
.timeline{{display:flex;gap:0;background:var(--card);border-radius:20px;border:2px solid var(--border);padding:28px 32px;margin-bottom:48px;box-shadow:0 4px 20px var(--shadow);position:relative}}
.timeline::before{{content:'';position:absolute;top:50px;left:calc(32px + 22px);right:calc(32px + 22px);height:3px;background:repeating-linear-gradient(90deg,var(--border) 0,var(--border) 6px,transparent 6px,transparent 12px);z-index:0}}
.tl-item{{flex:1;text-align:center;position:relative;z-index:1}}
.tl-dot{{width:44px;height:44px;border-radius:50%;margin:0 auto 10px;display:flex;align-items:center;justify-content:center;font-size:20px;border:3px solid #fff;box-shadow:0 3px 10px var(--shadow)}}
.tl-day{{font-size:11px;font-weight:700;color:var(--muted);letter-spacing:.05em;margin-bottom:4px}}
.tl-event{{font-size:13px;font-weight:700;line-height:1.35}}
.section{{margin-bottom:48px}}
.section-head{{display:flex;align-items:center;gap:10px;margin-bottom:20px}}
.section-emoji{{font-size:24px}}
.section-title{{font-family:'Nunito',sans-serif;font-weight:800;font-size:22px;flex:1}}
.pill{{padding:4px 14px;border-radius:100px;font-size:12px;font-weight:700}}
.pill-coral{{background:var(--coral-bg);color:var(--coral)}}
.pill-mint{{background:var(--mint-bg);color:var(--mint)}}
.pill-peach{{background:var(--peach-bg);color:var(--peach)}}
.icard{{background:var(--card);border-radius:20px;border:2px solid var(--border);overflow:hidden;margin-bottom:16px;box-shadow:0 3px 16px var(--shadow);transition:transform .2s,box-shadow .2s}}
.icard:hover{{transform:translateY(-2px);box-shadow:0 6px 24px var(--shadow)}}
.icard-top{{display:flex;align-items:center;gap:12px;padding:16px 20px;border-bottom:2px solid var(--border);flex-wrap:wrap}}
.icard-icon{{font-size:26px}}
.icard-meta{{flex:1;min-width:0}}
.icard-area{{font-size:11px;font-weight:700;color:var(--muted);letter-spacing:.08em;text-transform:uppercase;margin-bottom:2px}}
.icard-name{{font-weight:800;font-size:15px}}
.tag{{display:inline-flex;align-items:center;gap:4px;padding:3px 12px;border-radius:100px;font-size:12px;font-weight:700}}
.tag-oof{{background:#ffe0dc;color:#c0392b}}
.tag-meh{{background:#fff3cd;color:#9c6900}}
.tag-done{{background:var(--mint-bg);color:var(--mint)}}
.icard-body{{padding:18px 20px}}
.icard-desc{{font-size:14px;color:var(--soft);margin-bottom:14px;line-height:1.7}}
.fix-box{{background:var(--mint-bg);border-radius:12px;padding:10px 16px;font-size:13px;color:#2a7a56;font-weight:600;margin-bottom:16px;display:flex;gap:8px}}
.photo-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px}}
.photo-frame{{position:relative;aspect-ratio:4/3;overflow:hidden;border-radius:12px;cursor:zoom-in;background:var(--bg);border:2px solid var(--border)}}
.photo-frame img{{width:100%;height:100%;object-fit:cover;transition:transform .3s;display:block}}
.photo-frame:hover img{{transform:scale(1.08)}}
.photo-cap{{position:absolute;bottom:0;left:0;right:0;padding:20px 8px 7px;background:linear-gradient(transparent,rgba(0,0,0,.5));font-size:10px;color:#fff;font-weight:600;opacity:0;transition:opacity .2s}}
.photo-frame:hover .photo-cap{{opacity:1}}
.gallery-note{{font-size:13.5px;color:var(--soft);margin-bottom:18px;line-height:1.7}}
.gallery-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}
.gitem{{position:relative;aspect-ratio:4/3;overflow:hidden;border-radius:16px;cursor:zoom-in;background:var(--bg);border:2px solid var(--border);box-shadow:0 3px 12px var(--shadow)}}
.gitem img{{width:100%;height:100%;object-fit:cover;transition:transform .3s;display:block}}
.gitem:hover img{{transform:scale(1.06)}}
.gcap{{position:absolute;bottom:0;left:0;right:0;padding:28px 10px 10px;background:linear-gradient(transparent,rgba(0,0,0,.5));font-size:11px;color:rgba(255,255,255,.95);font-weight:700}}
.footer{{text-align:center;padding:40px;color:var(--muted);font-size:12.5px;border-top:2px dashed var(--border)}}
.footer-heart{{color:var(--coral)}}
.lightbox{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.88);z-index:9999;align-items:center;justify-content:center;padding:40px;cursor:zoom-out}}
.lightbox.active{{display:flex}}
.lightbox img{{max-width:100%;max-height:90vh;object-fit:contain;border-radius:12px}}
.lb-close{{position:fixed;top:16px;right:22px;color:rgba(255,255,255,.6);font-size:36px;cursor:pointer;font-weight:300;transition:color .15s}}
.lb-close:hover{{color:#fff}}
@media(max-width:600px){{.hero,.main{{padding-left:20px;padding-right:20px}}.timeline{{flex-direction:column;gap:18px;padding:24px 20px}}.timeline::before{{display:none}}.gallery-grid{{grid-template-columns:repeat(2,1fr)}}}}
</style>
</head>
<body>
<div class="hero">
  <div class="hero-eyebrow">House Log · {today}</div>
  <h1 class="hero-title">hey babe,<br>we need to <span>talk</span> 🙂</h1>
  <p class="hero-sub">i took over and found a few things. here's what i found + what i fixed 💪</p>
  <div class="hero-chips">
    <span class="hchip">😬 outgoing: {outgoing}</span>
    <span class="hchip">🙋‍♀️ incoming: {incoming}</span>
  </div>
</div>
<div class="sticky-note">
  <span class="sticky-icon">📝</span>
  <span>just so we're on the same page — everything below is stuff i found <strong>when i took over from you</strong>. i went ahead and fixed it all, but let's make sure it doesn't pile up like this again okay? no blame, just a heads up 💛</span>
</div>
<main class="main">
  <div class="timeline">
    <div class="tl-item">
      <div class="tl-dot" style="background:#ffe0dc">😴</div>
      <div class="tl-day">shift ends</div>
      <div class="tl-event">your shift ends<br>you hand over</div>
    </div>
    <div class="tl-item">
      <div class="tl-dot" style="background:#fff3cd">🔍</div>
      <div class="tl-day">handover</div>
      <div class="tl-event">i take over &amp;<br>find all this...</div>
    </div>
    <div class="tl-item">
      <div class="tl-dot" style="background:#edf8f3">✨</div>
      <div class="tl-day">cleaned</div>
      <div class="tl-event">all sorted!<br>here's the proof</div>
    </div>
  </div>
  <section class="section">
    <div class="section-head">
      <span class="section-emoji">🔍</span>
      <h2 class="section-title">what i found</h2>
      <span class="pill pill-coral">{len(issues)} thing{"s" if len(issues)!=1 else ""}</span>
    </div>
    {cards_html}
  </section>
  <section class="section">
    <div class="section-head">
      <span class="section-emoji">✨</span>
      <h2 class="section-title">how it looks now</h2>
      <span class="pill pill-mint">glowing up!</span>
    </div>
    <p class="gallery-note">these are the reference photos — this is what it should look like at every handover 🙏</p>
    <div class="gallery-grid">{gallery_html}</div>
  </section>
</main>
<footer class="footer">
  made with <span class="footer-heart">♥</span> (and cleaning products) · {today}
</footer>
<div class="lightbox" id="lightbox" onclick="closeLightbox()">
  <span class="lb-close" onclick="closeLightbox()">×</span>
  <img id="lb-img" src="" alt="">
</div>
<script>
function openLightbox(src){{document.getElementById('lb-img').src=src;document.getElementById('lightbox').classList.add('active')}}
function closeLightbox(){{document.getElementById('lightbox').classList.remove('active');document.getElementById('lb-img').src=''}}
document.addEventListener('keydown',e=>{{if(e.key==='Escape')closeLightbox()}})
</script>
</body>
</html>"""

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{BOLD}{M}╔══════════════════════════════════════╗")
    print(f"║  🏠  Handover Report Generator  🏠  ║")
    print(f"╚══════════════════════════════════════╝{X}")

    # 1. Check API key
    if not os.environ.get("GEMINI_API_KEY"):
        err("GEMINI_API_KEY not set.")
        print(f"  Get a free key at aistudio.google.com, then add to ~/.zshrc:")
        print(f"  {Y}export GEMINI_API_KEY=AIza...{X}")
        sys.exit(1)

    # 2. Check inbox
    h("Step 1 — Finding photos")
    photos = collect_photos()
    if not photos:
        warn(f"No photos found in {INBOX}")
        print(f"  Put your inspection photos there and run again.")
        sys.exit(0)
    info(f"Found {len(photos)} photo(s) in {INBOX.name}/:")
    for p in photos:
        print(f"     {p.name}")

    # 3. Convert HEIC → JPG
    h("Step 2 — Converting photos")
    tmp_dir = INBOX / ".converted"
    tmp_dir.mkdir(exist_ok=True)
    jpgs = []
    for p in photos:
        jpg = convert_to_jpg(p, tmp_dir)
        jpgs.append(jpg)
        ok(f"{p.name} → {jpg.name}")

    # 3.5. Collect verbal description
    h("Step 3 — Your verbal description (optional)")
    print(f"  Describe what you found in your own words — Gemini will use this")
    print(f"  to better classify each photo. Press {Y}Enter twice{X} when done.\n")
    print(f"  {M}(Just press Enter to skip){X}")
    lines = []
    while True:
        line = input("  > ")
        if line == "" and (not lines or lines[-1] == ""):
            break
        lines.append(line)
    verbal_context = "\n".join(lines).strip()
    if verbal_context:
        ok(f"Got description ({len(verbal_context)} chars) — will use as context")
    else:
        info("No description — Gemini will rely on photos only")

    # 4. Claude analysis
    h("Step 4 — Asking Gemini to analyse photos")
    info("Sending to Gemini Flash… (this takes ~10s per photo)")
    analyses = analyze_photos(jpgs, verbal_context)
    if not analyses:
        err("Claude returned no results. Check your API key or photos.")
        sys.exit(1)

    # 5. Confirm
    h("Step 5 — Review the analysis")
    analyses = confirm_analysis(analyses)

    # 6. Collect metadata
    h("Step 6 — Report details")
    today = date.today().isoformat()
    outgoing = input(f"  Outgoing manager name [{Y}boyfriend{X}]: ").strip() or "boyfriend"
    incoming = input(f"  Incoming manager name [{Y}Leonie{X}]: ").strip() or "Leonie"

    # 7. Move JPGs to Obsidian 附件
    h("Step 7 — Moving photos to Obsidian")
    final_names = []
    for jpg in jpgs:
        dest = ATTACHMENTS / jpg.name
        shutil.copy(jpg, dest)
        final_names.append(jpg.name)
        ok(f"Copied {jpg.name} → 附件/")

    # Update filenames in analyses to match what's now in 附件
    for a in analyses:
        # match by stem in case conversion changed extension
        stem = Path(a["filename"]).stem
        match = next((n for n in final_names if Path(n).stem == stem), a["filename"])
        a["filename"] = match

    # 8. Generate Markdown
    h("Step 8 — Writing Markdown to Obsidian")
    md_content = build_markdown(today, outgoing, incoming, analyses)
    md_path = LOG_DIR / f"{today} 管家交接总结.md"
    md_path.write_text(md_content, encoding="utf-8")
    ok(f"Markdown: {md_path.name}")

    # 9. Generate HTML
    h("Step 9 — Generating HTML report")
    html_content = build_html(today, outgoing, incoming, analyses)
    html_path = LOG_DIR / f"{today} 管家交接汇报.html"
    html_path.write_text(html_content, encoding="utf-8")
    ok(f"HTML: {html_path.name}")

    # 10. Clean up temp
    shutil.rmtree(tmp_dir, ignore_errors=True)
    # Move originals out of inbox to avoid reprocessing
    done_dir = INBOX / "done"
    done_dir.mkdir(exist_ok=True)
    for p in photos:
        shutil.move(str(p), done_dir / p.name)
    info(f"Original photos moved to {INBOX.name}/done/")

    # 11. Open report
    h("Done! 🎉")
    print(f"\n  {G}Markdown:{X} {md_path}")
    print(f"  {G}HTML:    {X} {html_path}")
    open_choice = input(f"\n  Open HTML in browser? [{Y}y{X}/n]: ").strip().lower()
    if open_choice != "n":
        webbrowser.open(f"file://{html_path}")
    print(f"\n  {M}Don't forget to fill in the 'resolution' lines in the report! 💪{X}\n")


if __name__ == "__main__":
    main()
