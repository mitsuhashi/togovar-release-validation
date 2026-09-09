cwlVersion: v1.2
class: Workflow
label: Reconcile TogoVar 2026.1 VCF allele counts with staging API counts
requirements:
  ScatterFeatureRequirement: {}
inputs:
  assemblies: string[]
  staging_urls: string[]
  chromosomes: string[]
  chromosomes_csv: string
  vcf_releases: string[]
  vcf_assemblies: string[]
  vcf_datasets: string[]
  vcf_reference_fastas:
    type: File[]
    secondaryFiles: [.fai]
  vcf_groups:
    type:
      type: array
      items:
        type: array
        items: File
  chrom_map: File
outputs:
  reconciliation:
    type: File
    outputSource: reconcile/counts
  mismatches:
    type: File
    outputSource: reconcile/mismatches
  api_counts:
    type: File[]
    outputSource: api/counts
  vcf_counts:
    type: File[]
    outputSource: count_vcf/counts
  reference_mismatches:
    type: File[]
    outputSource: count_vcf/reference_mismatches
steps:
  api:
    run: fetch_staging_api_counts.cwl
    in:
      assembly: assemblies
      api_url: staging_urls
      chromosomes: chromosomes
    out: [counts]
    scatter: [assembly, api_url]
    scatterMethod: dotproduct
  count_vcf:
    run: count_vcf_dataset.cwl
    in:
      release: vcf_releases
      assembly: vcf_assemblies
      dataset: vcf_datasets
      vcfs: vcf_groups
      reference_fasta: vcf_reference_fastas
      chromosomes_csv: chromosomes_csv
      chrom_map: chrom_map
    out: [counts, reference_mismatches]
    scatter: [release, assembly, dataset, vcfs, reference_fasta]
    scatterMethod: dotproduct
  reconcile:
    run: reconcile_api_vcf_counts.cwl
    in:
      api_counts: api/counts
      vcf_counts: count_vcf/counts
    out: [counts, mismatches]
