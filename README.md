# Landing Pages — صفحات هبوط للبزنسات المحلية

نظام بناء ونشر صفحات هبوط عربية (RTL) للبزنسات المحلية اللي مالهاش موقع رسمي.
مصدر البيانات: Google Maps (تقييمات، عناوين، مواعيد، صور حقيقية).

---

## الهيكل

```
landing-pages/
├── README.md                 ← الملف ده
├── data/
│   ├── selected_30.json      ← بيانات الـ 30 بزنس (المصدر الأساسي)
│   ├── riyadh_photos.json    ← روابط صور Google لكل محل (المصدر الخام)
│   ├── hours_data.json       ← مواعيد العمل
│   ├── stock_manifest.json   ← فهرس صور المجال البديلة لكل محل
│   ├── hero_manifest.json    ← فهرس صور الهيرو 4K للمجالات
│   ├── localize_plan.json    ← سجل توطين الصور (مولّد بـ tools/localize_images.py)
│   └── riyadh_businesses_30_v3.xlsx  ← الشيت (محلي فقط — مستثنى من git والبناء)
├── src/
│   ├── gen_index.sh          ← مولّد فهرس الصفحات
│   └── cities/
│       └── sa-riyadh/        ← 30 صفحة هبوط (النسخة النهائية)
├── assets/
│   ├── hero/                 ← 6 هيرو 4K (لكل مجال) + هيرو حقيقي للمحلات اللي صورتها نضيفة
│   └── stock/                ← 18 صورة مجال مشتركة + صور المحلات الحقيقية + PHOTOS.md
├── templates/
│   ├── page.html             ← هيكل الصفحة (تصميم + {{placeholders}}) — مولّد
│   ├── nginx.conf            ← إعداد nginx
│   ├── tracking.json         ← كونفج التحليلات (معطّل افتراضياً)
│   ├── landing-pages-router.yaml  ← توجيه Traefik (للتشغيل اليدوي فقط)
│   └── niches/               ← بروفايل كل مجال: ثيم + خدمات + كوبي + صور افتراضية
│       ├── coffee.json
│       ├── barbershop.json
│       ├── beauty_salon.json
│       ├── nail_salon.json
│       ├── gym.json
│       └── auto_repair.json
├── docker/
│   └── assemble.sh           ← تجميع مجلد الويب لحظة بناء الإيمج
├── Dockerfile                ← نشر Coolify (nginx + ملفات مبنية)
├── .dockerignore             ← تصغير سياق البناء
├── hero_audit.json           ← فحص الهيرو — مُعمَّت، يقرأه tools/inject_seo.py
└── tools/                    ← سكربتات البناء والترحيل (شوف tools/README.md)
```

### الصفحة تمبليت — البيانات بس هي اللي بتتغيّر

الصفحات في `src/cities/` **مبنية من البيانات**، مش مكتوبة بالإيد. أي صفحة = الثلاث طبقات دي:

| الطبقة | الملف | فيها إيه |
|---|---|---|
| الهيكل | `templates/page.html` | التصميم والـCSS والـJS و`{{placeholders}}` |
| بروفايل المجال | `templates/niches/<niche>.json` | الثيم، الخدمات، الكوبي المتكرر، صورة الهيرو والاستوك الافتراضية، نصوص الـSEO |
| بيانات البزنس | `data/businesses.json` | الاسم، التليفون، العنوان، التقييم، المراجعات، المواعيد، الصور، **والجمل اللي بيها اختصاص** |

القاعدة اللي تخليها تمبليت فعلاً: أي قيمة **مطابقة** للبروفايل بتتشال من سجل البزنس
ويسيبها في `templates/niches/`. اللي يفضل في السجل هو الـ**override** بس. فسجل بزنس
جديد بيبقى 20 سطر تقريباً (شوف `data/businesses.json`).

**عايز تضيف بزنس؟** ضيف سجل في `data/businesses.json` وبعدين:

```bash
python tools/gen_pages.py                 # يولد الصفحات الجديدة/المعدّلة
python tools/gen_pages.py --check         # يثبت إن الـ30 صفحة القديمة ماتغيّرتش
```

الحاجات اللي **مش** محتاجة تتكتب لبوظ جديد: الثيم، الخدمات، الأسئلة الشائعة، نصوص
الـ`<title>`/`meta`/`og:*`، صورة الهيرو، ومعرض الصور (بيعتمد على صور المجال
الافتراضية إلا لو حطيت `photos` بنفسك).

**الهروب (escaping) — العقد:** ملفات البيانات فيها **نص خام** (`&` مش `&amp;`)،
و`tools/pagekit.py` بيعمل `html.escape(v, quote=True)` مرة واحدة على طريق الدخل
للـHTML. ده بالظبط اللي صفحات المشروع بتعمله (اتأكدنا من 1650 قيمة نصية). الجمل
اللي فيها `{name}` / `{rating}` / `{city_ar}` بتتملى وهى بتتهرّب كمان، فتغيير
التقييم أو المدينة في الداتا بيغيّر كل جملة بتذكرهم.

**إعادة بناء التمبليت من الصفحات** (محتاجة بس لو ظهر شكل جديد مش متخمَّن):

```bash
python tools/extract_pages.py     # الصفحات  -> data/extracted.json  (محلي، مستثنى من git)
python tools/build_niches.py      #          -> templates/niches/*.json + data/businesses.json
python tools/gen_pages.py --check # لازم: PASS
```

> ⚠️ `build_niches.py` بيكتب `data/businesses.json` من الأول، فأي تعديل بالإيد بعد
> كده بيضيع. عدّله بالإيد وبس من غير ما تعيد البناء.

---

## البنية على السيرفر

| المسار | الوظيفة |
|---|---|
| `/data/landing-pages/` | الجذر — يخدمه حاوية nginx اسمها `landing-pages` |
| `/data/landing-pages/sa/riyadh/` | صفحات الرياض (30 صفحة) |
| `/data/landing-pages/hero/` | صور الهيرو 4K (لكل مجال واحدة) |
| `/data/landing-pages/stock/` | صور الجاليري |
| `/data/landing-pages/index.html` | الفهرس التلقائي (كل الدول والمدن) |
| `/data/landing-pages/<cc>/<city>/index.html` | بوابة المدينة (يولّدها `gen_index.sh` تلقائياً) |
| `/data/landing-pages/sitemap.xml` | خريطة الموقع لمحركات البحث (يولّدها `gen_index.sh` تلقائياً) |
| `/data/landing-pages/robots.txt` | السماح للزحف + الإشارة للـsitemap (يولّدها `gen_index.sh` تلقائياً) |
| `/data/landing-pages/404.html` | صفحة 404 عربية (من `templates/404.html`، يخدمها nginx عبر `error_page`) |
| `/data/coolify/proxy/dynamic/landing-pages-router.yaml` | توجيه Traefik |

## الروابط الشغالة

| الرابط | الوصف |
|---|---|
| `https://pages.aidy.site/` | فهرس كل الصفحات |
| `https://riyadh.aidy.site/` | بوابة مدينة الرياض |
| `https://riyadh.aidy.site/sa/riyadh/<slug>.html` | صفحة بزنس |
| `https://pages.aidy.site/hero/<niche>.jpg` | صورة هيرو 4K |
| `https://pages.aidy.site/stock/<slug>_<i>.jpg` | صورة جاليري |

---

## إضافة مدينة/دولة جديدة

النظام متصمّم للتوسع. الخطوات:

> عرّف IP السيرفر مرة واحدة في الجلسة (لا تحفظه في الريبو):
> ```bash
> export SERVER_IP=<ip-السيرفر>
> ```

### 1) بناء الهيكل محلياً

```bash
mkdir -p src/cities/<cc>-<city>     # مثال: ae-dubai
# حط صفحات الـ HTML الجديدة في الفولدر ده
```

> **سياسة أسماء الملفات (slugs):** الإنجليزية فقط (`a-z 0-9 -`)، قصيرة وثابتة —
> اسم الملف هو الرابط الدائم ولا يتغير بعد النشر. الاسم العربي يبقى داخل
> `<title>` و `<h1>` والمحتوى فقط. (بعض ملفات الرياض القديمة فيها عربي
> لأسباب تاريخية — لا تُعاد تسميتها لأن روابطها حية، والتزم بالإنجليزية
> في أي مدينة جديدة.)

### 2) رفعها على السيرفر

```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@$SERVER_IP \
  "sudo mkdir -p /data/landing-pages/<cc>/<city> && sudo chown -R ubuntu:ubuntu /data/landing-pages/<cc>"

scp -i ~/.ssh/id_ed25519 src/cities/<cc>-<city>/*.html \
  ubuntu@$SERVER_IP:/data/landing-pages/<cc>/<city>/
```

### 3) إعادة توليد الفهرس

```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@$SERVER_IP \
  "cd /data/landing-pages && bash gen_index.sh /data/landing-pages && sudo docker restart landing-pages"
```

### 4) إضافة دومين فرعي (اختياري)

**أ) راوتر Traefik** — عدّل `templates/landing-pages-router.yaml` و ضيف راوتر جديد:
```yaml
    lp-<city>-http:
      rule: "Host(`<city>.aidy.site`)"
      ...
```
ثم ارفع الملف و ريستارت البروكسي:
```bash
scp -i ~/.ssh/id_ed25519 templates/landing-pages-router.yaml \
  ubuntu@$SERVER_IP:/tmp/lp.yaml
ssh -i ~/.ssh/id_ed25519 ubuntu@$SERVER_IP \
  "sudo cp /tmp/lp.yaml /data/coolify/proxy/dynamic/landing-pages-router.yaml && rm /tmp/lp.yaml"
```

**ب) بوابة المدينة في nginx** — ضيف سطراً في `map $host $city_gateway`
داخل `templates/nginx.conf`:
```nginx
    <city>.aidy.site /<cc>/<city>/;
```
ثم ارفع `nginx.conf` على السيرفر وأعد إنشاء/تشغيل حاوية `landing-pages`
(حسب طريقة تركيب الكونف عندك — mount أو bake في الإيمج).
من غير السطر ده، جذر `<city>.aidy.site/` يعرض الفهرس العام بدل بوابة المدينة.

---

## نشر الصور (Hero + Gallery)

الصفحات تشير لصور مستضافة على السيرفر — HTML وحده لا يكفي:

| النوع | الملفات محلياً | تُرفع إلى | تُخاطَب كـ |
|---|---|---|---|
| الهيرو (مجال) | `assets/hero/<niche>.jpg` | `/data/landing-pages/hero/` | `https://pages.aidy.site/hero/<niche>.jpg` |
| الهيرو (محل) | `assets/hero/<slug>.jpg` | `/data/landing-pages/hero/` | `https://pages.aidy.site/hero/<slug>.jpg` |
| الجاليري | `assets/stock/<niche>-<i>.jpg` أو `<slug>_<i>.jpg` | `/data/landing-pages/stock/` | `https://pages.aidy.site/stock/<slug>_<i>.jpg` |

> **ممنوع hotlink.** أي صورة على صفحة عميل لازم تكون على `pages.aidy.site` — ممنوع
> `lh3.googleusercontent.com` أو أي دومين خارجي. جوجل بتدوّر الروابط وبتعمل rate-limit،
> والصفحة بتفقد صورها **بصمت** (مفيش خطأ، الصورة بتبقى مكسورة). لتوطين صور مدينة:
> ```bash
> python tools/localize_images.py --check   # تقرير
> python tools/localize_images.py           # تنزيل + إعادة كتابة
> ```
> السكربت مش بيكتب أي صفحة قبل ما كل التنزيلات تنجح، وقابل للاستكمال لو اتقطع.

> **انتبه للتسمية:** ملفات الجاليري المشتركة محلياً بأسماء **المجال** (`coffee-1.jpg`)،
> لكنها تُرفع بأسماء **المحلات** (`carve-coffee-bar_1.jpg`). مثال:
> ```bash
> # محل جديد بمجال الكوفي: انسخ صور المجال بأسماء المحل ثم ارفعها
> cp assets/stock/coffee-1.jpg /tmp/<slug>_1.jpg
> cp assets/stock/coffee-2.jpg /tmp/<slug>_2.jpg
> scp -i ~/.ssh/id_ed25519 /tmp/<slug>_*.jpg \
>   ubuntu@$SERVER_IP:/data/landing-pages/stock/
> ```
> مجال جديد تماماً (مطعم، عيادة...)؟ ضيف صوره في `assets/stock/PHOTOS.md`
> أولاً (قاعدة: بلا لوجو محل تاني)، ثم ارفع الهيرو لـ `/hero/` والجاليري لـ `/stock/`.
>
> **لو النشر عبر Coolify** (القسم التالي): لا ترفع شيئاً يدوياً —
> `docker/assemble.sh` يبني نفس التسمية (`<slug>_<i>.jpg`) تلقائياً من
> `assets/stock/` لحظة بناء الإيمج. الأولوية لصورة المحل نفسها
> (`assets/stock/<slug>_<i>.jpg`) وإن مالقاهاش يرجع لصورة المجال عبر
> `stock_manifest.json`. البناء يفشل بصوت عالٍ لو الاتنين مش موجودين.

---

## النشر عبر Coolify (الطريقة الأساسية)

> الحالة الحية: Project `Landing-Pages` ← Application `landing-pages`
> (`f3c9chhue2nistvynkpjcreb`) — النشر يدوياً من Coolify UI (زر Redeploy)
> أو عبر `POST /api/v1/deploy` (الدليل: جلسة النشر). التشغيل التلقائي عند
> الدفع يتطلب Webhook يدوياً (تطبيق public بلا GitHub App).

### الريبو المزدوج (مهم)

| الريمووت | الريبو | الدور |
|---|---|---|
| `origin` | `MahmoudMody96/riyadh-landing-pages` (خاص) | التطوير + الـ history الكاملة |
| `public` | `MahmoudMody96/landing-pages` (عام) | لقطات release فقط — ما يراقبه Coolify |

السبب: الـ GitHub App الخاص لا يرى الريبو الخاص، والـ history القديمة فيها
IP السيرفر — لذلك العام يستقبل squash نظيفاً فقط، بلا تاريخ.

### إصدار نسخة جديدة (release)

الطريقة الآمنة — سكربت يفحص البوابات قبل النشر (template سليم + لا hotlink + شجرة نظيفة):

```bash
bash tools/release.sh "Release: <وصف مختصر>"
```
(على ويندوز: نفّذه من Git Bash — الـ`bash` الافتراضي قد يكون WSL stub.)

أو يدوياً (نفس الخطوات):

```bash
git checkout -q --orphan rel-tmp
git add -A
git commit -q -m "Release: <وصف مختصر>"
git push -q -f public rel-tmp:main
git checkout -q main
git branch -D rel-tmp
```
الـ force-push يحدّث الريبو العام؛ ثم Deploy من Coolify UI (أو API)
لإطلاق البناء (لا webhook تلقائياً لتطبيق public).

> ⚠️ **`git add -A` بينشر كل ملف غير متجاهَل على ريبو عام.** قبل أي release:
> ```bash
> git status --porcelain --ignored=no   # لازم تبان بس الملفات اللي عايزها
> ```
> الملفات دي محميَّة بـ `.gitignore` (سكربت التواصل + الأسعار + أرقام العملاء):
> `data/*.xlsx` · `data/*.bak-*.xlsx` · `data/outreach_*.json` ·
> `data/*arabic_review*.json` · `.workbuddy-ai/`.
> وفوقهم مخرجات تطوير **محلية فقط** (بتتولّد تاني من `tools/` — مفيهاش بيانات
> حساسة، بس كثيفة الحجم): `hero_audit/` · `assets/hero_candidates/` ·
> `hero_candidates.json` · `prospects/`.
> ⚠️ `hero_audit.json` (الـmanifest) **مُعمَّت** لأن `tools/inject_seo.py` بيقراؤه —
> الشرطة المائلة في `hero_audit/` هي اللي بتفرّق بين المجلد والملف.
> لو ضفت ملف عمل جديد فيه بيانات تجارية، **ضيفه للـ`.gitignore` الأول**.
> (الشيت `riyadh_businesses_30_v3.xlsx` بيتولّد بـ `tools/build_sheet_v3.py` —
> محلي فقط، مش مُعمَّت ولا داخل الإيمج.)

### النشر الفعلي بعد الـrelease (Coolify API)

الـrelease بيرفع الكمِت للعام، **بس البناء بيبدأ لما تنشر** (مفيش webhook تلقائي
لتطبيق public). الطريقة البرمجية — على السيرفر `ubuntu@$SERVER_IP`:

```bash
ssh ubuntu@$SERVER_IP 'bash -s' <<'REMOTE'
APP=f3c9chhue2nistvynkpjcreb          # landing-pages
NAME=cli-deploy-$(date +%Y%m%d)       # اسم واضح باش يتنضف بعده
TOKEN=$(openssl rand -hex 32)
HASH=$(printf '%s' "$TOKEN" | sha256sum | cut -d' ' -f1)

# 1) توكن قصير العمر (abilities كاملة على مستخدم الجذر id 0)
docker exec -i coolify-db psql -U coolify -d coolify -v ON_ERROR_STOP=1 <<SQL
insert into personal_access_tokens
 (tokenable_type, tokenable_id, name, token, team_id, abilities, created_at, updated_at)
values ('App\Models\User', 0, '$NAME', '$HASH', '0', '["*"]', now(), now());
SQL

# 2) ابدأ النشر
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Accept: application/json" \
     -H "Content-Type: application/json" \
     -d "{\"uuid\":\"$APP\"}" http://127.0.0.1:8000/api/v1/deploy
REMOTE
```

ثم تابع الحالة (الحقل `status` بيوصل `finished` أو `failed`) — والكومِت لازم يطابق
كمِت الـrelease:

```bash
ssh ubuntu@$SERVER_IP 'bash -s' <<'REMOTE'
APP=f3c9chhue2nistvynkpjcreb
docker exec coolify-db psql -U coolify -d coolify -c \
  "select deployment_uuid, status, commit, created_at
     from application_deployment_queues
    where application_id = (select id::text from applications where uuid = '$APP')
    order by id desc limit 3;"
REMOTE
```

(مثال على نتيجة سليمة: `status=finished` و`commit` = أول 7 حروف من كمِت الـrelease
اللي فوق — كان `f0359db`.)

> ⚠️ **نضّف التوكن فوراً بعد النشر** — توكن API كامل الصلاحيات:
> `docker exec coolify-db psql -U coolify -d coolify -c "delete from personal_access_tokens where name = 'cli-deploy-YYYYMMDD';"`
>
> ⚠️ `application_id` في `application_deployment_queues` من نوع `varchar` لكن
> `applications.id` من نوع `bigint` — لازم cast صريح (`id::text`) وإلا
> `operator does not exist: character varying = bigint`.

### الإعداد (تم مرة واحدة — للمرجع)

1. تطبيق **Dockerfile** على `MahmoudMody96/landing-pages` فرع `main`:
   - Dockerfile location: `/Dockerfile` (الافتراضي)، Port: `80`
   - Health check path: `/nginx-health`
2. الدومينات على نفس التطبيق (Coolify يتولى TLS تلقائياً):
   - `pages.aidy.site` — الفهرس العام
   - `riyadh.aidy.site` — بوابة الرياض (تُحوَّل لـ `/sa/riyadh/` عبر `map` في nginx)
3. أي push على العام → بناء ونشر تلقائي.

### كيف يعمل البناء

`docker/assemble.sh` لحظة البناء: يترجم `src/cities/<cc>-<city>/` إلى
`<cc>/<city>/`، ينسخ الهيرو، يحل كل `stock/<slug>_<i>.jpg` مُشار له في
الصفحات إلى ملفات `assets/stock/<niche>-<i>.jpg` (**ويفشل البناء لو نقص
ملف — بدل 404 صامتة لاحقاً**)، ثم يشغّل `gen_index.sh` (الفهرس + بوابات
المدن + `sitemap.xml`). الناتج إيمج nginx ثابتة بلا volumes.

### التحقق بعد النشر

```bash
BASE=https://riyadh.aidy.site
curl -s -o /dev/null -w "gateway: %{http_code} -> %{redirect_url}\n" "$BASE/"
curl -s -o /dev/null -w "page: %{http_code}\n" "$BASE/sa/riyadh/carve-coffee-bar.html"
curl -s -o /dev/null -w "hero: %{http_code}\n" "https://pages.aidy.site/hero/coffee.jpg"
curl -s -o /dev/null -w "stock: %{http_code}\n" "https://pages.aidy.site/stock/carve-coffee-bar_1.jpg"
curl -s https://pages.aidy.site/sitemap.xml | grep -c "<loc>"
curl -s https://pages.aidy.site/robots.txt
curl -s "$BASE/sa/riyadh/carve-coffee-bar.html" | grep -o '<link rel="canonical"[^>]*>'
```

### مدينة جديدة عبر Coolify

1. `src/cities/<cc>-<city>/*.html` (slugs إنجليزية فقط) + أي صور مجال جديدة.
2. سطر في `map $host $city_gateway` داخل `templates/nginx.conf`.
3. ضيف `<city>.aidy.site` دومين على نفس التطبيق في Coolify.
4. `python tools/inject_seo.py` لصفحات المدينة
   (مثال: `--dir=src/cities/ae-dubai --base-url=https://dubai.aidy.site/ae/dubai`).
5. push → redeploy → تحقق.

> ملف `templates/landing-pages-router.yaml` للتشغيل **اليدوي** خارج Coolify
> فقط — مع Coolify لا حاجة له (التوجيه والشهادات من Coolify نفسها).

---

## التحليلات (Umami)

1. من كتالوج Coolify: انشر **Umami** (one-click) وافتحه.
2. أضف موقعاً (website) باسم الدومين وخد الـ Website ID.
3. املأ `templates/tracking.json`:
   ```json
   {"enabled": true, "provider": "umami",
    "src": "https://<umami-host>/script.js", "website_id": "<id>"}
   ```
4. `python tools/gen_pages.py` ثم راجع `gen_pages.py --check`.
5. commit + push → Coolify يعيد البناء والنشر.

العدّاد بقى جزء من التمبليت: `templates/page.html` فيه `{{tracking}}` قبل
`</head>`، و`pagekit` يبني السكربت من `templates/tracking.json` (نفس البايتات
اللي كان `inject_tracking.py` بيكتبها). معنى كده إن توليد الصفحات مابيشيلش
التحليلات لو نسيت تشغّل الحقن، والعكس صح — إلغاء التفعيل بيمسح السكربت من كل
الصفحات من غير أثر. السكربت القديم فضل موجود للتحقق (`--check`) ولإزالة حقن
قديم، وهو no-op على صفحة متولّدة (متأكدين عملياً: inject بعد توليد = صفر تغييرات).

---

## لوحة الإدارة (dashboard)

كونسول محلي لإدارة ومتابعة المشروع كله من المتصفح — stdlib فقط، مفيش
dependencies و مفيش credentials محفوظة:

```bash
# Windows: مهم — اشتغل بالمتغيّر ده أو تنظيف محاكاة البناء هيتعطّل
CODEBUDDY_SAFE_DELETE_ENABLED=0 python tools/dashboard.py --port 8765
```

- **العنوان:** `http://127.0.0.1:8765/` — مربوط على `127.0.0.1` بس (أداة
  مشغّل، مش تطبيق عام).
- **التابات:** نظرة عامة (KPIs + شارة بوابة المطابقة + حالة git) · الصفحات
  والسجلات (بحث/فلترة بالمدينة والمجال والمعرض + تعديل سجل أو إضافة بزنس جديد
  + معاينة حية) · المجالات والقوالب (محرر بروفايل + استنساخ مجال جديد) ·
  جودة المحتوى (تسرب أحياء/تكرار/لهجة/نواقص) · الوسائط (جرد hero/stock +
  رفع jpg صارم + فحص hotlink) · الاستيراد الجماعي (CSV/xlsx: معاينة صارمة ثم
  تأكيد الكل-أو-لا-شيء + قالب قابل للتنزيل) · الفحوصات والإجراءات (`check` /
  `gen` / محاكاة بناء الإيمج + فحص حياة الـ30 صفحة على الدومين الحقيقي) ·
  النشر والإصدار (الحالة غير الملتزمة + الريبو العام + زر `release.sh` +
  أوامر الـrelease) · الإحصاء والمتابعة (سجل الفحوصات عبر الزمن + الأحداث +
  الإصدارات) · السجل.
- **التعديل بيكتب** `data/businesses.json` بنفس شكل `build_niches.py`
  (بايت LF، `indent=1`، سطر أخير) — عشان الـdiff يبان حقول اللي اتغيّرت بس؛
  وبعدها يولّد الصفحات ويشغّل `--check`. الـslug مابتتغيّرش من اللوحة.
- **محاكاة البناء** بتنسخ staging مؤقت وتشغّل `docker/assemble.sh` وبعدين
  تفتّش بايثونياً على: مسارات مطلقة مسروقة · صور خارجية (`googleusercontent`) ·
  `{{` متبقية · عدد `<loc>` في السايت ماب. كل ده لازم يطلع نظيف.
- **فحص الحياة** بيـpercent-encode المسارات العربية قبل ما يطلبها —
  `urllib` مابيبعتش مسار unicode خام، والفحص بيقع كـstatus 0 (كذبة «الصفحة
  واقعة»). مفيش كاش أقدم من 5 دقايق.

---

## قواعد بناء الصفحات (مهمة)

1. **العربي RTL** — `<html lang="ar" dir="rtl">`
2. **موبايل أولاً** — الصفحة لازم تطلع صح على الموبايل
3. **عنوان قوي** — مناسب لنوع المحل، مش الاسم بس
4. **زرارين دايماً** — واتساب مباشر + اتصال
5. **العنوان من Google Maps** — بنصه، من غير أي تعديل
6. **مواعيد العمل** — جدول كامل 7 أيام
7. **تقييمات حقيقية** — بنصها من Google، **من غير أي تعديل**
   (إزالة التكرار بنفس الكاتب والنص مسموحة — الصفحات تستخدم `reviews_clean`، وتم التحقق آلياً أن كل الصفحات الـ 30 مطابقة له)
8. **الصور** — من pool المحل؛ لو ضعيف/طويلية، استخدم صور الهيرو 4K (شوف `assets/stock/PHOTOS.md`)
9. **ممنوع تختلق** — كل البيانات من Google Maps

---

## صور الهيرو — القواعد الحاسمة

> الهيرو هو أول حاجة الزائر بيشوفها. القواعد هنا **مش تفاوضية**:

1. **عريض (landscape) إلزامي** — الصورة الطولية (portrait) **مرفوضة تماماً**. بتعمل فراغات أو تقصير قبيح.
2. **4K** — 2560px عرض أو أكتر.
3. **مفيش لوجو محل تاني** — خطر تجاري.
4. **negative space** — الصورة لازم تسبّق مكان للنص.

**الموقف الحالي:** **30 من 30** بزنس على هيرو عريض عالي الجودة:
27 على هيرو مجال 4K، و 3 على صورة محلهم الحقيقية النضيفة (موطّنة محلياً).
**مفيش ولا صورة طولية، ومفيش ولا صورة مستضافة خارجياً** — كل الهيرو والجاليري على
`pages.aidy.site`.

اللي اتغيّر (2026-10-12):
- 4 محلات كانت صورتها الحقيقية ضعيفة/مخالفة → اتحولت لهيرو المجال 4K:
  `java-time` و `the-protocol-barbershop` (لافتة/لوجو محل تاني في الإطار ❌)،
  و `i2N Fitness` و `SPORTTYPE GYM` (أقصى دقة متاحة أقل من الحد ❌).
- 3 محلات صورتها نضيفة وعريضة → اتوطّنت محلياً بدل الـ hotlink.
- **85 صورة جاليري** كانت مستضافة عند Google على 18 صفحة → كلها اتوطّنت محلياً.

التفاصيل الكاملة + الصور المرفوضة وأسبابها في `assets/stock/PHOTOS.md`.

---

## أمان الصور (قاعدة ذهبية)

> أي صورة على صفحة عميل لازم تكون إما:
> **(أ)** من pool المحل نفسه (وطولية/ضعيفة → تُستبدل)، أو
> **(ب)** صورة عامة بنفس المجال **مفيش فيها لوجو أو اسم محل تاني**.

**ممنوع منعاً باتاً:** صورة محل منافس على صفحة عميل — ده خطر تجاري حقيقي.

الصور المتنازع عليها (اللي Google بيرفعها لأكتر من listing) بتتشال من كل الصفحات.

---

## التحقق قبل النشر

```bash
# تأكد إن كل الصفحات شغالة
for f in src/cities/sa-riyadh/*.html; do
  slug=$(basename "$f")
  code=$(curl -s -o /dev/null -w '%{http_code}' \
    "https://riyadh.aidy.site/sa/riyadh/$slug")
  echo "$code  $slug"
done
```

المتوقع: **200** لكل الصفحات.

**وتحقق من صور الهيرو:**
```bash
for n in coffee barbershop beauty_salon nail_salon gym auto_repair; do
  curl -s -o /dev/null -w "%{http_code}  $n\n" "https://pages.aidy.site/hero/$n.jpg"
done
```

**وتحقق من البوابات والـ sitemap:**
```bash
curl -s -o /dev/null -w "gateway: %{http_code} -> %{redirect_url}\n" "https://riyadh.aidy.site/"
curl -s "https://pages.aidy.site/sitemap.xml" | grep -c "<loc>"
```
المتوقع: `302` نحو `/sa/riyadh/`، وعدد `<loc>` = الصفحات + المدن + 1.

**وقبل أي release — شغّل محاكاة بناء محلية (أسرع وأأمن من التخمين):**
```bash
SIM=/tmp/lp-build; rm -rf "$SIM"; mkdir -p "$SIM/stage" "$SIM/html"; S="$SIM/stage"
cp -r src/cities "$S/cities"; cp -r assets/hero "$S/hero-src"
cp -r assets/stock "$S/stock-src"; cp data/stock_manifest.json src/gen_index.sh docker/assemble.sh "$S/"
bash "$S/assemble.sh" "$S" "$SIM/html" https://pages.aidy.site
```
المتوقع: `32 html files, hero: 9 files, stock: 107 files` **بصفر** `ERROR`.
ولو الصفحة بتروح لريبو عام، اتأكد كمان إنه مفيش مسار مسرّب ولا دومين صور خارجي:
```bash
grep -rlE '/tmp/|/usr/share/nginx|AppData' "$SIM/html" --include='*.html' | wc -l   # 0
grep -rhoE 'https?://[^"]*googleusercontent[^"]*' "$SIM/html" --include='*.html' | wc -l   # 0
```
> ⚠️ شغّل المحاكاة بمسار **POSIX** (`/tmp/...`) مش `$TEMP` بتاع ويندوز:
> `${f#$ROOT/}` في `gen_index.sh` بيفشل لو الجذر `C:\...\` (الـ`\` حرف escape في
> الـpattern) ويطلع `href` بمسارات مطلقة. ده عيب محاكاة ويندوز **فقط** — في
> الحاوية الجذر `/usr/share/nginx/html` والفصل بيشتغل عادي.

---

## ملاحظات تقنية

- **الحاوية:** اسمها دلوقتي `<app-uuid>-<رقم>` (مثال الآن:
  `f3c9chhue2nistvynkpjcreb-164935960790`) — Coolify غيّر نمط التسمية، فابحث بـ
  app-uuid مش باسم ثابت. (nginx:alpine) على شبكة `coolify`، restart policy
  `unless-stopped`. تأكيد إن الإصدار الصح شغّال: تاج الإيمج لازم يكون
  `<app-uuid>:<commit>` = نفس كومِت الـrelease الأخير:
  ```bash
  docker ps --format '{{.Names}}\t{{.Image}}' | grep f3c9chhue2nistvynkpjcreb
  ```
- **التوجيه:** Traefik file provider — راوتر `landing-pages-router.yaml` (self-contained، priority 20 فوق الـ wildcard).
- **الفهرس:** `gen_index.sh` يقرأ `src/cities/*/*/` و يبني `index.html` للجذر **+** `index.html` بوابة لكل مدينة **+** `sitemap.xml` تلقائياً.
- **بوابة المدينة:** `map $host $city_gateway` في `nginx.conf` يحوّل جذر `<city>.aidy.site/` لبوابة المدينة (302).
- **الشهادة TLS:** wildcard `*.aidy.site` عبر `certResolver: cfdns`.

## Git

- **الريبو:** `MahmoudMody96/riyadh-landing-pages` (private)
- **الفرع الأساسي:** `main`
- **مخرجات بتتولّد مرة واحدة (مش مُعمَّتة):** `hero_audit/` و`assets/hero_candidates/` —
  اتمسحوا بعد ما خلصوا دورهم، بس السكربتات اللي بتنتجهم محفوظة
  (`tools/audit_heroes.py` · `tools/fetch_hero_cands.py`) فمينفعش يتولّدوا تاني.
  الاستثناء: `hero_audit.json` **مُعمَّت** لأن `tools/inject_seo.py` بيقراه.
- **قبل كل كومِت / release:** شغّل `git status --porcelain --ignored` وتأكد إن اللي بيظهر
  هو اللي تقصده — من غير بنود `.gitignore` الشيت ورسايل التواصل هيتنشروا على ريبو **عام**.
