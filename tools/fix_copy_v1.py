"""fix_copy_v1.py -- one-off copy repair (district leaks + dialect + titles).

Rewrites templates/niches/*.json and data/businesses.json in place:
  1. plain-text replacements (Egyptian dialect -> neutral/Saudi-friendly fusha)
  2. district-leak repair: hardcoded district names in niche defaults become
     {district} tokens; per-record prose (usps/about_sub/faqs/services) gets
     its own district tokenized the same way (address/jsonld/hours untouched)
  3. new unique titles + h1 per niche ({name} + {district})
  4. nail_salon services replaced (were hair/makeup copy pasted from beauty)
  5. generic h1/cta overrides that duplicate old niche defaults are dropped
     so those pages inherit the fixed niche copy

Idempotent: re-running changes nothing (all replacements converge).
Run:  python tools/fix_copy_v1.py
Then: python tools/gen_pages.py  +  python tools/gen_pages.py --check
"""
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NICHE_DIR = ROOT / "templates" / "niches"
DATA = ROOT / "data" / "businesses.json"

# (old -> new) applied to niche files AND business records (raw file text).
PAIRS = [
    ("والرقم بيتكلم عن نفسه", "والأرقام تتحدث عن نفسها"),
    ("إيه اللي يميّز", "ما الذي يميّز"),
    ("أزاي أحجز أو أستفسر؟", "كيف أحجز أو أستفسر؟"),
    ("بأبسط طريقة: دوس على زر الواتساب أو الاتصال الموجود في الصفحة — هيتكلم معاهم مباشرة في أي وقت.",
     "بكل سهولة: اضغط زر الواتساب أو الاتصال في الصفحة — وسيتواصلون معك مباشرة."),
    ("فين الموقع بالظبط؟", "أين الموقع بالضبط؟"),
    ("إيه مواعيد العمل؟", "ما مواعيد العمل؟"),
    ("ومحدّد عليها يوم النهاردة — بس يتغير شيء، اسألهم على الواتساب.",
     "مع تمييز يوم اليوم — وإذا تغيّر شيء، اسألهم عبر الواتساب."),
    ("شفت صفحتكم على الإنترنت وعايز أستفسر", "رأيت صفحتكم على الإنترنت وأرغب بالاستفسار"),
    ("كلم {name} على الواتساب أو الاتصال — وهيردّوا عليك مباشرة.",
     "تواصل مع {name} عبر الواتساب أو الاتصال — وسيردّون عليك مباشرة."),
    ("عايز تجرّب قهوتنا؟ تعالالنا", "ودّك تجرّب قهوتنا؟ حيّاك الله"),
    ("جاهز لقصة شعر جديدة؟ احجز مكانك النهاردة", "جاهز لقصّة جديدة؟ احجز موعدك اليوم"),
    ("جاهزة تجربي؟ احجزي موعدك النهاردة", "جاهزة لإطلالة جديدة؟ احجزي موعدك اليوم"),
    ("جاهز تبدأ؟ اسأل عن الاشتراك النهاردة", "جاهز تبدأ؟ اسأل عن الاشتراك اليوم"),
    ("أظافرك تستاهل — احجزي موعدك", "أظافرك تستحق الأفضل — احجزي موعدك"),
    ("عربيتك محتاجة صيانة؟ كلمنا واحصل على عرض سعر", "سيارتك تحتاج صيانة؟ تواصل معنا واحصل على عرض سعر"),
    ("عربيتك محتاجة صيانة؟ كلمنا", "سيارتك تحتاج صيانة؟ تواصل معنا"),
    ("الأحسن تحجز قبل، خصوصاً في أوقات الذروة — كلمهم على الواتساب واحجز مكانك.",
     "الأفضل أن تحجز مسبقاً، خصوصاً في أوقات الذروة — راسلهم على الواتساب واحجز موعدك."),
    ("آه — الشفافية في التكلفة من أساسياتهم، وهيعرضوا عليك التقدير قبل أي إصلاح.",
     "نعم — الشفافية في التكلفة من أساسياتهم، وسيعرضون عليك التقدير قبل أي إصلاح."),
    ("فيه تجربة قبل الاشتراك؟", "هل تتوفر تجربة قبل الاشتراك؟"),
    ("اسألهم على الواتساب عن إمكانية تجربة أو زيارة قبل الاشتراك.",
     "اسألهم عبر الواتساب عن إمكانية التجربة أو الزيارة قبل الاشتراك."),
    ("فيه عرض سعر قبل الشغل؟", "هل أحصل على عرض سعر قبل بدء العمل؟"),
    ("صالون شعر بيغير شكلك بالكامل في الرياض", "صالون حلاقة يغيّر إطلالتك بالكامل في الرياض"),
    ("شعرك يستاهل العناية — تواصل معانا", "شعرك يستحق العناية — تواصل معنا"),
    ("نادي رياضي بيخليك توصل لهدفك", "نادٍ رياضي يساعدك على الوصول لهدفك"),
    ("ابدأ رحلتك معانا النهاردة", "ابدأ رحلتك اليوم"),
    ("عنابة بالبشرة", "العناية بالبشرة"),
    ("ورموش by يد متخصصة", "ورموش على يد متخصصة"),
    # about body (niche default + any record override carrying the same sentences)
    ("هو واحد من الأماكن اللي بقت مرجع في مجال", "من الأماكن المعروفة في مجال"),
    ("والدليل على كده", "والدليل على ذلك"),
    ("الرقم ده مش جاي من حملة إعلانية، جاي من ناس زاروا المكان فعلاً وقيّموه بصراحة.",
     "هذا الرقم ليس من حملة إعلانية، بل من زوّار حقيقيين قيّموا المكان بصراحة."),
    ("اللي بيقولوه العملاء في تقييماتهم بيتركّز على حاجات ملموسة: مستوى الشغل نفسه، النظافة، التعامل المحترم، والاهتمام بالتفاصيل الصغيرة اللي بتفرق.",
     "يتحدث العملاء في تقييماتهم عن أمور ملموسة: جودة العمل، والنظافة، والتعامل الراقي، والاهتمام بالتفاصيل الصغيرة التي تصنع الفرق."),
    ("والصفحة دي جمعنالك فيها كل حاجة تحتاجها قبل ما تروح: الصور الحقيقية، العنوان بالتفصيل، مواعيد العمل كاملة، والتقييمات بنصها بدون أي تعديل.",
     "جمعنا لك في هذه الصفحة كل ما تحتاجه قبل الزيارة: الصور الحقيقية، والعنوان التفصيلي، ومواعيد العمل الكاملة، والتقييمات بنصّها دون أي تعديل."),
]

NEW_H1 = {
    "coffee": "{name} — قهوة مختصة في {district}",
    "barbershop": "{name} — حلاقة وقصّات عصرية في {district}",
    "beauty_salon": "{name} — صالون تجميل في {district}",
    "nail_salon": "{name} — عناية بالأظافر في {district}",
    "gym": "{name} — لياقة وتدريب في {district}",
    "auto_repair": "{name} — صيانة سيارات تثق بها في {district}",
}
NEW_TITLE = "{name} — {niche_name} في {district}، {city_ar} | تقييم {rating}★"
NEW_OG_TITLE = "{name} — {niche_name} في {district}، {city_ar}"

NAIL_SERVICES = [
    {"title": "مناكير وباديكير", "text": "عناية متكاملة بالأظافر مع تشكيل وتنظيف دقيق وأدوات معقّمة لكل عميلة.", "tag": "أظافر"},
    {"title": "تركيب وجل", "text": "تركيب أظافر وجل وبولي جل بثبات عالٍ وشكل طبيعي يدوم.", "tag": "تركيب"},
    {"title": "تصاميم ونقوش", "text": "تصاميم عصرية ونقوش دقيقة بألوان ثابتة تناسب ذوقك ومناسباتك.", "tag": "تصاميم"},
    {"title": "تعقيم وعناية", "text": "تعقيم صارم للأدوات وعناية بالبشرة المحيطة لضمان تجربة آمنة ومريحة.", "tag": "عناية"},
]

# generic overrides that only duplicated the old niche defaults -> inherit anew
DROP_H1 = {
    "calibrated-coffee-roasters": ["h1", "cta_heading"],
    "java-time": ["h1", "cta_heading"],
    "fitness-star-gym": ["h1", "cta_heading"],
    "future-of-trust-car-workshop-shafi": ["h1", "cta_heading"],
    "university-cooperative-center-for-car-maintenance": ["h1", "cta_heading"],
    "holic-beauty-salon-nailsholic-سابقا": ["cta_heading"],
}

LEAKED_DISTRICTS = ["Al Mohammadiyyah", "Al Malqa", "Al Olaya", "As Sahafah", "Unnamed Road"]
PROSE_FIELDS = ("usps", "services", "faqs", "about_sub", "about_heading", "cta_heading", "h1")


def fix_prose_districts(rec: dict) -> bool:
    """Tokenize district names inside prose fields only (never address/urls)."""
    changed = False
    dist = rec.get("district", "")
    blob_fields = [f for f in PROSE_FIELDS if isinstance(rec.get(f), str)]
    list_fields = [f for f in ("usps", "services", "faqs") if isinstance(rec.get(f), list)]
    for f in blob_fields:
        t = rec[f]
        for leak in LEAKED_DISTRICTS:
            if leak != dist and leak in t:
                t = t.replace(leak, dist)
                changed = True
        if dist and dist in t:
            nt = t.replace("في %s" % dist, "في {district}").replace(
                "%s — " % dist, "{district} — ").replace(
                " — %s" % dist, " — {district}")
            if nt != t:
                t = nt
                changed = True
        rec[f] = t
    for f in list_fields:
        for item in rec[f]:
            for k, v in list(item.items()):
                if not isinstance(v, str):
                    continue
                t = v
                for leak in LEAKED_DISTRICTS:
                    if leak != dist and leak in t:
                        t = t.replace(leak, dist)
                        changed = True
                if dist and dist in t:
                    nt = t.replace("في %s" % dist, "في {district}").replace(
                        "%s — " % dist, "{district} — ").replace(
                        " — %s" % dist, " — {district}")
                    if nt != t:
                        t = nt
                        changed = True
                item[k] = t
    return changed


def main() -> None:
    # ---- 1) niche files ----
    for path in sorted(NICHE_DIR.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        for old, new in PAIRS:
            text = text.replace(old, new)
        # hardcoded district defaults -> {district} token
        for leak in LEAKED_DISTRICTS:
            text = text.replace("%s — {city_ar}" % leak, "في {district} — {city_ar}")
        text = text.replace("صالون تجميل في Al Olaya — ", "{niche_name} في {district} — ")
        text = text.replace("{city_ar} — {city_ar}", "في {district} — {city_ar}")
        prof = json.loads(text)
        prof["page_title"] = NEW_TITLE
        prof["og_title"] = NEW_OG_TITLE
        prof["h1"] = NEW_H1[prof["name"]]
        if prof["name"] == "nail_salon":
            prof["services"] = NAIL_SERVICES
        path.write_bytes((json.dumps(prof, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
        print("niche fixed: %s" % path.name)

    # ---- 2) business records ----
    records = json.loads(DATA.read_text(encoding="utf-8"))
    for rec in records:
        for slug, fields in DROP_H1.items():
            if rec.get("slug") == slug:
                for f in fields:
                    rec.pop(f, None)
        fix_prose_districts(rec)
    blob = json.dumps(records, ensure_ascii=False, indent=1) + "\n"
    for old, new in PAIRS:
        blob = blob.replace(old, new)
    blob = blob.replace("صالون تجميل في Al Olaya — ", "{niche_name} في {district} — ")
    blob = blob.replace("{city_ar} — {city_ar}", "في {district} — {city_ar}")
    DATA.write_bytes(blob.encode("utf-8"))
    # validate
    json.loads(DATA.read_text(encoding="utf-8"))
    print("records fixed: %d" % len(records))


if __name__ == "__main__":
    sys.exit(main())
