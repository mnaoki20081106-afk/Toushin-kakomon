#!/usr/bin/env python3
"""東進過去問データベース 英語過去問 一括ダウンロードツール

標準ライブラリのみで動作します（a-Shell などpipが使いにくい環境向け）。
実行・ダウンロードは利用者自身の判断と責任で行ってください。

使い方:
    python3 download_kakomon.py                     # 直近20年ぶん全大学+共通テスト/センター試験
    python3 download_kakomon.py --years 10           # 直近10年ぶん
    python3 download_kakomon.py --only 東京 早稲田    # 大学名で絞り込み
    python3 download_kakomon.py --skip-kyotsu         # 共通テスト/センター試験を除外
"""
import argparse
import datetime
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://www.toshin.com"
UA = "Mozilla/5.0 (compatible; personal-study-archiver/1.0)"


def fetch(url, timeout=20, retries=3, delay=1.5):
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(), resp.geturl(), resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, url, None
            last_err = e
        except Exception as e:
            last_err = e
        time.sleep(delay * attempt)
    print(f"  [warn] failed: {url} ({last_err})")
    return None, url, None


def safe_write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return False
    with open(path, "wb") as f:
        f.write(data)
    return True


def ext_from_content_type(ct, fallback=".pdf"):
    if not ct:
        return fallback
    ct = ct.split(";")[0].strip()
    return {"application/pdf": ".pdf", "text/html": ".html"}.get(ct, fallback)


def download_university(code, name, years, out_dir, delay):
    print(f"=== {name} ({code}) ===")
    for year in years:
        url = f"{BASE}/new_kakomon_db/university/{code}/{year}/"
        html, _, _ = fetch(url, delay=delay)
        time.sleep(delay)
        if not html:
            continue
        text = html.decode("utf-8", "ignore")
        yy = str(year)[-2:]
        pattern = re.compile(
            rf'href="(/new_kakomon_db/university/{re.escape(code)}/{year}/'
            rf'e{re.escape(code)}{yy}\d+/(question|answer|commentary)/)"'
        )
        seen = set()
        for href, kind in pattern.findall(text):
            if href in seen:
                continue
            seen.add(href)
            exam_id = href.strip("/").split("/")[-2]
            data, _, ct = fetch(BASE + href, delay=delay)
            time.sleep(delay)
            if not data:
                continue
            fname = f"{exam_id}_{kind}{ext_from_content_type(ct)}"
            path = os.path.join(out_dir, name, str(year), fname)
            if safe_write(path, data):
                print(f"  [ok] {year} {fname}")
            else:
                print(f"  [skip] {year} {fname} (既存)")


PDF_LINK_RE = re.compile(r'href="([^"]+\.pdf)"', re.IGNORECASE)


def resolve_question_pdf(question_url, delay):
    """問題ページ(HTML)からPDFリンクを探す。見つからなければHTMLをそのまま返す。"""
    data, final_url, ct = fetch(question_url, delay=delay)
    time.sleep(delay)
    if not data:
        return None, None
    if final_url and "toshin.com" not in final_url:
        print(f"    [note] toshin.com外へリダイレクトされたためスキップ: {final_url}")
        return None, None
    if ct and "pdf" in ct.lower():
        return data, ".pdf"
    text = data.decode("utf-8", "ignore")
    m = PDF_LINK_RE.search(text)
    if m:
        pdf_url = urllib.parse.urljoin(question_url, m.group(1))
        pdata, _, _ = fetch(pdf_url, delay=delay)
        time.sleep(delay)
        if pdata:
            return pdata, ".pdf"
    return data, ".html"


def _extract_and_save_pair(text, page_url, keyword, year, out_dir, delay):
    q_pattern = re.compile(rf'href="([^"]*{keyword}[^"]*(?:mondai|question)[^"]*\.html)"')
    m = q_pattern.search(text)
    if m:
        qurl = urllib.parse.urljoin(page_url, m.group(1))
        data, ext = resolve_question_pdf(qurl, delay)
        if data:
            fname = f"{year}_{keyword}_question{ext}"
            path = os.path.join(out_dir, "共通テスト・センター試験", fname)
            if safe_write(path, data):
                print(f"  [ok] {fname}")

    k_pattern = re.compile(rf'href="([^"]*{keyword}[^"]*\.pdf)"')
    m2 = k_pattern.search(text)
    if m2:
        kurl = urllib.parse.urljoin(page_url, m2.group(1))
        data, _, _ = fetch(kurl, delay=delay)
        time.sleep(delay)
        if data:
            fname = f"{year}_{keyword}_commentary.pdf"
            path = os.path.join(out_dir, "共通テスト・センター試験", fname)
            if safe_write(path, data):
                print(f"  [ok] {fname}")


def download_kyotsutest(years, out_dir, delay):
    print("=== 共通テスト（英語） ===")
    for year in years:
        if year < 2021:
            continue
        url = f"{BASE}/kyotsutest/{year}/"
        html, _, _ = fetch(url, delay=delay)
        time.sleep(delay)
        if not html:
            continue
        text = html.decode("utf-8", "ignore")
        _extract_and_save_pair(text, url, "reading", year, out_dir, delay)
        _extract_and_save_pair(text, url, "listening", year, out_dir, delay)


def download_center(years, out_dir, delay):
    print("=== センター試験（英語） ===")
    for year in years:
        if year > 2020:
            continue
        url = f"{BASE}/center/{year}/"
        html, _, _ = fetch(url, delay=delay)
        time.sleep(delay)
        if not html:
            continue
        text = html.decode("utf-8", "ignore")
        _extract_and_save_pair(text, url, "eigo", year, out_dir, delay)
        _extract_and_save_pair(text, url, "listening", year, out_dir, delay)


def main():
    ap = argparse.ArgumentParser(description="東進過去問DB 英語過去問 一括ダウンロード (標準ライブラリのみ)")
    ap.add_argument("--config", default="universities.json")
    ap.add_argument("--out", default="downloads")
    ap.add_argument("--start-year", type=int, default=None)
    ap.add_argument("--end-year", type=int, default=None)
    ap.add_argument("--years", type=int, default=20, help="末尾からの年数（既定20）")
    ap.add_argument("--delay", type=float, default=1.5, help="リクエスト間隔・秒（既定1.5）")
    ap.add_argument("--only", nargs="*", help="大学名の一部で絞り込み（スペース区切りで複数可）")
    ap.add_argument("--skip-kyotsu", action="store_true", help="共通テスト/センター試験を除外")
    ap.add_argument("--skip-universities", action="store_true", help="大学個別過去問を除外")
    args = ap.parse_args()

    end_year = args.end_year or datetime.date.today().year
    start_year = args.start_year or (end_year - args.years + 1)
    years = list(range(start_year, end_year + 1))

    with open(args.config, encoding="utf-8") as f:
        config = json.load(f)

    if not args.skip_universities:
        for schools in config.values():
            for school in schools:
                name, code = school["name"], school["code"]
                if args.only and not any(q in name for q in args.only):
                    continue
                download_university(code, name, years, args.out, args.delay)

    if not args.skip_kyotsu:
        download_kyotsutest(years, args.out, args.delay)
        download_center(years, args.out, args.delay)

    print("完了しました。")


if __name__ == "__main__":
    main()
