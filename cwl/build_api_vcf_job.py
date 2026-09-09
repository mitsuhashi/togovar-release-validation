#!/usr/bin/env python3
"""Build a CWL job for release VCF-count versus API-count reconciliation."""
import argparse
import csv
import json
from pathlib import Path

VCF_SUFFIXES = (".vcf", ".vcf.gz", ".bcf")
CHROMOSOMES = [str(value) for value in range(1, 23)] + ["X", "Y", "MT"]


def dataset_map(path):
    result = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.reader(handle, delimiter="\t"):
            if not row or row[0].startswith("#"):
                continue
            if len(row) != 2:
                raise SystemExit(f"bad dataset-map row: {row}")
            result[row[0]] = row[1]
    return result


def vcf_files(directory):
    if not directory.is_dir():
        return []
    return sorted(
        path for path in directory.rglob("*")
        if path.is_file() and path.name.endswith(VCF_SUFFIXES)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--new-root", required=True, type=Path)
    parser.add_argument("--dataset-map", required=True, type=Path)
    parser.add_argument("--chrom-map", required=True, type=Path)
    parser.add_argument("--grch37-reference", required=True, type=Path)
    parser.add_argument("--grch38-reference", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    mapping = dataset_map(args.dataset_map)
    references = {"GRCh37": args.grch37_reference, "GRCh38": args.grch38_reference}
    for reference in references.values():
        if not reference.is_file():
            raise SystemExit(f"missing reference FASTA: {reference}")
        if not Path(str(reference) + ".fai").is_file():
            raise SystemExit(f"missing reference FASTA index: {reference}.fai")
    releases = [("new", args.new_root)]
    groups = []
    for release, root in releases:
        for assembly_dir, assembly in (("grch37", "GRCh37"), ("grch38", "GRCh38")):
            base = root / assembly_dir / "frequency" / "vcf"
            for vcf_dataset, api_dataset in mapping.items():
                files = vcf_files(base / vcf_dataset)
                if files:
                    groups.append((release, assembly, api_dataset, files))
    if not groups:
        raise SystemExit("no mapped VCF dataset was found")
    job = {
        "assemblies": ["GRCh37", "GRCh38"],
        "staging_urls": ["https://stg-grch37.togovar.org", "https://stg-grch38.togovar.org"],
        "chromosomes": CHROMOSOMES,
        "chromosomes_csv": ",".join(CHROMOSOMES),
        "vcf_releases": [group[0] for group in groups],
        "vcf_assemblies": [group[1] for group in groups],
        "vcf_datasets": [group[2] for group in groups],
        "vcf_reference_fastas": [
            {
                "class": "File",
                "path": str(references[group[1]].absolute()),
                "secondaryFiles": [
                    {
                        "class": "File",
                        "path": str(references[group[1]].absolute()) + ".fai",
                    }
                ],
            }
            for group in groups
        ],
        "vcf_groups": [
            [{"class": "File", "path": str(path.resolve())} for path in group[3]]
            for group in groups
        ],
        "chrom_map": {"class": "File", "path": str(args.chrom_map.resolve())},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(groups)} release/assembly/dataset VCF groups to {args.output}")


if __name__ == "__main__":
    main()
