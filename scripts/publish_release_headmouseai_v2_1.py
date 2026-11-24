"""Publish HeadMouseAI v2.1.0 to GitHub Releases with binary installer and portable ZIP."""

import os
import sys
import json
import subprocess
import urllib.request
import urllib.error
import urllib.parse

REPO = "Harshsolanki9009/HeadMouseAI"
TAG = "v2.1.0"
TITLE = "HeadMouseAI v2.1.0 — Hands-Free Vision Control & Autonomous AI Computer-Use Agent"
DRAFT_FILE = "dist/GITHUB_RELEASE_DRAFT_V2_1.md"
ASSETS = [
    ("dist/HeadMouseAI-Setup.exe", "HeadMouseAI-Setup.exe", "application/vnd.microsoft.portable-executable"),
    ("dist/HeadMouseAI-v2.1.0-Windows-x64-Portable.zip", "HeadMouseAI-v2.1.0-Windows-x64-Portable.zip", "application/zip"),
]

def get_token():
    p = subprocess.Popen(['git', 'credential', 'fill'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, _ = p.communicate('protocol=https\nhost=github.com\n\n')
    for line in out.splitlines():
        if line.startswith('password='):
            return line.split('=', 1)[1]
    return None

def main():
    token = get_token()
    if not token:
        print("[ERROR] Could not retrieve GitHub token from Git Credential Manager.")
        sys.exit(1)

    print(f"[INFO] Authenticated with GitHub token (Prefix: {token[:4]}...)")

    with open(DRAFT_FILE, "r", encoding="utf-8") as f:
        release_body = f.read()

    # 1. Check if release already exists
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "HeadMouseAI-Release-Publisher")

    release_data = None
    try:
        with urllib.request.urlopen(req) as resp:
            release_data = json.loads(resp.read().decode("utf-8"))
            print(f"[INFO] Existing release found for tag '{TAG}' (ID: {release_data.get('id')}).")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"[INFO] No release exists for tag '{TAG}'. Creating a new release...")
        else:
            print(f"[ERROR] HTTP Error querying release: {e.code} {e.reason}")
            sys.exit(1)

    # 2. Create release if not found
    if release_data is None:
        payload = {
            "tag_name": TAG,
            "target_commitish": "main",
            "name": TITLE,
            "body": release_body,
            "draft": False,
            "prerelease": False,
        }
        create_req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/releases",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )
        create_req.add_header("Authorization", f"Bearer {token}")
        create_req.add_header("Accept", "application/vnd.github+json")
        create_req.add_header("Content-Type", "application/json")
        create_req.add_header("User-Agent", "HeadMouseAI-Release-Publisher")

        try:
            with urllib.request.urlopen(create_req) as resp:
                release_data = json.loads(resp.read().decode("utf-8"))
                print(f"[SUCCESS] Release '{TAG}' created successfully (ID: {release_data.get('id')})!")
        except urllib.error.HTTPError as e:
            print(f"[ERROR] Failed to create release: {e.code} {e.read().decode('utf-8')}")
            sys.exit(1)
    else:
        # Update existing release body and title
        update_url = release_data.get("url")
        payload = {"name": TITLE, "body": release_body}
        upd_req = urllib.request.Request(
            update_url,
            data=json.dumps(payload).encode("utf-8"),
            method="PATCH",
        )
        upd_req.add_header("Authorization", f"Bearer {token}")
        upd_req.add_header("Accept", "application/vnd.github+json")
        upd_req.add_header("Content-Type", "application/json")
        upd_req.add_header("User-Agent", "HeadMouseAI-Release-Publisher")
        with urllib.request.urlopen(upd_req) as resp:
            release_data = json.loads(resp.read().decode("utf-8"))
            print(f"[SUCCESS] Release metadata updated for '{TAG}'.")

    release_id = release_data["id"]
    upload_url_template = release_data["upload_url"]
    base_upload_url = upload_url_template.split("{")[0]

    # 3. Check existing assets
    existing_assets = {a["name"]: a["id"] for a in release_data.get("assets", [])}

    # 4. Upload assets
    for local_path, asset_name, content_type in ASSETS:
        if not os.path.exists(local_path):
            print(f"[WARN] Local asset '{local_path}' not found! Skipping...")
            continue

        file_size = os.path.getsize(local_path)
        print(f"\n[INFO] Preparing to upload '{asset_name}' ({file_size / (1024*1024):.2f} MB)...")

        # Delete existing asset if it exists
        if asset_name in existing_assets:
            asset_id = existing_assets[asset_name]
            print(f"[INFO] Deleting stale asset '{asset_name}' (ID: {asset_id})...")
            del_req = urllib.request.Request(
                f"https://api.github.com/repos/{REPO}/releases/assets/{asset_id}",
                method="DELETE",
            )
            del_req.add_header("Authorization", f"Bearer {token}")
            del_req.add_header("Accept", "application/vnd.github+json")
            del_req.add_header("User-Agent", "HeadMouseAI-Release-Publisher")
            try:
                with urllib.request.urlopen(del_req) as resp:
                    print(f"[INFO] Stale asset deleted.")
            except Exception as e:
                print(f"[WARN] Failed to delete existing asset: {e}")

        # Upload asset
        upload_url = f"{base_upload_url}?name={urllib.parse.quote(asset_name)}"
        print(f"[INFO] Uploading to {upload_url}...")

        with open(local_path, "rb") as f_data:
            data_bytes = f_data.read()

        up_req = urllib.request.Request(upload_url, data=data_bytes, method="POST")
        up_req.add_header("Authorization", f"Bearer {token}")
        up_req.add_header("Content-Type", content_type)
        up_req.add_header("Accept", "application/vnd.github+json")
        up_req.add_header("User-Agent", "HeadMouseAI-Release-Publisher")

        try:
            with urllib.request.urlopen(up_req) as resp:
                asset_resp = json.loads(resp.read().decode("utf-8"))
                print(f"[SUCCESS] Uploaded '{asset_name}' (ID: {asset_resp.get('id')})!")
        except urllib.error.HTTPError as e:
            print(f"[ERROR] Failed to upload '{asset_name}': {e.code} {e.read().decode('utf-8')}")

    print("\n" + "=" * 65)
    print(f"RELEASE PUBLISHED SUCCESSFULLY: {release_data.get('html_url')}")
    print("=" * 65)

if __name__ == "__main__":
    main()
