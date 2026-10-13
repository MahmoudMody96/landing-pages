# Landing pages — static Arabic RTL site, Coolify-ready.
#
# Coolify: create an Application -> Dockerfile deploy type pointing at this
# repo, expose port 80, add domains pages.aidy.site + riyadh.aidy.site
# (Coolify terminates TLS). Push to main -> redeploy, no SSH/scp needed.
#
# The image is self-contained: city pages + hero/stock images are baked in
# and index/sitemap are generated at build time (see docker/assemble.sh).
# No volumes, no runtime dependencies.
FROM nginx:alpine

RUN apk add --no-cache bash

WORKDIR /srv/site
COPY src/cities ./cities
COPY assets/hero ./hero-src
COPY assets/stock ./stock-src
COPY data/stock_manifest.json ./
COPY src/gen_index.sh ./
COPY templates/404.html ./404.html
COPY docker/assemble.sh ./assemble.sh

# Build /usr/share/nginx/html then drop the staging dir to keep layers lean.
RUN bash ./assemble.sh /srv/site /usr/share/nginx/html https://pages.aidy.site \
 && rm -rf /srv/site

COPY templates/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O- http://127.0.0.1/nginx-health | grep -q healthy
