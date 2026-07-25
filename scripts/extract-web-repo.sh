#!/bin/sh
set -eu

repo_root=$(git rev-parse --show-toplevel)
target=${1:-"$(dirname "$repo_root")/streamclip-web"}

if [ -n "$(git -C "$repo_root" status --porcelain)" ]; then
  echo "Refusing extraction: commit or stash the working tree first." >&2
  exit 1
fi
if [ -e "$target" ]; then
  echo "Refusing extraction: target already exists: $target" >&2
  exit 1
fi

split_commit=$(git -C "$repo_root" subtree split --prefix=web/app HEAD)
temp_branch="codex-web-split-$$"
cleanup() {
  git -C "$repo_root" branch -D "$temp_branch" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM
git -C "$repo_root" branch "$temp_branch" "$split_commit"
git clone --no-local --single-branch --branch "$temp_branch" "$repo_root" "$target"
git -C "$target" branch -m main
git -C "$target" remote remove origin
cleanup
trap - EXIT INT TERM

echo "Created local web repository at $target"
echo "Review it, then add a private GitHub origin and a Vercel project."
