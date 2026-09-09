#!/usr/bin/env bash
set -euo pipefail

source_fasta=/mnt/nas05/togovar/original/grch37/reference_genome/hg19.fa
output_dir=/data/togovar/etl/togovar-etl/2026.1/reference
output_fasta="$output_dir/GRCh37.hg19.canonical.fa"
output_fai="$output_fasta.fai"
mkdir -p "$output_dir"

if [ -L "$output_fasta" ]; then
  if [ "`readlink -f "$output_fasta"`" != "`readlink -f "$source_fasta"`" ]; then
    echo "unexpected symlink target: $output_fasta" >&2
    exit 1
  fi
elif [ -e "$output_fasta" ]; then
  echo "refusing to replace existing non-symlink: $output_fasta" >&2
  exit 1
else
  ln -s "$source_fasta" "$output_fasta"
fi

# hg19.fa contains chrM (16,571 bp) and chrMT (16,569 bp).  The release VCFs
# use the UCSC chrM sequence.  Rename chrM to MT and exclude chrMT so that the
# canonical name is unique after removing the chr prefix.
awk 'BEGIN{OFS="\t"} $1!="chrMT" {name=$1; sub(/^chr/,"",name); if(name=="M") name="MT"; $1=name; print}' \
  "$source_fasta.fai" > "$output_fai.tmp"
mv "$output_fai.tmp" "$output_fai"

if [ "`grep -c '^MT[[:space:]]' "$output_fai"`" -ne 1 ]; then
  echo "canonical FAI must contain exactly one MT entry" >&2
  exit 1
fi
samtools faidx "$output_fasta" MT:15951-15951 >/dev/null
printf 'prepared %s and %s\n' "$output_fasta" "$output_fai"
