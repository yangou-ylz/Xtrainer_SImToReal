#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "${REMOTE_URL:-}" ]]; then
  echo "Usage:"
  echo "  REMOTE_URL=git@github.com:<user>/<repo>.git bash scripts/init_and_push_template.sh"
  echo "or"
  echo "  REMOTE_URL=https://github.com/<user>/<repo>.git bash scripts/init_and_push_template.sh"
  exit 2
fi

cd "$ROOT"

if [[ ! -d .git ]]; then
  git init
fi

git add .
git status --short

if ! git diff --cached --quiet; then
  git commit -m "${COMMIT_MESSAGE:-Update X-Trainer simulation project}"
else
  echo "No staged changes. Skip commit."
fi

if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REMOTE_URL"
else
  git remote add origin "$REMOTE_URL"
fi

git branch -M main
git push -u origin main
