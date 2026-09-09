#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

assembly=$1
api_url=$2
shift 2
if [ "$#" -eq 0 ]; then
  echo "at least one chromosome is required" >&2
  exit 1
fi

tag=`printf '%s' "$assembly" | tr -c 'A-Za-z0-9._-' '_'`
raw_dir="$tag.staging-api.raw"
counts_file="$tag.staging-api-counts.tsv"
mkdir -p "$raw_dir"
printf 'assembly\tchromosome\tdataset\tapi_count\n' > "$counts_file"

for chrom in "$@"; do
  body=`printf '{"query":{"location":{"chromosome":"%s","position":{"gte":1,"lte":999999999}}},"limit":0}' "$chrom"`
  tmp="$raw_dir/$chrom.json.tmp"
  out="$raw_dir/$chrom.json"
  code=`curl -sS --retry 3 --retry-delay 2 --connect-timeout 15 --max-time 180 \
    -o "$tmp" -w '%{http_code}' -X POST "$api_url/api/search/variant?stat=1&data=0&quality=0" \
    -H 'Content-Type: application/json' -H 'Accept: application/json' --data "$body"`
  if [ "$code" != 200 ]; then
    printf 'API request failed: %s chromosome=%s HTTP=%s\n' "$api_url" "$chrom" "$code" >&2
    head -c 1000 "$tmp" >&2 || true
    exit 1
  fi
  if ! jq -e '.statistics.dataset | type == "object"' "$tmp" >/dev/null; then
    printf 'Invalid API response: %s chromosome=%s\n' "$api_url" "$chrom" >&2
    head -c 1000 "$tmp" >&2 || true
    exit 1
  fi
  mv "$tmp" "$out"
  jq -r --arg assembly "$assembly" --arg chrom "$chrom" '
    .statistics.dataset | to_entries[] | [$assembly,$chrom,.key,.value] | @tsv
  ' "$out" >> "$counts_file"
done
