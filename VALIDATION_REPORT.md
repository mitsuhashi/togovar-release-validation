# TogoVar 2026.1 リリース整合性検証報告

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
4. `sort -u` で同一alleleを重複排除する。

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
現在のjobは論理比較1,974件で、内訳は次のとおりである。

- 1対1比較：1,973件
- 旧JGA WGS 1件と新版の染色体別VCF 24件の1対多比較：1件

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

合格条件は、すべての比較が正常終了し、`missing_alleles=0`であることとする。
正当な削除がある場合は、理由とレビュー記録を持つ明示的なallow-listで扱う。

### 3.4 現在の結果

**全1,974比較は実行中であり、リリース間の欠落有無の最終判定は未完了である。**

2026年9月9日時点で、GRCh37の次の553比較は正常終了している。正規化済みallele
keyの集合差`old - new`は、いずれも0件だった。

| dataset | 完了比較数 | 欠落allele数 |
|---|---:|---:|
| `bbj_riken` | 128 | 0 |
| `gem_j_wga` | 23 | 0 |
| `gnomad_exomes` | 216 | 0 |
| `gnomad_genomes` | 184 | 0 |
| `hgvd` | 2 | 0 |
| 合計 | 553 | **0** |

残りのGRCh37 datasetおよびGRCh38は実行中または未実行である。既存の
`cwl-refnorm-cache`を再利用しているため、最終出力はワークフロー全体の完了時に
`cwl-refnorm-outputs/`へ集約される。

以前の実行は、GRCh37の一部で次の警告を出した後、CWLが`permanentFail`で停止した。

- JGA SNP：`MT:15951` のREF不一致
- JGA WES：`Y:2649476` のREF不一致
- 併せてBGZFストリームの終端警告と終了コード255が発生

前回ログでは`Homo_sapiens.GRCh37.dna.primary_assembly.fa`が使われていた。その後、
GRCh37参照を`GRCh37.hg19.canonical.fa`へ変更し、現在の`job.refnorm.json`にもその
参照を明示した。エラー対象だった旧JGA SNP VCFを現在の参照で同じ
`annotate → norm → query`処理に通した確認では、各コマンドが終了コード0となり、
1,249,724 alleleを最後まで処理できた。

現在の再実行では、GRCh37参照を`GRCh37.hg19.canonical.fa`へ変更したjob JSONと
既存の`cwl-refnorm-cache`を使用している。再実行が全件完了するまでは、上表の
部分結果だけからリリース全体の合否を出さない。

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
| GRCh37 | `jga_snp` | 1 | MT | VCF 5件、API 0件 |
| GRCh37 | `jga_wes` | 1 | MT | VCF 224件、API 0件 |
| GRCh37 | `tommo` | 1 | MT | VCF 3,503件、API 0件 |
| GRCh38 | `gnomad_exomes` | 8 | 3, 7, 8, 11, 13, 16, 20, 22 | APIが1～2件多い |
| GRCh38 | `gnomad_genomes` | 23 | 1～22, X | APIが4～31件多い |
| GRCh38 | `jga_snp` | 1 | MT | VCF 4件、API 0件 |
| GRCh38 | `jga_wes` | 1 | MT | VCF 54件、API 0件 |
| GRCh38 | `jogo` | 23 | 1～22, X | APIが2～24件多い |

GRCh37の不一致は30区分、GRCh38の不一致は56区分であり、合計86区分である。

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
| 1. VCFリリース間比較 | 全job成功かつ旧版のみのalleleが0件、または全件が承認済みallow-list内 |
| 2. 2026.1 VCF/API比較 | 全450行が一致し、不一致ファイルがheaderのみ |

現時点では、検査1は全件完了前であり、検査2は完了したものの86行の件数不一致が
残っている。そのため、リリース整合性検証は未完了である。

## 6. 再実行方法と成果物

job生成、CWL実行、一時ディレクトリとキャッシュの指定、出力ファイルの読み方は
[`README.md`](README.md)を参照する。結果更新時は、使用したjob JSON、CWL、対応表、
参照FASTA、実行日時、および最終summaryを一緒に保存する。
