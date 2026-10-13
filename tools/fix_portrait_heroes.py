#!/usr/bin/env python3
"""Point the 11 portrait-hero pages at the premium 4K landscape hero.

Why: an aspect-ratio audit of all 30 live heroes found 11 businesses whose
own Google hero is portrait (0.46-0.76 ratio). A portrait image in a
full-width hero banner either letterboxes or gets cropped — both look broken.
Fix: give them the same premium landscape 4K hero as their niche, keeping
their real photos in the gallery.
"""
import json, os, re

ROOT = r"D:\MAHMOUD\projects\landing-pages"
PAGES = os.path.join(ROOT, "src", "cities", "sa-riyadh")
HERO = "https://pages.aidy.site/hero"

# slug prefix -> niche hero file
MAP = {
    "ombre-beauty-salon": "beauty_salon",
    "five-minutes-barbershop": "barbershop",
    "gedeb": "coffee",
    "hair-lab-barbershop": "barbershop",
    "ed-salon-hair-nail": "beauty_salon",
    "y97-specialty-coffee": "coffee",
    "yoush-beauty-salon": "beauty_salon",
    "holic-beauty-salon": "nail_salon",
    "powerlife-gym": "gym",
    "جينيرال-كارز": "auto_repair",
    "مركز-يوروفيكس": "auto_repair",
}

changed = 0
for fn in os.listdir(PAGES):
    if not fn.endswith(".html"):
        continue
    niche = None
    for pref, n in MAP.items():
        if fn.startswith(pref):
            niche = n
            break
    if not niche:
        continue

    path = os.path.join(PAGES, fn)
    body = open(path, encoding="utf-8").read()
    hero_url = f"{HERO}/{niche}.jpg"

    # gallery: make the first frame the hero
    m = re.search(r"const PHOTOS = (\[.*?\]);", body, re.S)
    if m:
        photos = json.loads(m.group(1))
        if photos:
            photos[0]["url"] = hero_url
            arr = json.dumps(photos, ensure_ascii=False)
            body = re.sub(r"const PHOTOS = \[.*?\];", "const PHOTOS = " + arr + ";",
                          body, count=1, flags=re.S)

    # swap the hero everywhere (og:image, css, bgimg, gimg)
    hm = re.search(r'background-image:\s*url\(([^)]+)\)', body)
    if hm:
        old = hm.group(1).strip("'\"")
        if old != hero_url:
            body = body.replace(old, hero_url)

    open(path, "w", encoding="utf-8").write(body)
    changed += 1
    print(f"  {fn[:54]:54s} hero -> {niche}")

print(f"\n{changed} portrait-hero pages switched to premium 4K landscape")
