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

# ログインセッションのCookieを全リクエストで使い回すための共有opener。
COOKIE_JAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(COOKIE_JAR))

CSRF_RE = re.compile(r'name="_csrfToken"[^>]*value="([^"]+)"')


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


def login(email, password, delay):
    """https://www.toshin.com/member/login へログインする。
    CakePHP系のCSRFトークン方式で、ログインページのhidden inputに
    埋め込まれた_csrfTokenをそのままPOSTで送り返す必要がある。
    ログイン後、大学別過去問(toshin-kakomon.com、別ドメイン)が実際に
    閲覧できるかは別ドメインのため保証されないので、直後に疎通確認を行う。
    """
    print("=== ログイン ===")
    html, _, _ = fetch(LOGIN_URL, delay=delay)
    time.sleep(delay)
    if not html:
        print("  [error] ログインページの取得に失敗しました")
        return False
    text = html.decode("utf-8", "ignore")
    m = CSRF_RE.search(text)
    if not m:
        print("  [error] _csrfTokenが見つかりません（サイト側の仕様変更の可能性）")
        return False
    form_data = urllib.parse.urlencode(
        {
            "_method": "POST",
            "_csrfToken": m.group(1),
            "email": email,
            "password": password,
            "remember_me": "0",
        }
    ).encode()
    html, final_url, _ = fetch(LOGIN_URL, delay=delay, referer=LOGIN_URL, data=form_data)
    time.sleep(delay)
    if not html:
        print("  [error] ログインリクエストに失敗しました")
        return False
    if final_url and "/member/login" in final_url:
        print(f"  [error] ログインに失敗した可能性があります（リダイレクト先: {final_url}）。"
              f"メールアドレス/パスワードを確認してください。")
        return False

    check_url_target = f"{BASE_UNIV}/new_kakomon_db/university/0l/2026/"
    check_html, check_url, _ = fetch(check_url_target, delay=delay)
    time.sleep(delay)
    # ドメインごとリダイレクトされていないか（toshin.com側の会員ページに飛ばされていないか）も含めて確認する。
    # 単に"/member/login"を含まないかだけでは、会員トップ(/member/)などへのリダイレクトを見逃す。
    if check_html and check_url and check_url.startswith(BASE_UNIV):
        print("  [ok] ログイン成功（大学別過去問ページへのアクセスを確認）")
        return True
    print(
        f"  [error] toshin.comへのログインはできましたが、toshin-kakomon.com側では"
        f"ログイン状態が引き継がれていないようです（リダイレクト先: {check_url}）。"
        f"別ドメインのためセッションが連携されていない可能性があります。"
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


def download_university(code, name, years, out_dir, delay):
    """大学別の年度ページ (/new_kakomon_db/university/{code}/{year}/) を年度ごとに取得し、
    英語科目の問題/解答/解説リンク (exam id が e{code}{yy}NN の形式) を抜き出して保存する。
    実際のページ (東京大学 2026年度で確認済み) は例えば
    href="/new_kakomon_db/university/0l/2026/e0l261/question/" のような形で、
    末尾が .pdf ではなく question/answer/commentary ディレクトリになっている
    （このURLに直接GETするとPDFなどの実体が返る）。
    """
    print(f"=== {name} ({code}) ===")
    referer = f"{BASE_UNIV}/new_kakomon_db/university/{code}/subject/e/"
    for year in years:
        url = f"{BASE_UNIV}/new_kakomon_db/university/{code}/{year}/"
        html, final_url, _ = fetch(url, delay=delay, referer=referer)
        time.sleep(delay)
        if not html:
            print(f"  [warn] {year}: ページ取得失敗 ({url})")
            continue
        text = html.decode("utf-8", "ignore")
        yy = str(year)[-2:]
        pattern = re.compile(
            rf'href="(/new_kakomon_db/university/{re.escape(code)}/{year}/'
            rf'e{re.escape(code)}{yy}\d+/(question|answer|commentary)/)"'
        )
        found = pattern.findall(text)
        if not found:
            redirect_note = f" リダイレクト先: {final_url}" if final_url != url else ""
            snippet = re.sub(r"\s+", " ", text[:200]).strip()
            print(
                f"  [info] {year}: 取得{len(text)}文字 / 英語リンク一致0件"
                f"（サイト側の仕様変更やその年度未掲載の可能性）{redirect_note} 冒頭: {snippet!r}"
            )
            continue
        seen = set()
        for href, kind in found:
            if href in seen:
                continue
            seen.add(href)
            exam_id = href.strip("/").split("/")[-2]
            data, _, ct = fetch(BASE_UNIV + href, delay=delay, referer=url)
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
        if not login(email, password, args.delay):
            print("[error] ログインに失敗したため中断します。")
            return
        for group_name, schools in config.items():
            if args.group and group_name not in args.group:
                continue
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
            if os.path.isdir(args.out):
                shutil.rmtree(args.out)
                print(f"元フォルダを削除しました: {args.out}")
            else:
                print(f"元フォルダ({args.out})は生成されなかった（保存0件）ため削除をスキップしました。")

    print("完了しました。")


if __name__ == "__main__":
    main()
