#!/usr/bin/env python3
"""
Generate Markdown + HTML handover report from Claude's analysis JSON.
Usage: python3 report.py --input /tmp/handover_analysis.json
"""
import argparse
import json
import shutil
from collections import defaultdict
from datetime import date
from pathlib import Path

VAULT       = Path.home() / "Desktop" / "Obsidian Vault"
ATTACHMENTS = VAULT / "附件"
LOG_DIR     = VAULT / "My Life" / "管家周志"
INBOX       = Path.home() / "Desktop" / "交接照片"

AREA_ICON = {
    "fridge":      "🧊",
    "kitchen":     "☕",
    "sink":        "🚿",
    "bathroom":    "🚿",
    "living_room": "🛋️",
    "bedroom":     "🛏️",
    "laundry":     "🧺",
    "upstairs":    "🪜",
    "other":       "📦",
}

AREA_LABEL = {
    "fridge":      "Fridge",
    "kitchen":     "Kitchen",
    "sink":        "Sink Area",
    "bathroom":    "Bathroom",
    "living_room": "Living Area",
    "bedroom":     "Bedroom",
    "laundry":     "Laundry Area",
    "upstairs":    "Upstairs",
    "other":       "Other",
}

# Display order for sections
AREA_ORDER = ["living_room", "kitchen", "fridge", "bathroom", "sink",
              "laundry", "bedroom", "upstairs", "other"]

# Pill color per area (urgent-heavy areas get coral, others peach/sky)
AREA_PILL = {
    "kitchen": "pill-coral", "bathroom": "pill-coral", "fridge": "pill-coral",
    "sink": "pill-coral", "bedroom": "pill-sky", "upstairs": "pill-sky",
    "living_room": "pill-peach", "laundry": "pill-peach", "other": "pill-peach",
}

SEV_TAG = {
    "urgent": '<span class="tag tag-urgent">needs attention</span>',
    "next":   '<span class="tag tag-next">tidy up</span>',
    "minor":  '<span class="tag tag-minor">quick fix</span>',
}


def _sorted_areas(by_area: dict) -> list:
    ordered = [a for a in AREA_ORDER if a in by_area]
    ordered += [a for a in by_area if a not in AREA_ORDER]
    return ordered


def build_markdown(today: str, outgoing: str, incoming: str,
                   analyses: list, summary: dict) -> str:
    highlights = [a for a in analyses if a.get("state") == "highlight"]
    issues     = [a for a in analyses if a.get("state") == "issue"]
    afters     = [a for a in analyses if a.get("state") == "after_clean"]

    by_area: dict[str, list] = defaultdict(list)
    for a in issues:
        by_area[a.get("area", "other")].append(a)

    lines = [
        f"# Handover Report · {outgoing} · {today}", "",
        f"> Outgoing: **{outgoing}**   Incoming: **{incoming}**   Date: {today}", "",
    ]

    if highlights:
        lines += ["---", "", "## 🌟 Highlights", ""]
        for a in highlights:
            lines += [
                f"### {a.get('issue_title', 'Great work')}",
                "",
                a.get("description", ""),
                f"![[{a['filename']}]]",
                "",
            ]

    for area in _sorted_areas(by_area):
        items = by_area[area]
        icon  = AREA_ICON.get(area, "📦")
        label = AREA_LABEL.get(area, area.replace("_", " ").title())
        lines += ["---", "", f"## {icon} {label}", ""]
        for a in items:
            sev = a.get("severity", "next")
            loc = a.get("location", "")
            lines += [
                f"### {a.get('issue_title', 'Issue')}",
                f"`{sev}`{(' · ' + loc) if loc else ''}",
                "",
                a.get("description", ""),
                "",
                f"💡 {a.get('next_step', '')}",
                "",
                f"![[{a['filename']}]]",
                "",
            ]

    if afters:
        lines += ["---", "", "## ✅ After-Clean Reference", ""]
        for a in afters:
            lines.append(f"![[{a['filename']}]]")
        lines.append("")

    lines += [
        "---", "", "## 📋 Summary", "",
        f"🌟 **Highlights:** {summary.get('highlights', '—')}",
        "",
        f"⚠️ **Action needed today:** {summary.get('action_today', '—')}",
        "",
        f"📋 **Weekly habits to build:** {summary.get('habits', '—')}",
        "",
        f"💬 **To discuss:** {summary.get('discuss', '—')}",
        "",
    ]

    return "\n".join(lines)


def build_html(today: str, outgoing: str, incoming: str,
               analyses: list, summary: dict) -> str:
    highlights = [a for a in analyses if a.get("state") == "highlight"]
    issues     = [a for a in analyses if a.get("state") == "issue"]
    afters     = [a for a in analyses if a.get("state") == "after_clean"]

    by_area: dict[str, list] = defaultdict(list)
    for a in issues:
        by_area[a.get("area", "other")].append(a)

    # ── Highlights banner ──────────────────────────────────────────────────────
    highlights_html = ""
    if highlights:
        cards = ""
        for a in highlights:
            fname = a["filename"]
            icon  = AREA_ICON.get(a.get("area", "other"), "📦")
            cards += f"""
      <div class="hcard">
        <div class="hcard-icon">{icon}</div>
        <div class="hcard-title" contenteditable="true">{a.get('issue_title', '')}</div>
        <div class="hcard-desc" contenteditable="true">{a.get('description', '')}</div>
        <div class="highlight-photos" style="margin-top:12px">
          <div class="hphoto" style="grid-column:1/-1" onclick="openLightbox('../../附件/{fname}')">
            <img src="../../附件/{fname}" loading="lazy">
            <div class="hphoto-cap">{a.get('issue_title', '')} ✨</div>
          </div>
        </div>
      </div>"""
        highlights_html = f"""
  <div class="highlight-banner">
    <div class="highlight-title">🌟 First things first — you did some really great stuff!</div>
    <div class="highlight-cards">{cards}
    </div>
  </div>"""

    # ── Issue sections ─────────────────────────────────────────────────────────
    sections_html = ""
    for area in _sorted_areas(by_area):
        items      = by_area[area]
        icon       = AREA_ICON.get(area, "📦")
        label      = AREA_LABEL.get(area, area.replace("_", " ").title())
        pill_class = AREA_PILL.get(area, "pill-peach")
        count      = len(items)

        cards = ""
        for a in items:
            fname  = a["filename"]
            loc    = a.get("location", label)
            sev    = a.get("severity", "next")
            tag    = SEV_TAG.get(sev, SEV_TAG["next"])
            nexts  = a.get("next_step", "")
            title  = a.get("issue_title", "Issue")
            desc   = a.get("description", "")
            cards += f"""
    <div class="fcard">
      <div class="fcard-top">
        <span class="fcard-icon">{icon}</span>
        <div class="fcard-meta">
          <div class="fcard-area" contenteditable="true">{loc}</div>
          <div class="fcard-name" contenteditable="true">{title}</div>
        </div>
        {tag}
      </div>
      <div class="fcard-body">
        <p class="fcard-desc" contenteditable="true">{desc}</p>
        <div class="next-step" contenteditable="true">💡 {nexts}</div>
        <div class="photo-grid">
          <div class="photo-frame" onclick="openLightbox('../../附件/{fname}')">
            <img src="../../附件/{fname}" loading="lazy">
            <div class="photo-cap">{title}</div>
          </div>
        </div>
      </div>
    </div>"""

        sections_html += f"""
  <section class="section">
    <div class="section-head">
      <span class="section-emoji">{icon}</span>
      <h2 class="section-title">{label}</h2>
      <span class="pill {pill_class}">{count} thing{"s" if count != 1 else ""}</span>
    </div>
    {cards}
  </section>"""

    # ── After-clean gallery ────────────────────────────────────────────────────
    after_html = ""
    if afters:
        gallery = "".join(
            f'<div class="gitem" onclick="openLightbox(\'../../附件/{a["filename"]}\')"><img src="../../附件/{a["filename"]}" loading="lazy"><div class="gcap">{AREA_LABEL.get(a.get("area","other"), "other")} ✨</div></div>'
            for a in afters
        )
        after_html = f"""
  <section class="section">
    <div class="section-head">
      <span class="section-emoji">✨</span>
      <h2 class="section-title">reference: how it should look</h2>
      <span class="pill pill-mint">clean!</span>
    </div>
    <div class="gallery-grid">{gallery}</div>
  </section>"""

    # ── Summary table ──────────────────────────────────────────────────────────
    summary_html = f"""
  <div class="summary">
    <div class="summary-row">
      <span class="sr-icon">🌟</span>
      <div class="sr-text"><strong>Highlights:</strong> <span contenteditable="true">{summary.get('highlights','—')}</span></div>
    </div>
    <div class="summary-row">
      <span class="sr-icon">⚠️</span>
      <div class="sr-text"><strong>Action needed today:</strong> <span contenteditable="true">{summary.get('action_today','—')}</span></div>
    </div>
    <div class="summary-row">
      <span class="sr-icon">📋</span>
      <div class="sr-text"><strong>Weekly habits to build:</strong> <span contenteditable="true">{summary.get('habits','—')}</span></div>
    </div>
    <div class="summary-row">
      <span class="sr-icon">💬</span>
      <div class="sr-text"><strong>To discuss together:</strong> <span contenteditable="true">{summary.get('discuss','—')}</span></div>
    </div>
  </div>"""

    total = len(issues)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Weekly Check-in · {outgoing} · {today}</title>
<link href="https://fonts.googleapis.com/css2?family=Nunito:ital,wght@0,400;0,600;0,700;0,800;1,400&family=Nunito+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#fff8f3;--card:#fff;--text:#3a2e28;--soft:#7a6e68;--muted:#b5aba4;
  --coral:#f07060;--coral-bg:#fff1ee;
  --mint:#4caf88;--mint-bg:#edf8f3;
  --peach:#f5a06a;--peach-bg:#fff5ec;
  --gold:#d4a017;--gold-bg:#fffbe8;
  --sky:#5b9bd5;--sky-bg:#eef5fc;
  --border:#f0e8e0;--shadow:rgba(58,46,40,.07)
}}
body{{font-family:'Nunito Sans','Nunito',sans-serif;background:var(--bg);color:var(--text);line-height:1.65;font-size:15px}}
.hero{{background:linear-gradient(135deg,#e8f4e8 0%,#fef9e8 50%,#fde8dc 100%);padding:56px 40px 48px;text-align:center;position:relative;overflow:hidden}}
.hero::before{{content:'🏠';position:absolute;font-size:180px;opacity:.06;top:-20px;right:-20px;line-height:1}}
.hero-eyebrow{{display:inline-block;background:#fff;color:var(--mint);font-weight:800;font-size:11px;letter-spacing:.12em;text-transform:uppercase;padding:5px 14px;border-radius:100px;margin-bottom:20px;box-shadow:0 2px 8px rgba(76,175,136,.18)}}
.hero-title{{font-family:'Nunito',sans-serif;font-size:clamp(30px,5.5vw,50px);font-weight:800;line-height:1.15;margin-bottom:10px}}
.hero-title .name{{color:var(--mint)}}
.hero-sub{{font-size:14.5px;color:var(--soft);margin-bottom:28px}}
.hero-chips{{display:flex;flex-wrap:wrap;gap:8px;justify-content:center}}
.hchip{{background:#fff;border-radius:100px;padding:6px 16px;font-size:13px;font-weight:600;box-shadow:0 2px 8px var(--shadow)}}
.warm-note{{background:var(--gold-bg);border:2px dashed #e8c840;border-radius:16px;padding:18px 24px;margin:28px auto;max-width:860px;font-size:14px;color:#7a5a00;display:flex;gap:12px;align-items:flex-start}}
.warm-icon{{font-size:22px;flex-shrink:0}}
.main{{max-width:860px;margin:0 auto;padding:12px 40px 72px}}
.highlight-banner{{background:linear-gradient(135deg,var(--gold-bg),#fff9f0);border:2px solid #e8c840;border-radius:20px;padding:28px 32px;margin-bottom:48px;box-shadow:0 4px 20px rgba(212,160,23,.12)}}
.highlight-title{{font-family:'Nunito',sans-serif;font-weight:800;font-size:22px;margin-bottom:20px;display:flex;align-items:center;gap:10px}}
.highlight-cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px}}
.hcard{{background:#fff;border-radius:14px;padding:16px 18px;border:2px solid #f0e0a0;box-shadow:0 2px 10px rgba(212,160,23,.1)}}
.hcard-icon{{font-size:28px;margin-bottom:8px}}
.hcard-title{{font-weight:800;font-size:14px;margin-bottom:5px}}
.hcard-desc{{font-size:13px;color:var(--soft);line-height:1.6}}
.highlight-photos{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:16px}}
.hphoto{{position:relative;aspect-ratio:4/3;overflow:hidden;border-radius:12px;cursor:zoom-in;border:2px solid #f0e0a0}}
.hphoto img{{width:100%;height:100%;object-fit:cover;transition:transform .3s;display:block}}
.hphoto:hover img{{transform:scale(1.05)}}
.hphoto-cap{{position:absolute;bottom:0;left:0;right:0;padding:20px 8px 8px;background:linear-gradient(transparent,rgba(0,0,0,.45));font-size:10.5px;color:#fff;font-weight:600}}
.section{{margin-bottom:48px}}
.section-head{{display:flex;align-items:center;gap:10px;margin-bottom:20px}}
.section-emoji{{font-size:22px}}
.section-title{{font-family:'Nunito',sans-serif;font-weight:800;font-size:21px;flex:1}}
.pill{{padding:4px 14px;border-radius:100px;font-size:12px;font-weight:700}}
.pill-coral{{background:var(--coral-bg);color:var(--coral)}}
.pill-mint{{background:var(--mint-bg);color:var(--mint)}}
.pill-peach{{background:var(--peach-bg);color:var(--peach)}}
.pill-sky{{background:var(--sky-bg);color:var(--sky)}}
.fcard{{background:var(--card);border-radius:18px;border:2px solid var(--border);overflow:hidden;margin-bottom:14px;box-shadow:0 3px 14px var(--shadow);transition:transform .2s}}
.fcard:hover{{transform:translateY(-2px)}}
.fcard-top{{display:flex;align-items:center;gap:11px;padding:15px 20px;border-bottom:1.5px solid var(--border);flex-wrap:wrap}}
.fcard-icon{{font-size:24px}}
.fcard-meta{{flex:1;min-width:0}}
.fcard-area{{font-size:10.5px;font-weight:700;color:var(--muted);letter-spacing:.08em;text-transform:uppercase;margin-bottom:2px}}
.fcard-name{{font-weight:800;font-size:14.5px}}
.tag{{display:inline-flex;align-items:center;gap:4px;padding:3px 12px;border-radius:100px;font-size:11.5px;font-weight:700}}
.tag-urgent{{background:#ffe0dc;color:#c0392b}}
.tag-next{{background:#fff3cd;color:#9c6900}}
.tag-minor{{background:var(--sky-bg);color:var(--sky)}}
.fcard-body{{padding:16px 20px}}
.fcard-desc{{font-size:14px;color:var(--soft);margin-bottom:13px;line-height:1.75}}
.next-step{{background:var(--mint-bg);border-radius:10px;padding:10px 15px;font-size:13px;color:#2a7a56;font-weight:600;margin-bottom:14px;display:flex;gap:8px;align-items:flex-start;line-height:1.55}}
.photo-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}}
.photo-frame{{position:relative;aspect-ratio:4/3;overflow:hidden;border-radius:10px;cursor:zoom-in;background:var(--bg);border:1.5px solid var(--border)}}
.photo-frame img{{width:100%;height:100%;object-fit:cover;transition:transform .3s;display:block}}
.photo-frame:hover img{{transform:scale(1.07)}}
.photo-cap{{position:absolute;bottom:0;left:0;right:0;padding:18px 8px 7px;background:linear-gradient(transparent,rgba(0,0,0,.5));font-size:10px;color:#fff;font-weight:600;opacity:0;transition:opacity .2s}}
.photo-frame:hover .photo-cap{{opacity:1}}
.gallery-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}
.gitem{{position:relative;aspect-ratio:4/3;overflow:hidden;border-radius:16px;cursor:zoom-in;background:var(--bg);border:2px solid var(--border);box-shadow:0 3px 12px var(--shadow)}}
.gitem img{{width:100%;height:100%;object-fit:cover;transition:transform .3s;display:block}}
.gitem:hover img{{transform:scale(1.06)}}
.gcap{{position:absolute;bottom:0;left:0;right:0;padding:28px 10px 10px;background:linear-gradient(transparent,rgba(0,0,0,.5));font-size:11px;color:rgba(255,255,255,.95);font-weight:700}}
.summary{{background:var(--card);border:2px solid var(--border);border-radius:18px;overflow:hidden;margin-bottom:48px;box-shadow:0 3px 14px var(--shadow)}}
.summary-row{{display:flex;align-items:flex-start;gap:14px;padding:14px 20px;border-bottom:1.5px solid var(--border);font-size:14px}}
.summary-row:last-child{{border-bottom:none}}
.sr-icon{{font-size:20px;flex-shrink:0;margin-top:1px}}
.sr-text{{flex:1;line-height:1.6}}
.sr-text strong{{font-weight:700}}
.footer{{text-align:center;padding:36px 40px;color:var(--muted);font-size:12.5px;border-top:2px dashed var(--border)}}
.footer-heart{{color:var(--coral)}}
[contenteditable]{{cursor:text;border-radius:5px;transition:background .15s,outline .15s}}
[contenteditable]:hover{{background:rgba(76,175,136,.07)}}
[contenteditable]:focus{{outline:2px solid var(--mint);background:rgba(76,175,136,.06);border-radius:5px}}
.edit-badge{{position:fixed;bottom:20px;right:20px;background:var(--mint);color:#fff;font-size:11px;font-weight:800;letter-spacing:.05em;padding:7px 14px;border-radius:100px;box-shadow:0 3px 10px rgba(76,175,136,.35);z-index:100;pointer-events:none}}
.lightbox{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.9);z-index:9999;align-items:center;justify-content:center;padding:40px;cursor:zoom-out}}
.lightbox.active{{display:flex}}
.lightbox img{{max-width:100%;max-height:90vh;object-fit:contain;border-radius:10px}}
.lb-close{{position:fixed;top:16px;right:22px;color:rgba(255,255,255,.55);font-size:34px;cursor:pointer;transition:color .15s}}
.lb-close:hover{{color:#fff}}
@media(max-width:600px){{.hero,.main{{padding-left:20px;padding-right:20px}}.warm-note{{margin-left:20px;margin-right:20px}}.highlight-cards{{grid-template-columns:1fr}}.highlight-photos{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="hero">
  <div class="hero-eyebrow">Weekly Check-in · {today}</div>
  <h1 class="hero-title">hey <span class="name">{outgoing}</span> 💚</h1>
  <p class="hero-sub">here's a little recap — the wins AND the things to work on together</p>
  <div class="hero-chips">
    <span class="hchip">📅 {today}</span>
    <span class="hchip">✍️ written by {incoming}</span>
    <span class="hchip">📋 {total} thing{"s" if total != 1 else ""} to address</span>
  </div>
</div>
<div class="warm-note">
  <span class="warm-icon">💌</span>
  <span>this is meant as a <strong>team check-in</strong>, not a report card 😊 i can see you put real effort in and i want that to be recognised. the feedback below is just so we can keep improving together — one step at a time, no pressure.</span>
</div>
<main class="main">
  {highlights_html}
  {sections_html}
  {after_html}
  {summary_html}
</main>
<footer class="footer">
  written with love (and a bit of elbow grease) by {incoming} <span class="footer-heart">♥</span> · {today} · we've got this, {outgoing}!
</footer>
<div class="edit-badge">✏️ editable</div>
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()

    data      = json.loads(Path(args.input).read_text(encoding="utf-8"))
    today     = data.get("today", date.today().isoformat())
    outgoing  = data.get("outgoing", "boyfriend")
    incoming  = data.get("incoming", "Leonie")
    analyses  = data.get("analyses", [])
    originals = data.get("originals", [])
    tmp_dir   = data.get("tmp_dir")
    summary   = data.get("summary", {
        "highlights": "—", "action_today": "—", "habits": "—", "discuss": "—",
    })

    ATTACHMENTS.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    for a in analyses:
        src = Path(tmp_dir) / a["filename"] if tmp_dir else None
        if src and src.exists():
            shutil.copy(src, ATTACHMENTS / a["filename"])

    md_path = LOG_DIR / f"{today} 管家交接总结 {outgoing}.md"
    md_path.write_text(
        build_markdown(today, outgoing, incoming, analyses, summary),
        encoding="utf-8",
    )

    html_path = LOG_DIR / f"{today} 管家交接汇报 {outgoing}.html"
    html_path.write_text(
        build_html(today, outgoing, incoming, analyses, summary),
        encoding="utf-8",
    )

    done_dir = INBOX / "done"
    done_dir.mkdir(exist_ok=True)
    for orig in originals:
        p = Path(orig)
        if p.exists():
            shutil.move(str(p), done_dir / p.name)

    if tmp_dir and Path(tmp_dir).exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print(json.dumps({
        "markdown": str(md_path),
        "html":     str(html_path),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
