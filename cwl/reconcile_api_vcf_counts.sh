#!/usr/bin/env bash
set -euo pipefail

mkdir -p sort-tmp
export TMPDIR="$PWD/sort-tmp"
output=api-vcf-counts.tsv
awk -F '\t' -v OFS='\t' '
  FNR == 1 { next }
  FILENAME ~ /\.staging-api-counts\.tsv$/ {
    api["new" SUBSEP $1 SUBSEP $2 SUBSEP $3]=$4
    next
  }
  FILENAME ~ /\.vcf-counts\.tsv$/ {
    key=$1 SUBSEP $2 SUBSEP $3 SUBSEP $4
    vcf[key]=$5
    keys[key]=1
  }
  END {
    print "release","assembly","chromosome","dataset","vcf_count","api_count","delta","status","likely_cause","recommended_action"
    for (key in keys) {
      split(key, part, SUBSEP)
      vc=vcf[key]+0
      ac=api[key]+0
      if (vc == ac) {
        status="match"; cause=""; action=""
      } else if (vc > 0 && ac == 0) {
        status="api_missing"; cause="VCFは存在するがAPI dataset/chromosomeが未投入、alias漏れ、または公開対象外"; action="ETL投入ログ、index、alias、公開対象設定を確認"
      } else if (vc == 0 && ac > 0) {
        status="vcf_missing"; cause="APIに存在するが公開VCFに該当alleleがない、またはdataset対応が不正"; action="VCF export条件とdataset対応表を確認"
      } else {
        status="count_mismatch"; cause="VCF exportとAPI indexのfilter、normalize、重複排除、または投入状態が不一致"; action="同じdataset/chromosomeのallele集合を段階別に照合"
      }
      print part[1],part[2],part[3],part[4],vc,ac,ac-vc,status,cause,action
    }
  }
' "$@" > api-vcf-counts.unsorted.tsv
head -n 1 api-vcf-counts.unsorted.tsv > "$output"
tail -n +2 api-vcf-counts.unsorted.tsv | LC_ALL=C sort -T "$TMPDIR" -t '	' -k1,1 -k2,2 -k4,4 -k3,3V >> "$output"
awk -F '\t' 'NR==1 || $8!="match"' "$output" > api-vcf-mismatches.tsv
