#!/usr/bin/env python3
"""
Reddit OAuth helper - generates a new refresh token for automation-cli

Usage:
    python3 scripts/reddit_auth.py

This will:
1. Check for existing credentials or prompt for them
2. Start a local HTTP server to receive the OAuth callback
3. Open your browser for Reddit authorization
4. Exchange the code for tokens
5. Save the refresh token to ~/.config/automation/secrets.env
"""

import base64
import http.server
import json
import os
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

# Configuration
SECRETS_ENV_PATH = Path.home() / ".config" / "automation" / "secrets.env"
USER_AGENT = "PageSeeds/1.0"
REDIRECT_URI = "http://localhost:8080"
SCOPES = ["identity", "submit", "read", "history"]

# Global to store the authorization code
auth_code = None
auth_error = None


class OAuthHandler(http.server.BaseHTTPRequestHandler):
    """Handle OAuth callback from Reddit."""
    
    def do_GET(self):
        global auth_code, auth_error
        
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        
        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            html = """
                <html>
                <head><title>Reddit Auth Success</title></head>
                <body style="font-family: sans-serif; max-width: 600px; margin: 50px auto; text-align: center;">
                    <h1 style="color: green;">Authorization Successful!</h1>
                    <p>You can close this window and return to the terminal.</p>
                </body>
                </html>
            """
            self.wfile.write(html.encode('utf-8'))
        elif "error" in params:
            auth_error = params.get("error_description", [params["error"][0]])[0]
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            html = f"""
                <html>
                <head><title>Reddit Auth Failed</title></head>
                <body style="font-family: sans-serif; max-width: 600px; margin: 50px auto; text-align: center;">
                    <h1 style="color: red;">Authorization Failed</h1>
                    <p>{auth_error}</p>
                </body>
                </html>
            """
            self.wfile.write(html.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress request logs
        pass


def get_credentials():
    """Get Reddit app credentials from user or existing env."""
    # First check environment
    client_id = os.environ.get("REDDIT_CLIENT_ID", "").strip()
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "").strip()
    
    # Check secrets.env
    if SECRETS_ENV_PATH.exists():
        content = SECRETS_ENV_PATH.read_text()
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("REDDIT_CLIENT_ID=") and not client_id:
                client_id = line.split("=", 1)[1].strip().strip('"\'')
            elif line.startswith("REDDIT_CLIENT_SECRET=") and not client_secret:
                client_secret = line.split("=", 1)[1].strip().strip('"\'')
    
    # Prompt if still missing
    if not client_id:
        print("\nReddit App Credentials Required")
        print("=" * 50)
        print("\nIf you don't have a Reddit app yet:")
        print("1. Go to: https://www.reddit.com/prefs/apps")
        print("2. Click 'create another app...'")
        print("3. Select 'web app'")
        print("4. Set redirect URI to: http://localhost:8080")
        print("5. Copy the Client ID and Client Secret\n")
        
        client_id = input("Enter your Reddit Client ID: ").strip()
    
    if not client_secret:
        client_secret = input("Enter your Reddit Client Secret: ").strip()
    
    return client_id, client_secret


def start_oauth_server():
    """Start local HTTP server to receive OAuth callback."""
    server = http.server.HTTPServer(("localhost", 8080), OAuthHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    return server


def exchange_code_for_token(code, client_id, client_secret):
    """Exchange authorization code for refresh token."""
    # Build Basic auth header
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }).encode()
    
    headers = {
        "User-Agent": USER_AGENT,
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    
    req = urllib.request.Request(
        "https://www.reddit.com/api/v1/access_token",
        data=data,
        headers=headers,
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        raise Exception(f"Token exchange failed: {e.code} - {error_body}")


def save_refresh_token(refresh_token, client_id, client_secret):
    """Save refresh token and credentials to secrets.env."""
    SECRETS_ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # Read existing content
    existing_lines = []
    if SECRETS_ENV_PATH.exists():
        existing_lines = SECRETS_ENV_PATH.read_text().splitlines()
    
    # Filter out old Reddit-related entries
    new_lines = []
    for line in existing_lines:
        if not line.strip().startswith("REDDIT_"):
            new_lines.append(line)
    
    # Add new entries
    new_lines.extend([
        f"REDDIT_CLIENT_ID={client_id}",
        f"REDDIT_CLIENT_SECRET={client_secret}",
        f"REDDIT_REFRESH_TOKEN={refresh_token}",
    ])
    
    # Write back
    SECRETS_ENV_PATH.write_text("\n".join(new_lines) + "\n")
    
    # Secure the file
    os.chmod(SECRETS_ENV_PATH, 0o600)


def main():
    print("Reddit OAuth Token Generator")
    print("=" * 50)
    
    # Get credentials
    client_id, client_secret = get_credentials()
    
    if not client_id or not client_secret:
        print("\nError: Client ID and Client Secret are required")
        sys.exit(1)
    
    # Start OAuth server
    print("\nStarting local OAuth server on localhost:8080...")
    server = start_oauth_server()
    
    # Build auth URL
    state = "pageseeds_oauth_" + str(int(time.time()))
    auth_url = (
        "https://www.reddit.com/api/v1/authorize?"
        + urllib.parse.urlencode({
            "client_id": client_id,
            "response_type": "code",
            "state": state,
            "redirect_uri": REDIRECT_URI,
            "duration": "permanent",
            "scope": " ".join(SCOPES),
        })
    )
    
    # Open browser
    print("\nOpening browser for authorization...")
    print(f"   If it doesn't open automatically, visit:\n   {auth_url}\n")
    webbrowser.open(auth_url)
    
    # Wait for callback
    print("Waiting for authorization (timeout: 2 minutes)...")
    timeout = time.time() + 120
    while time.time() < timeout:
        if auth_code:
            break
        if auth_error:
            print(f"\nAuthorization error: {auth_error}")
            sys.exit(1)
        time.sleep(0.5)
    
    if not auth_code:
        print("\nTimeout: No authorization received")
        sys.exit(1)
    
    server.shutdown()
    
    print("Authorization code received")
    print("\nExchanging code for tokens...")
    
    try:
        token_data = exchange_code_for_token(auth_code, client_id, client_secret)
    except Exception as e:
        print(f"\nToken exchange failed: {e}")
        sys.exit(1)
    
    if "refresh_token" not in token_data:
        print("\nError: No refresh token in response")
        print(f"Response: {json.dumps(token_data, indent=2)}")
        sys.exit(1)
    
    refresh_token = token_data["refresh_token"]
    
    print("Token received successfully")
    print("\nSaving to ~/.config/automation/secrets.env...")
    
    try:
        save_refresh_token(refresh_token, client_id, client_secret)
    except Exception as e:
        print(f"\nFailed to save token: {e}")
        sys.exit(1)
    
    print("Token saved successfully")
    print("\n" + "=" * 50)
    print("Reddit authentication complete!")
    print("\nYou can now run:")
    print("  automation-cli reddit auth-status")
    print("\nOr continue with your batch posting.")


if __name__ == "__main__":
    main()
