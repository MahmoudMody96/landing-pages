"""build_niches.py -- collapse the extracted records into a niche profile plus
a minimal per-business record.

    python tools/extract_pages.py     # pages -> data/extracted.json
    python tools/build_niches.py      #       -> templates/niches/*.json
                                      #       -> data/businesses.json

The rule that makes the result a template rather than a dump: any value that is
byte-identical to the niche's shared template is DROPPED from the business
record and lives in templates/niches/<niche>.json instead. What is left in the
record is only what this business actually overrides -- its own name, phone,
address, rating, reviews, and the handful of sentences it words differently.

Everything stored is a {token} template, so changing a rating or a city label in
the data file changes every sentence that mentions it.

Running this OVERWRITES data/businesses.json. Hand edits after the bootstrap
belong in that file, so re-run extract+build only when you want to re-derive the
template from the pages on disk.
"""
import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pagekit as pk
import shapes

ROOT = Path(__file__).resolve().parent.parent
EXTRACTED = ROOT / "data" / "extracted.json"

# Fields rebuilt from a {token} template when the page really says that.
TEMPLATE_FIELDS = ("page_title", "og_title", "meta_desc", "og_desc", "og_image",
                   "hero_tag", "about_sub", "about_heading", "cta_text",
                   "h1", "about_html", "wa_message")

# List fields whose items are shared inside a niche but may name the business.
PROSE_LIST_FIELDS = ("usps", "services", "faqs")

# Fields that may be promoted into the niche profile and dropped from a record
# when they match the niche default.
SHAREABLE = TEMPLATE_FIELDS + PROSE_LIST_FIELDS + (
    "mark", "years", "niche_name", "cta_heading", "nav_services",
    "services_heading", "services_lead",
    "theme_css", "hero_css", "cta_bg_css", "city_ar",
)

# Per-business facts. These stay in the record no matter what, and a niche file
# must never be able to invent them.
NEVER_SHARE = {"slug", "file", "name", "url", "phone_intl", "phone_display",
               "address", "district", "rating", "review_count", "hero_url",
               "hero", "jsonld", "hours", "reviews", "photos", "niche"}

# Field order in the written record: identity first, then data, then copy.
RECORD_ORDER = ["slug", "file", "name", "niche", "url", "phone_intl", "rating",
                "review_count", "address", "district", "city_ar", "niche_name",
                "mark", "years", "hero_url", "hours", "reviews", "photos",
                "theme_css", "hero_css", "cta_bg_css", "jsonld"]

NICHE_ORDER = ["name", "mark", "hero", "gallery_prefix", "jsonld_type",
               "city_ar", "theme_css", "hero_css", "cta_bg_css",
               "page_title", "og_title", "meta_desc", "og_desc", "og_image",
               "h1", "hero_tag", "about_sub", "about_heading", "about_html",
               "cta_heading", "cta_text", "wa_message", "nav_services",
               "services_heading", "services_lead", "years",
               "usps", "services", "faqs", "reviews", "photos"]


def normalise(rec: dict) -> dict:
    """Rewrite every shareable field into its {token} template form.

    A field is only rewritten when the page really is that template filled with
    this record's own values -- anything else is genuine per-business copy and
    is kept verbatim.
    """
    esc_map = shapes.token_map(rec)
    raw_map = {k: str(v) for k, v in esc_map.items()}
    out = dict(rec)

    for field in TEMPLATE_FIELDS:
        if field not in rec:
            continue
        tpl = shapes.TEMPLATES.get(field)
        if tpl is None:
            continue
        if field == "wa_message":
            matches = rec[field] == shapes.fill_raw(tpl, raw_map)
        elif field == "about_html":
            matches = rec[field] == shapes.fill(tpl, esc_map)
        else:
            matches = rec[field] == shapes.fill_raw(tpl, raw_map)
        out[field] = tpl if matches else rec[field]

    for field in PROSE_LIST_FIELDS:
        items = rec.get(field)
        if not items:
            continue
        out[field] = [
            {k: (shapes.tokenize_prose(v, esc_map) if isinstance(v, str) else v)
             for k, v in item.items()}
            for item in items]
    return out


def modal(values):
    """Most common value; ties go to a template (boilerplate) then to the
    alphabetically first, so the output is deterministic."""
    def rank(item):
        value, count = item
        return (-count, 0 if "{" in str(value) else 1, str(value))
    return sorted(Counter(values).items(), key=rank)[0][0]


def same(a, b) -> bool:
    return json.dumps(a, ensure_ascii=False, sort_keys=True) == \
        json.dumps(b, ensure_ascii=False, sort_keys=True)


def hero_path(hero_url: str) -> str:
    return hero_url.replace(pk.BASE_URL, "") if hero_url else ""


def _dirty() -> bool:
    """True when the files this script overwrites have uncommitted changes."""
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain=v1", "--", "data/businesses.json",
             "templates/niches"],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(out.stdout.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="allow overwriting data/businesses.json with uncommitted changes present")
    args = ap.parse_args()
    if not args.force and _dirty():
        raise SystemExit(
            "refusing: data/businesses.json or templates/niches/ has uncommitted "
            "changes (this script OVERWRITES data/businesses.json). Commit first "
            "or re-run with --force.")
    if not EXTRACTED.exists():
        raise SystemExit(f"missing {EXTRACTED}; run tools/extract_pages.py first")
    records = [normalise(r) for r in
               json.loads(EXTRACTED.read_text(encoding="utf-8"))]

    niches: dict = {}
    for rec in records:
        niches.setdefault(rec["niche"], []).append(rec)

    written = []
    for name, rows in sorted(niches.items()):
        profile: dict = {"name": name}

        # ---- image + chrome defaults ----
        hero = modal([hero_path(r["hero_url"]) for r in rows])
        profile["hero"] = hero
        profile["gallery_prefix"] = hero.rsplit("/", 1)[-1].removesuffix(".jpg")
        profile["mark"] = modal([r.get("mark", "") for r in rows])
        profile["jsonld_type"] = modal([r["jsonld"]["type"] for r in rows])

        # ---- everything shareable, in a stable order ----
        for field in NICHE_ORDER:
            if field in profile:
                continue
            present = [r[field] for r in rows if field in r]
            if not present:
                continue
            if field in ("usps", "services", "faqs"):
                profile[field] = modal([json.dumps(v, ensure_ascii=False)
                                        for v in present])
                profile[field] = json.loads(profile[field])
            elif field == "reviews":
                profile[field] = []
            elif field == "photos":
                # the "images are basic unless you change them" default: the
                # niche hero plus the niche stock photos
                prefix = profile["gallery_prefix"]
                profile[field] = [{"url": "{hero_url}", "alt": ""}] + [
                    {"url": f"{pk.BASE_URL}/stock/{prefix}-{i}.jpg", "alt": ""}
                    for i in (0, 1, 2)]
            else:
                profile[field] = modal(present)

        dest = pk.NICHE_DIR / f"{name}.json"
        pk.NICHE_DIR.mkdir(parents=True, exist_ok=True)
        # write_bytes (not write_text): LF on every OS, so re-running the
        # bootstrap cannot turn these files into a whole-file CRLF diff
        dest.write_bytes((json.dumps(profile, ensure_ascii=False, indent=1)
                          + "\n").encode("utf-8"))
        written.append(dest)

        # ---- prune the records: drop anything the niche already says ----
        for rec in rows:
            for field in list(rec):
                if field in NEVER_SHARE or field == "jsonld":
                    continue
                if field in SHAREABLE and field in profile and same(rec[field],
                                                                    profile[field]):
                    del rec[field]
            if "photos" in rec and same(rec["photos"], profile["photos"]):
                del rec["photos"]

    # ---- write the records back, in a readable order ----
    out = []
    for rec in sorted(records, key=lambda r: r["slug"]):
        row = {k: rec[k] for k in RECORD_ORDER if k in rec}
        row.update({k: v for k, v in rec.items() if k not in row})
        out.append(row)
    dest = ROOT / "data" / "businesses.json"
    dest.write_bytes((json.dumps(out, ensure_ascii=False, indent=1)
                      + "\n").encode("utf-8"))

    print(f"wrote {len(written)} niche profile(s):")
    for p in written:
        print(f"  {p.relative_to(ROOT)}")
    print(f"wrote {dest.relative_to(ROOT)} ({len(out)} records, "
          f"{sum(len(r) for r in out)} fields)")
    for name, rows in sorted(niches.items()):
        print(f"  {name:12s} x{len(rows)} records, "
              f"{sum(len(r) for r in rows)} fields kept")


if __name__ == "__main__":
    main()
