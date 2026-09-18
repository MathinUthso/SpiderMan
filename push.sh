#!/usr/bin/env bash
# Commit and push the current work to origin/main.
# Usage: ./push.sh "Add the DP optimizer"
# Commits are authored solely by the configured git user; no co-author or
# contributor trailers are added.

set -euo pipefail

if [ $# -eq 0 ]; then
  echo "usage: ./push.sh \"commit message\"" >&2
  exit 1
fi

MSG="$*"

# Refuse to commit anything that looks like a secret.
if git status --porcelain | grep -qE '(^|/)\.env($|\.)'; then
  echo "refusing to commit: a .env file is staged or untracked-but-matched" >&2
  exit 1
fi

git add -A
if git diff --cached --quiet; then
  echo "nothing to commit"
  exit 0
fi

git commit -m "$MSG"
git push origin main
echo "pushed: $MSG"
