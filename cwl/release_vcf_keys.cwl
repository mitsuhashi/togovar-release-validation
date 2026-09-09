cwlVersion: v1.2
class: Workflow
label: Parallel allele-level degradation check for a TogoVar release comparison
requirements:
  ScatterFeatureRequirement: {}
inputs:
  old_vcfs: File[]
  new_vcf_groups:
    type:
      type: array
      items:
        type: array
        items: File
  pair_ids: string[]
  reference_fastas:
    type: File[]
    secondaryFiles: [.fai]
  chrom_map: File
outputs:
  missing_alleles:
    type: File[]
    outputSource: compare/missing_alleles
  summaries:
    type: File[]
    outputSource: compare/summary
  reference_mismatches:
    type: File[]
    outputSource: compare/reference_mismatches
steps:
  compare:
    run: compare_vcf_pair.cwl
    in:
      old_vcf: old_vcfs
      new_vcfs: new_vcf_groups
      pair_id: pair_ids
      reference_fasta: reference_fastas
      chrom_map: chrom_map
    out: [missing_alleles, summary, reference_mismatches]
    scatter: [old_vcf, new_vcfs, pair_id, reference_fasta]
    scatterMethod: dotproduct
