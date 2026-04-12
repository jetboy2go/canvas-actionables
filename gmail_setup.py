#!/usr/bin/env python3
"""
One-time Gmail OAuth setup.
Run this once to create gmail_token.json.
After that, pull_actionables.py will use it automatically.

Requires a Google Cloud project with Gmail API enabled.
Simpler alternative: use the gmail_token_from_claude.py script if
you have already authenticated via Claude's Gmail connector.
"""

import os, json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/drive.file"]
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gmail_token.json")
CREDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gmail_credentials.json")

def main():
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDS_FILE):
                print(f"""
ERROR: {CREDS_FILE} not found.

You need to:
1. Go to https://console.cloud.google.com/
2. Create a project (or use existing)
3. Enable Gmail API
4. Create OAuth credentials (Desktop app type)
5. Download as 'gmail_credentials.json' to this folder
6. Run this script again

Alternatively, if you just want to get started quickly,
see SETUP.md for the simpler token extraction method.
""")
                return
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    print(f"✓ Gmail token saved to: {TOKEN_FILE}")
    print("  You can now run: python3 pull_actionables.py matthew")

if __name__ == "__main__":
    main()
