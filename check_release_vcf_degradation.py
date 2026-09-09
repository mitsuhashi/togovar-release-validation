#!/usr/bin/env python3
"""Detect variants present in an old TogoVar release but absent from a new one.

The program deliberately treats the release trees as read-only.  All outputs,
including its per-file SQLite scratch database, live below --output-dir.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Iterator

VCF_SUFFIXES = (".vcf", ".vcf.gz", ".bcf")
MISSING_HEADER = [
    "old_relative_path", "new_relative_path", "chrom", "pos", "ref", "alt",
    "id", "qual", "filter", "info", "alt_index", "normalization",
]


def die(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def vcf_files(root: Path) -> dict[str, Path]:
    return {
        str(path.relative_to(root)): path
        for path in root.rglob("*")
        if path.is_file() and path.name.endswith(VCF_SUFFIXES)
    }


def open_vcf(path: Path):
    if path.suffix == ".bcf":
        die(f"BCF is not supported without bcftools: {path}")
    return gzip.open(path, "rt", encoding="utf-8", errors="replace") if path.suffix == ".gz" else path.open("rt", encoding="utf-8", errors="replace")


def canonical_chrom(chrom: str) -> str:
    value = chrom.removeprefix("chr").upper()
    return {"M": "MT", "CHRM": "MT"}.get(value, value)


def trim_allele(pos: int, ref: str, alt: str) -> tuple[int, str, str, str]:
    """Return a minimal allele representation; does not left-align indels."""
    original = (pos, ref, alt)
    if alt in {".", "*"} or alt.startswith("<") or "]" in alt or "[" in alt:
        return pos, ref, alt, "unchanged_symbolic_or_spanning"
    while len(ref) > 1 and len(alt) > 1 and ref[-1] == alt[-1]:
        ref, alt = ref[:-1], alt[:-1]
    while len(ref) > 1 and len(alt) > 1 and ref[0] == alt[0]:
        ref, alt, pos = ref[1:], alt[1:], pos + 1
    return pos, ref, alt, "trimmed" if (pos, ref, alt) != original else "unchanged"


def records(path: Path, trim: bool) -> Iterator[tuple[str, int, str, str, list[str], int, str]]:
    with open_vcf(path) as handle:
        for line_number, line in enumerate(handle, 1):
            if not line or line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 8:
                die(f"Malformed VCF record at {path}:{line_number}")
            try:
                pos = int(fields[1])
            except ValueError:
                die(f"Invalid POS at {path}:{line_number}: {fields[1]!r}")
            for alt_index, alt in enumerate(fields[4].split(","), 1):
                normalized = "not_requested"
                ref = fields[3]
                if trim:
                    pos_key, ref_key, alt_key, normalized = trim_allele(pos, ref, alt)
                else:
                    pos_key, ref_key, alt_key = pos, ref, alt
                yield canonical_chrom(fields[0]), pos_key, ref_key, alt_key, fields, alt_index, normalized


def read_manifest(path: Path, old_files: dict[str, Path], new_files: dict[str, Path]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle, delimiter="\t"):
            if not row or row[0].startswith("#"):
                continue
            if len(row) != 2:
                die(f"Manifest row must have exactly old and new relative paths: {row}")
            old_rel, new_rel = row
            if old_rel not in old_files or new_rel not in new_files:
                die(f"Manifest path not found: {old_rel!r} -> {new_rel!r}")
            pairs.append((old_rel, new_rel))
    return pairs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-release", required=True, type=Path)
    parser.add_argument("--new-release", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, help="TSV: old_relative_path<TAB>new_relative_path")
    parser.add_argument("--no-trim", action="store_true", help="Use literal CHROM/POS/REF/ALT keys.")
    parser.add_argument("--allow-missing", action="store_true", help="Exit 0 even when degradation is found.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    old_root, new_root = args.old_release.resolve(), args.new_release.resolve()
    output = args.output_dir.resolve()
    if not old_root.is_dir() or not new_root.is_dir():
        die("--old-release and --new-release must be existing directories")
    if output == old_root or output == new_root or old_root in output.parents or new_root in output.parents:
        die("--output-dir must not be inside either release tree")
    output.mkdir(parents=True, exist_ok=True)
    old_files, new_files = vcf_files(old_root), vcf_files(new_root)
    pairs = read_manifest(args.manifest, old_files, new_files) if args.manifest else sorted(set(old_files) & set(new_files))
    old_only, new_only = sorted(set(old_files) - {p[0] for p in pairs}), sorted(set(new_files) - {p[1] for p in pairs})
    if not pairs:
        die("No matching VCF pairs. Supply --manifest when relative paths changed.")

    files_path = output / "file_status.tsv"
    summary_path = output / "summary.tsv"
    missing_path = output / "missing_variants.tsv.gz"
    scratch = output / ".scratch.sqlite3"
    total_missing = total_old = total_new = 0
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    with files_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
        writer.writerow(["status", "relative_path"])
        writer.writerows(("paired", old) for old, _ in pairs)
        writer.writerows(("old_only", p) for p in old_only)
        writer.writerows(("new_only", p) for p in new_only)

    with summary_path.open("w", encoding="utf-8", newline="") as summary_fh, gzip.open(missing_path, "wt", encoding="utf-8", newline="") as missing_fh:
        summary = csv.writer(summary_fh, delimiter="\t", lineterminator="\n")
        missing = csv.writer(missing_fh, delimiter="\t", lineterminator="\n")
        summary.writerow(["old_relative_path", "new_relative_path", "old_alleles", "new_alleles", "missing_alleles"])
        missing.writerow(MISSING_HEADER)
        for index, (old_rel, new_rel) in enumerate(pairs, 1):
            if scratch.exists(): scratch.unlink()
            db = sqlite3.connect(scratch)
            db.execute("PRAGMA journal_mode=OFF")
            db.execute("PRAGMA synchronous=OFF")
            db.execute("CREATE TABLE old (chrom TEXT, pos INTEGER, ref TEXT, alt TEXT, id TEXT, qual TEXT, filter TEXT, info TEXT, alt_index INTEGER, normalization TEXT, PRIMARY KEY(chrom,pos,ref,alt)) WITHOUT ROWID")
            old_count = 0
            batch = []
            for chrom, pos, ref, alt, fields, alt_index, normalized in records(old_files[old_rel], not args.no_trim):
                batch.append((chrom, pos, ref, alt, fields[2], fields[5], fields[6], fields[7], alt_index, normalized))
                old_count += 1
                if len(batch) == 100_000:
                    db.executemany("INSERT OR IGNORE INTO old VALUES (?,?,?,?,?,?,?,?,?,?)", batch); db.commit(); batch.clear()
            if batch: db.executemany("INSERT OR IGNORE INTO old VALUES (?,?,?,?,?,?,?,?,?,?)", batch); db.commit()
            new_count = 0; batch = []
            for chrom, pos, ref, alt, _fields, _alt_index, _normalized in records(new_files[new_rel], not args.no_trim):
                batch.append((chrom, pos, ref, alt)); new_count += 1
                if len(batch) == 100_000:
                    db.executemany("DELETE FROM old WHERE chrom=? AND pos=? AND ref=? AND alt=?", batch); db.commit(); batch.clear()
            if batch: db.executemany("DELETE FROM old WHERE chrom=? AND pos=? AND ref=? AND alt=?", batch); db.commit()
            missing_count = 0
            for row in db.execute("SELECT chrom,pos,ref,alt,id,qual,filter,info,alt_index,normalization FROM old ORDER BY chrom,pos,ref,alt"):
                missing.writerow([old_rel, new_rel, *row]); missing_count += 1
            db.close(); scratch.unlink(missing_ok=True)
            summary.writerow([old_rel, new_rel, old_count, new_count, missing_count])
            total_old += old_count; total_new += new_count; total_missing += missing_count
            print(f"[{index}/{len(pairs)}] {old_rel}: {missing_count} missing", file=sys.stderr)
    metadata = {"started_at": started, "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(), "old_release": str(old_root), "new_release": str(new_root), "paired_files": len(pairs), "old_only_files": len(old_only), "new_only_files": len(new_only), "old_alleles": total_old, "new_alleles": total_new, "missing_alleles": total_missing, "key": "canonical_CHROM,POS,REF,ALT (one key per ALT)", "normalization": "trim common prefix/suffix" if not args.no_trim else "none"}
    (output / "run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2), file=sys.stderr)
    return 0 if args.allow_missing or total_missing == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
