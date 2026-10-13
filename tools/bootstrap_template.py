"""Bootstrap templates/page.html from a real page.

The template is DERIVED, never hand-typed: every dynamic block of an existing
page is replaced by a placeholder, and each replacement asserts the number of
occurrences it found. A count that drifts means the page structure moved, and
the bootstrap fails instead of quietly producing a wrong skeleton.

Two classes of placeholder, and the distinction matters:

  {{fragments}}  blocks that are already HTML/JSON/CSS (about_html, usps_html,
                 theme_css, jsonld, photos ...) -- inserted verbatim.
  {{scalars}}    plain data values ({{name}}, {{rating}}, {{address}} ...)
                 -- escaped exactly once by pagekit on the way in.

The page's own scalars are replaced by CONTEXT, never by bare value, because the
same word means different things in different places: the 📍 chip and the area
line carry the DISTRICT while the kicker, the title and the SEO copy carry the
CITY; "4.5" is a rating in five different sentences; "CARVE COFFEE BAR" appears
inside the gallery caption, an alt attribute and a map title.

    python tools/bootstrap_template.py src/cities/sa-riyadh/carve-coffee-bar.html

After editing this, the round-trip test is the only proof it is right:

    python tools/gen_pages.py --check
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "templates" / "page.html"

SRC = ROOT / "src" / "cities" / "sa-riyadh" / "carve-coffee-bar.html"

# The business carved into the skeleton. Used at the end to prove that no
# business-specific value survived into the template.
BUSINESS = {
    "name": "CARVE COFFEE BAR",
    "niche_name": "كوفي شوب",
    "district": "الرياض",
    "city_ar": "الرياض",
    "address": "Al Urubah Rd, تقاطع، Riyadh 12251, Saudi Arabia",
    "phone": "+966 50 574 5780",
    "rating": "4.5",
    "reviews": "1,753",
}


def derive(raw: str, counts: dict):
    def sub(pattern, repl, count, what, flags=0):
        nonlocal raw
        new, n = re.subn(pattern, repl, raw, flags=flags)
        if n != count:
            raise SystemExit(
                f"FAIL: expected {count} occurrence(s) of {what}, found {n}. "
                "The page structure drifted from what the template expects.")
        raw = new

    def lit(value, placeholder, count, what):
        nonlocal raw
        n = raw.count(value)
        if n != count:
            raise SystemExit(
                f"FAIL: {what}: expected {count} occurrence(s), found {n}.")
        counts[placeholder] = n
        raw = raw.replace(value, placeholder)

    # ---------------------------------------------------------------- blocks
    sub(r":root\{[^}]*\}", "{{theme_css}}", 1, ":root css")
    sub(r"\.hero\{position:relative;min-height:92vh;[^}]*\}",
        "{{hero_css}}", 1, ".hero css line")
    sub(r"\.cta-section::before\{content:\"\";position:absolute;inset:0;"
        r"background:url\('[^']*'\) center/cover;opacity:\.07\}",
        "{{cta_bg_css}}", 1, ".cta-section::before css line")
    # the <script> wrapper stays in the skeleton: {{jsonld}} is the JSON body
    sub(r'<script type="application/ld\+json">\s*.*?</script>',
        '<script type="application/ld+json">\n{{jsonld}}\n</script>',
        1, "JSON-LD", flags=re.S)
    # analytics slot. The snippet itself is data (templates/tracking.json), and
    # pagekit renders it right here -- the position inject_tracking.py used to
    # write by hand. Bootstrapping without this line would silently drop the
    # slot and, with tracking on, every regenerated page would lose the script
    # (caught by gen_pages.py --check, but only as a confusing 30-page diff).
    sub(r'\n</head>', '\n{{tracking}}</head>', 1, "tracking slot")
    # the <table> wrapper stays in the skeleton: {{hours_table}} is the rows
    sub(r'<table class="hours-table">.*?</table>',
        '<table class="hours-table">{{hours_table}}</table>', 1, "hours table",
        flags=re.S)
    # the JS declaration stays in the skeleton: {{photos}} is the array literal
    sub(r"const PHOTOS = \[[^\]]*\];",
        "const PHOTOS = {{photos}};", 1, "PHOTOS array")
    # bespoke about paragraphs (no nested <div> inside, non-greedy is safe)
    sub(r'<div class="about-text">.*?</div>',
        '<div class="about-text">{{about_html}}</div>', 1, "about-text", flags=re.S)

    # repeated item lists. These are data (a list of USPs / services / reviews /
    # FAQs), so the whole block becomes one placeholder and pagekit rebuilds it
    # from the record -- or from the niche profile when the record says nothing.
    # The USP list is anchored on THREE closing divs: every USP ends with two,
    # so only the wrapper's own close is unambiguous.
    sub(r'<div class="usp-list">.*?</div></div></div>',
        '<div class="usp-list">{{usps_html}}</div>', 1, "usp-list", flags=re.S)
    sub(r'<div class="svc-grid">.*?</div></div>\n  </div>',
        '<div class="svc-grid">{{services_html}}</div>\n  </div>',
        1, "svc-grid", flags=re.S)
    sub(r'<div class="faq-list reveal">.*?</div>\n  </div>',
        '<div class="faq-list reveal">{{faqs_html}}</div>\n  </div>',
        1, "faq-list", flags=re.S)
    sub(r'<div class="review-grid">.*?</div>\n    <div class="gsrc">',
        '<div class="review-grid">{{reviews_html}}</div>\n    <div class="gsrc">',
        1, "review-grid", flags=re.S)

    # ---------------------------------------------------- head / SEO strings
    # Captured as their own slots: each one is a niche-level template with
    # {tokens}, so a new business gets correct SEO copy for free.
    sub(r"<title>.*?</title>", "<title>{{page_title}}</title>", 1, "<title>", flags=re.S)
    sub(r'<meta name="description" content="[^"]*">',
        '<meta name="description" content="{{meta_desc}}">', 1, "meta description")
    sub(r'<meta property="og:title" content="[^"]*">',
        '<meta property="og:title" content="{{og_title}}">', 1, "og:title")
    sub(r'<meta property="og:description" content="[^"]*">',
        '<meta property="og:description" content="{{og_desc}}">', 1, "og:description")
    sub(r'<meta property="og:image" content="[^"]*">',
        '<meta property="og:image" content="{{og_image}}">', 1, "og:image")

    # ---------------------------------------------------------- contact links
    # wa.me embeds the phone and the URL-encoded message; tel: embeds the phone.
    # These go BEFORE the scalars that live inside them.
    sub(r"https://wa\.me/\d+\?text=[^\"]*", "{{wa_url}}", 4, "wa.me links")
    sub(r"tel:\+?\d+", "{{tel_url}}", 4, "tel: links")

    # ------------------------------------------------------ location strings
    # The chip and the area line show the DISTRICT; the kicker shows the CITY.
    sub(r'\U0001F4CD \u0627\u0644\u0631\u064A\u0627\u0636</span>',
        '\U0001F4CD {{district}}</span>', 1, "district chip")
    sub(r'<span class="vl">\u0627\u0644\u0631\u064A\u0627\u0636, \u0627\u0644\u0631\u064A\u0627\u0636</span>',
        '<span class="vl">{{district}}, {{city_ar}}</span>', 1, "area line")
    # the "reach us" line under the map: district, then city
    sub(r'<p>\u0627\u0644\u0631\u064A\u0627\u0636 \u2014 \u0627\u0644\u0631\u064A\u0627\u0636</p>',
        '<p>{{district}} \u2014 {{city_ar}}</p>', 1, "reach-us line")
    sub(r'<span class="kicker">\u0643\u0648\u0641\u064A \u0634\u0648\u0628 \u00B7 '
        r'\u0627\u0644\u0631\u064A\u0627\u0636</span>',
        '<span class="kicker">{{niche_name}} \u00B7 {{city_ar}}</span>', 1, "about kicker")
    # the niche label, in the three places that are plain markup
    sub(r'\U0001F3F7\uFE0F? \u0643\u0648\u0641\u064A \u0634\u0648\u0628</span>',
        '\U0001F3F7\uFE0F {{niche_name}}</span>', 1, "niche chip")
    sub(r'<span class="kicker">\u0643\u0648\u0641\u064A \u0634\u0648\u0628</span>',
        '<span class="kicker">{{niche_name}}</span>', 1, "services kicker")
    # the services section's heading and lead are niche vocabulary
    sub(r'<h2>[^<]*</h2>\n      <p>[^<]*</p>\n    </div>\n    <div class="svc-grid">',
        '<h2>{{services_heading}}</h2>\n      <p>{{services_lead}}</p>\n    </div>\n'
        '    <div class="svc-grid">', 1, "services heading + lead")
    sub(r'<span class="lb">\u0627\u0644\u062A\u0635\u0646\u064A\u0641</span>'
        r'<span class="vl">\u0643\u0648\u0641\u064A \u0634\u0648\u0628</span>',
        '<span class="lb">\u0627\u0644\u062A\u0635\u0646\u064A\u0641</span>'
        '<span class="vl">{{niche_name}}</span>', 1, "category loc-line")

    # ------------------------------------------------- the business's own name
    # Every occurrence sits inside HTML (text or attribute), so it is the
    # escaped form the renderer inserts as {{name}}.
    lit('<span class="mark">\u2615</span><span>CARVE COFFEE BAR</span>',
        '<span class="mark">{{mark}}</span><span>{{name}}</span>', 1, "nav logo")
    # the services entry in the nav is niche vocabulary, promoted to the profile
    sub(r'<a href="#services">[^<]*</a>',
        '<a href="#services">{{nav_services}}</a>', 1, "nav services label")
    sub(r'<p>\u0635\u0648\u0631 \u062D\u0642\u064A\u0642\u064A\u0629 \u0645\u0646 '
        r'\u062F\u0627\u062E\u0644 CARVE COFFEE BAR \u2014 \u0645\u0646\u0642\u0648\u0644\u0629 '
        r'\u0645\u0646 \u062D\u0633\u0627\u0628 \u0627\u0644\u0645\u0643\u0627\u0646 \u0639\u0644\u0649 '
        r'Google Maps</p>',
        '<p>\u0635\u0648\u0631 \u062D\u0642\u064A\u0642\u064A\u0629 \u0645\u0646 \u062F\u0627\u062E\u0644 '
        '{{name}} \u2014 \u0645\u0646\u0642\u0648\u0644\u0629 \u0645\u0646 \u062D\u0633\u0627\u0628 '
        '\u0627\u0644\u0645\u0643\u0627\u0646 \u0639\u0644\u0649 Google Maps</p>', 1, "gallery caption")
    sub(r'alt="CARVE COFFEE BAR"', 'alt="{{name}}"', 1, "gallery img alt")
    sub(r'<iframe class="map reveal" loading="lazy" src="[^"]*" '
        r'title="\u0645\u0648\u0642\u0639 CARVE COFFEE BAR '
        r'\u0639\u0644\u0649 \u0627\u0644\u062E\u0631\u064A\u0637\u0629"></iframe>',
        '<iframe class="map reveal" loading="lazy" src="{{map_url}}" '
        'title="\u0645\u0648\u0642\u0639 {{name}} '
        '\u0639\u0644\u0649 \u0627\u0644\u062E\u0631\u064A\u0637\u0629"></iframe>', 1, "map iframe")
    lit('<div class="fname">CARVE COFFEE BAR</div>',
        '<div class="fname">{{name}}</div>', 1, "footer name")

    # --------------------------------------------------------- bespoke phrases
    # ORDER MATTERS: these contain the shared scalars (h1 contains the city,
    # hero_tag contains the label, the rating and the review count), so they go
    # before any bare value could be mistaken for them.
    lit('\u0639\u0646 CARVE COFFEE BAR', '{{about_heading}}', 1, "about heading")
    lit('\u0643\u0644\u0645 CARVE COFFEE BAR \u0639\u0644\u0649 \u0627\u0644\u0648\u0627\u062A\u0633\u0627\u0628 '
        '\u0623\u0648 \u0627\u0644\u0627\u062A\u0635\u0627\u0644 \u2014 '
        '\u0648\u0647\u064A\u0631\u062F\u0651\u0648\u0627 \u0639\u0644\u064A\u0643 \u0645\u0628\u0627\u0634\u0631\u0629.',
        '{{cta_text}}', 1, "cta text")
    lit('\u0642\u0647\u0648\u0629 \u0645\u062E\u062A\u0635\u0629 \u0641\u064A \u0642\u0644\u0628 '
        '\u0627\u0644\u0631\u064A\u0627\u0636', '{{h1}}', 1, "h1")
    lit('\u0641\u064A \u0627\u0644\u0631\u064A\u0627\u0636 \u0628\u0627\u0644\u0631\u064A\u0627\u0636 \u2014 '
        '\u0643\u0648\u0641\u064A \u0634\u0648\u0628 \u0628\u062A\u0642\u064A\u064A\u0645 4.5\u2605 \u0645\u0646 '
        '1,753 \u062A\u0642\u064A\u064A\u0645 \u062D\u0642\u064A\u0642\u064A \u0639\u0644\u0649 Google.',
        '{{hero_tag}}', 1, "hero tag")
    lit('\u0643\u0648\u0641\u064A \u0634\u0648\u0628 \u0641\u064A \u0627\u0644\u0631\u064A\u0627\u0636 \u2014 '
        '\u0648\u0627\u0644\u0631\u0642\u0645 \u0628\u064A\u062A\u0643\u0644\u0645 \u0639\u0646 \u0646\u0641\u0633\u0647',
        '{{about_sub}}', 1, "about sub")
    lit('\u0639\u0627\u064A\u0632 \u062A\u062C\u0631\u0651\u0628 \u0642\u0647\u0648\u062A\u0646\u0627\u061F '
        '\u062A\u0639\u0627\u0644\u0627\u0644\u0646\u0627', '{{cta_heading}}', 1, "cta heading")

    # ------------------------------------------------------- numbers, by shape
    # The rating and the review count each appear in five different sentences.
    # Replacing the bare digits would eat them in the wrong order, so each one
    # is replaced inside its own markup.
    sub(r'<span>4\.5 \u00B7 1,753 \u062A\u0642\u064A\u064A\u0645</span>',
        '<span>{{rating}} \u00B7 {{reviews_fmt}} \u062A\u0642\u064A\u064A\u0645</span>',
        1, "hero rating")
    sub(r'<span class="stars">\u2605\u2605\u2605\u2605\u2605</span>',
        '<span class="stars">{{hero_stars}}</span>', 1, "hero stars")
    sub(r'<div class="stars">\u2605\u2605\u2605\u2605\u2606</div>',
        '<div class="stars">{{banner_stars}}</div>', 1, "banner stars")
    sub(r'<span class="big">4\.5</span>', '<span class="big">{{rating}}</span>',
        1, "rating banner")
    sub(r'<div class="cnt">1,753 \u062A\u0642\u064A\u064A\u0645 \u0639\u0644\u0649 Google Maps</div>',
        '<div class="cnt">{{reviews_fmt}} \u062A\u0642\u064A\u064A\u0645 \u0639\u0644\u0649 Google Maps</div>',
        1, "rating banner count")
    sub(r'<b>4\.5</b><span>\u062A\u0642\u064A\u064A\u0645 Google</span>',
        '<b>{{rating}}</b><span>\u062A\u0642\u064A\u064A\u0645 Google</span>',
        1, "trust: rating")
    sub(r'<b>1,753</b><span>\u0639\u0645\u064A\u0644 \u0642\u064A\u0651\u0645 '
        r'\u0627\u0644\u062A\u062C\u0631\u0628\u0629</span>',
        '<b>{{reviews_fmt}}</b><span>\u0639\u0645\u064A\u0644 \u0642\u064A\u0651\u0645 '
        '\u0627\u0644\u062A\u062C\u0631\u0628\u0629</span>', 1, "trust: reviews")
    # "years" is a bare digit that also occurs in ratings, phones and CSS, so
    # anchor it on its trust-strip markup instead of replacing the digit.
    # (a lambda, because a replacement string may not contain \u escapes)
    sub(r"<b>(\d+)</b><span>\u0633\u0646\u0629 \u062E\u0628\u0631\u0629</span>",
        lambda m: "<b>{{years}}</b><span>\u0633\u0646\u0629 \u062E\u0628\u0631\u0629</span>",
        1, "years cell")
    # the open-days cell is derived from the hours dict, not stored
    sub(r"<b>7</b><span>\u0623\u064A\u0627\u0645 \u0641\u064A \u0627\u0644\u0623\u0633\u0628\u0648\u0639</span>",
        lambda m: "<b>{{days_open}}</b><span>\u0623\u064A\u0627\u0645 \u0641\u064A \u0627\u0644\u0623\u0633\u0628\u0648\u0639</span>",
        1, "open days cell")
    sub(r'<p>4\.5 \u0645\u0646 5 \u00B7 1,753 \u062A\u0642\u064A\u064A\u0645</p>',
        '<p>{{rating}} \u0645\u0646 5 \u00B7 {{reviews_fmt}} \u062A\u0642\u064A\u064A\u0645</p>',
        1, "info-row rating")
    sub(r'<span class="vl">4\.5 \u2605 \(1,753 \u062A\u0642\u064A\u064A\u0645\)</span>',
        '<span class="vl">{{rating}} \u2605 ({{reviews_fmt}} \u062A\u0642\u064A\u064A\u0645)</span>',
        1, "rating loc-line")

    # ------------------------------------------------------------ address/phone
    sub(r'<p class="small">Al Urubah Rd, \u062A\u0642\u0627\u0637\u0639\u060C '
        r'Riyadh 12251, Saudi Arabia</p>',
        '<p class="small">{{address}}</p>', 1, "info-row address")
    sub(r'<span class="vl">Al Urubah Rd, \u062A\u0642\u0627\u0637\u0639\u060C '
        r'Riyadh 12251, Saudi Arabia</span>',
        '<span class="vl">{{address}}</span>', 1, "address loc-line")
    lit('<div class="faddr">Al Urubah Rd, \u062A\u0642\u0627\u0637\u0639\u060C '
        'Riyadh 12251, Saudi Arabia</div>',
        '<div class="faddr">{{address}}</div>', 1, "footer address")
    sub(r'<p dir="ltr">\+966 50 574 5780</p>', '<p dir="ltr">{{phone_display}}</p>',
        1, "info-row phone")
    sub(r'<span class="vl" dir="ltr">\+966 50 574 5780</span>',
        '<span class="vl" dir="ltr">{{phone_display}}</span>', 1, "phone loc-line")
    lit('<div class="faddr" dir="ltr">+966 50 574 5780</div>',
        '<div class="faddr" dir="ltr">{{phone_display}}</div>', 1, "footer phone")

    # ------------------------------------------------------------- hero image
    # .bgimg and the gallery <img> both carry the full niche hero URL; og:image
    # was already lifted out above and is served from the niche template.
    sub(r"https://pages\.aidy\.site/hero/coffee\.jpg", "{{hero_url}}", 2, "hero url")

    # ------------------------------------------------------- self-check
    # Nothing business-specific may survive into the skeleton: if it did, the
    # template would carry carve's data and a new business would inherit it.
    survivors = []
    for value in BUSINESS.values():
        for m in re.finditer(re.escape(value), raw):
            survivors.append(f"{value!r} in ...{raw[max(0, m.start()-40):m.end()+40]}...")
    if survivors:
        raise SystemExit(
            "FAIL: business values still present in the skeleton:\n  "
            + "\n  ".join(survivors[:10]))
    return raw


def main():
    src_path = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC
    raw = src_path.read_text(encoding="utf-8")
    counts: dict = {}
    skeleton = derive(raw, counts)

    tokens = sorted(set(re.findall(r"\{\{[a-z_]+\}\}", skeleton)))
    uses = len(re.findall(r"\{\{[a-z_]+\}\}", skeleton))
    print(f"placeholders: {uses} uses, {len(tokens)} distinct")
    for t in tokens:
        print(f"   {t}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # write_bytes: the pages are committed LF, and the round-trip test compares
    # exact bytes -- a CRLF skeleton would turn every generated page into a
    # whole-file diff (invisible to read_text, visible to git).
    OUT.write_bytes(skeleton.encode("utf-8"))
    print(f"\nwrote {OUT} ({len(skeleton)} bytes) from {src_path.name}")


if __name__ == "__main__":
    main()
