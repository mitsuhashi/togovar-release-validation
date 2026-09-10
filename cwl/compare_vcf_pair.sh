#!/usr/bin/env bash
set -euo pipefail
export PATH="/home/togovar/.local/bin:$PATH"
export LC_ALL=C
old=$1; chrom_map=$2; reference_fasta=$3; pair_id=$4; shift 4
if [ "$#" -eq 0 ]; then
  echo "no new VCF was supplied for $pair_id" >&2
  exit 1
fi
mkdir -p sort-tmp
export TMPDIR="$PWD/sort-tmp"
pair_key=`printf '%s' "$pair_id" | sha256sum | cut -c 1-16`
missing_file="$pair_key.missing.tsv"
summary_file="$pair_key.summary.tsv"
reference_mismatch_file="$pair_key.reference-mismatches.tsv"
printf 'source\tinput_vcf\tmessage\n' > "$reference_mismatch_file"
norm_index=0
keys() {
  input_vcf=$1
  source_label=$2
  norm_index=`expr "$norm_index" + 1`
  norm_log="norm.$norm_index.log"
  bcftools annotate --rename-chrs "$chrom_map" -Ou "$input_vcf" \
    | bcftools norm -f "$reference_fasta" --check-ref w -m -any -Ou 2> "$norm_log" \
    | bcftools query -f '%CHROM\t%POS\t%REF\t%ALT\n' \
    | awk 'BEGIN { OFS="\t" } { print $1, $2, toupper($3), toupper($4) }' \
    | sort -T "$TMPDIR" -u
  awk -v OFS='\t' -v source="$source_label" -v input="$input_vcf" \
    '/^(Reference allele mismatch|REF_MISMATCH)/ {print source,input,$0}' "$norm_log" >> "$reference_mismatch_file"
  cat "$norm_log" >&2
}
keys "$old" old > old.keys.tsv
: > new.keys.unsorted.tsv
new_list=`IFS=,; printf '%s' "$*"`
for new in "$@"; do
  keys "$new" new >> new.keys.unsorted.tsv
done
sort -T "$TMPDIR" -u new.keys.unsorted.tsv > new.keys.tsv
comm -23 old.keys.tsv new.keys.tsv > "$missing_file"
printf 'pair_id\told_vcf\tnew_vcf\told_alleles\tnew_alleles\tmissing_alleles\told_reference_mismatches\tnew_reference_mismatches\n' > "$summary_file"
old_count=`wc -l < old.keys.tsv`
new_count=`wc -l < new.keys.tsv`
missing_count=`wc -l < "$missing_file"`
old_reference_mismatches=`awk -F '\t' 'NR>1 && $1=="old" {count++} END{print count+0}' "$reference_mismatch_file"`
new_reference_mismatches=`awk -F '\t' 'NR>1 && $1=="new" {count++} END{print count+0}' "$reference_mismatch_file"`
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$pair_id" "$old" "$new_list" "$old_count" "$new_count" "$missing_count" "$old_reference_mismatches" "$new_reference_mismatches" >> "$summary_file"
