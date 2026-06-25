#!/usr/bin/env python3
"""
Scan ~/Desktop/交接照片/, convert photos to JPG, detect near-duplicates, output JSON to stdout.
Called by the /handover skill before Claude analyzes the images.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

INBOX      = Path.home() / "Desktop" / "交接照片"
IMAGE_EXTS = {".heic", ".jpg", ".jpeg", ".png", ".webp"}
TMP_DIR    = INBOX / ".converted"

# Perceptual hash: hamming distance threshold (out of 64 bits).
# ≤10 means ~84% similar — catches same-scene shots from slightly different angles.
DUPE_THRESHOLD = 10


def convert_to_jpg(src: Path, dst_dir: Path) -> Path:
    out = dst_dir / (src.stem + ".jpg")
    subprocess.run(
        ["sips", "-Z", "1024", "-s", "format", "jpeg",
         "-s", "formatOptions", "65", str(src), "--out", str(out)],
        capture_output=True, check=True
    )
    return out


def compute_phash(jpg_path: Path) -> str:
    """8×8 average hash → 16-char hex string (64 bits).
    Falls back to MD5 of raw bytes if Pillow is not installed
    (fallback only catches byte-identical files, not near-dupes)."""
    try:
        from PIL import Image
        img = Image.open(jpg_path).convert("L").resize((8, 8), Image.LANCZOS)
        pixels = list(img.getdata())
        avg = sum(pixels) / len(pixels)
        bits = "".join("1" if p >= avg else "0" for p in pixels)
        return format(int(bits, 2), "016x")
    except ImportError:
        return hashlib.md5(jpg_path.read_bytes()).hexdigest()


def hamming(h1: str, h2: str) -> int:
    # Works for both 16-char phash hex and 32-char MD5 hex
    min_len = min(len(h1), len(h2)) * 4  # bits
    return bin(int(h1, 16) ^ int(h2, 16)).count("1")


def find_duplicates(results: list) -> list[list[str]]:
    """Return groups of near-duplicate filenames (each group has ≥2 members)."""
    hashes = [(r["filename"], compute_phash(Path(r["converted"]))) for r in results]
    visited = set()
    groups = []
    for i, (name_i, hash_i) in enumerate(hashes):
        if name_i in visited:
            continue
        group = [name_i]
        for j, (name_j, hash_j) in enumerate(hashes):
            if i == j or name_j in visited:
                continue
            if hamming(hash_i, hash_j) <= DUPE_THRESHOLD:
                group.append(name_j)
        if len(group) > 1:
            visited.update(group)
            groups.append(group)
    return groups


def main():
    if not INBOX.exists():
        print(json.dumps({"error": f"Inbox not found: {INBOX}"}))
        sys.exit(1)

    photos = sorted(p for p in INBOX.iterdir()
                    if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    if not photos:
        print(json.dumps({"photos": [], "tmp_dir": str(TMP_DIR), "duplicates": []}))
        return

    TMP_DIR.mkdir(exist_ok=True)
    results = []
    for p in photos:
        jpg = convert_to_jpg(p, TMP_DIR)
        results.append({
            "original": str(p),
            "converted": str(jpg),
            "filename":  jpg.name,
        })

    duplicates = find_duplicates(results)
    print(json.dumps({
        "photos":     results,
        "tmp_dir":    str(TMP_DIR),
        "duplicates": duplicates,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
