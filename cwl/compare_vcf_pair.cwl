cwlVersion: v1.2
class: CommandLineTool
label: Compare one old/new VCF pair at canonical allele-key level
requirements:
  InitialWorkDirRequirement:
    listing:
      - entryname: compare_vcf_pair.sh
        entry: { $include: compare_vcf_pair.sh }
inputs:
  old_vcf: { type: File, inputBinding: { position: 1 } }
  chrom_map: { type: File, inputBinding: { position: 2 } }
  reference_fasta:
    type: File
    secondaryFiles: [.fai]
    inputBinding: { position: 3 }
  pair_id: { type: string, inputBinding: { position: 4 } }
  new_vcfs:
    type: File[]
    inputBinding: { position: 5 }
baseCommand: [bash, compare_vcf_pair.sh]
outputs:
  missing_alleles: { type: File, outputBinding: { glob: "*.missing.tsv" } }
  summary: { type: File, outputBinding: { glob: "*.summary.tsv" } }
  reference_mismatches: { type: File, outputBinding: { glob: "*.reference-mismatches.tsv" } }
