import os
import sys
import json
import shutil
import webbrowser
import requests
import argparse
import time
import uuid
import threading
from cards import get_cards

os.environ['COUPON_TOKEN'] = "demo1"
#API_BASE = "http://127.0.0.1:5000"  
API_BASE = "https://api.cranky.app" # for production

SCENE_PATH = "cranky_layout.json"
CARDS_CACHE = "cards_retrieved.json"
VIEWER_DIR = "viewer"

def poll_status(session_id):
    import time
    time.sleep(1)
    print(" Waiting for server to finish scene generation...")
    while True:
        try:
            resp = requests.get(f"{API_BASE}/v2/status/{session_id}")
            status = resp.json().get("status", "pending")
            print(f"   → {status}", end="\r", flush=True)
            if "complete" in status.lower():
                break
        except requests.exceptions.JSONDecodeError:
            print(f"⚠️ Status endpoint returned invalid JSON")
        except Exception as e:
            print(f"⚠️ Could not fetch status: {e}")
        time.sleep(2)
       

def call_api(path, json_data=None, timeout=600):
    url = f"{API_BASE}{path}"
    headers = {
        "X-Coupon-Token": os.environ.get("COUPON_TOKEN", "")
    }
    response = requests.post(url, json=json_data, headers=headers, timeout=timeout) if json_data else \
               requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response
    

def timed_call(label, func):
    import time
    print(f"\n⏱️ Starting: {label}")
    start = time.time()
    result = func()
    end = time.time()
    print(f"✅ Finished: {label} in {end - start:.2f} seconds")
    return result
    

def check_anki_connect():
    try:
        response = requests.post("http://localhost:8765", json={"action": "version", "version": 6}, timeout=2)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

def confirm_data_upload():
    print(""" 
 ⚠️  This tool transfers Anki card content and media to our Cranky API server as well as to OpenAI / Replicate Endpoints for layout generation.
 
 ⚠️  By using Cranky, you acknowledge that you do so at your own discretion and risk.
 
 ⚠️  The application providers accept no responsibility for any loss, misuse, or harm arising from use of this tool.
    """)
    confirm = input("Do you agree to proceed? (yes/no):  ").strip().lower()
    if confirm not in ("yes", "y"):
        print("❌ Operation cancelled.")
        sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description="Memory Palace CLI")
    parser.add_argument("--stored-scene", action="store_true", help="Use existing layout from disk")
    parser.add_argument("--stored-cards", action="store_true", help="Use cached Anki cards instead of refreshing")
    args = parser.parse_args()

    regenerate = not args.stored_scene
    force_refresh = not args.stored_cards

    if force_refresh:
        regenerate = True
        print(" Checking AnkiConnect...")
        if not check_anki_connect():
            print("❌ AnkiConnect not available at localhost:8765.")
            print(" Install the add-on: https://ankiweb.net/shared/info/2055492159")
            sys.exit(1)
        print(" AnkiConnect detected.")

    confirm_data_upload()

    if force_refresh or not os.path.exists(CARDS_CACHE):
        print(" Loading cards...")
        cards = get_cards(force_refresh=True)
        print(f" Loaded {len(cards)} cards.")
    else:
        cards = get_cards(force_refresh=False)
        print(f" Loaded {len(cards)} cards from cache.")

    if regenerate:
        theme = input(" Enter a theme for the memory palace: ").strip()
        print(" Sending cards to server...")

        session_id = uuid.uuid4().hex[:8]
        print(f" Generating layout for theme: '{theme}' (session {session_id})")

        layout = timed_call("Scene layout generation", lambda: call_api("/v2/generate_scene", json_data={
            "theme": theme,
            "cards": cards,
            "session_id": session_id
        }, timeout=1000).json())

        threading.Thread(target=poll_status, args=(session_id,), daemon=True).start()        
        
        if not layout.get("objects"):
            raise ValueError("❌ Scene layout is empty. Aborting.")

        with open(SCENE_PATH, "w") as f:
            json.dump(layout, f, indent=2)
            print(f" Layout saved to {SCENE_PATH}")

        media_src = os.path.join("viewer", "media")
        if os.path.exists(media_src):
            files = []
            for fname in os.listdir(media_src):
                path = os.path.join(media_src, fname)
                files.append(('files', (fname, open(path, 'rb'))))

            upload_url = f"{API_BASE}/upload_media/{session_id}"
            try:
                resp = requests.post(upload_url, files=files, headers={
                    "X-Coupon-Token": os.environ.get("COUPON_TOKEN", "")
                })
                if resp.status_code == 200:
                    print(f"✅ Uploaded {len(files)} media files to server.")
                else:
                    print(f"❌ Media upload failed: {resp.status_code} {resp.text}")
            except Exception as e:
                print(f"❌ Media upload error: {e}")

             
            else:
                if not os.path.exists(SCENE_PATH):
                    print("❌ Layout file not found.")
                    print(" Please regenerate scene.")
                    sys.exit(1)
                with open(SCENE_PATH, "r") as file:
                    layout = json.load(file)
                session_id = layout.get("session_id")
                
    else: 
        with open(SCENE_PATH, "r") as f:
            layout = json.load(f)
            print(f"Layout loaded from {SCENE_PATH}")
        session_id = layout.get("session_id")    

    print(" Generating HTML viewer...")
    resp = call_api("/generate_viewer", json_data={"layout": layout})
    print(" Viewer created successfully.")
    url = f"{API_BASE}/viewer/{session_id}/cranky_viewer.html"
    print(f" Viewer URL:\n {url}")

if __name__ == "__main__":
    main()

