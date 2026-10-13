"""pagekit -- one place that knows how a landing page is built.

Everything here is derived from the real pages in src/cities/, and every block
builder is verified by a round-trip test (tools/gen_pages.py --check rebuilds
the current pages and must match byte for byte). If a format drifts, that test
is what catches it -- not a 404 in production.

Layering (a page is data, never hand-written HTML):
    templates/page.html          skeleton: static design + {{placeholders}}
    templates/niches/<n>.json    per-niche defaults: theme, services, copy, hero
    data/businesses.json         per-business data + copy overrides

ESCAPING CONTRACT
    Data files store RAW text (no HTML entities). Every value that lands in the
    HTML body is escaped exactly once, here, with html.escape(v, quote=True) --
    which is precisely the convention the existing pages use (verified over
    1650 text values: "'" -> &#x27;, '"' -> &quot;, "&" -> &amp;).
    Blocks that are already HTML (about_html, the *_html builders) are built
    FROM escaped scalars, so they are inserted verbatim.
    JSON-LD and the wa.me/map URLs need the raw and the URL-encoded forms, so
    they are built from the raw values, never from the escaped ones.
"""
import html
import json
import math
import re
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import shapes

TEMPLATE = ROOT / "templates" / "page.html"
NICHE_DIR = ROOT / "templates" / "niches"

BASE_URL = "https://pages.aidy.site"

# JSON-LD @type -> niche directory name.
TYPE_TO_NICHE = {
    "CafeOrCoffeeShop": "coffee",
    "HairSalon": "barbershop",
    "BeautySalon": "beauty_salon",
    "NailSalon": "nail_salon",
    "ExerciseGym": "gym",
    "AutoRepair": "auto_repair",
}

# hero file stem -> niche. Stems absent from this map are business slugs
# (e.g. unsorso-cafe.jpg) that keep their own photo instead of niche stock.
NICHE_BY_HERO = {
    "coffee": "coffee",
    "barbershop": "barbershop",
    "beauty_salon": "beauty_salon",
    "nail_salon": "nail_salon",
    "gym": "gym",
    "auto_repair": "auto_repair",
}


def esc(value) -> str:
    """Escape a raw data value for an HTML text node or double-quoted attribute."""
    return html.escape(str(value), quote=True)


def resolve_niche(slug, hero_url, jsonld_type, manifest):
    """Which niche a page belongs to. Hero filename comes first because it is
    the one signal present on every page, including pages whose JSON-LD @type
    is unexpected (e.g. SportsActivityLocation on a gym page)."""
    stem = hero_url.rsplit("/", 1)[-1]
    if stem.endswith(".jpg"):
        stem = stem[:-4]
    if stem in NICHE_BY_HERO:
        return NICHE_BY_HERO[stem]
    if jsonld_type in TYPE_TO_NICHE:
        return TYPE_TO_NICHE[jsonld_type]
    return (manifest.get(slug) or {}).get("niche")

# Arabic weekday order used by the visible hours table.
AR_DAYS = ["السبت", "الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة"]
EN_DAYS = {"السبت": "Saturday", "الأحد": "Sunday", "الاثنين": "Monday",
           "الثلاثاء": "Tuesday", "الأربعاء": "Wednesday",
           "الخميس": "Thursday", "الجمعة": "Friday"}
# JSON-LD lists days Monday..Sunday.
LD_DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]


# ---------------------------------------------------------------- hours parse

def _to_24(tok: str, hint: str | None = None) -> str:
    """'6 AM'->'06:00', '12 PM'->'12:00', '11:30 PM'->'23:30'.
    A bare hour ('12' in '12-10 PM') inherits the meridiem from `hint`."""
    tok = tok.strip()
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*([AP]M)?$", tok)
    if not m:
        raise ValueError(f"unparsable time token: {tok!r}")
    h, minute, mer = int(m.group(1)), m.group(2) or "00", m.group(3)
    if mer is None:
        mer = hint
        if mer is None:
            raise ValueError(f"meridiem missing and no hint for {tok!r}")
    if mer == "AM":
        hh = 0 if h == 12 else h
    else:
        hh = 12 if h == 12 else h + 12
    return f"{hh:02d}:{minute}"


def parse_hours(text: str):
    """Split-hours display string -> [(start, end)] in 24h form.

    '6 AM-12 AM'            -> [('06:00','00:00')]
    '8 AM-12 PM , 4-9 PM'   -> [('08:00','12:00'), ('16:00','21:00')]
    'Open 24 hours'         -> [('00:00','23:59')]
    'Closed'                -> []   (a day with no entry in JSON-LD)
    The en dash used by Google is U+2013.
    """
    text = text.strip()
    if text.lower() == "closed":
        return []
    if text.lower() == "open 24 hours":
        return [("00:00", "23:59")]
    ranges = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "–" not in part:            # en dash
            raise ValueError(f"no range in {part!r}")
        a, b = [x.strip() for x in part.split("–", 1)]
        mer_b = re.search(r"([AP]M)", b)
        start = _to_24(a, mer_b.group(1) if mer_b else None)
        end = _to_24(b)
        ranges.append((start, end))
    return ranges


def hours_table_html(hours: dict) -> str:
    """Visible Arabic hours table, exactly as the pages write it."""
    head = '<tr><td>اليوم</td><td>الوقت</td></tr>'
    # the day names are ours; the values are data, so they get escaped
    rows = [f'<tr><td>{esc(d)}</td><td>{esc(hours[d])}</td></tr>'
            for d in AR_DAYS if d in hours]
    return head + "".join(rows)


def hours_ld(hours: dict):
    """JSON-LD OpeningHoursSpecification entries, Monday..Sunday."""
    out = []
    for d in LD_DAYS:
        if d not in hours:
            continue
        for opens, closes in parse_hours(hours[d]):
            out.append({"@type": "OpeningHoursSpecification",
                        "dayOfWeek": EN_DAYS[d],
                        "opens": opens, "closes": closes})
    return out


# ---------------------------------------------------------------- item blocks
# Formats copied verbatim from the pages; the round-trip test is the guarantee.
# Every field is escaped here -- that is the single place raw text becomes HTML.

def usp_html(items) -> str:
    # the pages put every USP on its own line
    return "\n".join(
        f'<div class="usp"><span class="ico">{esc(u["icon"])}</span><div>'
        f'<h4>{esc(u["title"])}</h4><p>{esc(u["text"])}</p></div></div>'
        for u in items)


def svc_html(items) -> str:
    # the pages put every service on its own line
    return "\n".join(
        f'<div class="svc"><div class="bd"><h4>{esc(s["title"])}</h4>'
        f'<p>{esc(s["text"])}</p><span class="tag">{esc(s["tag"])}</span></div></div>'
        for s in items)


def review_html(items) -> str:
    out = []
    for r in items:
        # the avatar is the author's initial, UPPER-cased ("nora" -> "N")
        initial = (str(r["author"]).strip()[:1] or "?").upper()
        # the page writes five glyphs: n filled, the rest empty (a 1-star
        # review is "★☆☆☆☆", never "★")
        n = int(r["stars"])
        out.append(
            f'<div class="review"><div class="q">”</div><div class="rhead">'
            f'<div class="avatar">{esc(initial)}</div><div class="who">'
            f'<h4>{esc(r["author"])}</h4>'
            f'<div class="rstars">{"★" * n}{"☆" * (5 - n)}</div>'
            f'</div></div><p class="rtext">{esc(r["text"])}</p></div>')
    return "\n".join(out)


def faq_html(items) -> str:
    return "\n".join(
        f'<details class="faq-item"><summary>{esc(f["q"])}</summary>'
        f'<div class="ans">{esc(f["a"])}</div></details>'
        for f in items)


def banner_stars(rating) -> str:
    """Round-half-down, matching the pages: 4.5->4, 4.6->5. Always five glyphs,
    the remainder empty."""
    full = int(rating)
    n = full + (1 if (rating - full) > 0.5 else 0)
    return "★" * n + "☆" * (5 - n)


def hero_stars(rating) -> str:
    """Hero stars. Every existing page shows 5 of 5 (all ratings are >= 4.2),
    so the only rule consistent with the data that also degrades sanely for a
    lower-rated business is ceil. If a 3.8 business ever lands here it will
    show 4 stars instead of a misleading 5. Always five glyphs."""
    return "★" * min(5, math.ceil(rating)) + "☆" * max(0, 5 - math.ceil(rating))


# ---------------------------------------------------------------- JSON-LD

def jsonld(rec: dict, niche: dict) -> str:
    j = rec.get("jsonld", {})
    addr = j.get("address", {})
    doc = {
        "@context": "https://schema.org",
        "@type": j.get("type") or niche.get("jsonld_type", "LocalBusiness"),
        "name": rec["name"],
        "image": rec.get("hero_url") or f"{BASE_URL}{niche['hero']}",
        "url": rec["url"],
        "telephone": rec.get("phone_intl", ""),
        "address": dict({"@type": "PostalAddress"}, **addr),
    }
    if "rating" in rec:
        doc["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": rec["rating"],
            "reviewCount": rec["review_count"],
        }
    if j.get("sameAs"):
        doc["sameAs"] = j["sameAs"]
    if rec.get("hours"):
        doc["openingHoursSpecification"] = hours_ld(rec["hours"])
    # rebuild the JSON with the exact indentation the pages use
    return "\n".join(json.dumps(doc, ensure_ascii=False, indent=2).splitlines())


# ---------------------------------------------------------------- render

def load_niche(name: str) -> dict:
    path = NICHE_DIR / f"{name}.json"
    if not path.exists():
        known = sorted(p.stem for p in NICHE_DIR.glob("*.json"))
        raise SystemExit(
            f"unknown niche {name!r}. Available: {', '.join(known)}\n"
            f"Add templates/niches/{name}.json to create a new one.")
    return json.loads(path.read_text(encoding="utf-8"))


# {token} slots that may appear in niche defaults and record overrides.
# Every one of them is an HTML context, so the substituted value is escaped.
TOKENS = ("{name}", "{niche_name}", "{city_ar}", "{district}", "{rating}",
          "{reviews_fmt}", "{address}", "{area}", "{phone_display}",
          "{hero_url}", "{h1}", "{hero_tag}", "{about_sub}")

# The only fields whose values may carry {tokens}. Restricting the fill to this
# list matters: `hours` and `photos` are opaque data that must not be touched
# (hours are escaped later by hours_table_html, photos are a JSON blob).
TOKEN_FILLED = ("about_html", "about_heading", "about_sub", "h1", "hero_tag",
                "cta_heading", "cta_text", "page_title", "meta_desc",
                "og_title", "og_desc", "og_image", "wa_message",
                "usps", "services", "faqs", "photos")

# Fields whose plain (token-free) strings must be inserted as-is: their builders
# escape every field, or their values are not HTML at all (photo URLs).
NO_PLAIN_ESCAPE = ("usps", "services", "faqs", "photos")


def _fill_tokens(value, mapping, raw=False, escape_plain=True):
    """Resolve {name}--style tokens in strings, lists and dicts.

    A string that carries no token is a plain scalar, so it is escaped here and
    now -- that is the single place raw text becomes HTML. A string that does
    carry tokens is a template: its literals are trusted (they come from the
    niche profile) and shapes.fill escapes only the substituted values.

    escape_plain=False is for the list fields (usps, services, faqs): their item
    builders already escape every field, so a second pass would double it.
    """
    if isinstance(value, str):
        if raw:
            return shapes.fill_raw(value, mapping)
        if "{" in value:
            return shapes.fill(value, mapping)
        return esc(value) if escape_plain else value
    if isinstance(value, list):
        return [_fill_tokens(v, mapping, raw, escape_plain) for v in value]
    if isinstance(value, dict):
        return {k: _fill_tokens(v, mapping, raw, escape_plain)
                for k, v in value.items()}
    return value


def phone_display(phone_intl: str) -> str:
    """'+966 50 574 5780' from '966505745780'. Anything that is not a Saudi
    12-digit number falls back to '+digits' rather than guessing."""
    digits = re.sub(r"\D", "", phone_intl or "")
    if len(digits) == 12 and digits.startswith("966"):
        rest = digits[3:]
        if len(rest) == 9:
            return f"+966 {rest[0:2]} {rest[2:5]} {rest[5:9]}"
    return "+" + digits if digits else ""


def rating_str(rating) -> str:
    """4.5 -> '4.5', 4.0 -> '4' (JSON-LD may carry either)."""
    if rating is None:
        return ""
    if isinstance(rating, float) and rating == int(rating):
        return str(int(rating))
    return str(rating)


TRACKING_CFG = ROOT / "templates" / "tracking.json"
TRACKING_START = '<!-- TRACKING-START (generated by tools/inject_tracking.py) -->'
TRACKING_END = '<!-- TRACKING-END -->'


def tracking_block() -> str:
    """The analytics snippet, or '' when tracking is off.

    Reads templates/tracking.json. When active the returned block is byte for
    byte what inject_tracking.py used to write into the pages by hand
    (START / tag / END / newline, immediately before </head>), so a page
    regenerated by the template is identical to an injected one -- and turning
    tracking off never leaves a stale script behind.
    """
    if not TRACKING_CFG.exists():
        return ""
    try:
        cfg = json.loads(TRACKING_CFG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not (cfg.get("enabled") and cfg.get("src") and cfg.get("website_id")):
        return ""
    provider = cfg.get("provider", "umami")
    if provider != "umami":
        raise SystemExit(
            f"unknown tracking provider: {provider!r} "
            f"(only 'umami' is supported)")
    tag = ('<script defer src="%(src)s" '
           'data-website-id="%(website_id)s"></script>') % cfg
    return f"{TRACKING_START}\n{tag}\n{TRACKING_END}\n"


def render(rec: dict, niche: dict, skeleton: str | None = None) -> str:
    """Merge niche defaults with the business record and fill the skeleton."""
    skeleton = TEMPLATE.read_text(encoding="utf-8") if skeleton is None else skeleton
    # start from the niche profile, then let the business record override
    vals: dict = {k: v for k, v in niche.items() if k != "name"}
    vals.update(rec)

    # ---- scalar values, raw (JSON-LD, URLs, and the token map below) ----
    name = str(vals.get("name", ""))
    city = str(vals.get("city_ar", ""))
    district = str(vals.get("district", ""))
    label = str(vals.get("niche_name", ""))
    rating = vals.get("rating")
    review_count = vals.get("review_count")
    reviews_fmt = (f"{review_count:,}" if review_count is not None else "")
    hero_url = vals.get("hero_url") or f"{BASE_URL}{niche['hero']}"

    # {token} slots -> raw values. shapes.fill escapes on the way into HTML;
    # wa_message is the one exception: it goes into a URL query, so it is filled
    # with fill_raw first and then holds no tokens left for the escaped pass.
    raw_map = {"name": name, "city_ar": city, "district": district,
               "niche_name": label, "rating": rating_str(rating),
               "reviews_fmt": reviews_fmt, "address": str(vals.get("address", "")),
               "area": f"{district}, {city}", "phone_display": str(vals.get("phone_display", "")),
               "hero_url": hero_url, "h1": str(vals.get("h1", "")),
               "hero_tag": str(vals.get("hero_tag", "")),
               "about_sub": str(vals.get("about_sub", ""))}

    if "wa_message" in vals:
        vals["wa_message"] = _fill_tokens(vals["wa_message"], raw_map, raw=True)
    for key in TOKEN_FILLED:
        # wa_message was already filled raw above; escaping it would corrupt
        # the URL query ("&amp;" instead of "&")
        # the list fields are escaped by their own builders, not here
        if key != "wa_message" and key in vals:
            vals[key] = _fill_tokens(vals[key], raw_map,
                                     escape_plain=key not in NO_PLAIN_ESCAPE)

    # when the district is unknown it equals the city ("الرياض") — collapse
    # "كوفي شوب في الرياض، الرياض" to "كوفي شوب في الرياض"
    if district and city and district == city:
        dup = "في %s، %s" % (esc(district), esc(city))
        for key in ("page_title", "og_title", "meta_desc", "og_desc", "hero_tag"):
            if isinstance(vals.get(key), str):
                vals[key] = vals[key].replace(dup, "في %s" % esc(city))

    # ---- derived values the skeleton expects ----
    # the JSON-LD body is always rebuilt from the record's own values: the
    # record's "jsonld" key is INPUT data (type / sameAs / address parts), not
    # the rendered block.
    vals["jsonld"] = jsonld(rec, niche)
    vals["hero_url"] = hero_url
    # canonical: the stable public URL of this page (one host only, so the
    # same bytes served under pages.* and <city>.* don't look duplicated)
    vals["canonical_url"] = rec.get("url", "")
    vals["rating"] = rating_str(rating)
    vals["reviews_fmt"] = reviews_fmt
    vals.setdefault("phone_display", phone_display(vals.get("phone_intl", "")))
    # how many days the business says it is open: derived from the hours dict,
    # so a business that lists 3 days shows 3 instead of a hard-coded 7
    vals["days_open"] = len(vals.get("hours") or {})
    # an empty nav mark must fall back to the niche emoji, not render blank
    if not vals.get("mark"):
        vals["mark"] = niche.get("mark", "")
    # default gallery: the niche hero plus the niche stock photos. A business
    # that has its own photos overrides this in its record -- that is the only
    # thing standing between a new business and a working page.
    vals.setdefault("photos", [
        {"url": hero_url, "alt": ""},
    ] + [{"url": f"{BASE_URL}/stock/{niche['gallery_prefix']}-{i}.jpg", "alt": ""}
         for i in (0, 1, 2)])
    vals.setdefault("hours_table", hours_table_html(vals.get("hours", {})))
    vals.setdefault("tel_url", f"tel:{dial(vals)}")
    vals.setdefault("wa_url", wa_url(vals, niche))
    vals.setdefault("map_url", map_url(vals))
    vals.setdefault("hero_stars", hero_stars(rating if rating is not None else 0))
    vals.setdefault("banner_stars", banner_stars(rating if rating is not None else 0))
    # the list builders read the MERGED, token-filled values so a niche default
    # and a record override behave identically
    vals.setdefault("usps_html", usp_html(vals.get("usps") or niche.get("usps", [])))
    vals.setdefault("services_html", svc_html(vals.get("services") or niche.get("services", [])))
    vals.setdefault("faqs_html", faq_html(vals.get("faqs") or niche.get("faqs", [])))
    vals.setdefault("reviews_html", review_html(vals.get("reviews", [])))
    # analytics snippet comes from templates/tracking.json, NOT from a hand
    # injection into the files: regenerating used to strip it silently
    vals["tracking"] = tracking_block()

    out = skeleton
    for key, value in vals.items():
        token = "{{" + key + "}}"
        if token in out:
            out = out.replace(token, _stringify(key, value))
    # fail loud rather than shipping a page with a visible placeholder
    left = sorted(set(re.findall(r"\{\{[a-z_]+\}\}", out)))
    if left:
        raise SystemExit(f"unfilled placeholders in {rec.get('name')!r}: {left}")
    return out


# Values that are already finished HTML / JSON / CSS / URLs, or that were
# token-filled above (so their literals are trusted and their substituted
# values are already escaped). Everything else that reaches the skeleton is raw
# data and gets html.escape(v, quote=True) exactly once, in _stringify.
FINAL_KEYS = frozenset({
    "theme_css", "hero_css", "cta_bg_css",          # CSS
    "jsonld", "photos",                             # JSON (script blocks)
    "about_html", "usps_html", "services_html",     # HTML fragments built
    "faqs_html", "reviews_html", "hours_table",     # from escaped scalars
    "hero_url", "map_url", "wa_url", "tel_url",     # URLs
    "canonical_url",                                # canonical link + og:url
    "hero_stars", "banner_stars",                   # star glyphs
    "tracking",                                     # analytics snippet (raw HTML)
}) | set(TOKEN_FILLED)                              # already escaped by the fill


def _stringify(key: str, v) -> str:
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, str) and key not in FINAL_KEYS:
        return esc(v)
    return str(v)


def wa_url(rec: dict, niche: dict) -> str:
    msg = rec.get("wa_message") or f"مرحباً {rec['name']}، شفت صفحتكم على الإنترنت وعايز أستفسر 👋"
    # wa.me rejects a leading "+": the pages carry it in JSON-LD's telephone
    # but never in the link itself.
    return f"https://wa.me/{dial(rec)}?text={quote(msg)}"


def dial(rec: dict) -> str:
    """The phone as the wa.me / tel: links write it: digits, no leading '+'."""
    return str(rec.get("phone_intl", "")).lstrip("+")


def map_url(rec: dict) -> str:
    """Google Maps embed for the business: name + street address, URL-encoded."""
    q = quote(f"{rec.get('name', '')} {rec.get('address', '')}".strip())
    return f"https://maps.google.com/maps?q={q}&output=embed"


def slugify(name: str) -> str:
    """Keep Arabic + latin, collapse everything else to single dashes."""
    s = re.sub(r"[^\w\u0600-\u06FF]+", "-", name.strip(), flags=re.UNICODE)
    return s.strip("-").lower()
