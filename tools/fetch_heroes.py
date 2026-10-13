#!/usr/bin/env python3
"""Download premium 4K hero images from Unsplash — one fixed hero per niche.

Unsplash's `w=2560` param returns a high-res rendition suitable for a full-width
hero (2400px is enough for retina on a 1920 viewport; w=2560 keeps headroom).
Images are chosen for: no branding, cinematic lighting, wide composition.
"""
import json, os, time, urllib.request

ROOT = r"D:\MAHMOUD\projects\landing-pages"
OUT = os.path.join(ROOT, "assets", "hero")
os.makedirs(OUT, exist_ok=True)

# One premium hero per niche (w=2560 for full-width retina).
HEROES = {
    "coffee": [
        "https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=2560&q=85&fm=jpg",
    ],
    "barbershop": [
        "https://images.unsplash.com/photo-1503951914875-452162b0f3f1?w=2560&q=85&fm=jpg",
    ],
    "beauty_salon": [
        "https://images.unsplash.com/photo-1560066984-138dadb4c035?w=2560&q=85&fm=jpg",
    ],
    "nail_salon": [
        "https://images.unsplash.com/photo-1604654894610-df63bc536371?w=2560&q=85&fm=jpg",
    ],
    "gym": [
        "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=2560&q=85&fm=jpg",
    ],
    "auto_repair": [
        "https://images.unsplash.com/photo-1486262715619-67b85e0b08d3?w=2560&q=85&fm=jpg",
    ],
}

# extra candidates in case a primary fails or needs replacing
FALLBACKS = {
    "coffee": [
        "https://images.unsplash.com/photo-1453614512568-c4024d13c247?w=2560&q=85&fm=jpg",
        "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=2560&q=85&fm=jpg",
    ],
    "barbershop": [
        "https://images.unsplash.com/photo-1585747860715-2ba37e788b70?w=2560&q=85&fm=jpg",
        "https://images.unsplash.com/photo-1621605815971-fbc98d665033?w=2560&q=85&fm=jpg",
    ],
    "beauty_salon": [
        "https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?w=2560&q=85&fm=jpg",
        "https://images.unsplash.com/photo-1633681926022-84c23e8cb2d6?w=2560&q=85&fm=jpg",
    ],
    "nail_salon": [
        "https://images.unsplash.com/photo-1610992015732-2449b76344bc?w=2560&q=85&fm=jpg",
        "https://images.unsplash.com/photo-1632345031435-8727f6897d53?w=2560&q=85&fm=jpg",
    ],
    "gym": [
        "https://images.unsplash.com/photo-1571902943202-507ec2618e8f?w=2560&q=85&fm=jpg",
        "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=2560&q=85&fm=jpg",
    ],
    "auto_repair": [
        "https://images.unsplash.com/photo-1487754180451-c456f719a1fc?w=2560&q=85&fm=jpg",
        "https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=2560&q=85&fm=jpg",
    ],
}


def jpeg_dims(data):
    i = 2
    while i < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        m = data[i + 1]
        if m in (0xC0, 0xC1, 0xC2):
            h = int.from_bytes(data[i + 5:i + 7], "big")
            w = int.from_bytes(data[i + 7:i + 9], "big")
            return w, h
        ln = int.from_bytes(data[i + 2:i + 4], "big")
        i += 2 + ln
    return None


def fetch(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = urllib.request.urlopen(req, timeout=40).read()
    if len(data) < 20000:
        raise RuntimeError(f"too small ({len(data)}B)")
    open(path, "wb").write(data)
    return len(data), jpeg_dims(data)


manifest = {}
for niche, urls in HEROES.items():
    dest = os.path.join(OUT, f"{niche}.jpg")
    got = False
    for attempt, u in enumerate(urls + FALLBACKS.get(niche, [])):
        try:
            size, dims = fetch(u, dest)
            print(f"  ok {niche:14s} {size//1024:5d}KB {dims}  (attempt {attempt+1})")
            manifest[niche] = {"url": u, "local": f"assets/hero/{niche}.jpg",
                               "width": dims[0], "height": dims[1], "bytes": size}
            got = True
            break
        except Exception as e:
            print(f"  fail {niche:14s} attempt {attempt+1}: {str(e)[:60]}")
            time.sleep(1)
    if not got:
        print(f"  !! {niche} FAILED COMPLETELY")
    time.sleep(0.5)

json.dump(manifest, open(os.path.join(ROOT, "data", "hero_manifest.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print(f"\n{len(manifest)}/6 hero images ready -> data/hero_manifest.json")
