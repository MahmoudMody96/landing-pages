import json
import os

# The output dir is intentionally NOT committed (see .gitignore / tools/README.md),
# so create it on demand instead of assuming it exists.
os.makedirs('prospects', exist_ok=True)

d = json.load(open('data/selected_30.json', encoding='utf-8'))

def slug_to_link(b):
    sf = b.get('source_file', '')
    if sf:
        return f"https://riyadh.aidy.site/sa/riyadh/{sf}"
    return ''

lines = ["# كيت التواصل — 30 بزنس في الرياض", "", "| # | البزنس | التقييم | الواتساب | لينك الصفحة الجاهزة |", "|---|---|---|---|---|"]
n = 0
for b in d:
    ph = b['phone'].strip()
    if not ph:
        continue
    n += 1
    link = slug_to_link(b)
    lines.append(f"| {n} | {b['name'].strip()} | {b['rating']}★ ({b['reviewCount']}) | {ph} | {link} |")

lines += ["", f"**الإجمالي: {n} بزنس عندهم رقم واتساب**", ""]

# stats
no_site = [b for b in d if not b['website'].strip() or b['website'].strip().lower() in ('n/a','none','')]
lines.append(f"## ملاحظات مهمة")
lines.append(f"- بزنس بدون موقع رسمي: {len(no_site)} من {len(d)}")
lines.append(f"- اللي عندهم موقع: {len(d) - len(no_site)}")
lines.append("")
lines.append("### اللي بدون موقع (أقربهم للشراء):")
for b in no_site:
    ph = b['phone'].strip()
    if ph:
        lines.append(f"- {b['name'].strip()} — {b['rating']}★ ({b['reviewCount']}) — {ph}")

out = "\n".join(lines)
open('prospects/whatsapp-outreach-30.md', 'w', encoding='utf-8').write(out)
print(out[:3000])
print("...")
print("SAVED: prospects/whatsapp-outreach-30.md")
