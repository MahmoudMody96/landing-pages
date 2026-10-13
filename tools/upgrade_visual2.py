#!/usr/bin/env python3
"""Apply the visual upgrade to the 18 real-photo pages (gallery + CTA only).

These pages keep their own Google photos as hero — that is correct and better.
But the dark hero overlay is softened the same way, and the gallery gets the
16/9 + blur-caption + hover-zoom treatment for a consistent look across the site.
"""
import os, re

ROOT = r"D:\MAHMOUD\projects\landing-pages"
PAGES = os.path.join(ROOT, "src", "cities", "sa-riyadh")

STOCK_SLUGS = [
    "carve-coffee-bar", "ik-coffee-downtown", "harmonic-barbershop",
    "twos-barbershop", "باب-الاناقة", "vog-salon", "stellar-beauty-salon",
    "fitness-star-gym", "j-f-revolution", "almultaka-ladies-center-fitness",
    "future-of-trust-car-workshop-shafi", "car-repairs",
]

HERO_OVERLAY_OLD = re.compile(
    r"\.hero::after\{content:\"\";position:absolute;inset:0;background:"
    r"linear-gradient\(180deg,rgba\(10,12,16,\.35\) 0%,rgba\(10,12,16,\.55\) 45%,"
    r"rgba\(10,12,16,\.88\) 100%\)\}"
)
HERO_OVERLAY_NEW = (
    ".hero::after{content:\"\";position:absolute;inset:0;"
    "background:linear-gradient(180deg,rgba(8,10,14,.02) 0%,rgba(8,10,14,.06) 40%,"
    "rgba(8,10,14,.42) 78%,rgba(8,10,14,.62) 100%)}\n"
    ".hero::before{content:\"\";position:absolute;inset:0;z-index:1;"
    "background:radial-gradient(120% 90% at 50% 40%,transparent 55%,rgba(0,0,0,.28) 100%)}"
)

GAL_MAIN_OLD = re.compile(r"\.gmain\{position:relative;border-radius:20px;overflow:hidden;aspect-ratio:16/10;background:#eef0f4;box-shadow:0 12px 40px rgba\(0,0,0,\.13\)\}")
GAL_MAIN_NEW = ".gmain{position:relative;border-radius:26px;overflow:hidden;aspect-ratio:16/9;background:#eef0f4;box-shadow:0 22px 60px rgba(0,0,0,.18)}"

GAL_CAP_OLD = re.compile(r"\.gmain \.cap\{position:absolute;bottom:0;left:0;right:0;padding:16px 20px;background:linear-gradient\(transparent,rgba\(0,0,0,\.75\)\);color:#fff;font-size:\.88rem;font-weight:600\}")
GAL_CAP_NEW = ".gmain .cap{position:absolute;bottom:0;left:0;right:0;padding:18px 22px;background:linear-gradient(transparent,rgba(0,0,0,.55));backdrop-filter:blur(2px);color:#fff;font-size:.92rem;font-weight:700}"

GAL_IMG_OLD = re.compile(r"\.gmain img\{width:100%;height:100%;object-fit:cover;transition:opacity \.35s\}")
GAL_IMG_NEW = ".gmain img{width:100%;height:100%;object-fit:cover;transition:opacity .35s,transform .6s ease}.gmain:hover img{transform:scale(1.03)}"

GAL_NAV_OLD = re.compile(r"\.gnav\{position:absolute;top:50%;transform:translateY\(-50%\);width:42px;height:42px;border-radius:50%;background:rgba\(255,255,255,\.92\);border:none;display:flex;align-items:center;justify-content:center;font-size:1\.15rem;cursor:pointer;box-shadow:0 3px 14px rgba\(0,0,0,\.2\);z-index:3;color:#111\}")
GAL_NAV_NEW = ".gnav{position:absolute;top:50%;transform:translateY(-50%);width:48px;height:48px;border-radius:50%;background:rgba(255,255,255,.95);border:none;display:flex;align-items:center;justify-content:center;font-size:1.3rem;cursor:pointer;box-shadow:0 6px 20px rgba(0,0,0,.25);z-index:3;color:#111;transition:transform .15s}.gnav:hover{transform:translateY(-50%) scale(1.08)}"

CTA_BG_OLD = re.compile(r"opacity:\.13\}")
CTA_BG_NEW = "opacity:.07}"

changed = 0
for fn in os.listdir(PAGES):
    if not fn.endswith(".html"):
        continue
    if any(fn.startswith(s) for s in STOCK_SLUGS):
        continue  # already upgraded

    path = os.path.join(PAGES, fn)
    body = open(path, encoding="utf-8").read()
    orig = body

    body, n1 = HERO_OVERLAY_OLD.subn(HERO_OVERLAY_NEW, body)
    body, n2 = GAL_MAIN_OLD.subn(GAL_MAIN_NEW, body)
    body, n3 = GAL_CAP_OLD.subn(GAL_CAP_NEW, body)
    body, n4 = GAL_IMG_OLD.subn(GAL_IMG_NEW, body)
    body, n5 = GAL_NAV_OLD.subn(GAL_NAV_NEW, body)
    body, n6 = CTA_BG_OLD.subn(CTA_BG_NEW, body)

    if body != orig:
        open(path, "w", encoding="utf-8").write(body)
        changed += 1
        flags = "".join(str(x) for x in (n1, n2, n3, n4, n5, n6))
        print(f"  {fn[:54]:54s} [{flags}]")

print(f"\n{changed} real-photo pages upgraded")
