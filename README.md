# Toushin-kakomon

東進過去問データベース（toshin.com）から、英語の過去問PDFをまとめてダウンロードするための個人用ツールです。
標準ライブラリのみで動くので、`pip` が使いにくい **a-Shell（iPad）** でもそのまま動きます。

対象校: 共通テスト／センター試験、旧帝大7校、TOCKY5校、早慶上理4校、MARCH5校、関関同立4校、日東駒専4校
（`universities.json` を編集すれば追加・削除できます）

ダウンロードの実行と、その利用は自分の判断と責任で行ってください。短時間に大量アクセスしないよう、
`--delay` は1秒以上を保つことを推奨します。

## a-Shellでの使い方

1. App StoreからiPad用「a-Shell」をインストールする。
2. このリポジトリを a-Shell に取り込む（どちらか）
   - `git clone` が使える場合: a-Shell上で
     ```
     git clone https://github.com/mnaoki20081106-afk/toushin-kakomon.git
     cd toushin-kakomon
     ```
   - もしくは「ファイル」アプリでこのフォルダをiPadの `On My iPad/a-Shell` 配下にコピーし、
     a-Shellで `cd` して移動する。
3. まず接続確認だけ行う（本番実行の前に必ず）
   ```
   python3 download_kakomon.py --selftest
   ```
   `[selftest] 成功` と出れば、この環境からサイトに接続できています。
   失敗する場合はWi-Fi/モバイル通信の設定や、機内モード等を確認してください。
4. 本番実行（例: 直近20年分、全校）
   ```
   python3 download_kakomon.py --years 20 --delay 2
   ```
   一部の大学だけ試したい場合:
   ```
   python3 download_kakomon.py --only 東京 早稲田 --years 5 --delay 2
   ```
5. 完了後、`downloads/` フォルダの中に「大学名/年度/ファイル」の形でPDFが並びます。
   実行結果の最後に出る `[summary]` 行で、新規取得件数・既存スキップ件数・失敗件数を確認できます。
6. まとめてZIPにしたい場合は `--zip` を付けてください（`--zip-only` で元フォルダを削除しZIPだけ残せます）。
7. a-Shellの `downloads/` フォルダは「ファイル」アプリの `On My iPad > a-Shell` 内から見えます。
   そこからiCloud DriveやAirDropで取り出せます。

## サイト構造が変わって0件になったとき

一致件数が0件になったページのHTMLは、既定で `diag/` フォルダに保存されます。
実行結果の `[summary]` に「英語リンク0件のページ」が出ていたら、`diag/` 内の該当ファイルを
確認するか、私（Claude）に共有してもらえれば正規表現を追従修正します。

## オプション一覧

```
python3 download_kakomon.py --help
```
