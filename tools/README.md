# tools/ — سكربتات البناء والترحيل

سكربتان فقط يُستخدمان باستمرار: خط التمبليت (أدناه) و`gen_pages.py`. باقي السكربتات
اشتغلت مرة واحدة أثناء بناء صفحات الرياض الـ 30 ومحفوظة للمرجعية — كل سكربت مستقل،
واقرأ الـ docstring أعلى الملف قبل التشغيل.

## خط إنتاج التمبليت (دائم — أي تعديل بيمر من هنا)

الصفحات مش مكتوبة بالإيد: `templates/page.html` سكيليتون + `templates/niches/<المجال>.json`
بيانات المجال المشتركة + سجل واحد لكل محل في `data/businesses.json`. تعديل صفحة =
تعديل بيانات، وبعدين:

| الملف | الدور | ملاحظات |
|---|---|---|
| `pagekit.py` | محرّك البناء: الهروب (escaping)، إعادة بناء JSON-LD وجدول المواعيد والمعرض، `render()` | مكتبة — يُستورَد من `gen_pages.py` |
| `shapes.py` | الأشكال المتكررة (boilerplate) اللي بتحوّل نص الصفحة لقالب `{token}` | مكتبة أيضاً |
| `bootstrap_template.py` | يستخرج `templates/page.html` من صفحة قائمة (عليها فحص ذاتي: مفيش قيمة محل تفضل في السكيليتون) | ⚠️ يعيد كتابة `data/businesses.json` |
| `extract_pages.py` | يقرأ الصفحات المنشورة → `data/extracted.json` (مستثنى من git) | خطوة تهيئة |
| `build_niches.py` | `extracted.json` → `templates/niches/*.json` + سجلات مقلّمة | ⚠️ يعيد كتابة `data/businesses.json` — يرفض العمل مع تغييرات غير ملتزمة إلا بـ`--force` |
| `gen_pages.py` | يولّد الصفحات من البيانات + التمبليت | `--check` البوابة |
| `release.sh` | إصدار آمن: `--check` + `localize --check` + رفض الشجرة المتسخة + orphan-push للعام | `bash tools/release.sh "Release: ..."` |
| `fix_copy_v1.py` | إصلاح نصوص one-off (تسرب الـdistrict + اللهجة + عناوين فريدة) — idempotent | ⚠️ أُنجز دوره؛ لا تشغّله إلا لمدينة جديدة بنفس العيوب |

### القاعدة الذهبية

`python tools/gen_pages.py --check` لازم يقول `PASS` قبل أي commit. لو قال mismatch،
الرسالة بتحدّد أول حرف مختلف (مع 30 حرف قبله وبعده) — تُصلَّح في البيانات مش في الصفحات.
`python tools/gen_pages.py` بيكتب بس الصفحات اللي اتغيرت فعلًا (idempotent).

### الهروب (escaping)

كل قيمة نصية في الصفحات = `html.escape(v, quote=True)` بالضبط — اتأكدنا على 1650 قيمة.
ملفات البيانات تحتفظ بالنص الخام؛ الهروب بيحصل مرة واحدة على طريق الدخول لـHTML.
`pagekit.FINAL_KEYS` و`NO_PLAIN_ESCAPE` هما اللي بيمنعوا الهروب المزدوج للي اتنمّل
بالـtoken؛ القيم الجاهزة (CSS/JSON/HTML/روابط) تُدرج كما هي.

### إضافة محل جديد

انسخ أي سجل في `data/businesses.json`، خلّص فيه `slug`/`niche`/`name` والحاجات اللي
تختلف فعلًا، واحذف كل حاجة بقيمة افتراضية للمجال (النسق، الخدمات، الأسئلة، نصوص SEO،
«سنوات الخبرة») — المحذوف يروح تلقائيًا لملف المجال، والمحل الجديد يكمل ~20 سطرًا.
الصور تفضل صور الـstock للمجال إلا لو حطيت `photos` أو `hero_url`. بعدها:
`python tools/gen_pages.py --check`.

> تتطلب `openpyxl` لسكربتات الشيت: `pip install openpyxl`
> بعض السكربتات القديمة فيها مسار `ROOT` مطلق قديم (`D:\...`) — حدّثه لمسارك قبل التشغيل.

## الشيت (Excel)

| السكربت | الوظيفة | الحالة |
|---|---|---|
| `build_sheet_v3.py` | يبني `data/riyadh_businesses_30_v3.xlsx` من `selected_30.json` (الأحدث — المستخدم حالياً) | ✅ الحالي |
| `add_hero_cols.py` | أضاف أعمدة الهيرو (`xlsx` → `_v2.xlsx`) | ⚠️ one-off منتهي |
| `add_hero_column_v2.py` | تحديث عمود الهيرو على `_v2.xlsx` | ⚠️ one-off منتهي |

محذوفات: `build_sheet_v2.py` (يطابق `v3` ما عدا اسم ملف الإخراج) و
`add_hero_column.py` (النسخة الأولى، تجاوزتها `v2`) — موجودة في تاريخ git عند الحاجة.

## الصور (Hero / Stock)

| السكربت | الوظيفة |
|---|---|
| `fetch_heroes.py` | تحميل 6 صور الهيرو 4K من Unsplash (صورة لكل مجال) إلى `assets/hero/` |
| `fetch_hero_cands.py` | تحميل بدائل عريضة للمجالات التي كانت صورها طولية. مجلد الإخراج `assets/hero_candidates/` **محلي فقط** (مستثنى من git ومن سياق Docker) — أُزيل من الريبو بعد ما خلص دوره |
| `fix_portrait_heroes.py` | توجيه الصفحات ذات الهيرو الطولي لصور الهيرو العريضة |
| `wire_heroes.py` | توجيه صفحات الـ stock للهيرو 4K الخاص بمجالها |
| `audit_heroes.py` | استخراج كل روابط الهيرو الحية + تحميلها للمراجعة البصرية. مخرجاته: `hero_audit.json` (**متتبَّع** — يقرأه `inject_seo.py`) ومجلد `hero_audit/` (**محلي فقط** — صور مراجعة بصرية، مستثنى من git). أُعيد بناء `hero_audit.json` من الصفحات الحية (23 هيرو 4K / 7 صور حقيقية) — أعد التشغيل لو تغيّرت الصفحات |
| `localize_images.py` | **توطين الصور الخارجية (إلزامي)** — ينزّل كل صورة `lh3.googleusercontent.com` من الصفحات، يطبّعها (قص 16:9 + 1600×900)، يحفظها `assets/stock/<slug>_<i>.jpg`، ويعيد كتابة الصفحات على `pages.aidy.site`. `--check` تقرير فقط · `--from-plan` يعيد توليد الأصل بدون لمس الصفحات. جوجل بتدوّر الروابط وبتعمل rate-limit، والصفحة بتفقد صورها **بصمت** — فممنوع hotlink |
| `gen_outreach.py` | يبني كيت تواصل واتساب للـ30 محل في `prospects/whatsapp-outreach-30.md`. المجلد **محلي فقط** (مستثنى من git) والسكربت بينشئه لوحده (`os.makedirs`) |

## التحسين البصري

| السكربت | الوظيفة |
|---|---|
| `upgrade_visual.py` | تحسين بصري لصفحات الـ stock-hero (تخفيف الـ overlay + معرض + CTA) |
| `upgrade_visual2.py` | نفس التحسين لصفحات الصور الحقيقية (مع الاحتفاظ بصور Google كهيرو) |
| `inject_seo.py` | حقن JSON-LD (LocalBusiness بأنواعه) في الصفحات من بيانات Google — idempotent (`--check` للتحقق فقط) |
| `inject_tracking.py` | التحليلات: بقى يتحقّق بس — `pagekit.tracking_block()` هو اللي بيبني السكربت من `templates/tracking.json` جوه `{{tracking}}` قبل `</head>`، فـ`gen_pages.py` بيولّده. تشغيله على صفحة متولّدة = no-op (verified) |

## لوحة الإدارة

| الملف | الدور | ملاحظات |
|---|---|---|
| `dashboard.py` | كونسول محلي (stdlib بس) على `127.0.0.1` — يقدّم `dashboard_ui.html` و API: `/api/overview` · `/api/businesses` · `/api/business/<slug>` · `/api/niches`+`/api/niche` (محرر المجالات) · `/api/preview/<slug>` · `/api/quality` · `/api/media` (رفع jpg صارم) · `/api/import` (جماعي CSV/xlsx: معاينة ثم تأكيد) · `/api/cities` · `/api/run` (check/gen/build-sim/media-check/release) · `/api/live` · `/api/stats` (سجل محلي مهمل) · `/api/publish` · `POST /api/business` (تعديل) · `POST /api/business/new` | بيكتب `data/businesses.json` بنفس شكل `build_niches.py` (بايت LF، `indent=1`)، بيولّد، وبعدها `--check`. الـslug ثابت. الأرقام تُحوَّل لأنواعها قبل الحفظ (إصلاح عيب كان يكسر التوليد) |
| `dashboard_ui.html` | واجهة عربية RTL بتابات: نظرة عامة · الصفحات والسجلات · الفحوصات · النشر · السجل | تفلتر client-side |

على ويندوز محتاج انتباه لثلاثة شوكات (كلهم اتظبطوا في الكود، اتفهموا بس):

1. **`CODEBUDDY_SAFE_DELETE_ENABLED=0`** قبل تشغيل الخدمة — محاكاة البناء
   بتعمل staging فيها ~146 ملف، وحارس حذف WorkBuddy الجماعي (سقف 50 في
   الدورّة) كان يرفض التنظيف، والاستثناء بيطلع من `shutil.rmtree` جوه
   `finally` في **قتل رد الـHTTP** (curl يشف Empty body). التنظيف دلوقتي
   متين وبيرجّع تحذير لو المجلد فضل، ومجلدات `lp-sim-*/` مستثناة من git.
2. **`bash` على ويندوز ممكن يبقى WSL stub** (`C:\Windows\System32\bash.exe`)
   اللي بيموت بـ«no installed distributions». `find_bash()` بيفحص المرشّحين
   بـ`--version` وبيختار أول Git bash حقيقي.
3. **`find` على ويندوز = `find.exe`** مش GNU find (بيرجع «File not found -
   *.html»). فحص المخرجات (مسارات مسروقة · صور خارجية · `{{` متبقية ·
   `<loc>`) بيتم في بايثون (`scan_output`) — نتيجته واحدة على كل جهاز،
   ومتحقّق إنه بيمسك العيوب الثلاثة على عيّنة معطوبة.

فحص الحياة بيـpercent-encode أسماء الملفات العربية قبل ما يطلبها —
`urllib` مابيبعتش مسار unicode، والفحص بيقع كـstatus 0 (كذبة «واقعة»).
متحقّق: 30/30 شغّالة على الدومين الحقيقي.

## ⛔ سكربتات متوقفة عن التوجيه اليدوي للصفحات

`inject_seo.py` و`upgrade_visual*.py` و`wire_heroes.py` و`fix_portrait_heroes.py`
كانت بتعدّل ملفات الـHTML بإيدها. النتيجة بقت بتتبني من `data/businesses.json`:
JSON-LD من حقل `jsonld` في السجل، التصميم من `templates/niches/*.json`، وكان التوجيه
بيعمل تغييرات على الأقراص مش في البيانات — فتشغيل أي واحد منهم يخالف
`gen_pages.py --check` (PASS → MISMATCH). التعديل الصح للتصميم/SEO/الصور دلوقتي هو:
عدّل `pagekit.py` أو ملف المجال أو السجل، وبعدها `python tools/gen_pages.py` —
متعدّلش `src/` بالإيد.

## ⚠️ أي أداة بتكتب ملفات: LF بس

`pagekit`/`gen_pages.py` بيكتبوا بايتات (`write_bytes`) مش `write_text`، لأن
`write_text` على ويندوز بيحوّل كل `\n` لـ`\r\n` — و`--check` (اللي بيقرأ بايتات
دلوقتي) مش هيلاحظ الفرق بينما git هيشوف 30 صفحة "معدّلة" بالكامل. نفس القاعدة
في `bootstrap_template.py` و`build_niches.py` و`extract_pages.py`.
