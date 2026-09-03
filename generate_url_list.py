#!/usr/bin/env python3
"""大学個別の過去問アーカイブを手動で開くための入り口URL一覧を生成する。

方針: 個々の問題PDFのURL（学部ごとに連番が変わる）はサイトを見ないと
正確に分からないため、ここでは推測しない。代わりに、サイト自身が
生成する「英語科目まとめページ」と「年度別ページ」という、常に構造が
確定している入り口URLだけを機械的に列挙する。ここから先はサイト上の
本物のリンクをたどるだけなので、抜け漏れや構造間違いが起きない。

使い方:
    python3 generate_url_list.py > url_checklist.md
    python3 generate_url_list.py --start-year 2007 --end-year 2026
"""
import argparse
import datetime
import json

BASE = "https://www.toshin.com"
BASE_KAKOMON = "https://www.toshin-kakomon.com"


def main():
    ap = argparse.ArgumentParser(description="大学個別過去問の入り口URL一覧を生成")
    ap.add_argument("--config", default="universities.json")
    ap.add_argument("--start-year", type=int, default=None)
    ap.add_argument("--end-year", type=int, default=None)
    ap.add_argument("--years", type=int, default=20, help="末尾からの年数（既定20）")
    args = ap.parse_args()

    end_year = args.end_year or datetime.date.today().year
    start_year = args.start_year or (end_year - args.years + 1)
    years = list(range(end_year, start_year - 1, -1))

    with open(args.config, encoding="utf-8") as f:
        config = json.load(f)

    print(f"# 大学別 英語過去問 入り口URL一覧（{start_year}〜{end_year}年度）\n")
    print(
        "個々の問題PDFのURLはサイト側の実リンクをたどらないと正確に分からないため、"
        "ここでは載せていません。まず「英語科目まとめページ」を開き、"
        "無ければ各年度ページから「英語」を探してください。\n"
    )

    print("## 共通テスト・センター試験（英語）\n")
    print(
        "こちらは `download_kakomon.py`（`--skip-universities` を付けずに実行）で自動取得済みですが、"
        "参照用に入り口ページも載せておきます。\n"
    )
    for year in years:
        if year >= 2021:
            print(f"- [ ] {year}年度 共通テスト: {BASE}/kyotsutest/{year}/")
        else:
            print(f"- [ ] {year}年度 センター試験: {BASE}/center/{year}/")
    print()

    for group, schools in config.items():
        print(f"## {group}\n")
        for school in schools:
            name, code = school["name"], school["code"]
            print(f"### {name}（コード: {code}）\n")
            print(f"- 英語科目まとめページ（まずここを確認）: {BASE_KAKOMON}/new_kakomon_db/university/{code}/subject/e/")
            print("- 年度別ページ（上記に無い年度はここから）:")
            for year in years:
                url = f"{BASE_KAKOMON}/new_kakomon_db/university/{code}/{year}/"
                print(f"  - [ ] {year}年度: {url}")
            print()


if __name__ == "__main__":
    main()
