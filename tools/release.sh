#!/bin/bash
# release.sh — guarded public release for the Coolify flow.
# Usage:  bash tools/release.sh "Release: <short description>"
#
# What it does (and why each gate exists):
#   1. gen_pages --check must PASS        (pages match data + template)
#   2. localize_images --check must show 0 hotlinked images
#   3. git status must show no barnacles  (release runs `git add -A` on an
#      orphan branch pushed to a PUBLIC repo — an extra file ships worldwide)
#   4. builds the orphan branch rel-tmp and force-pushes it to `public` main
# After this: Redeploy from Coolify UI (or the API deploy flow in README).
set -euo pipefail
cd "$(dirname "$0")/.."

MSG="${1:?usage: bash tools/release.sh \"Release: <short description>\"}"

echo "==> 1/3 gen_pages --check"
python tools/gen_pages.py --check

echo "==> 2/3 localize --check"
python tools/localize_images.py --check

echo "==> 3/3 working tree must be clean (tracked files)"
if [ -n "$(git status --porcelain=v1 --ignored=no)" ]; then
  echo "refusing: uncommitted changes present. Commit first:" >&2
  git status --porcelain=v1 --ignored=no >&2
  exit 1
fi

echo "==> release: orphan branch -> public/main"
git checkout -q --orphan rel-tmp
git add -A
git commit -q -m "$MSG"
git push -q -f public rel-tmp:main
git checkout -q main
git branch -D rel-tmp
echo "released. Redeploy the Coolify app to build."
