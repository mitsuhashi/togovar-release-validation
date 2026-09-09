#!/usr/bin/env python3
"""Build a conservative VCF-pair manifest between two releases.

Only exact relative-path matches and globally unique basename matches are added
automatically. Everything else is reported for review rather than guessed.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

SUFFIXES = (".vcf", ".vcf.gz", ".bcf")
CHROM_RE = re.compile(r"(?:^|[._-])chr?(?:[1-9]|1[0-9]|2[0-2]|X|Y|MT|M)(?=[._-]|$)", re.IGNORECASE)


def files(root: Path) -> dict[str, Path]:
    return {str(p.relative_to(root)): p for p in root.rglob("*") if p.is_file() and p.name.endswith(SUFFIXES)}


def dataset_key(relative: str) -> str:
    parts = Path(relative).parts
    # e.g. grch38/frequency/vcf/gnomad_exomes/afr/a.vcf.gz -> .../gnomad_exomes
    try:
        i = parts.index("vcf")
        return "/".join(parts[: i + 2])
    except (ValueError, IndexError):
        return "/".join(parts[:-1])


def chromosome(relative: str) -> str | None:
    match = CHROM_RE.search(Path(relative).name)
    if not match:
        return None
    value = match.group(0).lstrip("._-").lower().removeprefix("chr")
    return "mt" if value in {"m", "mt"} else value


def parent_chrom_key(relative: str) -> tuple[str, str | None]:
    return str(Path(relative).parent), chromosome(relative)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-release", required=True, type=Path)
    parser.add_argument("--new-release", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    old_root, new_root, output = args.old_release.resolve(), args.new_release.resolve(), args.output_dir.resolve()
    if not old_root.is_dir() or not new_root.is_dir():
        parser.error("release paths must be directories")
    if output in (old_root, new_root) or old_root in output.parents or new_root in output.parents:
        parser.error("output directory must be outside the release trees")
    output.mkdir(parents=True, exist_ok=True)
    old, new = files(old_root), files(new_root)
    pairs: dict[str, tuple[str, str]] = {}
    for rel in sorted(old.keys() & new.keys()):
        pairs[rel] = (rel, "exact_relative_path")
    unmatched_old, unmatched_new = set(old) - set(pairs), set(new) - set(pairs)
    old_names: dict[str, list[str]] = defaultdict(list); new_names: dict[str, list[str]] = defaultdict(list)
    for rel in unmatched_old: old_names[Path(rel).name].append(rel)
    for rel in unmatched_new: new_names[Path(rel).name].append(rel)
    for name in sorted(old_names.keys() & new_names.keys()):
        if len(old_names[name]) == len(new_names[name]) == 1:
            old_rel, new_rel = old_names[name][0], new_names[name][0]
            pairs[old_rel] = (new_rel, "unique_basename")
    paired_new = {new_rel for new_rel, _ in pairs.values()}
    remaining_old, remaining_new = set(old) - set(pairs), set(new) - paired_new
    old_parent_chrom: dict[tuple[str, str | None], list[str]] = defaultdict(list)
    new_parent_chrom: dict[tuple[str, str | None], list[str]] = defaultdict(list)
    for rel in remaining_old: old_parent_chrom[parent_chrom_key(rel)].append(rel)
    for rel in remaining_new: new_parent_chrom[parent_chrom_key(rel)].append(rel)
    for key in sorted(old_parent_chrom.keys() & new_parent_chrom.keys()):
        if key[1] is not None and len(old_parent_chrom[key]) == len(new_parent_chrom[key]) == 1:
            pairs[old_parent_chrom[key][0]] = (new_parent_chrom[key][0], "unique_parent_and_chromosome")
    # Older aggregate/raw files lived below all/ or raw/.  The new aggregate
    # files live directly below the dataset directory.  Reusing the same new
    # aggregate for both old all and raw is intentional and safe for loss checks.
    for old_rel in sorted(set(old) - set(pairs)):
        old_path = Path(old_rel)
        if old_path.parent.name not in {"all", "raw"} or chromosome(old_rel) is None:
            continue
        new_parent = old_path.parent.parent
        candidates = [
            rel for rel in new
            if Path(rel).parent == new_parent and chromosome(rel) == chromosome(old_rel)
        ]
        if len(candidates) == 1:
            pairs[old_rel] = (candidates[0], "dataset_root_and_chromosome")
    # A normalized duplicate in the old tree can be checked against the single
    # published file in the new tree without treating it as an independent dataset.
    for old_rel in sorted(set(old) - set(pairs)):
        if ".norm.vcf" not in old_rel:
            continue
        candidate = old_rel.replace(".norm.vcf", ".vcf")
        if candidate in new:
            pairs[old_rel] = (candidate, "normalized_duplicate")
    paired_new = {new_rel for new_rel, _ in pairs.values()}
    unmatched_old, unmatched_new = sorted(set(old) - set(pairs)), sorted(set(new) - paired_new)
    by_dataset: dict[str, list[str]] = defaultdict(list)
    for rel in unmatched_new: by_dataset[dataset_key(rel)].append(rel)
    with (output / "vcf_pair_manifest.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["# old_relative_path", "new_relative_path"])
        for old_rel in sorted(pairs): writer.writerow([old_rel, pairs[old_rel][0]])
    with (output / "vcf_pair_provenance.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["old_relative_path", "new_relative_path", "method"])
        for old_rel in sorted(pairs): writer.writerow([old_rel, *pairs[old_rel]])
    with (output / "vcf_pair_review.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["old_relative_path", "old_dataset", "candidate_new_count", "candidate_new_paths"])
        for old_rel in unmatched_old:
            candidates = sorted(by_dataset[dataset_key(old_rel)])
            writer.writerow([old_rel, dataset_key(old_rel), len(candidates), ";".join(candidates)])
    methods = defaultdict(int)
    for _, method in pairs.values(): methods[method] += 1
    report = {"old_vcfs": len(old), "new_vcfs": len(new), "paired": len(pairs), **dict(sorted(methods.items())), "old_needing_review": len(unmatched_old), "new_unpaired": len(unmatched_new)}
    (output / "vcf_pair_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
