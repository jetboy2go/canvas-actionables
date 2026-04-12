# Gmail Setup — One-Time Only

The actionables script reads your Gmail for:
  1. PowerSchool attendance (absences/tardies per class)
  2. Teacher emails (for Note column context)

Without this setup, it runs Canvas-only (still works, just no Gmail intel).

## Step 1 — Install dependencies

```
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

## Step 2 — Create a Gmail token

Run this one-time setup script:

```
python3 gmail_setup.py
```

It will open your browser, ask you to sign in to Google, and save
a `gmail_token.json` file in the same folder as pull_actionables.py.

That token file is what the script uses every time you run it.

## Step 3 — Run normally

```
python3 pull_actionables.py matthew
python3 pull_actionables.py edward
```

The script will print whether Gmail loaded successfully.

## Notes
- The token is read-only (it cannot send email or modify anything)
- If the token expires, just run gmail_setup.py again
- Keep gmail_token.json in the same folder as pull_actionables.py
- Never share gmail_token.json with anyone
