#!/usr/bin/env python3
"""Create a CWL job JSON from a two-column VCF pair manifest."""
import argparse, csv, json, os
from collections import OrderedDict
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument("manifest", type=Path); p.add_argument("--old-root", type=Path, required=True); p.add_argument("--new-root", type=Path, required=True); p.add_argument("--chrom-map", type=Path, required=True); p.add_argument("--grch37-reference", type=Path, required=True); p.add_argument("--grch38-reference", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
a=p.parse_args()
if not a.chrom_map.is_file(): raise SystemExit(f"missing chromosome map: {a.chrom_map}")
for reference in (a.grch37_reference, a.grch38_reference):
 if not reference.is_file(): raise SystemExit(f"missing reference FASTA: {reference}")
 if not Path(str(reference)+".fai").is_file(): raise SystemExit(f"missing reference FASTA index: {reference}.fai")
# Make paths absolute for CWL job files, but preserve a reference symlink and
# its colocated .fai.  Path.resolve() would replace a curated local reference
# link with its target, whose index may use a different contig convention.
a.grch37_reference = Path(os.path.abspath(a.grch37_reference))
a.grch38_reference = Path(os.path.abspath(a.grch38_reference))
groups = OrderedDict()
with a.manifest.open() as f:
 for r in csv.reader(f, delimiter="\t"):
  if not r or r[0].startswith("#"): continue
  if len(r)!=2: raise SystemExit(f"bad manifest row: {r}")
  op=a.old_root/r[0]; np=a.new_root/r[1]
  if not op.is_file() or not np.is_file(): raise SystemExit(f"missing input: {op} or {np}")
  groups.setdefault(r[0], [])
  if str(np) not in groups[r[0]]: groups[r[0]].append(str(np))
old=[{"class":"File","path":str(a.old_root/rel)} for rel in groups]
new_groups=[[{"class":"File","path":path} for path in paths] for paths in groups.values()]
pair_ids=list(groups)
references=[]
for rel in groups:
 assembly=Path(rel).parts[0].lower()
 if assembly == "grch37": reference=a.grch37_reference
 elif assembly == "grch38": reference=a.grch38_reference
 else: raise SystemExit(f"cannot infer assembly from manifest path: {rel}")
 references.append({
  "class":"File",
  "path":str(reference),
  "secondaryFiles":[{"class":"File","path":str(reference)+".fai"}],
 })
a.output.write_text(json.dumps({"old_vcfs":old,"new_vcf_groups":new_groups,"pair_ids":pair_ids,"reference_fastas":references,"chrom_map":{"class":"File","path":str(a.chrom_map.resolve())}}, indent=2)+"\n")
