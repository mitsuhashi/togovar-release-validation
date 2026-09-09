# TogoVar リリース VCF の欠落 allele 検査

旧リリースに存在し、新リリースから消えている allele を検出するワークフローです。
推奨実行経路は CWL と `bcftools` です。Python は VCF 対応表から CWL job JSON を
生成する箇所にだけ使用します。

比較対象の release ディレクトリは読み取り専用です。一時ファイル、ログ、結果は
すべて `/data/togovar/etl/togovar-etl/2026.1/` 以下に作成してください。

## 文書の使い分け

- この `README.md` は、検査を再実行するためのコマンドと出力の読み方を記載した手順書です。
- [`VALIDATION_REPORT.md`](VALIDATION_REPORT.md) は、二つの検査を行う理由、判定基準、
  現在までの結果、および不一致が見つかった場合の調査方針を一つの流れでまとめた報告書です。

リリース判定では、最初にVCF同士のリリース間比較で退行がないことを確認し、次に
2026.1 VCFとstaging APIを照合して公開系への反映を確認します。

## 処理の流れ

```text
旧・新 release
  ↓
VCF 対応表を生成・レビュー
  ↓
CWL job JSON を生成
  ↓
VCF ペアごとに scatter
  ├─ bcftools annotate: contig 名を統一
  ├─ bcftools norm: multi-ALT を分解
  ├─ bcftools query: CHROM/POS/REF/ALT を抽出
  └─ comm: 旧版だけの allele を抽出
  ↓
ペア別 missing.tsv / summary.tsv
```

## 前提

db01 に `bcftools` と CWL runner が必要です。

```bash
export PATH=/home/togovar/.local/bin:$PATH
bcftools --version
cwltool --version
```

作業ディレクトリへ移動し、結果用ディレクトリを作成します。

```bash
cd /data/togovar/etl/togovar-etl/2026.1
mkdir -p results/20241203_to_2026.1/mapping
mkdir -p results/20241203_to_2026.1/cwl-outputs
mkdir -p results/20241203_to_2026.1/tmp/jobs
mkdir -p results/20241203_to_2026.1/tmp/intermediate
mkdir -p results/20241203_to_2026.1/cwl-cache
```

## 実行手順

### 1. VCF 対応表を生成する

```bash
python3 build_vcf_pair_manifest.py \
  --old-release /mnt/nas05/togovar/public/downloads/release/20241203 \
  --new-release /mnt/nas05/togovar/public/downloads/release/.2026.1 \
  --output-dir results/20241203_to_2026.1/mapping
```

次のファイルが生成されます。

- `vcf_pair_manifest.tsv`: 自動対応できた VCF ペア。CWL 入力に使用します。
- `vcf_pair_provenance.tsv`: 各対応の判定根拠。
- `vcf_pair_review.tsv`: 自動対応できなかった VCF。
- `vcf_pair_report.json`: 対応数の集計。

自動採用するのは、相対パス完全一致、両 release で一意な basename、または
一意な「親ディレクトリ＋chromosome」の組だけです。曖昧な対応は推測しません。

### 2. 対応表をレビューする

```bash
cat results/20241203_to_2026.1/mapping/vcf_pair_report.json
less results/20241203_to_2026.1/mapping/vcf_pair_review.tsv
```

`vcf_pair_review.tsv` に残った VCF は、次のいずれかを確認してください。

- 単なるファイル名・ディレクトリ変更
- 一つの VCF から chromosome 別 VCF への分割、またはその逆
- population や dataset 構成の変更
- 新版で意図的に廃止された VCF

1 対 1 と確認できた組だけを `vcf_pair_manifest.tsv` のコピーへ追記します。
現在の CWL は旧 VCF 1件に対して新 VCF 1件以上をまとめて比較できます。

20241203 → .2026.1 では、レビュー済みの JGA WGS 1対24対応を追加した実行用
manifest を次のように作成します。

```bash
cp results/20241203_to_2026.1/mapping/vcf_pair_manifest.tsv \
  results/20241203_to_2026.1/mapping/vcf_pair_manifest.ready.tsv
grep -v '^#' mapping/20241203_to_2026.1.overrides.tsv \
  >> results/20241203_to_2026.1/mapping/vcf_pair_manifest.ready.tsv
```

同じ旧 VCF が manifest に複数行ある場合、`build_job.py` はそれらを一つの
比較 job にまとめ、新 VCF 群の allele 和集合と比較します。今回の保留・除外理由は
`mapping/20241203_to_2026.1.exclusions.tsv` に記録しています。

### 3. CWL を検証する

```bash
cwltool --validate cwl/compare_vcf_pair.cwl
cwltool --validate cwl/release_vcf_keys.cwl
```

### 4. CWL job JSON を生成する

GRCh37 VCFはUCSC hg19の `chrM`（16,571 bp）を使用するため、最初にcanonical名の
参照indexを作業ディレクトリへ準備します。FASTA本体はコピーせず、読み取り専用元への
symlinkを使用します。

```bash
bash cwl/prepare_grch37_reference.sh
```

```bash
python3 cwl/build_job.py \
  results/20241203_to_2026.1/mapping-reviewed/vcf_pair_manifest.ready.tsv \
  --old-root /mnt/nas05/togovar/public/downloads/release/20241203 \
  --new-root /mnt/nas05/togovar/public/downloads/release/.2026.1 \
  --chrom-map cwl/rename_chrom.tsv \
  --grch37-reference /data/togovar/etl/togovar-etl/2026.1/reference/GRCh37.hg19.canonical.fa \
  --grch38-reference /mnt/nas05/togovar/original/grch38/reference_genome/Homo_sapiens.GRCh38.dna.primary_assembly.fa \
  --output results/20241203_to_2026.1/job.refnorm.json
```

この Python は VCF を読みません。manifest の各行を CWL の `old_vcfs`、
`new_vcfs`、`pair_ids` 配列へ変換するだけです。

### 5. まず 1 ペアで動作確認する

```bash
sed -n '1,2p' results/20241203_to_2026.1/mapping-reviewed/vcf_pair_manifest.ready.tsv \
  > results/20241203_to_2026.1/smoke-manifest.tsv
mkdir -p results/20241203_to_2026.1/smoke-output

python3 cwl/build_job.py \
  results/20241203_to_2026.1/smoke-manifest.tsv \
  --old-root /mnt/nas05/togovar/public/downloads/release/20241203 \
  --new-root /mnt/nas05/togovar/public/downloads/release/.2026.1 \
  --chrom-map cwl/rename_chrom.tsv \
  --grch37-reference /data/togovar/etl/togovar-etl/2026.1/reference/GRCh37.hg19.canonical.fa \
  --grch38-reference /mnt/nas05/togovar/original/grch38/reference_genome/Homo_sapiens.GRCh38.dna.primary_assembly.fa \
  --output results/20241203_to_2026.1/smoke-job.json

cwltool --parallel \
  --tmpdir-prefix "$PWD/results/20241203_to_2026.1/tmp/jobs/" \
  --cachedir "$PWD/results/20241203_to_2026.1/smoke-cache" \
  --outdir results/20241203_to_2026.1/smoke-output \
  --write-summary results/20241203_to_2026.1/smoke-cwl-output.json \
  cwl/release_vcf_keys.cwl \
  results/20241203_to_2026.1/smoke-job.json
```

### 6. 全 VCF ペアを実行する

手順4で生成した参照FASTA正規化対応jobを使用します。

- `results/20241203_to_2026.1/job.refnorm.json`
- 論理比較 1,974件（1対1が1,973件、JGA WGSの1対24が1件）
- MGENDは新版VCF追加待ちのため未収載
- GRCh38 ToMMo `chrMT` は確認済み除外

`cwltool` で実行する場合：

```bash
mkdir -p results/20241203_to_2026.1/tmp/jobs
mkdir -p results/20241203_to_2026.1/cwl-refnorm-cache
mkdir -p results/20241203_to_2026.1/cwl-refnorm-outputs

cwltool --parallel \
  --tmpdir-prefix "$PWD/results/20241203_to_2026.1/tmp/jobs/" \
  --cachedir "$PWD/results/20241203_to_2026.1/cwl-refnorm-cache" \
  --outdir results/20241203_to_2026.1/cwl-refnorm-outputs \
  --write-summary results/20241203_to_2026.1/cwl-refnorm-output.json \
cwl/release_vcf_keys.cwl \
  results/20241203_to_2026.1/job.refnorm.json
```

#### 大規模scatterが停止した場合の分割再開

`cwltool --parallel`が多数のscatter jobを開始できず、CPU使用だけが継続して
結果ファイルが増えない場合は、そのプロセスを停止し、datasetごと・最大50論理比較ごとに
分割して**逐次**実行します。既存の`--cachedir`を使うため、完了済み比較は再利用されます。

次はGRCh37 `tommo`の例です。`split_manifest.py`は同じ旧VCFに対応する複数の新版VCFを
同じbatchに保持するため、1対多比較を分断しません。

```bash
cd /data/togovar/etl/togovar-etl/2026.1

python3 cwl/split_manifest.py \
  results/20241203_to_2026.1/mapping-reviewed/vcf_pair_manifest.ready.tsv \
  --prefix grch37/frequency/vcf/tommo/ \
  --max-pairs 50 \
  --output-dir results/20241203_to_2026.1/batches/grch37-tommo

for manifest in results/20241203_to_2026.1/batches/grch37-tommo/batch-*.tsv; do
  name=$(basename "$manifest" .tsv)
  python3 cwl/build_job.py "$manifest" \
    --old-root /mnt/nas05/togovar/public/downloads/release/20241203 \
    --new-root /mnt/nas05/togovar/public/downloads/release/.2026.1 \
    --chrom-map cwl/rename_chrom.tsv \
    --grch37-reference reference/GRCh37.hg19.canonical.fa \
    --grch38-reference /mnt/nas05/togovar/original/grch38/reference_genome/Homo_sapiens.GRCh38.dna.primary_assembly.fa \
    --output "results/20241203_to_2026.1/batches/grch37-tommo/${name}.json"
  /home/togovar/.local/bin/cwltool \
    --tmpdir-prefix "$PWD/results/20241203_to_2026.1/tmp/jobs/" \
    --cachedir "$PWD/results/20241203_to_2026.1/cwl-refnorm-cache" \
    --outdir "results/20241203_to_2026.1/cwl-refnorm-outputs-resume/${name}" \
    --write-summary "results/20241203_to_2026.1/cwl-refnorm-output-${name}.json" \
    cwl/release_vcf_keys.cwl \
    "results/20241203_to_2026.1/batches/grch37-tommo/${name}.json"
done
```

`--prefix`を`grch38/frequency/vcf/ncbn/`など対象datasetの相対パスへ変更して同様に実行します。
新しい出力先を指定しても、同じcacheを指定する限り完了済み比較は再計算しません。

Toil を使用する場合：

```bash
toil-cwl-runner \
  --jobStore results/20241203_to_2026.1/toil-jobstore \
  --workDir "$PWD/results/20241203_to_2026.1/tmp/toil" \
  --outdir results/20241203_to_2026.1/cwl-refnorm-outputs \
  cwl/release_vcf_keys.cwl \
  results/20241203_to_2026.1/job.refnorm.json
```

### 7. MGEND追加後に再生成する

新版の MGEND VCF が配置された後は、手順1の対応表生成をもう一度実行します。
その後、JGA WGS overrideを追記して手順4の job JSONを再生成してください。
同じ相対パスにMGENDが追加されれば、対応表へ自動的に採用されます。

手順6と**同じ `--cachedir`** を指定すると、入力VCF・比較スクリプト・パラメータが
変わっていない1,974件はcacheから再利用され、追加されたMGENDのjobだけが新規実行
されます。全結果を一つにまとめた新しい出力ディレクトリを指定してください。

```bash
mkdir -p results/20241203_to_2026.1/cwl-refnorm-outputs-final

cwltool --parallel \
  --tmpdir-prefix "$PWD/results/20241203_to_2026.1/tmp/jobs/" \
  --cachedir "$PWD/results/20241203_to_2026.1/cwl-refnorm-cache" \
  --outdir results/20241203_to_2026.1/cwl-refnorm-outputs-final \
  --write-summary results/20241203_to_2026.1/cwl-refnorm-output-final.json \
  cwl/release_vcf_keys.cwl \
  results/20241203_to_2026.1/job.final.json
```

`cwl-refnorm-outputs-final/` にはcacheから再利用した既存結果と、新規MGEND結果がまとめて
配置されます。比較スクリプトや既存VCFを変更した場合、その影響を受けるjobはcache
keyが変わるため再実行されます。

## 結果の見方

CWL は VCF ペアごとに、pair IDのSHA-256先頭16桁を名前にした二つのファイルを出力します。

- `<pair-key>.missing.tsv`: 旧版だけに存在する `CHROM POS REF ALT`。
- `<pair-key>.summary.tsv`: pair ID、旧・新 VCF、旧・新 allele 数、欠落 allele 数、REF不一致数。
- `<pair-key>.reference-mismatches.tsv`: FASTAとVCFのREFが一致しないレコード。

`*.missing.tsv` が空なら、その VCF ペアに欠落はありません。`*.summary.tsv` の
`missing_alleles` が 0 より大きいペアから調査します。CWL の出力ファイル一覧と
対応関係は `cwl-output.json` に記録されます。

## 比較仕様と注意点

- `chr1` と `1` のような contig 表記は `cwl/rename_chrom.tsv` で統一します。
- multi-ALT レコードは `bcftools norm -m -any` で allele 単位に分解します。
- GRCh37/38それぞれのprimary assembly FASTAを指定した `bcftools norm -f` で
  left-alignし、REFも検証します。
- REF不一致は `--check-ref w` で記録し、比較全体は停止しません。REF不一致を含む
  pairは `reference-mismatches.tsv` を確認してから判定してください。
- 比較キーは `CHROM,POS,REF,ALT` です。INFO、FILTER、ID は同一性判定に使いません。
- 比較全体で `LC_ALL=C` を固定し、`sort` と `comm` の照合順序を一致させます。
- `bcftools isec` は record 単位の同一性判定がこの検査の allele キーと異なる場合が
  あるため、release gate には使用していません。

## 欠落原因の調査

1. manifest の VCF 対応が正しいか確認します。
2. `summary.tsv` で欠落数が多い dataset・assembly・chromosome を特定します。
3. `missing.tsv` の allele キーを使い、入力、filter、liftover、normalization、export
   の各 ETL 段階を追跡します。
4. 原因となった ETL rule または入力対応を修正し、staging 領域で再生成します。
5. 同じ CWL job を再実行し、欠落が解消したことを確認します。

正当な削除は dataset/assembly/CHROM/POS/REF/ALT、理由、issue link を含む
レビュー済み allow-list で管理してください。ファイルや dataset 全体を一括で
無視しないでください。

## VCF件数とAPI件数の照合

API検査では旧APIと新APIを直接比較しません。2026.1 release内で同じ
`assembly × dataset × chromosome` の公開VCF allele数とstaging API件数だけを比較します。

```text
2026.1 VCF ────→ new VCF件数 ──┐
                               ├─ VCF/API照合
staging API ───→ API件数 ──────┘
```

VCF件数はdataset配下の全VCFから `CHROM/POS/REF/ALT` を抽出し、multi-ALTを
分解し、assembly別の参照FASTAでleft-alignしたうえで和集合を取ります。
重複VCFやpopulation別VCFによる二重計上は `sort -u` で除きます。
APIリクエストにはすべて `quality=0` を指定します。

### 1. API/VCF照合用jobを生成する

```bash
python3 cwl/build_api_vcf_job.py \
  --new-root /mnt/nas05/togovar/public/downloads/release/.2026.1 \
  --dataset-map cwl/api_vcf_datasets.tsv \
  --chrom-map cwl/rename_chrom.tsv \
  --grch37-reference /data/togovar/etl/togovar-etl/2026.1/reference/GRCh37.hg19.canonical.fa \
  --grch38-reference /mnt/nas05/togovar/original/grch38/reference_genome/Homo_sapiens.GRCh38.dna.primary_assembly.fa \
  --output results/20241203_to_2026.1/api-vcf-staging-job.json
```

`cwl/api_vcf_datasets.tsv` が、公開VCFのdirectory名とAPIのdataset名の対応表です。
対応を推測しないため、ここに記載されたdatasetだけを照合します。MGEND VCF追加後は
job JSONを再生成してください。

### 2. CWLを実行する

```bash
mkdir -p results/20241203_to_2026.1/tmp/api-vcf-jobs
mkdir -p results/20241203_to_2026.1/api-vcf-cache
mkdir -p results/20241203_to_2026.1/api-vcf-final

cwltool \
  --tmpdir-prefix "$PWD/results/20241203_to_2026.1/tmp/api-vcf-jobs/" \
  --cachedir "$PWD/results/20241203_to_2026.1/api-vcf-cache" \
  --outdir results/20241203_to_2026.1/api-vcf-final \
  --write-summary results/20241203_to_2026.1/api-vcf-output-final.json \
  cwl/api_vcf_release_check.cwl \
  results/20241203_to_2026.1/api-vcf-staging-job.json
```

GNU sortの一時ファイルとCWL jobの一時ファイルはすべて作業directory以下に置かれます。
既存の不完全な `api-counts` は削除せず、そのまま残して構いません。
この照合はdatasetごとに多数のVCFを和集合化するため、標準手順ではI/O集中と一時領域の
急増を避けて逐次実行します。再実行時は同じ `--cachedir` を指定すると、完了済みの
dataset集計が再利用されます。

比較先はjob生成時に次のように設定されます。

| assembly | 2026.1 staging API |
|---|---|
| GRCh37 | `https://stg-grch37.togovar.org` |
| GRCh38 | `https://stg-grch38.togovar.org` |

主な出力は次のとおりです。

- `api-vcf-counts.tsv`: release・assembly・dataset・chromosomeごとのVCF件数、API件数、差、判定。
- `api-vcf-mismatches.tsv`: 件数不一致の行だけを抽出した調査対象一覧。
- `new.<assembly>.<dataset>.vcf-counts.tsv`: 参照正規化・重複排除後の2026.1 VCF件数。
- `<assembly>.staging-api-counts.tsv`: staging APIから取得した件数。
- `new.<assembly>.<dataset>.reference-mismatches.tsv`: VCFと参照FASTAのREF不一致。

判定は `match`、`api_missing`、`vcf_missing`、`count_mismatch` です。
`api-vcf-mismatches.tsv` がheaderだけなら、照合対象datasetのVCF件数とAPI件数は
すべて一致しています。不一致時はAPI用ETL投入、Elasticsearch index、alias、
公開対象設定、VCF export条件を確認します。

この件数照合だけではvariant identityの一致までは証明できません。release間で旧variantが
消えていないことは、前節のVCF集合差 `missing_alleles` で判定してください。

## 補助的な Python/SQLite 比較

`check_release_vcf_degradation.py` は CWL とは独立した検証用実装です。通常の
release-wide 実行では CWL を使用し、結果のクロスチェックが必要な場合だけ
Python/SQLite 版を使用してください。
