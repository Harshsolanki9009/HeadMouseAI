"""Publish HeadMouseAI v1.0.0-beta.2 to GitHub Releases with binary assets."""

import os
import sys
import json
import subprocess
import urllib.request
import urllib.error
import urllib.parse

REPO = "Harshsolanki9009/HeadMouseAI"
TAG = "v1.0.0-beta.2"
TITLE = "HeadMouseAI v1.0.0 Beta 2"
DRAFT_FILE = "dist/GITHUB_RELEASE_DRAFT_BETA2.md"
ASSETS = [
    ("dist/HeadMouseAI_Windows_v1.0.0-beta.2.zip", "HeadMouseAI_Windows_v1.0.0-beta.2.zip", "application/zip"),
    ("dist/installer/HeadMouseAI_Setup.exe", "HeadMouseAI_Setup.exe", "application/vnd.microsoft.portable-executable"),
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
    req.add_header("User-Agent", "HeadMouseAI-Publisher")

    release_data = None
    try:
        with urllib.request.urlopen(req) as resp:
            release_data = json.loads(resp.read().decode("utf-8"))
            print(f"[INFO] Existing release found for tag '{TAG}' (ID: {release_data.get('id')}).")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"[INFO] No release exists for tag '{TAG}'. Creating a new pre-release...")
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
            "prerelease": True,
        }
        create_req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases", data=json.dumps(payload).encode("utf-8"), method="POST")
        create_req.add_header("Authorization", f"Bearer {token}")
        create_req.add_header("Accept", "application/vnd.github+json")
        create_req.add_header("Content-Type", "application/json")
        create_req.add_header("User-Agent", "HeadMouseAI-Publisher")

        try:
            with urllib.request.urlopen(create_req) as resp:
                release_data = json.loads(resp.read().decode("utf-8"))
                print(f"[SUCCESS] Release created successfully! ID: {release_data.get('id')}")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            print(f"[ERROR] Failed to create release: {e.code} {e.reason}\n{err_body}")
            sys.exit(1)

    release_id = release_data.get("id")
    html_url = release_data.get("html_url")
    upload_url_template = release_data.get("upload_url", "").split("{")[0]
    existing_assets = {a.get("name"): a.get("id") for a in release_data.get("assets", [])}

    print(f"[INFO] Release HTML URL: {html_url}")
    print(f"[INFO] Existing assets count: {len(existing_assets)}")

    # 3. Upload assets
    uploaded_assets = []
    for filepath, filename, content_type in ASSETS:
        if not os.path.exists(filepath):
            print(f"[ERROR] Asset file not found: {filepath}")
            sys.exit(1)

        file_size = os.path.getsize(filepath)
        print(f"\n[INFO] Preparing upload: {filename} ({file_size:,} bytes, {file_size / (1024*1024):.2f} MB)...")

        # Delete existing asset with same name if present
        if filename in existing_assets:
            del_id = existing_assets[filename]
            print(f"[INFO] Deleting prior asset '{filename}' (ID: {del_id})...")
            del_req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/assets/{del_id}", method="DELETE")
            del_req.add_header("Authorization", f"Bearer {token}")
            del_req.add_header("Accept", "application/vnd.github+json")
            del_req.add_header("User-Agent", "HeadMouseAI-Publisher")
            try:
                with urllib.request.urlopen(del_req) as resp:
                    print(f"[INFO] Prior asset deleted successfully.")
            except Exception as ex:
                print(f"[WARNING] Could not delete existing asset: {ex}")

        # Read file binary
        with open(filepath, "rb") as f:
            data = f.read()

        upload_url = f"{upload_url_template}?name={urllib.parse.quote(filename)}"
        upload_req = urllib.request.Request(upload_url, data=data, method="POST")
        upload_req.add_header("Authorization", f"Bearer {token}")
        upload_req.add_header("Accept", "application/vnd.github+json")
        upload_req.add_header("Content-Type", content_type)
        upload_req.add_header("Content-Length", str(len(data)))
        upload_req.add_header("User-Agent", "HeadMouseAI-Publisher")

        try:
            with urllib.request.urlopen(upload_req) as resp:
                asset_resp = json.loads(resp.read().decode("utf-8"))
                asset_dl_url = asset_resp.get("browser_download_url")
                print(f"[SUCCESS] Uploaded {filename} -> {asset_dl_url}")
                uploaded_assets.append((filename, asset_dl_url))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            print(f"[ERROR] Failed to upload {filename}: {e.code} {e.reason}\n{err_body}")
            sys.exit(1)

    # 4. Verify public access without auth
    print("\n--- VERIFYING PUBLIC ACCESSIBILITY ---")
    verify_req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}")
    verify_req.add_header("Accept", "application/vnd.github+json")
    verify_req.add_header("User-Agent", "HeadMouseAI-Verifier")

    try:
        with urllib.request.urlopen(verify_req) as resp:
            public_data = json.loads(resp.read().decode("utf-8"))
            print(f"[VERIFIED] Public API access confirmed. Tag: {public_data.get('tag_name')}, Pre-release: {public_data.get('prerelease')}")
            for a in public_data.get("assets", []):
                print(f"  Asset available: {a.get('name')} ({a.get('size'):,} bytes) -> {a.get('browser_download_url')}")
    except Exception as e:
        print(f"[WARNING] Public verification check warning: {e}")

    # Test download URLs (HEAD / redirect check)
    for filename, dl_url in uploaded_assets:
        try:
            head_req = urllib.request.Request(dl_url, method="HEAD")
            head_req.add_header("User-Agent", "HeadMouseAI-Verifier")
            with urllib.request.urlopen(head_req) as resp:
                print(f"[VERIFIED] Download link verified for {filename}: HTTP {resp.status}")
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 200):
                print(f"[VERIFIED] Download link redirect confirmed for {filename}: HTTP {e.code}")
            else:
                print(f"[WARNING] HTTP response {e.code} on {dl_url}")
        except Exception as e:
            print(f"[INFO] Download link checked: {dl_url}")

    print("\n=======================================================")
    print("RELEASE PUBLISHED SUCCESSFULLY!")
    print(f"Release URL: {html_url}")
    print("=======================================================")

if __name__ == "__main__":
    main()
