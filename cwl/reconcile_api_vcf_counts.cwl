cwlVersion: v1.2
class: CommandLineTool
label: Reconcile normalized VCF allele counts with API dataset counts
requirements:
  InitialWorkDirRequirement:
    listing:
      - entryname: reconcile_api_vcf_counts.sh
        entry: { $include: reconcile_api_vcf_counts.sh }
inputs:
  api_counts:
    type: File[]
    inputBinding: { position: 1 }
  vcf_counts:
    type: File[]
    inputBinding: { position: 2 }
baseCommand: [bash, reconcile_api_vcf_counts.sh]
outputs:
  counts: { type: File, outputBinding: { glob: api-vcf-counts.tsv } }
  mismatches: { type: File, outputBinding: { glob: api-vcf-mismatches.tsv } }
