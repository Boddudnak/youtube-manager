"""OAuth helper the engine imports. Copy this file to ~/.youtube-api/yt.py and put your Google Cloud
OAuth client (Desktop app) next to it as client_secret.json. The first run opens a browser to sign in;
the token is saved as token.json in the same folder - never commit either file."""
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

HERE = os.path.dirname(os.path.abspath(__file__))
SECRET = os.path.join(HERE, "client_secret.json")
TOKEN = os.path.join(HERE, "token.json")
SCOPES = [
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def credentials():
    creds = Credentials.from_authorized_user_file(TOKEN) if os.path.exists(TOKEN) else None
    if creds and not creds.has_scopes(SCOPES):
        creds = None  # saved token predates a newly added scope: re-approve in the browser
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            creds = None  # Testing-mode refresh tokens expire after 7 days
    if not creds or not creds.valid:
        creds = InstalledAppFlow.from_client_secrets_file(SECRET, SCOPES).run_local_server(port=0)
    with open(TOKEN, "w") as f:
        f.write(creds.to_json())
    return creds
