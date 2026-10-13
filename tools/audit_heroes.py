#!/usr/bin/env python3
"""Extract every live hero URL + download it for visual review."""
import json, os, re, time, urllib.request

ROOT = r"D:\MAHMOUD\projects\landing-pages"
PAGES = os.path.join(ROOT, "src", "cities", "sa-riyadh")
OUT = os.path.join(ROOT, "hero_audit")
os.makedirs(OUT, exist_ok=True)

sel = json.load(open(os.path.join(ROOT, "data", "selected_30.json"), encoding="utf-8"))


def slugify(n):
    s = n.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")[:60]


rows = []
for i, b in enumerate(sel, 1):
    slug = slugify(b["name"])
    body = open(os.path.join(PAGES, slug + ".html"), encoding="utf-8").read()
    m = re.search(r'background-image:\s*url\(([^)]+)\)', body)
    url = m.group(1).strip("'\"") if m else ""
    is_stock = "pages.aidy.site/hero/" in url
    rows.append({"idx": i, "name": b["name"], "slug": slug, "url": url, "stock": is_stock})

# download the non-stock heroes (the real Google photos) for review
print(f"total heroes: {len(rows)} | stock: {sum(r['stock'] for r in rows)} | to download: {sum(not r['stock'] for r in rows)}\n")
for r in rows:
    if r["stock"]:
        print(f"  [{r['idx']:2d}] STOCK  {r['name'][:42]}")
        continue
    fn = os.path.join(OUT, f"{r['idx']:02d}.jpg")
    if os.path.exists(fn) and os.path.getsize(fn) > 8000:
        print(f"  [{r['idx']:2d}] cached {r['name'][:42]}")
        continue
    try:
        req = urllib.request.Request(r["url"], headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=25).read()
        open(fn, "wb").write(data)
        print(f"  [{r['idx']:2d}] {len(data)//1024:4d}KB {r['name'][:42]}")
    except Exception as e:
        print(f"  [{r['idx']:2d}] FAIL  {r['name'][:42]}  {str(e)[:40]}")
    time.sleep(0.3)

json.dump(rows, open(os.path.join(ROOT, "hero_audit.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\nmanifest -> hero_audit.json ({len(rows)} heroes)")
