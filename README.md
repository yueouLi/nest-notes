# nest-notes 🪺

> A weekly household handover system for two — built on appreciation, not blame.

---

## Why this exists

Living together is easy to romanticize and hard to coordinate.

When two people share a home, they rarely share the same standard of clean. What one person notices immediately, the other genuinely doesn't see. Both are working — just on different things, at different thresholds. Neither can see the other's effort. And so the classic argument begins: *"I do everything around here."*

The default system most couples run is invisible and reactive: whoever notices the mess, fixes it. Whoever doesn't notice, doesn't. This isn't laziness — it's just how differently people are wired. But it breeds resentment, because invisible labor stays invisible.

**nest-notes replaces the invisible system with a visible one.**

---

## The idea

Instead of a permanent, undefined division of labor — we rotate.

Each week, one person is the **keeper**: fully responsible for the home that week. The other person is the **inspector**: their job is to *see clearly* — to name what was done well, and to point out what was missed.

The inspector isn't a critic. They're a witness.

The report they generate isn't a complaint — it's a record. Photos, observations, a summary of highlights and action items. Something concrete to look at together, instead of a feeling that festers into a fight.

At handover, both people sit with the same information. Not *"you never clean the coffee machine"* but *"the coffee machine came up again — let's figure out a system."* The problem is on the table. Not the person.

---

## The shift

| Old system | nest-notes |
|---|---|
| Whoever sees it, does it | One person owns the week |
| Invisible effort | Photographed, named, acknowledged |
| "You never notice what I do" | Appreciation is built into the ritual |
| Arguments about who did more | Both look at the same report |
| Two people vs. each other | Two people vs. the mess |

---

## How it works

A Claude Code skill (`/handover`) walks through the weekly handover in five steps:

1. **Who's inspecting?** — identify the inspector and who they're checking after
2. **Scan photos** — drop photos in `~/Desktop/交接照片/`, the skill converts and deduplicates them
3. **Analyze** — Claude reads each photo, classifies the area, notes the state (highlight / issue / after-clean), and suggests a next step
4. **Confirm** — review the analysis together, skip or edit anything that's off
5. **Generate report** — outputs a Markdown log and an editable HTML report

The HTML is fully editable in the browser — because the best version of any report is the one you finish together.

---

## What's in this repo

```
skill/SKILL.md       ← Claude skill definition (drop into ~/.claude/skills/handover/)
scripts/prep.py      ← photo scanning, HEIC conversion, perceptual dedup
scripts/report.py    ← HTML + Markdown report generator
scripts/handover.py  ← standalone entry point
```

---

## Setup

```bash
git clone https://github.com/yueouLi/nest-notes.git

# Install the skill
cp -r nest-notes/skill ~/.claude/skills/handover

# Create the photo inbox
mkdir -p ~/Desktop/交接照片
```

Optional: `pip install pillow` for better duplicate detection (perceptual hash instead of MD5 fallback).

---

*The goal was never a perfectly clean home. It was a home where both people feel seen.*
