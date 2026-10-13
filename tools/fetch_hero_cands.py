#!/usr/bin/env python3
"""Replace the 3 portrait heroes with wide landscape alternatives.

barbershop, nail_salon, auto_repair currently use portrait stock images.
These candidates are landscape-oriented Unsplash photos in the same niches.
"""
import json, os, struct, time, urllib.request

ROOT = r"D:\MAHMOUD\projects\landing-pages"
HERO = os.path.join(ROOT, "assets", "hero")
CAND = os.path.join(ROOT, "assets", "hero_candidates")
os.makedirs(CAND, exist_ok=True)

# landscape candidates per niche (w=2560)
CANDS = {
    "barbershop": [
        "https://images.unsplash.com/photo-1621605815971-fbc98d665033?w=2560&q=85&fm=jpg",
        "https://images.unsplash.com/photo-1585747860715-2ba37e788b70?w=2560&q=85&fm=jpg",
        "https://images.unsplash.com/photo-1622286342621-4bd786c2447c?w=2560&q=85&fm=jpg",
    ],
    "nail_salon": [
        "https://images.unsplash.com/photo-1632345031435-8727f6897d53?w=2560&q=85&fm=jpg",
        "https://images.unsplash.com/photo-1610992015732-2449b76344bc?w=2560&q=85&fm=jpg",
        "https://images.unsplash.com/photo-1457972729786-0411a3b2b626?w=2560&q=85&fm=jpg",
    ],
    "auto_repair": [
        "https://images.unsplash.com/photo-1487754180451-c456f719a1fc?w=2560&q=85&fm=jpg",
        "https://images.unsplash.com/photo-1632823471565-1ecdf5c6cf77?w=2560&q=85&fm=jpg",
        "https://images.unsplash.com/photo-1517524008697-84bbe3c3fd98?w=2560&q=85&fm=jpg",
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


manifest = {}
for niche, urls in CANDS.items():
    entries = []
    for j, u in enumerate(urls):
        fn = os.path.join(CAND, f"{niche}-{j}.jpg")
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=40).read()
            if len(data) < 20000:
                print(f"  skip {niche}-{j} ({len(data)}B)")
                continue
            open(fn, "wb").write(data)
            dims = jpeg_dims(data)
            orient = "landscape" if dims and dims[0] > dims[1] else "PORTRAIT"
            print(f"  {niche}-{j}  {len(data)//1024:5d}KB  {dims}  {orient}")
            entries.append({"file": f"{niche}-{j}.jpg", "url": u, "w": dims[0], "h": dims[1],
                            "landscape": dims[0] > dims[1]})
        except Exception as e:
            print(f"  fail {niche}-{j}: {str(e)[:50]}")
        time.sleep(0.5)
    manifest[niche] = entries

json.dump(manifest, open(os.path.join(ROOT, "hero_candidates.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print(f"\ncandidates saved -> hero_candidates.json")
