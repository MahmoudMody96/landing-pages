#!/bin/bash
# Dashboard entrypoint: SSH key -> clone private repo -> serve it.
# Everything secret comes from the environment (Coolify env vars).
set -euo pipefail

REPO_DIR=/srv/repo
PRIVATE_REPO="${GIT_REPO:-git@github.com:MahmoudMody96/riyadh-landing-pages.git}"
BRANCH="${GIT_BRANCH:-main}"

mkdir -p ~/.ssh
chmod 700 ~/.ssh
# Keys arrive base64-encoded (multiline values get mangled by env storage
# otherwise -- this exact failure killed the first deploy). Raw vars still
# accepted as fallback.
if [ -n "${GIT_SSH_KEY_B64:-}" ]; then
  printf '%s' "$GIT_SSH_KEY_B64" | base64 -d > ~/.ssh/id_ed25519
elif [ -n "${GIT_SSH_KEY:-}" ]; then
  printf '%s' "$GIT_SSH_KEY" > ~/.ssh/id_ed25519
fi
if [ -f ~/.ssh/id_ed25519 ]; then
  chmod 600 ~/.ssh/id_ed25519
  printf 'Host *\n  StrictHostKeyChecking accept-new\n' > ~/.ssh/config
  chmod 600 ~/.ssh/config
fi
# Second key for the PUBLIC repo (release.sh pushes there). GitHub deploy
# keys are unique per repo, so one key cannot cover both remotes: this one
# is reached through the github-public SSH alias.
if [ -n "${GIT_SSH_KEY_PUBLIC_B64:-}" ]; then
  printf '%s' "$GIT_SSH_KEY_PUBLIC_B64" | base64 -d > ~/.ssh/id_public
elif [ -n "${GIT_SSH_KEY_PUBLIC:-}" ]; then
  printf '%s' "$GIT_SSH_KEY_PUBLIC" > ~/.ssh/id_public
fi
if [ -f ~/.ssh/id_public ]; then
  chmod 600 ~/.ssh/id_public
  printf 'Host github-public\n  HostName github.com\n  IdentityFile ~/.ssh/id_public\n' >> ~/.ssh/config
fi

if [ ! -d "$REPO_DIR/.git" ]; then
  git clone --branch "$BRANCH" "$PRIVATE_REPO" "$REPO_DIR"
fi
cd "$REPO_DIR"
git fetch origin "$BRANCH"
git checkout -q "$BRANCH"
git reset -q --hard "origin/$BRANCH"
git config user.name "${GIT_USER_NAME:-landing-pages-dash}"
git config user.email "${GIT_USER_EMAIL:-dash@localhost}"
if ! git remote get-url public >/dev/null 2>&1; then
  git remote add public "${PUBLIC_REPO:-git@github.com:MahmoudMody96/landing-pages.git}"
fi
if [ -n "${GIT_SSH_KEY_PUBLIC_B64:-}${GIT_SSH_KEY_PUBLIC:-}" ]; then
  git remote set-url public "git@github-public:${PUBLIC_REPO_PATH:-MahmoudMody96/landing-pages.git}"
fi

export LP_ROOT="$REPO_DIR"
export REQUIRE_AUTH=1
exec python3 tools/dashboard.py --host 0.0.0.0 --port 8765 \
  --require-auth --no-open
