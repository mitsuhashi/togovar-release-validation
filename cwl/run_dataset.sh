#!/usr/bin/env bash
# Resume one assembly/dataset VCF comparison without duplicating completed batches.
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 LABEL MANIFEST_PREFIX" >&2
  exit 2
fi

label=$1
prefix=$2
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

old_root=/mnt/nas05/togovar/public/downloads/release/20241203
new_root=/mnt/nas05/togovar/public/downloads/release/.2026.1
result_root=results/20241203_to_2026.1
batch_dir="$result_root/batches/$label"
output_dir="$result_root/cwl-refnorm-outputs-resume/$label"

python3 cwl/split_manifest.py \
  "$result_root/mapping-reviewed/vcf_pair_manifest.ready.tsv" \
  --prefix "$prefix" \
  --max-pairs 50 \
  --output-dir "$batch_dir"

for manifest in "$batch_dir"/batch-*.tsv; do
  name=$(basename "$manifest" .tsv)
  if compgen -G "$output_dir/$name/*.summary.tsv" > /dev/null; then
    echo "skip completed batch: $label/$name" >&2
    continue
  fi

  python3 cwl/build_job.py "$manifest" \
    --old-root "$old_root" \
    --new-root "$new_root" \
    --chrom-map "$root/cwl/rename_chrom.tsv" \
    --grch37-reference "$root/reference/GRCh37.hg19.canonical.fa" \
    --grch38-reference /mnt/nas05/togovar/original/grch38/reference_genome/Homo_sapiens.GRCh38.dna.primary_assembly.fa \
    --output "$batch_dir/$name.json"

  /home/togovar/.local/bin/cwltool \
    --tmpdir-prefix "$root/$result_root/tmp/jobs/" \
    --cachedir "$root/$result_root/cwl-refnorm-cache" \
    --outdir "$output_dir/$name" \
    --write-summary "$result_root/cwl-refnorm-output-$label-$name.json" \
    cwl/release_vcf_keys.cwl \
    "$batch_dir/$name.json"
done
