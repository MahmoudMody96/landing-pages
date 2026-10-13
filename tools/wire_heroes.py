#!/usr/bin/env python3
"""Point the 12 stock-photo pages at the premium 4K hero per niche.

Hero URL becomes https://pages.aidy.site/hero/<niche>.jpg while the gallery
keeps its three stock frames.
"""
import json, os, re

ROOT = r"D:\MAHMOUD\projects\landing-pages"
PAGES = os.path.join(ROOT, "src", "cities", "sa-riyadh")
HERO_BASE = "https://pages.aidy.site/hero"

# slug prefix -> niche (matches assets/hero/<niche>.jpg)
NICHE_BY_SLUG = [
    ("carve-coffee-bar", "coffee"),
    ("ik-coffee-downtown", "coffee"),
    ("harmonic-barbershop", "barbershop"),
    ("twos-barbershop", "barbershop"),
    ("باب-الاناقة", "barbershop"),
    ("vog-salon", "beauty_salon"),
    ("stellar-beauty-salon", "nail_salon"),
    ("fitness-star-gym", "gym"),
    ("j-f-revolution", "gym"),
    ("almultaka-ladies-center-fitness", "gym"),
    ("future-of-trust-car-workshop-shafi", "auto_repair"),
    ("car-repairs", "auto_repair"),
]

changed = 0
for fn in os.listdir(PAGES):
    if not fn.endswith(".html"):
        continue
    niche = None
    for pref, n in NICHE_BY_SLUG:
        if fn.startswith(pref):
            niche = n
            break
    if not niche:
        continue

    path = os.path.join(PAGES, fn)
    body = open(path, encoding="utf-8").read()
    hero_url = f"{HERO_BASE}/{niche}.jpg"

    # 1) gallery: keep first stock entry as the hero frame, replace its URL
    m = re.search(r"const PHOTOS = (\[.*?\]);", body, re.S)
    if m:
        photos = json.loads(m.group(1))
        if photos:
            photos[0]["url"] = hero_url
            arr = json.dumps(photos, ensure_ascii=False)
            body = re.sub(r"const PHOTOS = \[.*?\];", "const PHOTOS = " + arr + ";",
                          body, count=1, flags=re.S)

    # 2) swap the hero everywhere it appears (og:image, css, bgimg, gimg)
    hm = re.search(r'background-image:\s*url\(([^)]+)\)', body)
    if hm:
        old = hm.group(1).strip("'\"")
        if old != hero_url:
            body = body.replace(old, hero_url)

    open(path, "w", encoding="utf-8").write(body)
    changed += 1
    print(f"  {fn[:52]:52s} hero -> {niche}")

print(f"\n{changed} pages now use the premium 4K hero")
