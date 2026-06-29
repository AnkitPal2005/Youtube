"""
YouTube OAuth Setup Helper — run this ONCE to set up upload credentials.
Usage: python setup_youtube.py
"""
import os, sys, json, webbrowser, time
from pathlib import Path

ROOT = Path(__file__).parent

def step(n, text): print(f"\n{'='*55}\n  Step {n}: {text}\n{'='*55}")
def ok(text):       print(f"  [OK] {text}")
def err(text):      print(f"  [ERROR] {text}"); sys.exit(1)
def ask(prompt):    return input(f"\n  {prompt}: ").strip()

print("""
╔══════════════════════════════════════════════════════╗
║       YouTube Upload — One-Time Setup Helper         ║
╚══════════════════════════════════════════════════════╝
Ye script aapko ek baar Google Cloud setup karne mein
help karegi. Baad mein upload fully automatic hoga.
""")

# ── Step 1: Check if already done ──────────────────────────
secret = ROOT / "client_secret.json"
token  = ROOT / "data" / "token.json"

if token.exists():
    ok("Token already exists! You're already set up.")
    print("  Run: python main.py upload --video <path> --script <path>")
    sys.exit(0)

if secret.exists():
    ok("client_secret.json found! Skipping to authentication...")
    print("  Run: python main.py upload --video <path> --script <path>")
    print("  Browser will open for one-time Google login.")
    sys.exit(0)

# ── Step 2: Open Google Cloud Console ──────────────────────
step(1, "Google Cloud Console mein project banao")
print("""
  Abhi browser mein Google Cloud Console khul raha hai.

  Karna kya hai:
  a) Top pe 'Select a project' → 'New Project'
  b) Project name: yt-shorts-bot → 'Create'
  c) Project ban jaane ke baad next step pe aao.
""")
input("  Enter dabao browser kholne ke liye...")
webbrowser.open("https://console.cloud.google.com/projectcreate")
input("  Project ban gaya? Enter dabao aage badhne ke liye...")

# ── Step 3: Enable YouTube API ──────────────────────────────
step(2, "YouTube Data API v3 enable karo")
print("""
  Browser mein YouTube API ka page khul raha hai.

  Karna kya hai:
  a) 'ENABLE' button dabao
  b) Confirm karo ki API enabled ho gayi
""")
input("  Enter dabao browser kholne ke liye...")
webbrowser.open("https://console.cloud.google.com/apis/library/youtube.googleapis.com")
input("  API enable ho gayi? Enter dabao aage badhne ke liye...")

# ── Step 4: OAuth Consent Screen ───────────────────────────
step(3, "OAuth Consent Screen setup karo")
print("""
  Karna kya hai:
  a) User Type: 'External' select karo → Create
  b) App name: yt-shorts-bot
  c) User support email: apni email dalo
  d) Developer contact email: apni email dalo
  e) 'Save and Continue' dabao (baaki sab skip)
  f) 'Test users' section mein apni Gmail add karo
  g) 'Save and Continue' → 'Back to Dashboard'
""")
input("  Enter dabao browser kholne ke liye...")
webbrowser.open("https://console.cloud.google.com/apis/credentials/consent")
input("  Consent screen setup ho gaya? Enter dabao...")

# ── Step 5: Create OAuth Credentials ───────────────────────
step(4, "OAuth Credentials (client_secret.json) banao")
print("""
  Karna kya hai:
  a) '+ CREATE CREDENTIALS' → 'OAuth client ID'
  b) Application type: 'Desktop app'
  c) Name: yt-shorts-bot → 'Create'
  d) Pop-up mein 'DOWNLOAD JSON' dabao
  e) Downloaded file ka naam: client_secret.json rakho
  f) Us file ko yahan move karo:
""")
print(f"     {ROOT}")
input("  Enter dabao browser kholne ke liye...")
webbrowser.open("https://console.cloud.google.com/apis/credentials")

# ── Step 6: Wait for file ──────────────────────────────────
print(f"\n  Waiting for client_secret.json in: {ROOT}")
print("  (file download karke yahan rakho, phir Enter dabao)")

while not secret.exists():
    input("  File abhi nahi mili. Rakh ke Enter dabao...")

ok("client_secret.json mil gayi!")

# ── Step 7: Test authentication ────────────────────────────
step(5, "YouTube authentication test karo")
print("""
  Ab browser mein Google login page khulega.
  Apna YouTube wala Google account se login karo.
  'Allow' dabao — ek baar hi karna hai.
""")
input("  Enter dabao authentication shuru karne ke liye...")

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
              "https://www.googleapis.com/auth/youtube.readonly"]

    flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)

    token_path = ROOT / "data" / "token.json"
    token_path.parent.mkdir(exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")

    # Test: get channel info
    yt = build("youtube", "v3", credentials=creds)
    resp = yt.channels().list(part="snippet", mine=True).execute()
    channel = resp["items"][0]["snippet"]["title"] if resp.get("items") else "Unknown"

    print(f"""
╔══════════════════════════════════════════════════════╗
║              SETUP COMPLETE!                         ║
╠══════════════════════════════════════════════════════╣
║  Channel : {channel:<42}║
║  Token   : data/token.json (saved)                  ║
╠══════════════════════════════════════════════════════╣
║  Ab upload karo:                                     ║
║                                                      ║
║  python main.py upload \\                            ║
║    --video output/final/<id>.mp4 \\                  ║
║    --script output/scripts/<id>.json                 ║
╚══════════════════════════════════════════════════════╝
""")

except Exception as e:
    err(f"Authentication failed: {e}\nCheck client_secret.json aur dobara try karo.")
