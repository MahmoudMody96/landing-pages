#!/bin/bash
# Assemble the static web root for the Docker image (run at build time).
# Usage: assemble.sh <staging-dir> <html-out> [base-url]
#   1. city pages   -> <html-out>/<cc>/<city>/*.html
#   2. niche heroes -> <html-out>/hero/<niche>.jpg
#   3. every stock/<slug>_<i>.jpg referenced by the pages is resolved to a
#      local file: the business's own photo when assets/stock/<slug>_<i>.jpg
#      exists, otherwise the shared <niche>-<i>.jpg named by
#      stock_manifest.json (build FAILS if neither exists — fail loud, not
#      404 later)
#   4. gen_index.sh -> root index + per-city gateway + sitemap.xml
#
# Needs: bash, awk, grep, tr, cp, find (busybox versions are fine).
set -euo pipefail

SRC="${1:?usage: assemble.sh <staging-dir> <html-out> [base-url]}"
HTML="${2:?usage: assemble.sh <staging-dir> <html-out> [base-url]}"
BASE_URL="${3:-https://pages.aidy.site}"

mkdir -p "$HTML"

# Repo layout is cities/<cc>-<city>/ but the web root is <cc>/<city>/.
for city_src in "$SRC"/cities/*/; do
  base="$(basename "$city_src")"        # e.g. sa-riyadh
  case "$base" in
    *-*) cc="${base%%-*}"; city="${base#*-}" ;;
    *) echo "ERROR: city dir '$base' does not follow <cc>-<city> naming" >&2; exit 1 ;;
  esac
  mkdir -p "$HTML/$cc/$city"
  cp "$city_src"*.html "$HTML/$cc/$city/"
done

mkdir -p "$HTML/hero"
cp "$SRC/hero-src/"*.jpg "$HTML/hero/"

mkdir -p "$HTML/stock"

# slug -> niche map (stock_manifest.json is machine-generated, stable shape:
# two-space-indented "slug": { blocks with a "niche": "<niche>" line).
declare -A NICHE_OF
while IFS='=' read -r slug niche; do
  if [ -n "$slug" ] && [ -n "$niche" ]; then
    NICHE_OF["$slug"]="$niche"
  fi
done < <(awk -F'"' '/^  "/{slug=$2} /"niche"/{print slug"=" $4}' "$SRC/stock_manifest.json")

# Page URLs are absolute (https://host/stock/...) — extract the stock/ tail.
# tr splits lines into bare tokens; sed pulls the stock/<file>.jpg part.
# Tooling notes (alpine busybox): no grep -o, no grep --include
# (use find -name + grep -h instead).
STOCK_URLS=$(find "$HTML" -name '*.html' -exec grep -h 'stock/' {} + \
  | tr ' "\t' '\n\n\n' \
  | sed -n 's|.*\(stock/[^ ]*\.jpg\).*|\1|p' \
  | sort -u)
missing=0
while IFS= read -r url; do
  [ -n "$url" ] || continue
  file="${url#stock/}"                  # <slug>_<i>.jpg
  idx="${file##*_}"; idx="${idx%.jpg}"  # <i>
  slug="${file%_"$idx".jpg}"            # <slug>
  # Prefer the business's OWN photo when one was localized into assets/stock
  # (tools/localize_images.py writes <slug>_<i>.jpg). Only when there is no
  # such file do we fall back to the shared niche image for that category.
  own="$SRC/stock-src/$file"
  niche="${NICHE_OF[$slug]:-}"
  src="$SRC/stock-src/${niche}-${idx}.jpg"
  if [ -f "$own" ]; then
    cp "$own" "$HTML/stock/$file"
  elif [ -n "$niche" ] && [ -f "$src" ]; then
    cp "$src" "$HTML/stock/$file"
  else
    echo "ERROR: no local source for referenced $url" >&2
    missing=1
  fi
done <<EOF
$STOCK_URLS
EOF

if [ "$missing" != "0" ]; then
  echo "assembly failed: unresolved stock references" >&2
  exit 1
fi

# Final gate: every local image referenced by any page must exist
# (catches hero typos and any stock URL the resolver missed).
# Two plain greps (no \| alternation) for busybox compatibility.
while IFS= read -r path; do
  [ -n "$path" ] || continue
  if [ ! -f "$HTML/$path" ]; then
    echo "ERROR: referenced image missing from web root: $path" >&2
    missing=1
  fi
done <<EOF
$({ find "$HTML" -name '*.html' -exec grep -h 'stock/' {} +
    find "$HTML" -name '*.html' -exec grep -h 'hero/' {} +; } \
  | tr ' "\t' '\n\n\n' \
  | sed -n -e 's|.*\(stock/[^ ]*\.jpg\).*|\1|p' -e 's|.*\(hero/[^ ]*\.jpg\).*|\1|p' \
  | sort -u)
EOF
[ "$missing" = "0" ] || exit 1

bash "$SRC/gen_index.sh" "$HTML" "$BASE_URL"

# static companions: custom 404 (templates/404.html) + robots.txt is already
# written by gen_index.sh above
if [ -f "$SRC/404.html" ]; then
  cp "$SRC/404.html" "$HTML/404.html"
fi

echo "assembled: $(find "$HTML" -name '*.html' | wc -l) html files,"
echo "  hero: $(ls "$HTML/hero" | wc -l) files, stock: $(ls "$HTML/stock" | wc -l) files"
