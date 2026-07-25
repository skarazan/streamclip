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
git clone --no-local "$repo_root" "$target"
git -C "$target" checkout --detach "$split_commit"
git -C "$target" switch -c main
git -C "$target" remote remove origin

echo "Created local web repository at $target"
echo "Review it, then add a private GitHub origin and a Vercel project."
