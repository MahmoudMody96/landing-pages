#!/usr/bin/env python3
"""Localize hotlinked Google Maps images into the repo.

Why: pages used to point their hero + gallery at `lh3.googleusercontent.com`
URLs. Those are third-party, un-cached on our side, and Google rotates them —
so a client page can silently lose its gallery. This tool downloads every
hotlinked image, normalizes it, stores it under `assets/stock/<slug>_<i>.jpg`
(and business-specific heroes under `assets/hero/<slug>.jpg`), and rewrites the
pages to use our own domain.

Layout it assumes (produced by tools/upgrade_visual*.py):
  * hero      = the `class="bgimg"` background-image URL
  * gallery   = the `const PHOTOS = [...]` array, where item[0] is the hero and
                items[1..N] are the business's own photos

Usage:
  python tools/localize_images.py --check     # report only, no writes
  python tools/localize_images.py             # download + rewrite pages

Hero policy: a hotlinked hero is only kept when it is a clean landscape photo
of the business itself. Otherwise the page falls back to the 4K niche hero
(see HERO_OVERRIDE) — same rule as assets/stock/PHOTOS.md.

Requires: Pillow (pip install Pillow)
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CITIES = ROOT / "src" / "cities"
STOCK = ROOT / "assets" / "stock"
HERO = ROOT / "assets" / "hero"
PLAN_OUT = ROOT / "data" / "localize_plan.json"

BASE_URL = "https://pages.aidy.site"
TARGET_AR = 16 / 9                        # matches the .gmain gallery frame
TARGET_W, TARGET_H = 1600, 900
QUALITY = 80

GOOG_RE = re.compile(r"https://lh3\.googleusercontent\.com/[^\"'\s)]+")
UA = {"User-Agent": "Mozilla/5.0"}

# Business-specific hero replacements for the 7 pages that used a Google photo
# as hero. Keys are slugs; values are the URL path to use instead.
#   * a downloaded storefront -> "/hero/<slug>.jpg" (kept, clean landscape)
#   * a rejected storefront   -> the 4K niche hero (see the "why" column)
HERO_OVERRIDE = {
    # clean landscape photos of the business itself -> localized below
    "calibrated-coffee-roasters": "keep",
    "unsorso-cafe": "keep",
    "university-cooperative-center-for-car-maintenance": "keep",
    # neighbouring business signage visible in frame -> brand-safety reject
    "java-time": "/hero/coffee.jpg",
    "the-protocol-barbershop": "/hero/barbershop.jpg",
    # source photo too small (1280x960 / 1024x768) -> below the 4K rule
    "in2fitness-al-arid-men": "/hero/gym.jpg",
    "sporttype-gym": "/hero/gym.jpg",
}


def fetch(url: str, timeout: int = 60, attempts: int = 4) -> bytes:
    """GET with backoff — googleusercontent can rate-limit bursts."""
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=timeout
            ) as resp:
                return resp.read()
        except Exception as exc:                       # noqa: BLE001
            last = exc
            time.sleep(min(2 ** attempt, 15))
    raise RuntimeError(f"{type(last).__name__}: {str(last)[:120]}")


def best_source(base: str) -> tuple[bytes, str]:
    """Ask Google for the largest sensible variant, fall back to the original."""
    data = fetch(f"{base}=w2560-h1920-k-no")
    try:
        if Image.open(io.BytesIO(data)).width >= 1200:
            return data, "w2560-h1920-k-no"
    except Exception:                                  # noqa: BLE001
        pass
    return fetch(f"{base}=s0"), "s0"


def normalize(data: bytes) -> bytes:
    """Center-crop to 16:9 and cap at 1600x900.

    The gallery frame is `.gmain{aspect-ratio:16/9}` with `object-fit:cover`,
    so the browser already crops every photo to the middle 16:9 band. Doing it
    here means we store exactly what gets shown — same picture on screen, a
    fraction of the bytes, and no portrait files in the repo.
    """
    im = Image.open(io.BytesIO(data))
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    w, h = im.size
    if w / h > TARGET_AR:                       # too wide -> trim the sides
        nw = round(h * TARGET_AR)
        left = (w - nw) // 2
        im = im.crop((left, 0, left + nw, h))
    else:                                       # too tall -> trim top/bottom
        nh = round(w / TARGET_AR)
        top = (h - nh) // 2
        im = im.crop((0, top, w, top + nh))
    if im.width > TARGET_W:
        im = im.resize((TARGET_W, TARGET_H), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    return out.getvalue()


def pages() -> list[Path]:
    return sorted(p for p in CITIES.glob("*/*.html") if p.name != "index.html")


def analyse(path: Path) -> dict | None:
    s = path.read_text(encoding="utf-8")
    urls = GOOG_RE.findall(s)
    if not urls:
        return None
    slug = path.stem
    m = re.search(r'class="bgimg"[^>]*background-image:url\(\'([^\']+)\'', s)
    hero_old = m.group(1) if m and "googleusercontent" in m.group(1) else None
    m2 = re.search(r"const PHOTOS\s*=\s*\[(.*?)\];", s, re.S)
    items = re.findall(r'"url":\s*"([^"]+)"', m2.group(1)) if m2 else []
    gallery = [u for u in items[1:] if "googleusercontent" in u]
    return {"path": path, "slug": slug, "src": s, "hero_old": hero_old, "gallery": gallery}


def regen_from_plan(delay: float) -> int:
    """Re-download the recorded assets without touching any page.

    Useful after changing the crop/quality settings: the pages already point at
    /stock/<slug>_<i>.jpg, so only the files under assets/stock need rebuilding.
    """
    if not PLAN_OUT.exists():
        print(f"no plan at {PLAN_OUT} — run without --from-plan first", file=sys.stderr)
        return 1
    plan = json.loads(PLAN_OUT.read_text(encoding="utf-8"))
    failures: list[tuple[str, str, str]] = []
    done = 0
    for n, (slug, v) in enumerate(plan.items(), start=1):
        for e in v["gallery"]:
            try:
                data, _ = best_source(e["old"].split("=")[0])
                (STOCK / e["file"]).write_bytes(normalize(data))
                done += 1
            except Exception as exc:                   # noqa: BLE001
                failures.append((slug, e["old"], f"{type(exc).__name__}: {str(exc)[:120]}"))
            time.sleep(delay)
        print(f"[{n}/{len(plan)}] {slug}: done", flush=True)
    print(f"\nassets regenerated: {done}")
    if failures:
        (ROOT / "data" / "localize_failures.json").write_text(
            json.dumps([{"slug": s, "url": u, "error": e} for s, u, e in failures],
                       ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        for slug, url, err in failures:
            print(f"  FAIL {slug}: {err}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only, write nothing")
    ap.add_argument("--from-plan", action="store_true",
                    help="re-download the assets recorded in data/localize_plan.json (pages untouched)")
    ap.add_argument("--delay", type=float, default=0.4, help="seconds between downloads")
    args = ap.parse_args()

    if args.from_plan:
        return regen_from_plan(args.delay)

    STOCK.mkdir(parents=True, exist_ok=True)
    HERO.mkdir(parents=True, exist_ok=True)

    work = [w for w in (analyse(p) for p in pages()) if w]
    total = sum(len(w["gallery"]) for w in work)
    print(f"pages with hotlinked images: {len(work)} | gallery images to localize: {total}")
    if args.check:
        for w in work:
            print(f"  {w['slug'][:56]:58} gallery={len(w['gallery']):2} hero={'google' if w['hero_old'] else 'self'}")
        return 0

    # ---- 1. download everything first; abort before touching any page ----
    failures: list[tuple[str, str, str]] = []
    plan: dict[str, dict] = {}
    for n, w in enumerate(work, start=1):
        slug = w["slug"]
        entries = []
        for i, url in enumerate(w["gallery"], start=1):
            dest = STOCK / f"{slug}_{i}.jpg"
            base = url.split("=")[0]
            if dest.exists() and dest.stat().st_size > 20000:
                # Resumable: a previous run already fetched this one.
                try:
                    with Image.open(dest) as im:
                        im.verify()
                    entries.append({"i": i, "old": url, "file": dest.name,
                                    "variant": "cached", "bytes": dest.stat().st_size})
                    continue
                except Exception:                          # noqa: BLE001
                    dest.unlink(missing_ok=True)
            try:
                data, variant = best_source(base)
                payload = normalize(data)
                dest.write_bytes(payload)
                entries.append({"i": i, "old": url, "file": dest.name,
                                "variant": variant, "bytes": len(payload)})
            except Exception as exc:                       # noqa: BLE001
                err = f"{type(exc).__name__}: {str(exc)[:150]}"
                failures.append((slug, url, err))
                print(f"    FAIL {dest.name}: {err}", file=sys.stderr, flush=True)
            time.sleep(args.delay)
        print(f"[{n}/{len(work)}] {slug}: {len(entries)}/{len(w['gallery'])} ok", flush=True)

        hero_new = None
        if w["hero_old"]:
            override = HERO_OVERRIDE.get(slug)
            if override == "keep":
                src = HERO / f"{slug}.jpg"
                if not src.exists():
                    failures.append((slug, w["hero_old"], f"missing local hero {src.name}"))
                hero_new = f"{BASE_URL}/hero/{slug}.jpg"
            elif override:
                hero_new = f"{BASE_URL}{override}"
            else:
                failures.append((slug, w["hero_old"], "no HERO_OVERRIDE decision recorded"))
        plan[slug] = {"hero_old": w["hero_old"], "hero_new": hero_new, "gallery": entries}

    if failures:
        (ROOT / "data" / "localize_failures.json").write_text(
            json.dumps([{"slug": s, "url": u, "error": e} for s, u, e in failures],
                       ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print("\nFAILED downloads — no page was modified:", file=sys.stderr)
        for slug, url, err in failures:
            print(f"  {slug}: {err}\n    {url[:110]}", file=sys.stderr)
        print(f"({len(failures)} failures written to data/localize_failures.json)")
        return 1

    # ---- 2. rewrite pages ----
    changed = 0
    for w in work:
        slug = w["slug"]
        s = w["src"]
        mapping = {e["old"]: f"{BASE_URL}/stock/{e['file']}" for e in plan[slug]["gallery"]}
        if plan[slug]["hero_new"] and w["hero_old"]:
            mapping[w["hero_old"]] = plan[slug]["hero_new"]
        for old, new in mapping.items():
            s = s.replace(old, new)
        leftover = GOOG_RE.findall(s)
        if leftover:
            print(f"  WARN {slug}: {len(leftover)} hotlinked URL(s) left", file=sys.stderr)
            continue
        w["path"].write_text(s, encoding="utf-8")
        changed += 1

    # Never clobber a recorded plan with an empty one: a second run finds no
    # hotlinks (the pages are already rewritten) and used to wipe the record
    # needed by --from-plan.
    if plan:
        PLAN_OUT.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\npages rewritten: {changed}/{len(work)}")
    print(f"gallery files written: {sum(len(p['gallery']) for p in plan.values())}")
    print(f"plan: {PLAN_OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
