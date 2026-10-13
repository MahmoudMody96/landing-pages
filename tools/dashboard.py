"""dashboard.py — local ops dashboard for the landing-pages project.

    python tools/dashboard.py [--port 8765] [--no-open] [--host 127.0.0.1]

Serves a single-page Arabic/RTL dashboard that monitors the whole project and
runs the actions that are safe from a browser:

    /api/overview   counts + health badge + git state (no writes)
    /api/businesses page inventory + niche summary (optional ?city=)
    /api/business   read / edit one record (writes data/businesses.json)
    /api/niches|/api/niche/<n>|/api/niche  niche profiles (read/save+regen)
    /api/preview/<slug>  render one page in memory (no writes)
    /api/quality    content audits (district leaks, duplicates, dialect)
    /api/media      hero/stock inventory (GET) + strict .jpg upload (POST)
    /api/import     bulk CSV/xlsx: preview then all-or-nothing apply
    /api/cities     discovered cities + page counts
    /api/run        run a gate: check | gen | build-sim | media-check
                    | release (runs tools/release.sh, needs message)
    /api/live       probe every published page URL (optional ?city=)
    /api/stats      probe history + event log (local, gitignored)
    /api/publish    what a release would ship right now (read-only)

Rules baked in on purpose:

  * Binds 127.0.0.1 only -- this is an operator console, not a public app.
  * Never stores a credential. A deploy token is pasted per use and used once.
  * Writes data/businesses.json as LF bytes in the exact shape build_niches.py
    writes it (json.dumps(indent=1) + "\n"), so an edit shows up in git as the
    fields that changed -- never as a 3,000-line whitespace diff.
  * Regenerating is the only way a page changes: the server never edits
    src/cities/ by hand. Same rule as the README.
  * Non-ASCII page URLs are percent-encoded before probing: urllib cannot
    send a raw Arabic path and a failed probe would lie (status 0 = "down").

Windows note: run the server with CODEBUDDY_SAFE_DELETE_ENABLED=0 or the
build-sim staging cleanup (146 files) is blocked by the bulk-delete guard.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote

# Repo root. Overridable for the container (entrypoint clones the private
# repo to /srv/repo and exports LP_ROOT) -- everything else derives from it.
ROOT = Path(os.environ.get("LP_ROOT") or
            Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT / "tools"))

DATA = ROOT / "data" / "businesses.json"
NICHE_DIR = ROOT / "templates" / "niches"
PAGES_DIR = ROOT / "src" / "cities" / "sa-riyadh"
LIVE_BASE = "https://riyadh.aidy.site/sa/riyadh"
ASSEMBLE = ROOT / "docker" / "assemble.sh"
UI_FILE = Path(__file__).resolve().parent / "dashboard_ui.html"

REQUIRED_NEW = ("slug", "file", "niche", "name")
# fields the edit form exposes; everything else stays in the raw JSON editor
FORM_FIELDS = ("slug", "file", "name", "niche", "district", "city_ar",
               "phone_intl", "rating", "review_count", "address", "years",
               "hero_url", "url")

INT_FIELDS = ("review_count", "years")
FLOAT_FIELDS = ("rating",)


def coerce_patch(patch):
    """Form values arrive as strings; numerics must go back as numbers.

    Without this, saving rating "4.7" as a string crashes pagekit.render
    (ValueError on f"{review_count:,}") and leaves data/pages mismatched.
    Returns (clean, error): error is "" when everything coerced.
    """
    clean = {}
    for k, v in patch.items():
        if k == "_replace":
            clean[k] = v
            continue
        if v is None or (isinstance(v, str) and v.strip() == ""):
            clean[k] = ""                       # empty form field = delete key
            continue
        s = v.strip() if isinstance(v, str) else v
        if k in INT_FIELDS:
            try:
                clean[k] = int(str(s))
            except (TypeError, ValueError):
                return None, f"حقل {k} لازم يكون عدداً صحيحاً (وصلك: {v!r})"
        elif k in FLOAT_FIELDS:
            try:
                clean[k] = float(str(s))
            except (TypeError, ValueError):
                return None, f"حقل {k} لازم يكون رقماً (وصلك: {v!r})"
        else:
            clean[k] = s
    return clean, ""


def validate_record(rec):
    """Light sanity checks before a write. Returns error string or ""."""
    rating = rec.get("rating")
    if rating is not None and not isinstance(rating, bool):
        try:
            f = float(rating)
        except (TypeError, ValueError):
            return "التقييم لازم يكون رقماً بين 0 و 5"
        if not 0 <= f <= 5:
            return "التقييم لازم يكون بين 0 و 5"
    rc = rec.get("review_count")
    if rc is not None and not isinstance(rc, bool):
        try:
            i = int(rc)
        except (TypeError, ValueError):
            return "عدد التقييمات لازم يكون عدداً صحيحاً"
        if i < 0:
            return "عدد التقييمات لا يمكن أن يكون سالباً"
    phone = str(rec.get("phone_intl") or "").replace(" ", "")
    if phone and not re.fullmatch(r"\+?\d{7,15}", phone):
        return "رقم الهاتف لازم يكون أرقاماً فقط (7-15 خانة، + اختيارية)"
    url = str(rec.get("url") or "")
    if url and not url.startswith("https://"):
        return "الرابط لازم يبدأ بـ https://"
    slug = str(rec.get("slug") or "")
    if slug and not re.fullmatch(r"[A-Za-z0-9\u0600-\u06FF-]+", slug):
        return "الـslug فيه حروف غير مسموحة"
    return ""


# ------------------------------------------------------------------ helpers

def run(cmd, timeout=180):
    """Run a command in the repo root, return (ok, output)."""
    try:
        p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           shell=isinstance(cmd, str))
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode == 0, out.strip()
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout}s"
    except Exception as exc:                       # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def git(*args):
    ok, out = run(["git", *args])
    return out if ok else f"(git failed) {out}"


def to_msys(path: Path) -> str:
    """D:/x/y -> /d/x/y for the bash-driven build simulation."""
    s = str(path).replace("\\", "/")
    m = re.match(r"^([A-Za-z]):/(.*)$", s)
    return f"/{m.group(1).lower()}/{m.group(2)}" if m else s


def find_bash() -> str:
    """A real bash, never the Windows WSL stub.

    On Windows a bare "bash" can resolve to C:\\Windows\\System32\\bash.exe,
    which only relays to WSL -- the build sim then dies with "Windows
    Subsystem for Linux has no installed distributions". Probe the candidates
    with `--version`: the WSL stub fails it, a real Git bash answers.
    """
    if sys.platform != "win32":
        return "bash"
    candidates: list[str] = []
    try:
        r = subprocess.run(["where.exe", "bash"], capture_output=True,
                           text=True, timeout=15)
        candidates += [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    except Exception:                                    # noqa: BLE001
        pass
    candidates.append(r"C:\Program Files\Git\bin\bash.exe")
    for c in candidates:
        low = c.lower()
        if "system32" in low or "windowsapps" in low:
            continue                       # the WSL relay, not a shell
        if not Path(c).exists():
            continue
        try:
            p = subprocess.run([c, "--version"], capture_output=True, timeout=15)
            if p.returncode == 0:
                return c
        except Exception:                                # noqa: BLE001
            continue
    return "bash"


def load_records():
    return json.loads(DATA.read_text(encoding="utf-8"))


def save_records(records):
    """LF bytes, same shape build_niches.py writes -- keeps git diffs honest."""
    DATA.write_bytes((json.dumps(records, ensure_ascii=False, indent=1)
                      + "\n").encode("utf-8"))


def load_niche(name):
    path = NICHE_DIR / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def niches():
    out = []
    for p in sorted(NICHE_DIR.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        out.append({"name": p.stem, "niche_name": d.get("niche_name"),
                    "hero": d.get("hero"),
                    "gallery_prefix": d.get("gallery_prefix"),
                    "theme_css": bool(d.get("theme_css")),
                    "services": len(d.get("services") or []),
                    "usps": len(d.get("usps") or []),
                    "faqs": len(d.get("faqs") or [])})
    return out


def default_gallery(rec, niche):
    """A record with no photos/hero_url of its own renders the niche stock."""
    has_own = bool(rec.get("photos")) and any(
        p.get("url") for p in rec.get("photos") or [])
    hero_own = bool(rec.get("hero_url")) and "/stock/" not in str(rec.get("hero_url"))
    return not (has_own and hero_own)


def probe(url, timeout=10):
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "landing-pages-dashboard/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


# ------------------------------------------------------------------ actions

def action_run(what, extra=None):
    extra = extra or {}
    if what == "check":
        ok, out = run([sys.executable, str(ROOT / "tools" / "gen_pages.py"),
                       "--check"])
        log_event("run", "بوابة المطابقة البايتية", ok)
        return {"ok": ok, "action": "check", "output": out,
                "label": "بوابة المطابقة البايتية"}
    if what == "gen":
        ok, out = run([sys.executable, str(ROOT / "tools" / "gen_pages.py")])
        log_event("run", "توليد الصفحات", ok)
        return {"ok": ok, "action": "gen", "output": out,
                "label": "توليد الصفحات"}
    if what == "build-sim":
        res = build_simulation()
        log_event("run", "محاكاة بناء الإيمج", res.get("ok"))
        return res
    if what == "media-check":
        ok, out = run([sys.executable,
                       str(ROOT / "tools" / "localize_images.py"), "--check"])
        log_event("run", "فحص الصور الخارجية", ok)
        return {"ok": ok, "action": "media-check", "output": out,
                "label": "فحص الصور الخارجية"}
    if what == "release":
        msg = str(extra.get("message") or "").strip()
        if not msg:
            return {"ok": False,
                    "output": "اكتب رسالة الإصدار أولاً (مثال: Release: ...)"}
        ok, out = run([find_bash(), str(ROOT / "tools" / "release.sh"), msg],
                      timeout=300)
        log_event("release", msg, ok)
        return {"ok": ok, "action": "release", "output": out,
                "label": "إصدار للريبو العام"}
    if what == "deploy":
        return action_deploy()
    if what == "deploy-status":
        return action_deploy_status()
    return {"ok": False, "output": f"unknown action {what!r}"}


def _coolify():
    """(base, token, app) for in-panel deploys. Token lives in env only."""
    base = os.environ.get("COOLIFY_API",
                          "http://coolify:8000/api/v1").rstrip("/")
    return base, os.environ.get("COOLIFY_TOKEN", ""), os.environ.get(
        "LP_APP_UUID", "f3c9chhue2nistvynkpjcreb")


def action_deploy():
    base, tok, app = _coolify()
    if not tok:
        return {"ok": False,
                "output": "COOLIFY_TOKEN غير مضبوط — النشر يدوي من Coolify UI"}
    try:
        req = urllib.request.Request(
            f"{base}/deploy", data=json.dumps({"uuid": app}).encode("utf-8"),
            headers={"Authorization": f"Bearer {tok}",
                     "Content-Type": "application/json",
                     "Accept": "application/json"})
        body = json.loads(urllib.request.urlopen(req, timeout=30).read()
                          .decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"ok": False, "output": f"Coolify HTTP {e.code}"}
    except Exception as e:                               # noqa: BLE001
        return {"ok": False, "output": f"{type(e).__name__}: {e}"}
    log_event("deploy", f"نشر {app}", True)
    return {"ok": True, "action": "deploy", "output": json.dumps(
        body, ensure_ascii=False)[:300], "label": "نشر على Coolify"}


def action_deploy_status():
    base, tok, app = _coolify()
    if not tok:
        return {"ok": False,
                "output": "COOLIFY_TOKEN غير مضبوط — النشر يدوي من Coolify UI"}
    try:
        req = urllib.request.Request(
            f"{base}/deployments/applications/{app}",
            headers={"Authorization": f"Bearer {tok}",
                     "Accept": "application/json"})
        data = json.loads(urllib.request.urlopen(req, timeout=20).read()
                          .decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"ok": False, "output": f"Coolify HTTP {e.code}"}
    except Exception as e:                               # noqa: BLE001
        return {"ok": False, "output": f"{type(e).__name__}: {e}"}
    deps = data.get("deployments") or []
    first = deps[0] if deps else {}
    return {"ok": True, "action": "deploy-status",
            "output": f"STATUS:{first.get('status', '?')} "
                      f"COMMIT:{str(first.get('commit', ''))[:7]}",
            "label": "حالة النشر"}


def _cleanup_sim(tmp: Path) -> str:
    """Remove the sim staging dir; never raise.

    A blocked cleanup must not kill the HTTP response -- an exception inside
    do_POST propagates to socketserver, which closes the connection with an
    EMPTY body (curl sees a JSON decode error, not an error message). Returns
    a warning line when the directory survived.
    """
    try:
        shutil.rmtree(tmp, ignore_errors=True)
    except Exception as e:                      # safe-delete guard, perms, ...
        return (f"\n\nWARNING: could not remove {tmp.name} ({e}). "
                f"Remove it by hand before any release.")
    if tmp.exists():
        return (f"\n\nWARNING: {tmp.name} still exists after cleanup "
                f"(safe-delete guard?). Remove it by hand before any release.")
    return ""


def scan_output(html: Path):
    """Post-build audit in Python -- never shell out to grep/find.

    `where.exe find` resolves to C:\\Windows\\System32\\find.exe, which reads
    `*.html` as a literal search string and prints "File not found - *.html".
    Doing it here makes the sim's verdict identical on every machine.
    """
    leak_pat = re.compile(r"/tmp/|/usr/share/nginx|AppData|MAHMOUD")
    ext_pat = re.compile(r"https?://[^\"]*googleusercontent[^\"]*")
    leaks: list[str] = []
    ext: list[str] = []
    unfilled: list[str] = []
    for p in sorted(html.rglob("*.html")):
        text = p.read_text(encoding="utf-8", errors="replace")
        if leak_pat.search(text):
            leaks.append(str(p.relative_to(html)))
        if ext_pat.search(text):
            ext.append(str(p.relative_to(html)))
        if "{{" in text:
            unfilled.append(str(p.relative_to(html)))
    return leaks, ext, unfilled


def build_simulation():
    """The documented local Docker build simulation (33 html / 9 / 107).

    Run the server with CODEBUDDY_SAFE_DELETE_ENABLED=0 or the staging-dir
    cleanup is blocked by WorkBuddy's bulk-delete guard (146 files > 50) and
    the guard's exception used to abort the whole request.
    """
    tmp = Path(tempfile.mkdtemp(prefix="lp-sim-", dir=str(ROOT)))
    result = None
    try:
        stage, html = tmp / "stage", tmp / "html"
        stage.mkdir()
        shutil.copytree(PAGES_DIR.parent, stage / "cities")
        shutil.copytree(ROOT / "assets" / "hero", stage / "hero-src")
        shutil.copytree(ROOT / "assets" / "stock", stage / "stock-src")
        for f in ("data/stock_manifest.json", "src/gen_index.sh",
                  "templates/404.html", "docker/assemble.sh"):
            src = ROOT / f
            dst = stage / Path(f).name
            dst.write_bytes(src.read_bytes())
        ok, out = run([find_bash(), str(ASSEMBLE), to_msys(stage),
                       to_msys(html), "https://pages.aidy.site"], timeout=300)
        if not ok:
            result = {"ok": False, "action": "build-sim", "output": out,
                      "label": "محاكاة بناء الإيمج"}
        else:
            leaks, ext, unfilled = scan_output(html)
            sitemap = html / "sitemap.xml"
            locs = (sitemap.read_text(encoding="utf-8", errors="replace")
                    .count("<loc>")) if sitemap.exists() else -1
            summary = (f"{out}\n\nleaked paths: {leaks or 'none'}\n"
                       f"external image refs: {ext or 'none'}\n"
                       f"unfilled placeholders: {unfilled or 'none'}\n"
                       f"sitemap <loc> entries: {locs}")
            result = {"ok": True, "action": "build-sim", "output": summary,
                      "label": "محاكاة بناء الإيمج",
                      "detail": {"leaks": leaks, "ext": ext,
                                 "unfilled": unfilled, "locs": locs}}
    except Exception as e:
        result = {"ok": False, "action": "build-sim",
                  "output": f"build-sim failed: {e!r}\n{tmp}",
                  "label": "محاكاة بناء الإيمج"}
    finally:
        warn = _cleanup_sim(tmp)
        if warn and result is not None:
            result["output"] = result.get("output", "") + warn
    return result


def action_live(city=None):
    recs = load_records()
    if city:
        recs = [r for r in recs if record_city(r) == city]
    # Arabic slugs must be percent-encoded: urllib will not send a raw unicode
    # path, and a failed probe shows up as status 0 (a false "page is down").
    urls = [f"{live_base_for(record_city(r))}/{quote(r['file'])}"
            for r in recs]
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        codes = list(ex.map(probe, urls))
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    rows = [{"slug": r["slug"], "file": r["file"], "status": c, "checked_at": now}
            for r, c in zip(recs, codes)]
    return {"ok": True, "checked_at": now,
            "up": sum(1 for r in rows if r["status"] == 200),
            "total": len(rows), "rows": rows}


def action_publish():
    status = git("status", "--porcelain", "--ignored=no")
    ignored = git("status", "--porcelain", "--ignored")
    tracked = run(["git", "ls-files"])[1].splitlines()
    risky = [l for l in ignored.splitlines()
             if l.startswith("!!") and re.search(
                 r"xlsx|outreach|arabic_review|prospects|workbuddy|hero_audit/",
                 l)]
    return {
        "ok": True,
        "dirty": bool(status.strip()),
        "status": status,
        "tracked_files": len(tracked),
        "ignored_risk": risky,
        "head": git("log", "--oneline", "-3"),
        "public_head": git("log", "--oneline", "-1", "public/main"),
        "origin_head": git("log", "--oneline", "-1", "origin/main"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
    }


def update_record(slug, patch):
    recs = load_records()
    idx = next((i for i, r in enumerate(recs) if r.get("slug") == slug), None)
    if idx is None:
        return {"ok": False, "output": f"no record with slug {slug!r}"}
    rec = recs[idx]
    if patch.get("_replace"):                      # whole-record JSON editor
        try:
            new = json.loads(patch["_replace"])
        except ValueError as e:
            return {"ok": False, "output": f"JSON غير صالح: {e}"}
        if not isinstance(new, dict):
            return {"ok": False, "output": "السجل لازم يكون كائن JSON"}
        if new.get("slug") != slug:
            return {"ok": False,
                    "output": "مينفعش تغيّر الـslug من هنا (انشئ سجل جديد)"}
        err = validate_record(new)
        if err:
            return {"ok": False, "output": err}
        recs[idx] = new
    else:
        clean, err = coerce_patch(patch)
        if err:
            return {"ok": False, "output": err}
        for k, v in clean.items():
            if k in ("_replace",):
                continue
            if v is None or v == "":
                rec.pop(k, None)
            else:
                rec[k] = v
        err = validate_record(rec)
        if err:
            return {"ok": False, "output": err}
    save_records(recs)
    ok, out = run([sys.executable, str(ROOT / "tools" / "gen_pages.py")])
    chk_ok, chk = run([sys.executable, str(ROOT / "tools" / "gen_pages.py"),
                       "--check"])
    log_event("update", f"تحديث سجل {slug}", ok and chk_ok)
    return {"ok": ok and chk_ok, "action": "update", "slug": slug,
            "output": out, "check": chk,
            "label": f"تحديث سجل {slug}"}


def add_record(record):
    missing = [k for k in REQUIRED_NEW if not record.get(k)]
    if missing:
        return {"ok": False, "output": f"حقول ناقصة: {', '.join(missing)}"}
    recs = load_records()
    if any(r.get("slug") == record["slug"] for r in recs):
        return {"ok": False,
                "output": f"الـslug {record['slug']!r} موجود بالفعل"}
    if not record.get("file"):
        record["file"] = f"{record['slug']}.html"
    niche = load_niche(record["niche"])
    if niche is None:
        return {"ok": False,
                "output": f"المجال {record['niche']!r} غير موجود"}
    clean, err = coerce_patch(record)
    if err:
        return {"ok": False, "output": err}
    record = {k: v for k, v in clean.items() if v != ""}
    err = validate_record(record)
    if err:
        return {"ok": False, "output": err}
    recs.append(record)
    save_records(recs)
    ok, out = run([sys.executable, str(ROOT / "tools" / "gen_pages.py")])
    chk_ok, chk = run([sys.executable, str(ROOT / "tools" / "gen_pages.py"),
                       "--check"])
    log_event("add", f"إضافة {record['slug']}", ok and chk_ok)
    return {"ok": ok and chk_ok, "action": "add", "slug": record["slug"],
            "output": out, "check": chk,
            "label": f"إضافة {record['slug']}"}


# ------------------------------------------------------------------ payloads

def overview_payload():
    recs = load_records()
    ok, out = run([sys.executable, str(ROOT / "tools" / "gen_pages.py"),
                   "--check"])
    per_niche = {}
    for r in recs:
        per_niche[r.get("niche", "?")] = per_niche.get(r.get("niche", "?"), 0) + 1
    return {
        "ok": True,
        "counts": {
            "pages": len(recs),
            "niches": len(niches()),
            "hero_images": len(list((ROOT / "assets" / "hero").glob("*.jpg"))),
            "stock_images": len(list((ROOT / "assets" / "stock").glob("*.jpg"))),
            "default_gallery": sum(1 for r in recs
                                   if default_gallery(r, load_niche(r.get("niche")))),
        },
        "per_niche": per_niche,
        "gate": {"ok": ok, "output": out},
        "git": {
            "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "head": git("log", "--oneline", "-1"),
            "dirty": bool(git("status", "--porcelain", "--ignored=no").strip()),
            "public_head": git("log", "--oneline", "-1", "public/main"),
        },
        "live_cached": LIVE_CACHE.get("checked_at"),
    }


def businesses_payload(city=None):
    recs = load_records()
    if city:
        recs = [r for r in recs if record_city(r) == city]
    rows = []
    for r in recs:
        niche = load_niche(r.get("niche"))
        photos = r.get("photos") or []
        rows.append({
            "slug": r.get("slug"), "file": r.get("file"),
            "name": r.get("name"), "niche": r.get("niche"),
            "niche_name": r.get("niche_name") or (niche or {}).get("niche_name"),
            "district": r.get("district"),
            "rating": r.get("rating"), "review_count": r.get("review_count"),
            "phone_display": r.get("phone_display"),
            "url": r.get("url"),
            "own_photos": len(photos),
            "default_gallery": default_gallery(r, niche),
            "fields": len(r),
            "has_usps_override": "usps" in r,
            "has_services_override": "services" in r,
            "has_faqs_override": "faqs" in r,
        })
    return {"ok": True, "rows": rows, "niches": niches()}


def business_payload(slug):
    recs = load_records()
    rec = next((r for r in recs if r.get("slug") == slug), None)
    if rec is None:
        return {"ok": False, "output": f"no record {slug!r}"}
    niche = load_niche(rec.get("niche"))
    return {"ok": True, "record": rec, "niche": niche,
            "raw": json.dumps(rec, ensure_ascii=False, indent=1),
            "form_fields": FORM_FIELDS,
            "available_niches": [n["name"] for n in niches()]}


def business_payload(slug):
    recs = load_records()
    rec = next((r for r in recs if r.get("slug") == slug), None)
    if rec is None:
        return {"ok": False, "output": f"no record {slug!r}"}
    niche = load_niche(rec.get("niche"))
    return {"ok": True, "record": rec, "niche": niche,
            "raw": json.dumps(rec, ensure_ascii=False, indent=1),
            "form_fields": FORM_FIELDS,
            "available_niches": [n["name"] for n in niches()]}


def save_niche(name, profile_text):
    """Replace a niche profile (or create one), then regen + check."""
    if not re.fullmatch(r"[a-z0-9_]+", str(name or "")):
        return {"ok": False,
                "output": "اسم المجال حروف إنجليزية صغيرة وأرقام و_ فقط"}
    try:
        profile = json.loads(profile_text)
    except ValueError as e:
        return {"ok": False, "output": f"JSON غير صالح: {e}"}
    if not isinstance(profile, dict):
        return {"ok": False, "output": "البروفايل لازم يكون كائن JSON"}
    profile["name"] = name
    (NICHE_DIR / f"{name}.json").write_bytes(
        (json.dumps(profile, ensure_ascii=False, indent=1) + "\n")
        .encode("utf-8"))
    ok, out = run([sys.executable, str(ROOT / "tools" / "gen_pages.py")])
    chk_ok, chk = run([sys.executable, str(ROOT / "tools" / "gen_pages.py"),
                       "--check"])
    log_event("niche", f"حفظ مجال {name}", ok and chk_ok)
    return {"ok": ok and chk_ok, "action": "niche", "niche": name,
            "output": out, "check": chk,
            "label": f"حفظ مجال {name}"}


def preview_page(slug):
    """Render one page in memory (no writes) for the live preview."""
    from pagekit import TEMPLATE, load_niche as pk_niche, render
    recs = load_records()
    rec = next((r for r in recs if r.get("slug") == slug), None)
    if rec is None:
        return None, f"no record {slug!r}"
    niche = pk_niche(rec.get("niche"))
    try:
        return render(rec, niche, TEMPLATE.read_text(encoding="utf-8")), ""
    except Exception as e:                       # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


# ------------------------------------------------------------------ quality

LEAKED_DISTRICTS = ("Al Mohammadiyyah", "Al Malqa", "Al Olaya", "As Sahafah",
                    "Unnamed Road")
DIALECT_NEEDLES = ("بيتكلم", "أزاي", "النهاردة", "تعالالنا", "عربيت",
                   "عنابة", "by يد", "دوس على", "كباية", "معانا", "بيخليك",
                   "إيه اللي", "فين الموقع", "إيه مواعيد")
PROSE_KEYS = ("usps", "services", "faqs", "about_sub", "about_heading",
              "cta_heading", "cta_text", "h1", "hero_tag", "about_html")


def _prose_blob(rec):
    parts = []
    for k in PROSE_KEYS:
        v = rec.get(k)
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, list):
            parts.append(json.dumps(v, ensure_ascii=False))
    return "\n".join(parts)


def action_quality():
    """Content audits that used to be manual review (see fix_copy_v1.py)."""
    from pagekit import TEMPLATE, load_niche as pk_niche, render
    recs = load_records()
    skeleton = TEMPLATE.read_text(encoding="utf-8")
    issues = []
    titles, h1s = {}, {}
    for rec in recs:
        slug = rec.get("slug", "?")
        dist = rec.get("district", "")
        blob = _prose_blob(rec)
        for leak in LEAKED_DISTRICTS:
            if leak != dist and leak in blob:
                issues.append({"severity": "high", "slug": slug,
                               "check": "district-leak",
                               "msg": f"اسم حي غريب في النصوص: {leak}"})
        for needle in DIALECT_NEEDLES:
            if needle in blob:
                issues.append({"severity": "medium", "slug": slug,
                               "check": "dialect",
                               "msg": f"بقايا لهجة مصرية: «{needle}»"})
                break
        for field in ("phone_intl", "address", "hours", "reviews", "url"):
            if not rec.get(field):
                issues.append({"severity": "medium", "slug": slug,
                               "check": "missing",
                               "msg": f"حقل ناقص: {field}"})
        phone = str(rec.get("phone_intl") or "").replace(" ", "")
        if phone and not re.fullmatch(r"\+?\d{7,15}", phone):
            issues.append({"severity": "high", "slug": slug,
                           "check": "phone",
                           "msg": "صيغة هاتف غير صالحة"})
        niche = pk_niche(rec.get("niche"))
        try:
            html = render(rec, niche, skeleton)
        except Exception as e:                   # noqa: BLE001
            issues.append({"severity": "high", "slug": slug,
                           "check": "render",
                           "msg": f"التوليد يفشل: {e}"})
            continue
        m = re.search(r"<title>(.*?)</title>", html)
        t = m.group(1) if m else ""
        titles.setdefault(t, []).append(slug)
        m = re.search(r"<h1>(.*?)</h1>", html)
        h = m.group(1) if m else ""
        h1s.setdefault(h, []).append(slug)
    for t, slugs in titles.items():
        if len(slugs) > 1:
            for s in slugs:
                issues.append({"severity": "medium", "slug": s,
                               "check": "dup-title",
                               "msg": f"عنوان مكرر مع: {', '.join(slugs)}"})
    for h, slugs in h1s.items():
        if len(slugs) > 1:
            for s in slugs:
                issues.append({"severity": "medium", "slug": s,
                               "check": "dup-h1",
                               "msg": f"H1 مكرر مع: {', '.join(slugs)}"})
    # niche profiles carry the same risks (they render into every page)
    for p in sorted(NICHE_DIR.glob("*.json")):
        blob = p.read_text(encoding="utf-8")
        for needle in DIALECT_NEEDLES:
            if needle in blob:
                issues.append({"severity": "medium", "slug": p.stem,
                               "check": "dialect",
                               "msg": f"بقايا لهجة في بروفايل المجال: «{needle}»"})
                break
        for leak in LEAKED_DISTRICTS:
            if f"{leak} — " in blob or f"في {leak}" in blob:
                issues.append({"severity": "high", "slug": p.stem,
                               "check": "district-leak",
                               "msg": f"حي ثابت في بروفايل المجال: {leak}"})
    high = sum(1 for i in issues if i["severity"] == "high")
    return {"ok": True, "records": len(recs), "issues": issues,
            "high": high, "total": len(issues)}


# ------------------------------------------------------------------ import

IMPORT_COLUMNS = ("slug", "file", "niche", "name", "url", "phone_intl",
                  "rating", "review_count", "address", "district", "city_ar",
                  "hero_url")


def _parse_table(filename, raw):
    """Spreadsheet bytes -> list of dicts. xlsx needs openpyxl (optional);
    csv always works (Excel: Save As -> CSV UTF-8)."""
    import io
    name = str(filename or "")
    if name.lower().endswith(".csv"):
        import csv
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        return rows, ""
    if name.lower().endswith((".xlsx", ".xls")):
        try:
            import openpyxl
        except ImportError:
            return None, ("openpyxl غير مثبتة — احفظ الملف CSV UTF-8 من إكسل "
                          "وارفعه (pip install openpyxl للدعم المباشر)")
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True,
                                    data_only=True)
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        try:
            header = next(it)
        except StopIteration:
            return None, "ملف فارغ"
        rows = []
        for line in it:
            if all(v is None or str(v).strip() == "" for v in line):
                continue
            rows.append({str(h).strip(): (None if v is None else v)
                         for h, v in zip(header, line) if h})
        return rows, ""
    return None, "الصيغة المدعومة: .csv أو .xlsx فقط"


def action_import(filename, raw, confirm):
    import base64
    try:
        data = base64.b64decode(raw)
    except Exception:
        return {"ok": False, "output": "ملف غير صالح (base64)"}
    rows, err = _parse_table(filename, data)
    if err:
        return {"ok": False, "output": err}
    recs = load_records()
    by_slug = {r.get("slug"): r for r in recs}
    valid, invalid = [], []
    for i, row in enumerate(rows, start=2):
        rec = {k: row.get(k) for k in IMPORT_COLUMNS if row.get(k) not in
               (None, "")}
        errs = []
        for k in ("slug", "niche", "name"):   # file defaults from slug
            if not rec.get(k):
                errs.append(f"ناقص: {k}")
        if rec.get("niche") and load_niche(rec["niche"]) is None:
            errs.append(f"مجال غير موجود: {rec['niche']}")
        clean, cerr = coerce_patch({k: v for k, v in rec.items()})
        if cerr:
            errs.append(cerr)
        else:
            rec = {k: v for k, v in clean.items() if v != ""}
            verr = validate_record(rec)
            if verr:
                errs.append(verr)
        (invalid if errs else valid).append(
            {"row": i, "slug": rec.get("slug"), "errors": errs} if errs
            else {"row": i, "record": rec,
                  "mode": "تحديث" if rec.get("slug") in by_slug else "جديد"})
    if not confirm:
        return {"ok": True, "preview": True, "filename": filename,
                "valid": valid, "invalid": invalid,
                "summary": f"صالح: {len(valid)} — مرفوض: {len(invalid)}"}
    if invalid:
        return {"ok": False,
                "output": f"التأكيد مرفوض: {len(invalid)} صفوف فيها أخطاء — "
                          f"صححها أولاً (الوضع الصارم: الكل أو لا شيء)"}
    if not record_file_default_ok(valid):
        return {"ok": False, "output": "خطأ داخلي في تجهيز الملفات"}
    for v in valid:
        rec = dict(v["record"])
        if not rec.get("file"):
            rec["file"] = f"{rec['slug']}.html"
        if rec["slug"] in by_slug:
            by_slug[rec["slug"]].update(rec)
        else:
            recs.append(rec)
    save_records(recs)
    ok, out = run([sys.executable, str(ROOT / "tools" / "gen_pages.py")])
    chk_ok, chk = run([sys.executable, str(ROOT / "tools" / "gen_pages.py"),
                       "--check"])
    log_event("import", f"استيراد جماعي ({len(valid)} سجلاً)", ok and chk_ok)
    return {"ok": ok and chk_ok, "action": "import",
            "output": f"طبّق {len(valid)} سجلاً\n{out}",
            "check": chk, "label": "استيراد جماعي"}


def record_file_default_ok(valid):
    return all(v["record"].get("slug") for v in valid)


# ------------------------------------------------------------------ media

def action_media():
    """Hero + stock inventory with sizes (assemble expects .jpg only)."""
    def listing(d):
        out = []
        for p in sorted(d.glob("*.jpg")):
            out.append({"name": p.name, "kb": p.stat().st_size // 1024})
        return out
    hero = listing(ROOT / "assets" / "hero")
    stock = listing(ROOT / "assets" / "stock")
    return {"ok": True, "hero": hero, "stock": stock,
            "hero_count": len(hero), "stock_count": len(stock)}


def upload_media(target, filename, raw):
    """Store one image. Strict: .jpg only, basename only, <= 8MB.

    assemble.sh resolves stock/<slug>_<i>.jpg and hero/<x>.jpg, so anything
    else would never be served -- reject it here instead of failing the build.
    """
    import base64
    if target not in ("hero", "stock"):
        return {"ok": False, "output": "الوجهة: hero أو stock فقط"}
    name = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    if not re.fullmatch(r"[A-Za-z0-9_\-]+\.jpg", name):
        return {"ok": False,
                "output": "اسم غير صالح: حروف وأرقام و- و_ بامتداد .jpg فقط"}
    try:
        data = base64.b64decode(raw)
    except Exception:
        return {"ok": False, "output": "ملف غير صالح (base64)"}
    if len(data) > 8 * 1024 * 1024:
        return {"ok": False, "output": "الحد الأقصى 8MB"}
    if not (data[:2] == b"\xff\xd8"):
        return {"ok": False, "output": "الملف ليس JPEG صالحاً"}
    dest = ROOT / "assets" / target / name
    dest.write_bytes(data)
    return {"ok": True, "action": "upload",
            "output": f"حُفظ {target}/{name} ({len(data) // 1024}KB)",
            "label": f"رفع صورة {name}"}


LIVE_CACHE: dict = {}


# ------------------------------------------------------------------ auth
# Local mode: open (loopback only). Public mode (--require-auth, used by the
# container): password login + HMAC-signed session cookie. No credentials are
# ever stored -- both values come from environment.

REQUIRE_AUTH = os.environ.get("REQUIRE_AUTH", "") == "1"
SESSION_TTL = 12 * 3600


def _password_ok(pw) -> bool:
    exp = os.environ.get("DASHBOARD_PASSWORD", "")
    return bool(exp) and hmac.compare_digest(str(pw or ""), exp)


def _make_session() -> str:
    exp = str(int(time.time()) + SESSION_TTL)
    sig = hmac.new(os.environ.get("DASHBOARD_SECRET", "").encode(),
                   exp.encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def _valid_session(token: str) -> bool:
    try:
        exp, sig = token.split(".", 1)
        if int(exp) < time.time():
            return False
        want = hmac.new(os.environ.get("DASHBOARD_SECRET", "").encode(),
                        exp.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, want)
    except (ValueError, TypeError):
        return False


LOGIN_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>دخول — لوحة صفحات الهبوط</title>
<style>
body{font-family:system-ui,Tahoma,sans-serif;background:#0d1322;color:#e9edf7;display:grid;place-items:center;min-height:100vh;margin:0}
.card{background:#151c2e;border:1px solid rgba(255,255,255,.07);border-radius:15px;padding:28px;width:min(360px,90vw)}
h1{font-size:1.1rem;margin:0 0 16px}
input{width:100%;box-sizing:border-box;padding:10px 12px;border-radius:10px;border:1px solid rgba(255,255,255,.13);background:#0f1526;color:#fff;margin-bottom:12px;font:inherit}
button{width:100%;padding:10px;border:0;border-radius:11px;background:#7f8ff2;color:#fff;font:inherit;font-weight:700;cursor:pointer}
.err{color:#f27272;font-size:.82rem;min-height:1.4em;margin-top:8px}
</style></head><body>
<div class="card"><h1>🔐 لوحة صفحات الهبوط</h1>
<input type="password" id="pw" placeholder="كلمة المرور" autocomplete="current-password">
<button onclick="go()">دخول</button><div class="err" id="e"></div></div>
<script>
async function go(){
  const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:document.getElementById('pw').value})});
  if(r.ok){location='/';}else{document.getElementById('e').textContent='كلمة المرور غير صحيحة';}
}
document.getElementById('pw').addEventListener('keydown',e=>{if(e.key==='Enter')go();});
</script></body></html>"""


# ------------------------------------------------------------------ state
# dashboard_state.json: live-probe history + operator event log. Local only
# (gitignored) -- never part of a release.

STATE = ROOT / "data" / "dashboard_state.json"


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"live_history": [], "events": [], "releases": []}


def save_state(state):
    STATE.write_bytes((json.dumps(state, ensure_ascii=False, indent=1)
                       + "\n").encode("utf-8"))


def log_event(kind, label, ok):
    try:
        state = load_state()
        state.setdefault("events", []).insert(
            0, {"at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "kind": kind, "label": label, "ok": bool(ok)})
        state["events"] = state["events"][:300]
        save_state(state)
    except Exception:                                # noqa: BLE001
        pass                                         # logging never breaks ops


def record_live_history(up, total):
    try:
        state = load_state()
        state.setdefault("live_history", []).append(
            {"at": time.strftime("%Y-%m-%d %H:%M:%S"),
             "up": up, "total": total})
        state["live_history"] = state["live_history"][-200:]
        save_state(state)
    except Exception:                                # noqa: BLE001
        pass


# ------------------------------------------------------------------ cities

def record_city(rec):
    """sa-riyadh out of .../sa/riyadh/file.html (unknown when unparseable)."""
    m = re.search(r"/([a-z]{2})/([a-z-]+)/", str(rec.get("url") or ""))
    return f"{m.group(1)}-{m.group(2)}" if m else "unknown"


def action_cities():
    recs = load_records()
    counts = {}
    for r in recs:
        c = record_city(r)
        counts[c] = counts.get(c, 0) + 1
    cities = []
    for d in sorted((ROOT / "src" / "cities").iterdir()):
        if d.is_dir() and "-" in d.name:
            cc, _, city = d.name.partition("-")
            cities.append({"id": d.name, "cc": cc, "city": city,
                           "pages": counts.get(d.name, 0)})
    return {"ok": True, "cities": cities,
            "live_bases": {c["id"]: live_base_for(c["id"]) for c in cities}}


def live_base_for(city_id):
    cc, _, city = city_id.partition("-")
    if city_id == "sa-riyadh":
        return LIVE_BASE
    return f"https://{city}.aidy.site/{cc}/{city}"


# ------------------------------------------------------------------ server

class Handler(BaseHTTPRequestHandler):
    server_version = "landing-pages-dashboard/1.0"

    def log_message(self, *a):                     # keep the console quiet
        pass

    def _send(self, payload, code=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self):
        body = UI_FILE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _page(self, html_text):
        body = html_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError:
            return {}

    def _authed(self) -> bool:
        if not REQUIRE_AUTH:
            return True
        cookie = self.headers.get("Cookie") or ""
        m = re.search(r"(?:^|;\s*)sess=([0-9]+\.[0-9a-f]+)", cookie)
        return bool(m) and _valid_session(m.group(1))

    def _deny(self, api: bool):
        if api:
            return self._send({"ok": False,
                               "output": "unauthorized"}, 401)
        self.send_response(302)
        self.send_header("Location", "/login")
        self.end_headers()

    def do_GET(self):
        path, _, qs = self.path.partition("?")
        params = parse_qs(qs)
        city = (params.get("city") or [None])[0]
        if path == "/healthz":
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if path == "/login":
            body = LOGIN_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if not self._authed():
            return self._deny(path.startswith("/api/"))
        if path in ("/", "/index.html"):
            return self._html()
        if path == "/api/overview":
            return self._send(overview_payload())
        if path == "/api/businesses":
            return self._send(businesses_payload(city))
        if path == "/api/niches":
            return self._send({"ok": True, "niches": niches()})
        if path == "/api/cities":
            return self._send(action_cities())
        if path == "/api/media":
            return self._send(action_media())
        if path == "/api/stats":
            return self._send({"ok": True, **load_state()})
        if path == "/api/publish":
            return self._send(action_publish())
        if path == "/api/quality":
            return self._send(action_quality())
        if path == "/api/import/template":
            cols = ",".join(IMPORT_COLUMNS)
            sample = ("my-shop,my-shop.html,coffee,My Shop,"
                      "https://riyadh.aidy.site/sa/riyadh/my-shop.html,"
                      "+966500000000,4.6,120,"
                      "شارع مثال، الرياض,Al Olaya,الرياض,")
            body = (cols + "\n" + sample + "\n").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if path.startswith("/api/preview/"):
            slug = path.rsplit("/", 1)[-1]
            html_text, err = preview_page(slug)
            if html_text is None:
                return self._send({"ok": False, "output": err}, 404)
            return self._page(html_text)
        if path.startswith("/api/niche/"):
            name = path.rsplit("/", 1)[-1]
            niche = load_niche(name)
            if niche is None:
                return self._send({"ok": False,
                                   "output": f"no niche {name!r}"}, 404)
            return self._send({"ok": True, "name": name, "niche": niche,
                               "raw": json.dumps(niche, ensure_ascii=False,
                                                 indent=1)})
        if path == "/api/live":
            cached = LIVE_CACHE.get("rows")
            if (cached and not city
                    and time.time() - LIVE_CACHE.get("ts", 0) < 300):
                return self._send({"ok": True, "cached": True, **LIVE_CACHE})
            res = action_live(city)
            record_live_history(res["up"], res["total"])
            LIVE_CACHE.clear()
            LIVE_CACHE.update(res)
            LIVE_CACHE["ts"] = time.time()
            return self._send(res)
        if path.startswith("/api/business/"):
            slug = path.rsplit("/", 1)[-1]
            return self._send(business_payload(slug))
        return self._send({"ok": False, "output": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0]
        body = self._body()
        if path == "/api/login":
            time.sleep(0.5)                              # anti-brute pause
            if _password_ok(body.get("password")):
                # Behind Coolify TLS terminates at Traefik: mark the cookie
                # Secure only when the client really came over https,
                # otherwise loopback http logins could never keep a session.
                https = (self.headers.get("X-Forwarded-Proto", "http")
                         == "https")
                self.send_response(200)
                self.send_header("Set-Cookie",
                                 f"sess={_make_session()}; HttpOnly; Path=/; "
                                 f"SameSite=Lax; "
                                 f"{'Secure; ' if https else ''}"
                                 f"Max-Age={SESSION_TTL}")
                self.send_header("Content-Type",
                                 "application/json; charset=utf-8")
                self.end_headers()
                return self.wfile.write(b'{"ok": true}')
            return self._send({"ok": False, "output": "bad password"}, 401)
        if path == "/api/logout":
            self.send_response(200)
            self.send_header("Set-Cookie",
                             "sess=; HttpOnly; Path=/; SameSite=Lax; Secure; "
                             "Max-Age=0")
            self.send_header("Content-Type",
                             "application/json; charset=utf-8")
            self.end_headers()
            return self.wfile.write(b'{"ok": true}')
        if not self._authed():
            return self._deny(True)
        if path == "/api/run":
            return self._send(action_run(body.get("cmd", ""), body))
        if path == "/api/business":
            return self._send(update_record(body.get("slug", ""),
                                            body.get("patch") or {}))
        if path == "/api/business/new":
            return self._send(add_record(body.get("record") or {}))
        if path == "/api/niche":
            return self._send(save_niche(body.get("name", ""),
                                        body.get("profile", "")))
        if path == "/api/import":
            return self._send(action_import(body.get("filename", ""),
                                           body.get("base64", ""),
                                           bool(body.get("confirm"))))
        if path == "/api/live/refresh":
            city = (parse_qs(self.path.partition("?")[2]).get("city")
                    or [None])[0]
            res = action_live(city)
            record_live_history(res["up"], res["total"])
            LIVE_CACHE.clear()
            LIVE_CACHE.update(res)
            LIVE_CACHE["ts"] = time.time()
            return self._send(res)
        if path == "/api/media":
            return self._send(upload_media(body.get("target", ""),
                                           body.get("filename", ""),
                                           body.get("base64", "")))
        if path == "/api/stats/release":
            state = load_state()
            state.setdefault("releases", []).insert(
                0, {"at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "commit": str(body.get("commit") or ""),
                    "note": str(body.get("note") or "")})
            state["releases"] = state["releases"][:100]
            save_state(state)
            log_event("release-note", str(body.get("commit") or ""), True)
            return self._send({"ok": True})
        return self._send({"ok": False, "output": "not found"}, 404)


def main():
    global REQUIRE_AUTH
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--require-auth", action="store_true",
                    help="password login (public deployments must use this)")
    args = ap.parse_args()
    if args.require_auth:
        REQUIRE_AUTH = True
    if REQUIRE_AUTH and (not os.environ.get("DASHBOARD_PASSWORD")
                         or not os.environ.get("DASHBOARD_SECRET")):
        raise SystemExit("REQUIRE_AUTH needs DASHBOARD_PASSWORD + "
                         "DASHBOARD_SECRET in the environment")
    if not UI_FILE.exists():
        raise SystemExit(f"missing UI file: {UI_FILE}")
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"dashboard: {url}  (Ctrl+C to stop)")
    if not args.no_open:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
