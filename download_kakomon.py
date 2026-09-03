#!/usr/bin/env python3
"""東進過去問データベース 英語過去問 一括ダウンロードツール

標準ライブラリのみで動作します（a-Shell などpipが使いにくい環境向け）。
実行・ダウンロードは利用者自身の判断と責任で行ってください（利用規約の範囲内で）。

大学別過去問は toshin-kakomon.com の「英語科目まとめページ」を起点にPDFリンクを
自動収集し、無ければ年度別ページ・問題/解答/解説の個別ページを辿ります
（サイト構造は変わりうるので、リンクが見つからない場合は都度ログに出します）。
共通テスト/センター試験は従来どおり toshin.com を参照します。

ネットワーク越しの実サイト確認はこの実行環境からは行えなかったため、
実際のHTML構造とズレがあればリンク抽出パターンの調整が必要な場合があります。

負荷をかけすぎないよう --delay（既定1.5秒）で間隔を空けて順番にアクセスします。
並列アクセスやアクセス元の偽装（IPローテーション等)は行いません。

使い方:
    python3 download_kakomon.py                     # 直近20年ぶん全大学+共通テスト/センター試験
    python3 download_kakomon.py --years 10           # 直近10年ぶん
    python3 download_kakomon.py --only 東京 早稲田    # 大学名で絞り込み
    python3 download_kakomon.py --skip-kyotsu         # 共通テスト/センター試験を除外
    python3 download_kakomon.py --skip-universities   # 共通テスト/センター試験のみ
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
import zipfile

BASE = "https://www.toshin.com"
BASE_UNIV = "https://www.toshin-kakomon.com"
UA = (
    "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
}


def fetch(url, timeout=20, retries=3, delay=1.5, referer=None):
    last_err = None
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
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


PDF_HREF_RE = re.compile(r'href="([^"]+\.pdf)"', re.IGNORECASE)


def _collect_pdf_links(html_bytes, page_url):
    text = html_bytes.decode("utf-8", "ignore")
    links = {urllib.parse.urljoin(page_url, m.group(1)) for m in PDF_HREF_RE.finditer(text)}
    return links, text


def _save_pdf_link(link, name, subdir, out_dir, delay, referer):
    data, _, ct = fetch(link, delay=delay, referer=referer)
    time.sleep(delay)
    if not data:
        return
    fname = os.path.basename(urllib.parse.urlparse(link).path) or "file.pdf"
    if not fname.lower().endswith((".pdf", ".html")):
        fname += ext_from_content_type(ct)
    path = os.path.join(out_dir, name, subdir, fname)
    if safe_write(path, data):
        print(f"  [ok] {subdir} {fname}")
    else:
        print(f"  [skip] {subdir} {fname} (既存)")


def _download_year_page(code, name, year, url, out_dir, delay):
    html, _, _ = fetch(url, delay=delay, referer=f"{BASE_UNIV}/new_kakomon_db/university/{code}/subject/e/")
    time.sleep(delay)
    if not html:
        return
    pdf_links, text = _collect_pdf_links(html, url)
    if pdf_links:
        for link in sorted(pdf_links):
            _save_pdf_link(link, name, str(year), out_dir, delay, referer=url)
        return
    # 直接PDFが無い場合は問題/解答/解説の個別ページを辿る
    subpage_re = re.compile(r'href="([^"]*/(?:question|answer|commentary)/)"')
    subpages = {urllib.parse.urljoin(url, h) for h in subpage_re.findall(text)}
    if not subpages:
        print(f"  [info] {year}: PDFリンクが見つかりません（サイト構造の変更や年度未掲載の可能性）")
        return
    for sp in sorted(subpages):
        sdata, sfinal, sct = fetch(sp, delay=delay, referer=url)
        time.sleep(delay)
        if not sdata:
            continue
        kind = sp.rstrip("/").split("/")[-1]
        if sct and "pdf" in sct.lower():
            fname = f"{sp.rstrip('/').split('/')[-2]}_{kind}.pdf"
            path = os.path.join(out_dir, name, str(year), fname)
            if safe_write(path, sdata):
                print(f"  [ok] {year} {fname}")
            else:
                print(f"  [skip] {year} {fname} (既存)")
            continue
        sub_links, _ = _collect_pdf_links(sdata, sp)
        for link in sorted(sub_links):
            _save_pdf_link(link, name, str(year), out_dir, delay, referer=sp)


def download_university(code, name, years, out_dir, delay):
    print(f"=== {name} ({code}) ===")
    subject_url = f"{BASE_UNIV}/new_kakomon_db/university/{code}/subject/e/"
    html, _, _ = fetch(subject_url, delay=delay, referer=BASE_UNIV)
    time.sleep(delay)

    handled_years = set()
    if html:
        pdf_links, text = _collect_pdf_links(html, subject_url)
        for link in sorted(pdf_links):
            _save_pdf_link(link, name, "英語科目まとめ", out_dir, delay, referer=subject_url)

        year_link_re = re.compile(
            rf'href="([^"]*/university/{re.escape(code)}/(20\d\d)/[^"]*)"'
        )
        for href, yr_str in year_link_re.findall(text):
            yr = int(yr_str)
            if yr not in years or yr in handled_years:
                continue
            _download_year_page(code, name, yr, urllib.parse.urljoin(subject_url, href), out_dir, delay)
            handled_years.add(yr)
    else:
        print(f"  [warn] まとめページ取得失敗: {subject_url}")

    for year in years:
        if year in handled_years:
            continue
        url = f"{BASE_UNIV}/new_kakomon_db/university/{code}/{year}/"
        _download_year_page(code, name, year, url, out_dir, delay)


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


def make_zip(out_dir, zip_path):
    out_dir = out_dir.rstrip("/")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(out_dir):
            for fname in files:
                full = os.path.join(root, fname)
                arcname = os.path.relpath(full, os.path.dirname(out_dir))
                zf.write(full, arcname)
    print(f"ZIP作成: {zip_path}")


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
    ap.add_argument("--zip", action="store_true", help="完了後にdownloadsフォルダをZIPにまとめる")
    ap.add_argument("--zip-name", default=None, help="ZIPファイル名（既定: <out>.zip）")
    ap.add_argument("--zip-only", action="store_true", help="ZIP化後に元のフォルダを削除してZIPだけ残す")
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

    if args.zip:
        zip_path = args.zip_name or f"{args.out.rstrip('/')}.zip"
        make_zip(args.out, zip_path)
        if args.zip_only:
            import shutil
            shutil.rmtree(args.out)
            print(f"元フォルダを削除しました: {args.out}")

    print("完了しました。")


if __name__ == "__main__":
    main()
