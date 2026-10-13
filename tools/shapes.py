"""shapes.py -- the boilerplate patterns that turn a rendered page string back
into a {token} template.

Why this exists: a landing page is mostly the same sentence with the business
name, its Google label, its city and its rating slid into it. If we stored the
finished sentence, changing the rating in the data file would NOT change the
page -- the copy would go stale. So every repeated sentence is stored as a
template with {tokens}, and the tokens are filled at render time.

The rule for deciding whether a value is boilerplate is deliberately strict:
rebuild the page string from the record's own raw values and compare it to what
the page actually says. Equal -> store the template. Different -> the copy is
genuinely bespoke for this business, so store the raw text as an override.

    python -c "import sys; sys.path.insert(0,'tools'); import shapes; print(shapes.ABOUT_TEMPLATE)"
"""
import html
import re
from urllib.parse import unquote

# ---------------------------------------------------------------- head / SEO
# The <title>, <meta> and og:* strings are pure interpolation; the round-trip
# test (tools/gen_pages.py --check) is what proves these templates are exact.

SEO = {
    "page_title": "{name} — {niche_name} في {district}، {city_ar} | تقييم {rating}★",
    "og_title": "{name} — {niche_name} في {district}، {city_ar}",
    "meta_desc": ("{name} — {niche_name} في {district} ب{city_ar}. تقييم {rating}★ "
                  "من {reviews_fmt} تقييم على Google. العنوان، المواعيد، "
                  "والتقييمات الحقيقية."),
    "og_image": "{hero_url}",
}
# og:description repeats the meta description verbatim on every page.
SEO["og_desc"] = SEO["meta_desc"]

# ---------------------------------------------------------------- hero / copy
COPY = {
    "hero_tag": ("في {district} ب{city_ar} — {niche_name} بتقييم {rating}★ "
                 "من {reviews_fmt} تقييم حقيقي على Google."),
    "about_sub": "{niche_name} في {city_ar} — والرقم بيتكلم عن نفسه",
    "about_heading": "عن {name}",
    "cta_text": "كلم {name} على الواتساب أو الاتصال — وهيردّوا عليك مباشرة.",
    # only two niches phrase their h1 this way; every other h1 is bespoke and
    # therefore stays in the record
    "h1": "جمالك بيبدأ من هنا — {niche_name} في {city_ar}",
    # the pre-filled WhatsApp text. Filled RAW at render time (it goes into a
    # URL query, not into HTML), which is why it is compared with fill_raw.
    "wa_message": "مرحباً {name}، رأيت صفحتكم على الإنترنت وأرغب بالاستفسار 👋",
}

# The about section is one long paragraph pair, identical on all 30 pages apart
# from five slots.
ABOUT_TEMPLATE = (
    "<p><strong>{name}</strong> هو واحد من الأماكن اللي بقت مرجع في مجال "
    "<strong>{niche_name}</strong> في {city_ar} — والدليل على كده "
    "<strong>{reviews_fmt} تقييم</strong> على Google Maps بمتوسط "
    "<strong>{rating} من 5</strong>. الرقم ده مش جاي من حملة إعلانية، جاي من ناس "
    "زاروا المكان فعلاً وقيّموه بصراحة.</p>"
    "<p>اللي بيقولوه العملاء في تقييماتهم بيتركّز على حاجات ملموسة: مستوى الشغل "
    "نفسه، النظافة، التعامل المحترم، والاهتمام بالتفاصيل الصغيرة اللي بتفرق. "
    "والصفحة دي جمعنالك فيها كل حاجة تحتاجها قبل ما تروح: الصور الحقيقية، "
    "العنوان بالتفصيل، مواعيد العمل كاملة، والتقييمات بنصها بدون أي تعديل.</p>"
)

TEMPLATES = dict(SEO)
TEMPLATES.update(COPY)
TEMPLATES["about_html"] = ABOUT_TEMPLATE

# Values that may be substituted into a prose sentence. Longest first: a name
# that contains the city ("رياض كوفي") must not be half-replaced.
PROSE_ORDER = ("name", "niche_name", "city_ar", "reviews_fmt", "rating")


def esc(value) -> str:
    """Same escaping the pages use (html.escape(..., quote=True))."""
    return html.escape(str(value), quote=True)


def token_map(rec: dict) -> dict:
    """{token name} -> the value this record would put there (raw, unescaped)."""
    rating = rec.get("rating")
    review_count = rec.get("review_count")
    return {
        "name": str(rec.get("name", "")),
        "niche_name": str(rec.get("niche_name", "")),
        "city_ar": str(rec.get("city_ar", "")),
        "district": str(rec.get("district", "")),
        "rating": _num(rating),
        "reviews_fmt": f"{review_count:,}" if review_count is not None else "",
        "address": str(rec.get("address", "")),
        "phone_display": str(rec.get("phone_display", "")),
        "hero_url": str(rec.get("hero_url", "")),
    }


def _num(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


def fill(template: str, mapping: dict) -> str:
    """Fill a {token} template. Every slot here is an HTML context, so values
    are escaped -- that is the single place raw text becomes HTML."""
    out = template
    for tok, val in mapping.items():
        out = out.replace("{%s}" % tok, esc(val))
    return out


def fill_raw(template: str, mapping: dict) -> str:
    """Same, without escaping. Only for values that go into a URL query (the
    pre-filled WhatsApp message), where &amp; would be wrong."""
    out = template
    for tok, val in mapping.items():
        out = out.replace("{%s}" % tok, str(val))
    return out


def rendered(field: str, rec: dict) -> str:
    """What the page should say for `field` if it is plain boilerplate."""
    return fill(TEMPLATES[field], token_map(rec))


def tokenize_prose(value, mapping: dict) -> str:
    """Replace the record's own scalars inside a sentence with {tokens}.

    Used for list items (USPs, services, FAQ answers) that are shared inside a
    niche but still name the business. The city is tokenized, never the
    district: prose says "في الرياض", and a district here is usually a Latin
    street name that prose would not contain anyway.
    """
    text = str(value)
    for key in sorted(PROSE_ORDER, key=lambda k: -len(esc(mapping.get(k, "")))):
        v = esc(mapping.get(key, ""))
        if v and v in text:
            text = text.replace(v, "{%s}" % key)
    return text


def wa_message_from(url: str) -> str:
    """Pull the pre-filled WhatsApp text back out of a wa.me link."""
    m = re.search(r"[?&]text=([^&]*)", url)
    return unquote(m.group(1)) if m else ""
