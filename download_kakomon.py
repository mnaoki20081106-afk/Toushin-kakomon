#!/usr/bin/env python3
"""東進過去問データベース 英語過去問 一括ダウンロードツール

標準ライブラリのみで動作します（a-Shell などpipが使いにくい環境向け）。
実行・ダウンロードは利用者自身の判断と責任で行ってください（利用規約の範囲内で）。

大学別過去問は toshin-kakomon.com の年度別ページ
(/new_kakomon_db/university/{code}/{year}/) を年度ごとに取得し、
英語科目のexam id (e{code}{年の下2桁}NN) を持つ問題/解答/解説リンクを抜き出して
保存します（東京大学2026年度の実HTMLで構造を確認済み）。
共通テスト/センター試験は従来どおり toshin.com を参照します。

リンクが見つからない場合は [info]/[warn] でログに出すので、サイト構造が変わった
場合や年度未掲載の場合はそこで気づけます。

負荷をかけすぎないよう --delay（既定1.5秒）で間隔を空けて順番にアクセスします。
並列アクセスやアクセス元の偽装（IPローテーション等)は行いません。

大学別過去問（new_kakomon_db）の閲覧には東進会員ログインが必要です。環境変数
TOSHIN_EMAIL / TOSHIN_PASSWORD にログイン情報を設定しておくと、実行時に
https://www.toshin.com/member/login へログインしてから取得します
（パスワードをコマンドライン引数にしないのは、シェル履歴やプロセス一覧に
残らないようにするためです）。

toshin.com（ログイン）と toshin-kakomon.com（過去問DB本体）はドメインが
別で、単純なCookie使い回しだけではログイン状態が引き継がれないことを
実機検証で確認したため、大学別過去問の取得はPlaywright（実ブラウザの
Chromiumを自動操作）で行います。人がブラウザで操作するのと同じ手順
（ログインフォーム送信→各ページへ遷移）をなぞるだけで、内部のSSO連携が
どう動いていても正しく再現されます。事前に
    pip install playwright && playwright install chromium
が必要です（共通テスト/センター試験は従来どおりtoshin.comの公開ページを
標準ライブラリのみで取得するので、大学別過去問を使わないなら不要です）。

使い方:
    python3 download_kakomon.py                     # 直近20年ぶん全大学+共通テスト/センター試験
    python3 download_kakomon.py --years 10           # 直近10年ぶん
    python3 download_kakomon.py --only 東京 早稲田    # 大学名で絞り込み
    python3 download_kakomon.py --group 旧帝大 TOCKY  # universities.jsonのグループ名で絞り込み
    python3 download_kakomon.py --skip-kyotsu         # 共通テスト/センター試験を除外
    python3 download_kakomon.py --skip-universities   # 共通テスト/センター試験のみ
"""
import argparse
import datetime
import http.cookiejar
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
LOGIN_URL = f"{BASE}/member/login"
UA = (
    "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
}

# 共通テスト/センター試験(toshin.comの公開ページ、ログイン不要)用の共有opener。
COOKIE_JAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(COOKIE_JAR))


def fetch(url, timeout=20, retries=3, delay=1.5, referer=None, data=None):
    last_err = None
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers, data=data)
            with OPENER.open(req, timeout=timeout) as resp:
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


def login_playwright(page, email, password, delay):
    """https://www.toshin.com/member/login へ実ブラウザでログインする。
    toshin.comとtoshin-kakomon.com(過去問DB本体)は別ドメインで、単純な
    Cookie使い回しだけではログイン状態が引き継がれないことを実機検証で
    確認済み。Playwrightで実際にフォーム送信・ページ遷移させることで、
    サイト側がJSで行っている可能性のあるSSO連携もそのまま再現する。
    """
    # 広告/計測タグが常時通信し続けるページなので、networkidleは待っても
    # 到達しない（実際にタイムアウトした）。domcontentloaded + 要素待ちに
    # する。
    print("=== ログイン ===")
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    page.wait_for_selector('input[name="email"]', timeout=30000)
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', password)
    page.click('input.btn-login[type="submit"]')
    page.wait_for_load_state("domcontentloaded")
    if "/member/login" in page.url:
        print(f"  [error] ログインに失敗した可能性があります（現在のURL: {page.url}）。"
              f"メールアドレス/パスワードを確認してください。")
        return False

    time.sleep(delay)
    page.goto(f"{BASE_UNIV}/new_kakomon_db/university/0l/2026/", wait_until="domcontentloaded")
    if page.url.startswith(BASE_UNIV) and "/member" not in page.url:
        print("  [ok] ログイン成功（大学別過去問ページへのアクセスを確認）")
        return True
    print(
        f"  [error] toshin.comへのログインはできましたが、toshin-kakomon.com側では"
        f"ログイン状態が引き継がれていないようです（現在のURL: {page.url}）。"
    )
    return False


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


def download_university_pw(page, context, code, name, years, out_dir, delay):
    """大学別の年度ページ (/new_kakomon_db/university/{code}/{year}/) を年度ごとに
    ログイン済みのPlaywrightページで開き、英語科目の問題/解答/解説リンク
    (exam id が e{code}{yy}NN の形式) を抜き出して保存する。
    実際のページ (東京大学 2026年度で確認済み) は例えば
    href="/new_kakomon_db/university/0l/2026/e0l261/question/" のような形で、
    末尾が .pdf ではなく question/answer/commentary ディレクトリになっている。
    PDF本体のダウンロードは、ページ遷移せずに同じブラウザセッションのCookieを
    引き継ぐ context.request で行う（新しいタブを開かずに済む）。
    """
    print(f"=== {name} ({code}) ===")
    for year in years:
        url = f"{BASE_UNIV}/new_kakomon_db/university/{code}/{year}/"
        try:
            page.goto(url, wait_until="domcontentloaded")
        except Exception as e:
            print(f"  [warn] {year}: ページ取得失敗 ({url}) ({e})")
            time.sleep(delay)
            continue
        time.sleep(delay)
        if not page.url.startswith(BASE_UNIV):
            print(f"  [warn] {year}: ログイン状態が外れた可能性があります（現在のURL: {page.url}）")
            continue
        text = page.content()
        yy = str(year)[-2:]
        pattern = re.compile(
            rf'href="(/new_kakomon_db/university/{re.escape(code)}/{year}/'
            rf'e{re.escape(code)}{yy}\d+/(question|answer|commentary)/)"'
        )
        found = pattern.findall(text)
        if not found:
            snippet = re.sub(r"\s+", " ", text[:200]).strip()
            print(
                f"  [info] {year}: 取得{len(text)}文字 / 英語リンク一致0件"
                f"（サイト側の仕様変更やその年度未掲載の可能性） 冒頭: {snippet!r}"
            )
            continue
        seen = set()
        for href, kind in found:
            if href in seen:
                continue
            seen.add(href)
            exam_id = href.strip("/").split("/")[-2]
            pdf_url = BASE_UNIV + href
            try:
                resp = context.request.get(pdf_url)
            except Exception as e:
                print(f"  [warn] {year} {exam_id}_{kind}: 取得失敗 ({e})")
                time.sleep(delay)
                continue
            time.sleep(delay)
            if not resp.ok:
                print(f"  [warn] {year} {exam_id}_{kind}: HTTP {resp.status}")
                continue
            data = resp.body()
            ct = resp.headers.get("content-type", "")
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

    if not m and not m2:
        print(f"  [info] {year} {keyword}: リンク一致0件（サイト側の仕様変更やその年度未掲載の可能性）")


def download_kyotsutest(years, out_dir, delay):
    print("=== 共通テスト（英語） ===")
    for year in years:
        if year < 2021:
            continue
        url = f"{BASE}/kyotsutest/{year}/"
        html, _, _ = fetch(url, delay=delay)
        time.sleep(delay)
        if not html:
            print(f"  [warn] {year}: ページ取得失敗、または404 ({url})")
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
            print(f"  [warn] {year}: ページ取得失敗、または404 ({url})")
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
    ap.add_argument("--group", nargs="*", help="universities.jsonのグループ名で絞り込み（例: 旧帝大 TOCKY）")
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
        email = os.environ.get("TOSHIN_EMAIL")
        password = os.environ.get("TOSHIN_PASSWORD")
        if not email or not password:
            print(
                "[error] 大学別過去問には東進会員ログインが必要です。"
                "環境変数 TOSHIN_EMAIL / TOSHIN_PASSWORD を設定してください。"
            )
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print(
                "[error] playwrightがインストールされていません。"
                "`pip install playwright && playwright install chromium` を実行してください。"
            )
            return
        with sync_playwright() as p:
            browser = p.chromium.launch()
            browser_context = browser.new_context(user_agent=UA)
            page = browser_context.new_page()
            if not login_playwright(page, email, password, args.delay):
                print("[error] ログインに失敗したため中断します。")
                browser.close()
                return
            for group_name, schools in config.items():
                if args.group and group_name not in args.group:
                    continue
                for school in schools:
                    name, code = school["name"], school["code"]
                    if args.only and not any(q in name for q in args.only):
                        continue
                    download_university_pw(page, browser_context, code, name, years, args.out, args.delay)
            browser.close()

    if not args.skip_kyotsu:
        download_kyotsutest(years, args.out, args.delay)
        download_center(years, args.out, args.delay)

    if args.zip:
        zip_path = args.zip_name or f"{args.out.rstrip('/')}.zip"
        make_zip(args.out, zip_path)
        if args.zip_only:
            import shutil
            if os.path.isdir(args.out):
                shutil.rmtree(args.out)
                print(f"元フォルダを削除しました: {args.out}")
            else:
                print(f"元フォルダ({args.out})は生成されなかった（保存0件）ため削除をスキップしました。")

    print("完了しました。")


if __name__ == "__main__":
    main()
