# Toushin-kakomon

東進過去問データベースから、英語の過去問PDFをダウンロードするための個人用ツールです。
標準ライブラリのみで動くので、`pip` が使いにくい **a-Shell（iPad）** でもそのまま動きます。

対象校: 共通テスト／センター試験、旧帝大7校、TOCKY5校、早慶上理4校、MARCH5校、関関同立4校、日東駒専4校
（`universities.json` を編集すれば追加・削除できます）

ダウンロードの実行と、その利用は自分の判断と責任で行ってください。短時間に大量アクセスしないよう、
`--delay` は1秒以上を保つことを推奨します。

**重要**: 共通テスト／センター試験（`toshin.com`）は自動ダウンロードに対応していますが、
大学個別の過去問アーカイブ（`toshin-kakomon.com`）は、同じURLでもスクリプトからの機械的な
アクセスだけ404を返す挙動が確認されており（ブラウザで開くと正常に表示される）、意図的な
アクセス制限とみられます。そのため大学個別ページは**自動化せず、`url_checklist.md` を使って
手動でダウンロード**する運用にしています。詳しくは下記「大学個別ページの手動ダウンロード」を
参照してください。

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
4. 本番実行（共通テスト／センター試験のみ。大学個別は自動化していないので `--skip-universities` を付ける）
   ```
   python3 download_kakomon.py --skip-universities --years 20 --delay 2
   ```
5. 完了後、`downloads/` フォルダの中にPDFが並びます。
   実行結果の最後に出る `[summary]` 行で、新規取得件数・既存スキップ件数・失敗件数を確認できます。
6. まとめてZIPにしたい場合は `--zip` を付けてください（`--zip-only` で元フォルダを削除しZIPだけ残せます）。
7. a-Shellの `downloads/` フォルダは「ファイル」アプリの `On My iPad > a-Shell` 内から見えます。
   そこからiCloud DriveやAirDropで取り出せます。

## 大学個別ページの手動ダウンロード

大学個別の過去問アーカイブ（`toshin-kakomon.com`）は、前述のとおりスクリプトからのアクセスだけ
404になるため自動化していません。代わりに `url_checklist.md` に、各大学の「英語科目まとめページ」
と「年度別ページ（20年分）」の入り口URLを機械的に列挙してあります。

使い方:
1. iPadのSafariで `url_checklist.md` を開く（またはGitHub上でそのまま見る）。
2. 大学ごとに、まず「英語科目まとめページ」を開く。そこに求める年度の英語問題へのリンクが
   あれば、それをタップしてPDFを保存する（Safariの共有メニュー→「ファイルに保存」）。
3. まとめページに無い年度があれば、その大学の「年度別ページ」を開いて「英語」のリンクを探す。
4. 一覧を更新したい場合（学校や年数を変えたいときなど）は、リポジトリ内で再生成できます:
   ```
   python3 generate_url_list.py --years 20 > url_checklist.md
   ```

これらの入り口URL（`.../university/{code}/subject/e/` と `.../university/{code}/{year}/`）は
サイト自身が使っている構造そのものなので、ここから先はサイト上の本物のリンクをたどるだけで、
抜け漏れや構造の間違いは起きません。

## サイト構造が変わって0件になったとき

共通テスト／センター試験側で一致件数が0件になったページのHTMLは、既定で `diag/` フォルダに
保存されます。実行結果の `[summary]` に「取得失敗」や「英語リンク0件」が出ていたら、`diag/` 内の
該当ファイルを確認するか、私（Claude）に共有してもらえれば正規表現を追従修正します。

## オプション一覧

```
python3 download_kakomon.py --help
python3 generate_url_list.py --help
```
