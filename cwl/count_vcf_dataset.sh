#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

release=$1
assembly=$2
dataset=$3
chromosomes_csv=$4
chrom_map=$5
reference_fasta=$6
shift 6
if [ "$#" -eq 0 ]; then
  echo "no VCF was supplied for $release/$assembly/$dataset" >&2
  exit 1
fi

tag=`printf '%s.%s.%s' "$release" "$assembly" "$dataset" | tr -c 'A-Za-z0-9._-' '_'`
output="$tag.vcf-counts.tsv"
reference_mismatch_output="$tag.reference-mismatches.tsv"
printf 'release\tassembly\tdataset\tinput_vcf\tmessage\n' > "$reference_mismatch_output"
mkdir -p sort-tmp
export TMPDIR="$PWD/sort-tmp"
: > alleles.unsorted.tsv

norm_index=0
for vcf in "$@"; do
  norm_index=`expr "$norm_index" + 1`
  norm_log="norm.$norm_index.log"
  bcftools annotate --rename-chrs "$chrom_map" -Ou "$vcf" \
    | bcftools norm -f "$reference_fasta" --check-ref w -m -any -Ou 2> "$norm_log" \
    | bcftools query -f '%CHROM\t%POS\t%REF\t%ALT\n' \
    >> alleles.unsorted.tsv
  awk -v OFS='\t' -v release="$release" -v assembly="$assembly" \
    -v dataset="$dataset" -v input="$vcf" \
    '/^(Reference allele mismatch|REF_MISMATCH)/ {print release,assembly,dataset,input,$0}' "$norm_log" \
    >> "$reference_mismatch_output"
  cat "$norm_log" >&2
done

sort -T "$TMPDIR" -u alleles.unsorted.tsv > alleles.tsv
printf 'release\tassembly\tchromosome\tdataset\tvcf_count\n' > "$output"
awk -F '\t' -v OFS='\t' -v release="$release" -v assembly="$assembly" \
  -v dataset="$dataset" -v chromosomes="$chromosomes_csv" '
  { count[$1]++ }
  END {
    n=split(chromosomes, values, ",")
    for (i=1; i<=n; i++)
      print release, assembly, values[i], dataset, count[values[i]]+0
  }
' alleles.tsv >> "$output"
