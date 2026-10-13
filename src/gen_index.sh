#!/bin/bash
# Landing pages index generator — builds a country/city contact sheet.
#
# Reads the assembled web root (in production /usr/share/nginx/html, where the
# layout is <cc>/<city>/*.html next to the image dirs hero/ and stock/) and
# writes:
#   1. <root>/index.html          — global index
#   2. <cc>/<city>/index.html     — per-city gateway
#   3. <root>/sitemap.xml         — sitemap
#
# Usage: gen_index.sh [web-root] [base-url]
set -euo pipefail

ROOT="${1:-/data/landing-pages}"
BASE_URL="${2:-https://pages.aidy.site}"
OUT="$ROOT/index.html"
TODAY=$(date -u +%F)

xml_escape() {
  # minimal XML escaping for URLs (filenames here contain Arabic, not &<>)
  printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'
}

# Readable Arabic labels for the page chrome. Unknown codes fall back to the
# raw value, so adding a country/city never needs a code change here.
country_label() {
  case "$1" in
    sa) echo 'السعودية' ;;
    ae) echo 'الإمارات' ;;
    eg) echo 'مصر' ;;
    kw) echo 'الكويت' ;;
    qa) echo 'قطر' ;;
    bh) echo 'البحرين' ;;
    om) echo 'عمان' ;;
    *)  echo "$1" ;;
  esac
}
city_label() {
  case "$1" in
    riyadh) echo 'الرياض' ;;
    jeddah) echo 'جدة' ;;
    dammam) echo 'الدمام' ;;
    dubai)  echo 'دبي' ;;
    abudhabi) echo 'أبوظبي' ;;
    cairo)  echo 'القاهرة' ;;
    *)      echo "$1" ;;
  esac
}

# Pages of a city dir (excludes the generated gateway itself).
city_pages() {
  find "$1" -maxdepth 1 -name '*.html' ! -name 'index.html' | sort
}

# A top-level dir counts as a country only if it holds at least one <city>/
# dir with real pages. Content-based on purpose: it keeps asset dirs that
# live in the same web root (hero/, stock/, and any future css/ or fonts/)
# out of the index without a hardcoded deny-list that could go stale.
is_country() {
  local d="$1" c
  for c in "$d"*/; do
    [ -d "$c" ] || continue
    if [ -n "$(find "$c" -maxdepth 1 -name '*.html' ! -name 'index.html' -print -quit)" ]; then
      return 0
    fi
  done
  return 1
}

{
  echo '<!DOCTYPE html>'
  echo '<html lang="ar" dir="rtl"><head><meta charset="UTF-8">'
  echo '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
  echo '<title>صفحات الهبوط — فهرس</title>'
  echo '<style>'
  echo 'body{font-family:system-ui,sans-serif;max-width:900px;margin:40px auto;padding:0 20px;background:#f8fafc;color:#0f172a}'
  echo 'h1{font-size:28px;margin-bottom:8px}h2{font-size:20px;margin:32px 0 12px;color:#1F3864}'
  echo 'ul{list-style:none;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}'
  echo 'li{background:#fff;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden}'
  echo 'a{display:block;padding:12px 14px;text-decoration:none;color:#0f172a;font-size:14px}'
  echo 'a:hover{background:#eff6ff}.muted{color:#64748b;font-size:13px;margin-bottom:24px}'
  echo '</style></head><body>'
  echo '<h1>📄 صفحات الهبوط</h1>'
  echo '<p class="muted">فهرس تلقائي — مرتب حسب الدولة ثم المدينة</p>'

  for country_dir in "$ROOT"/*/; do
    [ -d "$country_dir" ] || continue
    is_country "$country_dir" || continue
    cc=$(basename "$country_dir")
    echo "<h2>🌍 $(country_label "$cc")</h2>"
    for city_dir in "$country_dir"*/; do
      [ -d "$city_dir" ] || continue
      city=$(basename "$city_dir")
      count=$(city_pages "$city_dir" | wc -l)
      [ "$count" -gt 0 ] || continue
      echo "<h3 style='font-size:16px;margin:18px 0 8px;color:#334155'>📍 $(city_label "$city") — $count صفحة</h3>"
      echo '<ul>'
      while IFS= read -r f; do
        name=$(basename "$f" .html)
        rel="${f#$ROOT/}"
        echo "<li><a href=\"$rel\">$name</a></li>"
      done < <(city_pages "$city_dir")
      echo '</ul>'

      # City gateway (e.g. riyadh.aidy.site serves <country>/<city>/ directly).
      # Relative links keep it working under any host or sub-path.
      {
        echo '<!DOCTYPE html>'
        echo '<html lang="ar" dir="rtl"><head><meta charset="UTF-8">'
        echo '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        echo "<title>صفحات الهبوط — $(city_label "$city")</title>"
        echo '<style>'
        echo 'body{font-family:system-ui,sans-serif;max-width:900px;margin:40px auto;padding:0 20px;background:#f8fafc;color:#0f172a}'
        echo 'h1{font-size:28px;margin-bottom:8px}'
        echo 'ul{list-style:none;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}'
        echo 'li{background:#fff;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden}'
        echo 'a{display:block;padding:12px 14px;text-decoration:none;color:#0f172a;font-size:14px}'
        echo 'a:hover{background:#eff6ff}.muted{color:#64748b;font-size:13px;margin-bottom:24px}'
        echo '</style></head><body>'
        echo "<h1>📍 $(city_label "$city")</h1>"
        echo "<p class=\"muted\">$count صفحة — $(country_label "$cc")</p>"
        echo '<ul>'
        while IFS= read -r f; do
          file=$(basename "$f")
          name="${file%.html}"
          echo "<li><a href=\"$file\">$name</a></li>"
        done < <(city_pages "$city_dir")
        echo '</ul>'
        echo '</body></html>'
      } > "${city_dir}index.html"
      # Progress log -> stderr. This used to be echoed inside the redirected
      # block above, which wrote the server path into the public index.html.
      echo "city index written: ${city_dir}index.html" >&2
    done
  done

  echo '</body></html>'
} > "$OUT"

echo "index written: $OUT" >&2

# Sitemap for search engines (UTF-8 URLs are valid in sitemaps).
SM="$ROOT/sitemap.xml"
{
  echo '<?xml version="1.0" encoding="UTF-8"?>'
  echo '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
  echo "  <url><loc>$(xml_escape "$BASE_URL/")</loc><lastmod>$TODAY</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>"
  for country_dir in "$ROOT"/*/; do
    [ -d "$country_dir" ] || continue
    is_country "$country_dir" || continue
    for city_dir in "$country_dir"*/; do
      [ -d "$city_dir" ] || continue
      [ -n "$(city_pages "$city_dir" | head -1)" ] || continue
      rel="${city_dir#$ROOT/}"
      echo "  <url><loc>$(xml_escape "$BASE_URL/$rel")</loc><lastmod>$TODAY</lastmod><changefreq>weekly</changefreq><priority>0.7</priority></url>"
      while IFS= read -r f; do
        rel="${f#$ROOT/}"
        echo "  <url><loc>$(xml_escape "$BASE_URL/$rel")</loc><lastmod>$TODAY</lastmod><changefreq>monthly</changefreq><priority>0.6</priority></url>"
      done < <(city_pages "$city_dir")
    done
  done
  echo '</urlset>'
} > "$SM"

echo "sitemap written: $SM" >&2

# robots.txt: allow everything, point crawlers at the sitemap.
{
  echo 'User-agent: *'
  echo 'Allow: /'
  echo "Sitemap: $BASE_URL/sitemap.xml"
} > "$ROOT/robots.txt"
echo "robots written: $ROOT/robots.txt" >&2
