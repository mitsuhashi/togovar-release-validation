#!/usr/bin/env python3
"""Split a two-column VCF-pair manifest without separating one old VCF's new VCF group."""

import argparse
import csv
from collections import OrderedDict
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("manifest", type=Path)
parser.add_argument("--output-dir", type=Path, required=True)
parser.add_argument("--prefix", required=True, help="old VCF relative-path prefix to include")
parser.add_argument("--max-pairs", type=int, default=50)
args = parser.parse_args()

if args.max_pairs < 1:
    raise SystemExit("--max-pairs must be at least 1")

groups: OrderedDict[str, list[list[str]]] = OrderedDict()
with args.manifest.open(newline="") as stream:
    for row in csv.reader(stream, delimiter="\t"):
        if not row or row[0].startswith("#"):
            continue
        if len(row) != 2:
            raise SystemExit(f"bad manifest row: {row}")
        if row[0].startswith(args.prefix):
            groups.setdefault(row[0], []).append(row)

if not groups:
    raise SystemExit(f"no old VCF paths match prefix: {args.prefix}")

args.output_dir.mkdir(parents=True, exist_ok=True)
batches: list[list[list[str]]] = []
batch: list[list[str]] = []
batch_pair_count = 0
for rows in groups.values():
    if batch and batch_pair_count >= args.max_pairs:
        batches.append(batch)
        batch = []
        batch_pair_count = 0
    batch.extend(rows)
    batch_pair_count += 1
if batch:
    batches.append(batch)

for number, rows in enumerate(batches, start=1):
    output = args.output_dir / f"batch-{number:03d}.tsv"
    with output.open("w", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(["# old_relative_path", "new_relative_path"])
        writer.writerows(rows)
    print(output)
