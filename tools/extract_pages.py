"""extract_pages.py -- turn an existing page into a data record.

This is the first half of the bootstrap pipeline:

    src/cities/**/*.html  --extract-->  data/extracted.json
                                          --build_niches-->  templates/niches/*.json
                                                             data/businesses.json
                                          --gen_pages-->    src/cities/**/*.html

It reads a page and pulls out every business-specific value AND every bit of
bespoke copy (h1, about paragraphs, USPs, reviews, FAQs). Everything captured
out of the HTML is UNESCAPED before it is stored: the data files hold raw text
("ED salon Hair & Nail"), and tools/pagekit.py escapes exactly once, on the way
into the HTML. The only value kept in its escaped form is about_html, which is
handed to build_niches.py to be turned back into a {token} template.

    python tools/extract_pages.py --dir src/cities/sa-riyadh --out data/extracted.json
"""
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pagekit as pk
import shapes

ROOT = Path(__file__).resolve().parent.parent


def one(pattern, text, flags=0, what=""):
    m = re.search(pattern, text, flags)
    if not m:
        raise SystemExit(f"FAIL: could not extract {what or pattern!r}")
    return m.group(1)


def raw(value: str) -> str:
    """Undo the page's HTML escaping so the data file holds plain text."""
    return html.unescape(value)


def extract(path: Path, manifest: dict) -> dict:
    page = path.read_text(encoding="utf-8")
    slug = path.stem
    rec: dict = {"slug": slug, "file": path.name}

    # ---- JSON-LD (authoritative for phone, address parts, type) ----
    ld = json.loads(one(r'<script type="application/ld\+json">(.*?)</script>',
                        page, re.S, "JSON-LD"))
    rec["name"] = ld["name"]
    rec["url"] = ld.get("url", "")
    rec["phone_intl"] = ld.get("telephone", "")
    addr = ld.get("address", {})
    rec["jsonld"] = {
        "type": ld.get("@type"),
        "sameAs": ld.get("sameAs", []),
        # keep the schema.org keys exactly as the page writes them: two pages
        # omit postalCode, and re-adding it as "" would change the output
        "address": {k: addr[k] for k in addr if k != "@type"},
    }
    agg = ld.get("aggregateRating", {})
    rec["rating"] = agg.get("ratingValue")
    rec["review_count"] = agg.get("reviewCount")

    # ---- identity ----
    # niche is resolved by the caller: extract() cannot decide it alone, because
    # some pages use a niche hero without saying so anywhere machine-readable.
    rec["niche_name"] = raw(one(r'<span class="hero-chip">\U0001F3F7\uFE0F? ([^<]*)</span>',
                                page, what="niche chip"))
    # The 📍 chip and the area line carry the DISTRICT; the title, the kicker and
    # the SEO copy carry the CITY. They are the same word on most Riyadh pages,
    # which is exactly why they must be read from different places.
    rec["district"] = raw(one(r'<span class="hero-chip">\U0001F4CD ([^<]*)</span>',
                              page, what="district chip"))
    m = re.search(r'<span class="kicker">([^<]*) \u00B7 ([^<]*)</span>', page)
    if not m:
        raise SystemExit(f"FAIL: could not extract city kicker from {slug}")
    rec["niche_name_kicker"] = raw(m.group(1))
    rec["city_ar"] = raw(m.group(2))
    if rec["niche_name_kicker"] != rec["niche_name"]:
        raise SystemExit(
            f"FAIL: {slug} disagrees with itself: hero chip says "
            f"{rec['niche_name']!r}, kicker says {rec['niche_name_kicker']!r}")
    del rec["niche_name_kicker"]
    rec["mark"] = raw(one(r'<span class="mark">([^<]*)</span>', page, what="nav mark emoji"))
    # the nav label for the services section is niche vocabulary
    # ("خدماتنا" / "برامجنا" / "اللي نوفّره"), not business data
    rec["nav_services"] = raw(one(r'<a href="#services">([^<]*)</a>', page, what="nav services label"))
    # the services section's heading and lead: niche vocabulary
    m = re.search(r'<div class="sec-head reveal">\s*<span class="kicker">([^<]*)</span>\s*'
                  r'<h2>([^<]*)</h2>\s*<p>([^<]*)</p>\s*</div>\s*<div class="svc-grid">', page)
    if not m:
        raise SystemExit(f"FAIL: could not extract the services section head from {slug}")
    rec["services_heading"] = raw(m.group(2))
    rec["services_lead"] = raw(m.group(3))
    rec["phone_display"] = raw(one(r'<span class="vl" dir="ltr">([^<]*)</span>',
                                   page, what="phone display"))
    rec["address"] = raw(one(r'<div class="faddr">([^<]*)</div>', page, what="footer address"))

    # ---- hero + gallery ----
    hero = one(r'<div class="bgimg" style="background-image:url\(\'([^\']*)\'\)"',
               page, what="hero bg")
    rec["hero_url"] = hero
    photos = json.loads(one(r"const PHOTOS = (\[[^\]]*\]);", page, what="PHOTOS"))
    rec["photos"] = photos

    # ---- hero copy ----
    rec["h1"] = raw(one(r"<h1>([^<]*)</h1>", page, what="h1"))
    rec["hero_tag"] = raw(one(r'<p class="tag">([^<]*)</p>', page, what="hero tag"))

    # ---- trust strip ----
    rec["years"] = int(one(r"<b>(\d+)</b><span>\u0633\u0646\u0629 \u062E\u0628\u0631\u0629</span>",
                           page, what="years"))

    # ---- about ----
    # the heading is the whole <h2> text ("عن CARVE COFFEE BAR"), not just the
    # name, so that it can be compared against the niche template "عن {name}"
    rec["about_heading"] = raw("\u0639\u0646 " + one(
        r"<h2>\u0639\u0646 ([^<]*)</h2>", page, what="about heading"))
    rec["about_sub"] = raw(one(r"</h2>\s*<p>([^<]*)</p>", page, re.S, what="about sub"))
    # kept escaped on purpose: build_niches turns this into a {token} template
    rec["about_html"] = one(r'<div class="about-text">(.*?)</div>', page, re.S,
                            what="about paragraphs")

    # ---- hours (display strings, verbatim) ----
    rows = re.findall(r"<tr><td>([^<]+)</td><td>([^<]+)</td></tr>", page)
    rec["hours"] = {day: val for day, val in rows if day != "\u0627\u0644\u064A\u0648\u0645"}

    # ---- bespoke lists ----
    rec["usps"] = [
        {"icon": i, "title": raw(t), "text": raw(x)}
        for i, t, x in re.findall(
            r'<div class="usp"><span class="ico">([^<]*)</span><div><h4>([^<]*)</h4>'
            r'<p>(.*?)</p></div></div>', page, re.S)]
    rec["services"] = [
        {"title": raw(t), "text": raw(x), "tag": raw(g)}
        for t, x, g in re.findall(
            r'<div class="svc"><div class="bd"><h4>([^<]*)</h4><p>(.*?)</p>'
            r'<span class="tag">([^<]*)</span></div></div>', page, re.S)]
    rec["reviews"] = [
        # stars: count the filled ones. len() would read a 1-star review
        # ("★☆☆☆☆") as five and silently rewrite it as ★★★★★.
        {"author": raw(a), "stars": s.count("\u2605"), "text": raw(t)}
        for a, s, t in re.findall(
            r'<div class="who"><h4>([^<]*)</h4><div class="rstars">([\u2605\u2606]*)</div>'
            r'</div></div><p class="rtext">(.*?)</p>', page, re.S)]
    rec["faqs"] = [
        {"q": raw(q), "a": raw(a)}
        for q, a in re.findall(
            r'<details class="faq-item"><summary>(.*?)</summary>'
            r'<div class="ans">(.*?)</div></details>', page, re.S)]

    rec["cta_heading"] = raw(one(r'<h2 class="reveal">([^<]*)</h2>', page, what="cta heading"))
    rec["cta_text"] = raw(one(r'<p class="reveal">([^<]*)</p>', page, what="cta text"))

    # ---- head / SEO strings ----
    rec["page_title"] = raw(one(r"<title>(.*?)</title>", page, re.S, what="<title>"))
    rec["meta_desc"] = raw(one(r'<meta name="description" content="([^"]*)">',
                               page, what="meta description"))
    rec["og_title"] = raw(one(r'<meta property="og:title" content="([^"]*)">',
                              page, what="og:title"))
    rec["og_desc"] = raw(one(r'<meta property="og:description" content="([^"]*)">',
                             page, what="og:description"))
    rec["og_image"] = one(r'<meta property="og:image" content="([^"]*)">',
                          page, what="og:image")

    # ---- pre-filled WhatsApp message (decoded out of the link) ----
    rec["wa_message"] = shapes.wa_message_from(
        one(r'href="(https://wa\.me/[^"]*)"', page, what="wa.me link"))

    # ---- chrome: theme + the two CSS variants (kept per page) ----
    rec["theme_css"] = one(r"(:root\{[^}]*\})", page, re.S, what=":root css")
    rec["hero_css"] = one(r"(\.hero\{position:relative;min-height:92vh;[^}]*\})",
                          page, what=".hero css")
    rec["cta_bg_css"] = one(
        r"(\.cta-section::before\{content:\"\";position:absolute;inset:0;"
        r"background:url\('[^']*'\) center/cover;opacity:\.07\})", page, what="cta bg css")
    return rec


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="src/cities/sa-riyadh")
    ap.add_argument("--out", default="data/extracted.json")
    args = ap.parse_args()

    dest = ROOT / args.dir if not Path(args.dir).is_absolute() else Path(args.dir)
    mpath = ROOT / "data" / "stock_manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}

    pages = sorted(dest.glob("*.html"))
    records = []
    for p in pages:
        rec = extract(p, manifest)
        rec["niche"] = pk.resolve_niche(rec["slug"], rec["hero_url"],
                                        rec["jsonld"]["type"], manifest)
        if not rec["niche"]:
            raise SystemExit(f"FAIL: cannot determine niche for {rec['slug']}")
        records.append(rec)

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(json.dumps(records, ensure_ascii=False, indent=1).encode("utf-8"))

    niches: dict = {}
    for r in records:
        niches.setdefault(r["niche"], []).append(r["slug"])
    print(f"extracted {len(records)} pages -> {out}")
    for n, slugs in sorted(niches.items()):
        print(f"  {n:12s} x{len(slugs)}")


if __name__ == "__main__":
    main()
