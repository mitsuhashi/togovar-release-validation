cwlVersion: v1.2
class: CommandLineTool
label: Fetch staging TogoVar API counts by assembly, dataset, and chromosome
requirements:
  NetworkAccess:
    networkAccess: true
  InitialWorkDirRequirement:
    listing:
      - entryname: fetch_staging_api_counts.sh
        entry: { $include: fetch_staging_api_counts.sh }
inputs:
  assembly: { type: string, inputBinding: { position: 1 } }
  api_url: { type: string, inputBinding: { position: 2 } }
  chromosomes:
    type: string[]
    inputBinding: { position: 3 }
baseCommand: [bash, fetch_staging_api_counts.sh]
outputs:
  counts: { type: File, outputBinding: { glob: "*.staging-api-counts.tsv" } }
  raw_responses: { type: Directory, outputBinding: { glob: "*.staging-api.raw" } }
