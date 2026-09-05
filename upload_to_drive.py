#!/usr/bin/env python3
"""ダウンロード結果のPDFをGoogleドライブへ直接アップロードする。

download_kakomon.py が作る出力ディレクトリ (例: downloads/<大学名>/<年度>/<file>.pdf、
共通テスト・センター試験なら downloads/共通テスト・センター試験/<file>.pdf) を歩いて、
Googleドライブ上に

    <root-name>/<group>/<大学名 or 共通テスト・センター試験>/<file>.pdf

という構造でアップロードする。年度ディレクトリはドロップしてフラット化する
（ファイル名にexam idや年度が含まれているため衝突しない）。

認証にはサービスアカウントを使う。事前に以下が必要:
  1. Google Cloudでサービスアカウントを作成し、Drive APIを有効化してJSON鍵を発行
  2. アップロード先の親フォルダ（--root-folder-id）をそのサービスアカウントの
     メールアドレスに「編集者」権限で共有しておく
  3. JSON鍵の中身を環境変数 GDRIVE_SA_KEY に設定する

同名ファイルが既にドライブ上に存在する場合はアップロードをスキップするので、
ワークフローを何度再実行しても重複アップロードにはならない。
"""
import argparse
import json
import os
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_MIME = "application/vnd.google-apps.folder"


def get_service(key_json):
    info = json.loads(key_json)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)


def _escape(name):
    return name.replace("\\", "\\\\").replace("'", "\\'")


def find_child(service, name, parent_id, mime_type=None):
    q = f"'{parent_id}' in parents and name = '{_escape(name)}' and trashed = false"
    if mime_type:
        q += f" and mimeType = '{mime_type}'"
    res = (
        service.files()
        .list(
            q=q,
            fields="files(id, name)",
            pageSize=1,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    files = res.get("files", [])
    return files[0]["id"] if files else None


def ensure_folder(service, name, parent_id):
    fid = find_child(service, name, parent_id, FOLDER_MIME)
    if fid:
        return fid
    meta = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]}
    f = service.files().create(body=meta, fields="id", supportsAllDrives=True).execute()
    print(f"[folder] created: {name}")
    return f["id"]


def upload_file(service, path, name, parent_id):
    if find_child(service, name, parent_id):
        print(f"  [skip] {name} (既存)")
        return False
    media = MediaFileUpload(path, resumable=True)
    meta = {"name": name, "parents": [parent_id]}
    service.files().create(
        body=meta, media_body=media, fields="id", supportsAllDrives=True
    ).execute()
    print(f"  [ok] {name}")
    return True


def main():
    ap = argparse.ArgumentParser(description="downloads/ 以下のPDFをGoogleドライブへ直接アップロード")
    ap.add_argument("--src", required=True, help="ダウンロード結果のディレクトリ (例: downloads)")
    ap.add_argument("--group", required=True, help="大学群名。過去問/<group>/ 以下に配置される")
    ap.add_argument("--root-folder-id", required=True, help="過去問フォルダを作成する親のDriveフォルダID")
    ap.add_argument("--root-name", default="過去問", help="ルートフォルダ名（既定: 過去問）")
    args = ap.parse_args()

    key_json = os.environ.get("GDRIVE_SA_KEY")
    if not key_json:
        print("[error] 環境変数 GDRIVE_SA_KEY が設定されていません。", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(args.src):
        print(f"[error] ディレクトリが見つかりません: {args.src}", file=sys.stderr)
        sys.exit(1)

    service = get_service(key_json)

    root_id = ensure_folder(service, args.root_name, args.root_folder_id)
    group_id = ensure_folder(service, args.group, root_id)

    folder_cache = {}
    uploaded = 0
    skipped = 0
    for dirpath, _dirs, files in os.walk(args.src):
        pdfs = [f for f in files if f.lower().endswith(".pdf")]
        if not pdfs:
            continue
        rel = os.path.relpath(dirpath, args.src)
        parts = [] if rel == "." else rel.split(os.sep)
        # 4桁数字だけの年度ディレクトリはドロップしてフラット化する
        univ_parts = [p for p in parts if not (p.isdigit() and len(p) == 4)]
        univ_name = univ_parts[0] if univ_parts else args.group

        if univ_name not in folder_cache:
            folder_cache[univ_name] = ensure_folder(service, univ_name, group_id)
        univ_id = folder_cache[univ_name]

        for fname in pdfs:
            if upload_file(service, os.path.join(dirpath, fname), fname, univ_id):
                uploaded += 1
            else:
                skipped += 1

    print(f"完了: 新規アップロード{uploaded}件 / 既存スキップ{skipped}件")


if __name__ == "__main__":
    main()
