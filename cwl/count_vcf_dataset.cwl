cwlVersion: v1.2
class: CommandLineTool
label: Count unique normalized VCF alleles by release, assembly, dataset, and chromosome
requirements:
  InitialWorkDirRequirement:
    listing:
      - entryname: count_vcf_dataset.sh
        entry: { $include: count_vcf_dataset.sh }
inputs:
  release: { type: string, inputBinding: { position: 1 } }
  assembly: { type: string, inputBinding: { position: 2 } }
  dataset: { type: string, inputBinding: { position: 3 } }
  chromosomes_csv: { type: string, inputBinding: { position: 4 } }
  chrom_map: { type: File, inputBinding: { position: 5 } }
  reference_fasta:
    type: File
    secondaryFiles: [.fai]
    inputBinding: { position: 6 }
  vcfs:
    type: File[]
    inputBinding: { position: 7 }
baseCommand: [bash, count_vcf_dataset.sh]
outputs:
  counts: { type: File, outputBinding: { glob: "*.vcf-counts.tsv" } }
  reference_mismatches: { type: File, outputBinding: { glob: "*.reference-mismatches.tsv" } }
