#!/usr/bin/env bash
set -euo pipefail

OWNER=openai
REPO=openai-python
START_TAG=v1.86.0
END_TAG=v2.6.0
OUT="releases_${START_TAG}..${END_TAG}.md"

# Make gh print instead of paging to your editor
export GH_PAGER=cat        # gh-specific
export PAGER=cat           # belt-and-suspenders

# Collect the tags between END_TAG..START_TAG (newest first)
mapfile -t TAGS < <(
  gh api repos/$OWNER/$REPO/releases --paginate --jq '.[].tag_name' \
  | awk -v end="$END_TAG" -v start="$START_TAG" '
      BEGIN {collect=0}
      { if ($0==end) collect=1; if (collect) print; if ($0==start) exit }'
)

: > "$OUT"  # truncate/create output file
for TAG in "${TAGS[@]}"; do
  {
    echo "## $TAG"
    gh release view "$TAG" --repo "$OWNER/$REPO" \
      --json tagName,publishedAt,body \
      --template '{{.tagName}} ({{.publishedAt}}){{"\n"}}{{.body}}{{"\n\n"}}'
  } >> "$OUT"
done

echo "Wrote $(wc -l < "$OUT") lines to $OUT"
