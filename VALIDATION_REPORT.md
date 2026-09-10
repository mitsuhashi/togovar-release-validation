# TogoVar 2026.1 リリース整合性検証報告

## 結論（要約）

**現時点の総合判定は不合格である。** VCFリリース間比較では、今回の対象1,423比較を
すべて完了したが、GRCh38の3比較で旧版にのみ存在するalleleが合計535件検出された。
また、2026.1 VCFとstaging APIの比較では、450区分中86区分に件数不一致が残っている。

| 検査 | 実行結果 | 結論 |
|---|---|---|
| 20241203 VCFと2026.1 VCF | 対象1,423比較中1,420比較は`old - new = 0`。GRCh38 `gem_j_wga`で3件、GRCh38 `jga_wes`で532件、合計535件の旧版のみalleleを検出 | 原因確認と修正後の再検証が必要 |
| 2026.1 VCFとstaging API | 450区分中364区分が一致、86区分が不一致 | APIへの反映経路の調査が必要 |

VCF比較のmanifestは全1,974比較だが、GRCh38 `gnomad_exomes` 240比較、
`gnomad_genomes` 288比較、`tommo` 23比較の計551比較は今回計算せず、判定対象外とした。

GRCh37 `jga_snp`で当初検出された121件はREF/ALTの大小文字差による偽陽性であり、
大文字へ統一した再照合では0件となったため、上記535件には含めていない。

GRCh37 `tommo`のMTでは、旧・新VCFとも参照FASTAとのREF不一致を2,486件確認した。
旧・新間のallele key差は0件だが、今回はREF不一致を合否判定から除外しており、
MT VCFと参照FASTAの整合性が確認できたという意味ではない。

## 1. 検証の目的と全体像

20241203から2026.1への更新を、次の二段階で検証する。

```text
20241203 VCF ──┐
               ├─ 1. リリース間比較 ── 旧版variantの欠落がないことを確認
2026.1 VCF  ───┘
      │
      └───────── 2. VCF/API比較 ───── 2026.1がstaging APIへ反映されたことを確認
```

二つの検査は目的が異なる。

1. **VCF同士のリリース間比較**は、20241203に存在したalleleが2026.1から意図せず
   消えていないかを調べる退行検査である。
2. **最新VCFとAPIの比較**は、2026.1の公開VCFとstaging APIの件数が
   `assembly × dataset × chromosome` ごとに一致するかを調べる反映確認である。

API件数がVCF件数と一致しても、旧版のvariantが別のvariantと入れ替わっていないことまでは
証明できない。そのため、リリース間比較を先に行い、API比較を後段の整合性検査として行う。

比較元の次のディレクトリは、全処理を通じて読み取り専用とする。

- `/mnt/nas05/togovar/public/downloads/release/20241203`
- `/mnt/nas05/togovar/public/downloads/release/.2026.1`

一時ファイル、キャッシュ、結果は
`/data/togovar/etl/togovar-etl/2026.1/results/20241203_to_2026.1/` 以下に置く。

## 2. 共通する比較単位

VCFの行数ではなく、次の正規化済みallele keyを比較単位とする。

```text
CHROM  POS  REF  ALT
```

主な前処理は次のとおりである。

1. `bcftools annotate --rename-chrs` で `chr1` と `1` などのcontig名を統一する。
2. `bcftools norm -f ... -m -any` で参照配列に基づくleft alignmentとmulti-ALT分解を行う。
3. `bcftools query` で `CHROM/POS/REF/ALT` を抽出する。
4. REF/ALTを大文字へ統一し、塩基の大小文字だけによる偽の差分を除く。
5. `sort -u` で同一alleleを重複排除する。

GRCh37ではUCSC hg19のmitochondrial配列を含む
`reference/GRCh37.hg19.canonical.fa`、GRCh38では指定されたprimary assembly FASTAを使う。
REF不一致は別ファイルに記録し、結果を判定する際に確認する。

## 3. VCF同士のリリース間比較

### 3.1 目的

20241203の各VCFについて、そこに存在した正規化済みalleleが、対応する2026.1 VCF群の
和集合にすべて残っているかを確認する。単なる総件数の増減ではなく、集合差
`old - new` を求める。

### 3.2 対応関係

VCF対応表を自動生成した後、曖昧な組をレビューして実行用manifestを作成した。
manifest全体は論理比較1,974件で、内訳は次のとおりである。

- 1対1比較：1,973件
- 旧JGA WGS 1件と新版の染色体別VCF 24件の1対多比較：1件

このうち、今回の実行対象は1,423比較とした。次のGRCh38 551比較は計算しない方針とし、
今回の結果および合否判定の対象外とした。

| 対象外dataset | 比較数 |
|---|---:|
| `gnomad_exomes` | 240 |
| `gnomad_genomes` | 288 |
| `tommo` | 23 |
| 合計 | **551** |

1対多の場合は新版VCF群を別々に判定せず、全alleleの和集合を旧VCFと比較する。
MGENDは新版VCF追加後にmanifestとjobを再生成して追加する。確認済みのGRCh38 ToMMo
`chrMT` は除外記録に基づき対象外としている。

### 3.3 処理

`cwl/release_vcf_keys.cwl` がVCF対応単位でscatterし、
`cwl/compare_vcf_pair.cwl`から`compare_vcf_pair.sh`を実行する。

各比較では次のファイルを出力する。

- `*.missing.tsv`：旧版だけに存在したallele key
- `*.summary.tsv`：旧・新allele数、欠落数、REF不一致数
- `*.reference-mismatches.tsv`：VCFのREFと参照FASTAが一致しなかったレコード

合格条件は、今回の対象比較がすべて正常終了し、`missing_alleles=0`であることとする。
正当な削除がある場合は、理由とレビュー記録を持つ明示的なallow-listで扱う。

### 3.4 最終結果（今回の対象範囲）

**今回の対象1,423比較はすべて正常終了した。** そのうち1,420比較（99.8%）では、
正規化済みallele keyの集合差`old - new`が0件だった。残る3比較で、旧版にのみ存在する
alleleが合計535件検出されたため、VCFリリース間比較は不合格である。

| assembly | dataset | 完了比較数 | `old - new` allele数 | 差分あり比較数 |
|---|---|---:|---:|---:|
| GRCh37 | `bbj_riken` | 128 | 0 | 0 |
| GRCh37 | `gem_j_wga` | 23 | 0 | 0 |
| GRCh37 | `gnomad_exomes` | 216 | 0 | 0 |
| GRCh37 | `gnomad_genomes` | 184 | 0 | 0 |
| GRCh37 | `hgvd` | 2 | 0 | 0 |
| GRCh37 | `jga_snp` | 1 | 0 | 0 |
| GRCh37 | `jga_wes` | 1 | 0 | 0 |
| GRCh37 | `tommo` | 24 | 0 | 0 |
| GRCh38 | `bbj_riken` | 128 | 0 | 0 |
| GRCh38 | `gem_j_wga` | 23 | **3** | **2** |
| GRCh38 | `jga_snp` | 1 | 0 | 0 |
| GRCh38 | `jga_wes` | 1 | **532** | **1** |
| GRCh38 | `jga_wgs` | 1 | 0 | 0 |
| GRCh38 | `ncbn` | 690 | 0 | 0 |
| **合計** |  | **1,423** | **535** | **3** |

全完了比較の旧版allele数を単純合計すると9,177,988,466件で、`old - new` 535件を
差し引いた保持率は99.999994171%である。ただし、リリース退行検査では割合の大小ではなく、
承認されていない欠落が1件でもあるかを判定する。

#### 検出された旧版のみallele

GRCh38 `gem_j_wga`の3件は次のとおりである。

```text
11:54525074 N>NGAGGATATGCG
11:54525074 N>NGCG
21:10324327 N>NGGA
```

GRCh38 `jga_wes`の532件は、chromosome 7の12件
（101,655,590～101,684,341）とchromosome 22の520件
（15,154,542～15,583,065）に集中している。先頭例は次のとおりである。

```text
22:15154542 C>T
22:15154742 G>A
22:15154941 C>T
22:15155793 G>A
22:15156956 C>T
```

全532件は
`results/20241203_to_2026.1/cwl-refnorm-outputs-resume/grch38-jga-wes/batch-001/0617ef6279bdeaa3.missing.tsv`
を参照する。
旧VCFには上記例のレコードが存在し、2026.1 VCFの同一座位周辺には存在しないことを確認した。

#### 大小文字差とREF不一致の扱い

GRCh37 `jga_snp`では、修正前の比較で121件が検出されたが、旧版の正規化後REF/ALTが
小文字、新版が大文字だったことが原因である。REF/ALTを大文字化して再照合すると
`old - new`は0件になったため、欠落には含めない。比較スクリプトにも大文字化を追加した。

GRCh37 `tommo`のMTでは、旧・新とも参照FASTAとのREF不一致が2,486件記録されたが、
今回の方針ではREF不一致を合否判定から除外した。旧・新間のallele key差自体は0件である。
これはMT VCFが参照FASTAと整合することを保証するものではない。

## 4. 2026.1 VCFとstaging APIの比較

### 4.1 目的

2026.1公開VCFから得た正規化済みallele数と、2026.1 staging APIが返すvariant件数を、
`assembly × dataset × chromosome`単位で照合する。旧APIとの比較は行わない。

比較先は次のとおりである。

| assembly | staging API |
|---|---|
| GRCh37 | `https://stg-grch37.togovar.org` |
| GRCh38 | `https://stg-grch38.togovar.org` |

### 4.2 処理

`cwl/api_vcf_release_check.cwl`は次の三段階を実行する。

1. dataset配下の2026.1 VCFを共通手順で正規化し、全ファイルの和集合から染色体別件数を得る。
2. staging APIへ`quality=0`を指定して問い合わせ、quality filterによる除外を避けた件数を得る。
3. assembly、dataset、chromosomeをkeyとして両件数を結合し、差と判定を出力する。

対象は18組の`assembly × dataset`、各25染色体で、完了時には合計450行を照合する。
データセットごとのVCF和集合化はI/Oと一時領域を多く使うため、標準手順では逐次実行する。

合格条件は、全対象で`vcf_count = api_count`となり、
`api-vcf-mismatches.tsv`がheaderだけになることである。

### 4.3 2026年9月9日時点の最終件数結果

**API比較は完了している。**

- 完了済み：18/18 dataset組
- 照合済み：450/450行
- 一致：364行
- 件数不一致：86行
- VCF件数がAPI件数より多い差の合計：3,807
- API件数がVCF件数より多い差の合計：679
- 絶対差の合計：4,486

不一致の内訳を示す。差の方向は正規化済みユニークallele数の比較による。

| assembly | dataset | 不一致区分数 | 不一致染色体 | 差の方向・範囲 |
|---|---|---:|---|---|
| GRCh37 | `gem_j_wga` | 13 | 2, 3, 4, 6, 7, 10, 11, 16, 17, 19, 20, 21, X | VCFが1～3件多い |
| GRCh37 | `gnomad_exomes` | 1 | 1 | APIが1件多い |
| GRCh37 | `gnomad_genomes` | 13 | 1, 2, 3, 5, 10, 11, 12, 13, 16, 17, 19, 21, 22 | APIが1～5件多い |
| GRCh37 | `jga_snp` | 1 | MT | **VCFのみ5件、APIのみ0件** |
| GRCh37 | `jga_wes` | 1 | MT | **VCFのみ224件、APIのみ0件** |
| GRCh37 | `tommo` | 1 | MT | **VCFのみ3,503件、APIのみ0件** |
| GRCh38 | `gnomad_exomes` | 8 | 3, 7, 8, 11, 13, 16, 20, 22 | APIが1～2件多い |
| GRCh38 | `gnomad_genomes` | 23 | 1～22, X | APIが4～31件多い |
| GRCh38 | `jga_snp` | 1 | MT | **VCFのみ4件、APIのみ0件** |
| GRCh38 | `jga_wes` | 1 | MT | **VCFのみ54件、APIのみ0件** |
| GRCh38 | `jogo` | 23 | 1～22, X | APIが2～24件多い |

GRCh37の不一致は30区分、GRCh38の不一致は56区分であり、合計86区分である。

#### APIが0件のMT区分の解釈

`VCFのみ4件、APIのみ0件`は、当該の`assembly × dataset × MT`区分で、VCFに
正規化済みalleleが4件あり、APIの同じdatasetにはalleleが1件もないことを示す。
API側の集合が空なので、VCF側の4件はすべてAPIに未反映であると判断できる。
これは「VCF 5件、API 1件」のように一部だけが未反映という意味ではない。

GRCh38 `jga_snp`のMTでは、この状態が確認されている。単なる少数の正規化差よりも、
次の投入・公開設定上の問題を優先して調査する。

1. MTデータ自体がETLの入力対象から漏れた。
2. `MT`、`M`、`chrM`などのcontig名変換で除外された。
3. indexへの投入後に、staging APIが参照するaliasへ反映されていない。
4. MTが意図的に公開対象外となる設定がある。

ただし、件数だけから「追加し忘れ」と断定はしない。ETLの入力、変換、index登録、
alias反映の各段階でMTが存在するかを順に確認する。

一方、`VCFが1～3件多い`や`APIが4～31件多い`は、不一致染色体ごとの**件数差**である。
両方に多数のalleleが存在するため、どのalleleがVCFのみ・APIのみかは、この件数表だけでは
特定できない。原因調査では正規化済みallele keyの集合差を取得する。

正式結果は`api-vcf-final/api-vcf-counts.tsv`と
`api-vcf-final/api-vcf-mismatches.tsv`を参照する。

件数差が小さくてもallele集合差が相殺される場合がある。例えばGRCh37
`gem_j_wga`のchromosome 3は、全体件数ではVCFが1件多いだけだが、VCF側にのみ
存在するalleleとして少なくとも次の6件を確認した。

```text
3:1069573 CT>C
3:1069590 T>C
3:1069594 T>C
3:1069596 T>TTCC
3:1069598 T>C
3:1069600 T>C
```

したがって、件数比較は異常箇所の検出に使用し、原因調査と修正確認では同じ
正規化済みallele keyによる集合比較を追加する。

### 4.4 不一致の調査方針

不一致は次の順で調査する。

1. `api-vcf-mismatches.tsv`でassembly、dataset、chromosome、差の方向を確定する。
2. `*.reference-mismatches.tsv`を確認し、参照配列差による集計除外がないか調べる。
3. MTでAPIが0件となる組は、`MT`、`M`、`chrM`の変換、datasetのMT投入対象設定、
   Elasticsearch index/aliasおよびAPIのchromosome条件を確認する。
4. VCFがAPIより多い場合は、API投入時のfilter、正規化、重複統合、投入漏れを確認する。
5. APIがVCFより多い場合は、旧データがindexに残っていないか、aliasが正しいindexを
   指しているか、VCF export条件とAPI dataset対応が一致しているか確認する。
6. 数件差の組は、該当染色体のallele keyを対象に差分を絞り、元VCF、ETL中間生成物、
   API indexの順に追跡する。
7. 修正後に同じCWLを同じキャッシュディレクトリで再実行し、不一致が0になったことを確認する。

## 5. リリース判定

リリース可能と判断するには、次の両方を満たす必要がある。

| 検査 | 必要な状態 |
|---|---|
| 1. VCFリリース間比較 | 今回の対象1,423比較が全job成功し、旧版のみのalleleが0件、または全件が承認済みallow-list内 |
| 2. 2026.1 VCF/API比較 | 全450行が一致し、不一致ファイルがheaderのみ |

検査1は今回の対象1,423比較を完了したが、3比較に旧版のみのalleleが合計535件残っている。
また、検査2は完了したものの86行の件数不一致が残っている。そのため、現時点の
リリース整合性検証は不合格であり、差分原因の確認と修正後の再検証が必要である。

## 6. 再実行方法と成果物

job生成、CWL実行、一時ディレクトリとキャッシュの指定、出力ファイルの読み方は
[`README.md`](README.md)を参照する。結果更新時は、使用したjob JSON、CWL、対応表、
参照FASTA、実行日時、および最終summaryを一緒に保存する。
