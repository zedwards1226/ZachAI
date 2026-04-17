"""Google Drive client: OAuth flow, folder tree cache, PDF download."""
import json
import os
import sys
import io
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
BASE = Path(__file__).parent
TOKEN_FILE = BASE / "token.json"
CACHE_FILE = BASE / "machines.json"


def _client_config():
    return {
        "installed": {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


def get_creds():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(_client_config(), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
    return creds


def _service():
    return build("drive", "v3", credentials=get_creds(), cache_discovery=False)


def _list_children(svc, folder_id):
    q = f"'{folder_id}' in parents and trashed = false"
    out, token = [], None
    while True:
        resp = svc.files().list(
            q=q, pageSize=1000, pageToken=token,
            fields="nextPageToken, files(id, name, mimeType, modifiedTime, size)",
        ).execute()
        out.extend(resp.get("files", []))
        token = resp.get("nextPageToken")
        if not token:
            break
    return out


def build_tree(root_id: str):
    """Walk the Drive folder tree starting at root_id. Returns dict keyed by machine name."""
    svc = _service()
    machines = {}
    for machine in _list_children(svc, root_id):
        if machine["mimeType"] != "application/vnd.google-apps.folder":
            continue
        docs = {"electrical": [], "manuals": [], "other": []}
        for sub in _list_children(svc, machine["id"]):
            if sub["mimeType"] == "application/vnd.google-apps.folder":
                bucket = sub["name"].lower()
                if "elec" in bucket or "drawing" in bucket or "schematic" in bucket:
                    key = "electrical"
                elif "manual" in bucket or "doc" in bucket:
                    key = "manuals"
                else:
                    key = "other"
                for f in _list_children(svc, sub["id"]):
                    if f["mimeType"] != "application/vnd.google-apps.folder":
                        docs[key].append(
                            {"id": f["id"], "name": f["name"], "mime": f["mimeType"]}
                        )
            else:
                docs["other"].append(
                    {"id": sub["id"], "name": sub["name"], "mime": sub["mimeType"]}
                )
        machines[machine["name"]] = {"id": machine["id"], "docs": docs}
    return machines


def refresh_cache():
    root = os.getenv("DRIVE_ROOT_FOLDER_ID")
    if not root:
        raise RuntimeError("DRIVE_ROOT_FOLDER_ID not set in .env")
    tree = build_tree(root)
    CACHE_FILE.write_text(json.dumps(tree, indent=2))
    return tree


def load_cache():
    if not CACHE_FILE.exists():
        return refresh_cache()
    return json.loads(CACHE_FILE.read_text())


def download_file(file_id: str) -> bytes:
    svc = _service()
    buf = io.BytesIO()
    req = svc.files().get_media(fileId=file_id)
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    return buf.getvalue()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(BASE.parent / ".env")
    if "--auth" in sys.argv:
        get_creds()
        print(f"Token saved to {TOKEN_FILE}")
    elif "--refresh" in sys.argv:
        tree = refresh_cache()
        print(f"Cached {len(tree)} machines to {CACHE_FILE}")
    else:
        print("Usage: python drive_client.py [--auth | --refresh]")
