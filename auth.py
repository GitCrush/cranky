# auth.py

import os
import json
import threading
import webbrowser
from .bottle import Bottle, request, response, run
from aqt import mw
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import Qt
from .config import API_BASE_FRONT, VIEWER_DIR

CRANKY_CONFIG_KEY = "cranky_jwt_token"
TOKEN_PORT = 7777
LOGIN_URL = f"{API_BASE_FRONT}/login?from_anki=true"
ADDON_NAME = "Cranky - Memory Palace Builder"
DEV_TOKEN_FILE = os.path.join(os.path.dirname(__file__), ".cranky_dev_token")
META_PATH = os.path.join(os.path.dirname(__file__), "meta.json")

app = Bottle()
_active_server = [None]  # list for mutability in closures

def save_token(token):
    try:
        mw.addonManager.writeConfig(ADDON_NAME, {CRANKY_CONFIG_KEY: token})
        print(f"[Cranky] Token saved to addon config")
    except Exception as e:
        print(f"[Cranky] Failed to save token via addonManager: {e}")
        try:
            with open(DEV_TOKEN_FILE, "w") as f:
                f.write(token)
            print("[Cranky] Token saved to .cranky_dev_token")
        except Exception as e:
            print(f"[Cranky] Failed to write dev token file: {e}")

def load_token():
    try:
        config = mw.addonManager.getConfig(ADDON_NAME)
        if config:
            token = config.get(CRANKY_CONFIG_KEY)
            if token:
                print("[Cranky] Loaded token from addon config")
                return token
    except Exception as e:
        print(f"[Cranky] Failed to load token via addonManager: {e}")

    if os.path.exists(DEV_TOKEN_FILE):
        try:
            with open(DEV_TOKEN_FILE, "r") as f:
                token = f.read().strip()
                print("[Cranky] Loaded token from .cranky_dev_token")
                return token
        except Exception as e:
            print(f"[Cranky] Failed to read dev token file: {e}")

    if os.path.exists(META_PATH):
        try:
            with open(META_PATH, "r") as f:
                meta = json.load(f)
                token = meta.get("config", {}).get(CRANKY_CONFIG_KEY)
                if token:
                    print("[Cranky] Loaded token from meta.json")
                    return token
        except Exception as e:
            print(f"[Cranky] Failed to read meta.json: {e}")

    print("[Cranky] No token found in any source")
    return None

def get_cranky_token():
    return load_token()

# CORS preflight for /token
@app.route('/token', method=['OPTIONS'])
def token_options():
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return ''

# Actual POST handler
@app.post('/token')
def token_post():
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    data = request.json
    token = data.get('token') if data else None
    print(f"[Cranky] Bottle received token: {token}")
    if token:
        save_token(token)
        mw.taskman.run_on_main(
            lambda: _active_server[0]['callback'](token) if _active_server[0] and _active_server[0]['callback']
            else QMessageBox.information(mw, "Cranky Login", "Login successful!")
        )
        threading.Thread(target=shutdown_server, daemon=True).start()
        return "OK"
    return "No token", 400

def shutdown_server():
    import time
    time.sleep(1)
    print("[Cranky] Shutting down Bottle server.")
    # Attempt to exit only the server thread (not the whole process)


def run_cranky_login(callback=None):
    if _active_server[0]:
        print("[Cranky] Login already running (bottle)")

        msg = QMessageBox(mw)
        msg.setWindowTitle("Cranky Login")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(
            'Login already in progress.<br>'
            'Please <a href="http://localhost:3000/login?from_anki=true">click here to open the login page again</a> in your browser.'
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        msg.exec()

        return

    print(f"[Cranky] Starting Bottle server on {TOKEN_PORT}")
    _active_server[0] = {'callback': callback}

    def run_server():
        try:
            run(app, host='localhost', port=TOKEN_PORT, quiet=True)
        except Exception as e:
            print(f"[Cranky] Bottle server crashed: {e}")
        finally:
            _active_server[0] = None

    threading.Thread(target=run_server, daemon=True).start()
    webbrowser.open(LOGIN_URL)

def start_cranky_login():
    run_cranky_login()
