"""gen_pages.py — render landing pages from data + niche profile.

    python tools/gen_pages.py                     # write pages
    python tools/gen_pages.py --check             # rebuild and diff against the
                                                   # committed pages (must match)
    python tools/gen_pages.py --slide zafer.html   # render one page to stdout
    python tools/gen_pages.py --dir src/cities/ae-dubai --out-dir src/cities/ae-dubai

Data lives in data/businesses.json, per-niche defaults in
templates/niches/<niche>.json, the design in templates/page.html.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pagekit as pk

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data" / "businesses.json"
DEFAULT_SRC = ROOT / "src" / "cities" / "sa-riyadh"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DEFAULT_DATA))
    ap.add_argument("--dir", default=str(DEFAULT_SRC), help="source dir to write into")
    ap.add_argument("--out-dir", help="write somewhere else (keeps --dir for --check)")
    ap.add_argument("--check", action="store_true", help="diff against existing pages")
    ap.add_argument("--dry-run", action="store_true", help="parse and validate only")
    ap.add_argument("page", nargs="?", help="render a single page to stdout")
    args = ap.parse_args()

    records = json.loads(Path(args.data).read_text(encoding="utf-8"))
    skeleton = pk.TEMPLATE.read_text(encoding="utf-8")
    niches = {}
    for r in records:
        if r["niche"] not in niches:
            niches[r["niche"]] = pk.load_niche(r["niche"])

    if args.page:
        want = args.page.removesuffix(".html")
        rec = next((r for r in records if r["slug"] == want), None)
        if rec is None:
            raise SystemExit(f"no record with slug {want!r}")
        out = pk.render(rec, niches[rec["niche"]], skeleton)
        print(out, end="")
        return

    if args.check or args.dry_run:
        src = Path(args.dir)
        bad = []
        for rec in records:
            expected_path = src / rec["file"]
            want = pk.render(rec, niches[rec["niche"]], skeleton)
            if not expected_path.exists():
                bad.append((rec["slug"], "missing on disk"))
                continue
            # read bytes: read_text() would translate CRLF->LF and hide a
            # line-ending drift that git still reports as a whole-file diff
            got = expected_path.read_bytes().decode("utf-8")
            if want != got:
                # narrow the first divergence so the message is actionable
                i = next((k for k, (a, b) in enumerate(zip(want, got)) if a != b),
                        min(len(want), len(got)))
                bad.append((rec["slug"], f"differs at char {i}: "
                                        f"want {want[i-30:i+30]!r} got {got[i-30:i+30]!r}"))
        print(f"checked {len(records)} pages")
        if bad:
            print(f"\n{len(bad)} MISMATCH(ES):")
            for slug, why in bad[:10]:
                print(f"  {slug}: {why}")
            raise SystemExit(1)
        print("PASS: every page regenerates byte-for-byte from data + template")
        return

    out_dir = Path(args.out_dir) if args.out_dir else Path(args.dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    changed = []
    for rec in records:
        html = pk.render(rec, niches[rec["niche"]], skeleton)
        target = out_dir / rec["file"]
        if target.exists() and target.read_bytes().decode("utf-8") == html:
            continue
        # write_bytes, not write_text: the default would translate every '\n'
        # to CRLF on Windows, and the comparison below (which must also read
        # bytes) would still say "already identical" while git sees a 30-page
        # whole-file diff. The pages are committed LF -- keep them LF.
        target.write_bytes(html.encode("utf-8"))
        written += 1
        changed.append(rec["slug"])
    print(f"wrote {written} page(s), {len(records) - written} already identical")
    for slug in changed:
        print(f"  + {slug}")
    if not written:
        print("(nothing changed — data matches the pages on disk)")


if __name__ == "__main__":
    main()
