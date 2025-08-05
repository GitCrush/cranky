# ui.py

import os
import uuid
import webbrowser
from heapq import nlargest
from aqt import mw
from aqt.qt import QAction
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QLabel, QComboBox, QDialogButtonBox,
    QPushButton, QMessageBox, QInputDialog
)
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QProgressDialog, QMessageBox, QInputDialog
import requests
import time
from PyQt6.QtWidgets import QProgressDialog
from PyQt6.QtWidgets import QHBoxLayout
from aqt.qt import QApplication
import base64
import json
from .cards import fetch_cards_by_criteria, get_cards
from .tag_input_widget import TagInputWidget
from .style import MODERN_STYLE
from .auth import get_cranky_token, run_cranky_login, CRANKY_CONFIG_KEY, ADDON_NAME
from .config import API_BASE_FRONT, API_BASE_BACK, VIEWER_DIR
from .utils import clean_media_folder
from PyQt6.QtWidgets import QInputDialog
from .auth import run_cranky_login, get_cranky_token, save_token


LIMIT = 25  # Match current backend/export logic

def add_cranky_login_menu():
    login_action = QAction("Log in to Cranky", mw)
    login_action.triggered.connect(run_cranky_login)
    mw.form.menuTools.addAction(login_action)


def get_jwt_expiry(jwt_token):
    try:
        parts = jwt_token.split('.')
        if len(parts) != 3:
            return None
        def b64pad(s):
            return s + '=' * ((4 - len(s) % 4) % 4)
        payload_b64 = b64pad(parts[1])
        payload_json = base64.urlsafe_b64decode(payload_b64.encode()).decode()
        payload = json.loads(payload_json)
        exp = payload.get('exp')
        return int(exp) if exp else None
    except Exception as e:
        print(f"[Cranky] Could not parse JWT expiry: {e}")
        return None


def fetch_top_cards(card_ids, key, limit=LIMIT):
    best_cards_by_note = {}
    for cid in card_ids:
        card = mw.col.get_card(cid)
        note_id = card.nid
        val = getattr(card, key, 0)
        if note_id not in best_cards_by_note or val > getattr(best_cards_by_note[note_id], key, 0):
            best_cards_by_note[note_id] = card
    return nlargest(limit, best_cards_by_note.values(), key=lambda c: getattr(c, key, 0))

def show_server_error(msg, details=None):
    txt = f"Cranky server error:\n\n{msg}"
    if details:
        txt += f"\n\nDetails:\n{details}"
    QMessageBox.critical(mw, "Cranky Error", txt)


def launch_cranky_selector():
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QLabel, QComboBox, QDialogButtonBox, QPushButton, QMessageBox, QInputDialog
    )
    from PyQt6.QtCore import Qt
    from .style import MODERN_STYLE

    decks = sorted([d['name'] for d in mw.col.decks.all()], key=str.casefold)
    tags = sorted(mw.col.tags.all())

    jwt_token = get_cranky_token()
    logged_in = bool(jwt_token)

    expired = False
    exp = None
    if jwt_token:
        exp = get_jwt_expiry(jwt_token)
        if exp and time.time() > exp:
            expired = True
            # Clear the token (logout)
            save_token("")
            jwt_token = None
            logged_in = False

    if expired:
        QMessageBox.warning(mw, "Session Expired", "Your Cranky session has expired. Please log in again.")
        

    dialog = QDialog(mw)
    dialog.setWindowTitle("Select Deck and Tags")
    dialog.setFixedSize(750, 500)
    dialog.setStyleSheet(MODERN_STYLE)
    layout = QVBoxLayout(dialog)

    layout.addWidget(QLabel("Select Deck:"))
    deck_combo = QComboBox()
    deck_combo.addItem("all")
    deck_combo.addItems(decks)
    layout.addWidget(deck_combo)

    layout.addWidget(QLabel("Select Tags:"))
    from .tag_input_widget import TagInputWidget
    tag_widget = TagInputWidget(tags)
    layout.addWidget(tag_widget)

    layout.addWidget(QLabel("Card Selection Mode:"))
    mode_combo = QComboBox()
    mode_combo.addItems(["Most Lapses", "Most Repetitions", "Random"])
    layout.addWidget(mode_combo)

    card_count_label = QLabel("")
    layout.addWidget(card_count_label)

    button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    layout.addWidget(button_box)

    if not logged_in:
        warn_label = QLabel("🔒 Please log in to Cranky first.")
        warn_label.setStyleSheet("color: orange; font-weight: bold;")
        layout.insertWidget(0, warn_label)

        button_row = QHBoxLayout()
        login_btn = QPushButton("Log in to Cranky now")
        paste_btn = QPushButton("Paste Access Token Manually")
        button_row.addWidget(login_btn)
        button_row.addWidget(paste_btn)
        layout.insertLayout(1, button_row)

        deck_combo.setEnabled(False)
        button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

        def do_login():
            def on_logged_in(token):
                def update_gui():
                    for w in (warn_label, login_btn, paste_btn):
                        if w:
                            w.hide()
                    # Force the dialog to re-layout immediately
                    dialog.layout().update()
                    dialog.layout().activate()
                    dialog.adjustSize()
                    dialog.repaint()
                    deck_combo.setEnabled(True)
                    button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
                    update_card_count()
                    QMessageBox.information(mw, "Cranky Login", "Login successful!")

                mw.taskman.run_on_main(update_gui)
            run_cranky_login(callback=on_logged_in)
        login_btn.clicked.connect(do_login)

        def do_paste():
            jwt, ok = QInputDialog.getText(
                mw, "Paste JWT Token",
                "Paste your Cranky JWT token here:"
            )
            if ok and jwt.strip():
                save_token(jwt.strip())
                if warn_label:
                    warn_label.hide()
                if login_btn:
                    login_btn.hide()
                if paste_btn:
                    paste_btn.hide()
                deck_combo.setEnabled(True)
                button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
                update_card_count()
                QMessageBox.information(mw, "Cranky Login", "Token saved!")

        paste_btn.clicked.connect(do_paste)
    else:
        deck_combo.setEnabled(True)
        button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

        open_dashboard_btn = QPushButton("Open Cranky Dashboard")
        open_dashboard_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #d0ebff;
                color: #185485;
                border: 1px solid #a3c2e6;
                border-radius: 6px;
                padding: 6px 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #b6e0fe;
            }
            """
        )
        layout.insertWidget(0, open_dashboard_btn)

        def open_dashboard():
            token = get_cranky_token()
            if not token:
                QMessageBox.warning(mw, "Cranky Login", "No valid token found!")
                return
            url = f"{API_BASE_FRONT}/?token={token}"
            import webbrowser
            webbrowser.open(url)

        open_dashboard_btn.clicked.connect(open_dashboard)


    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)

    # --- LIVE CARD COUNT UPDATE ---
    def update_card_count():
        deck = deck_combo.currentText()
        tags = tag_widget.get_tags()
        mode = mode_combo.currentText()
        tag_query = " ".join([f'tag:"{tag}"' for tag in tags])

        # Build base query: deck and tags
        if deck in ("all", "-none-", "", None):
            base_query = tag_query
        else:
            base_query = f'deck:"{deck}" {tag_query}'.strip()

        # For Most Lapses/Most Repetitions, only count review cards
        if mode in ("Most Lapses", "Most Repetitions"):
            if base_query:
                full_query = f"{base_query} is:review"
            else:
                full_query = "is:review"
        else:  # Random mode, count all cards in deck/tag
            full_query = base_query

        try:
            card_ids = mw.col.find_cards(full_query.strip())
            card_count_label.setText(f"Cards in scope: {len(card_ids)}")
            button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(len(card_ids) > 0)
        except Exception as e:
            card_count_label.setText("Cards in scope: error")
            button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

    deck_combo.currentIndexChanged.connect(update_card_count)
    mode_combo.currentIndexChanged.connect(update_card_count)
    tag_widget.tagChanged.connect(update_card_count)
    update_card_count()  # initial count

    if dialog.exec():
        deck = deck_combo.currentText()
        selected_tags = tag_widget.get_tags()
        selection_mode = mode_combo.currentText()
        return deck, selected_tags, selection_mode
    else:
        return None



def on_menu():
    result = launch_cranky_selector()
    if not result:
        print("User cancelled selection.")
        return
    deck, tags, mode = result

    clean_media_folder()
    print(f"User selected: deck={deck}, tags={tags}, mode={mode}")

    exported_cards = fetch_cards_by_criteria(deck, tags, mode, limit=25)
    print(f"Exported {len(exported_cards)} cards.")

    if not exported_cards:
        QMessageBox.warning(mw, "Export Failed", "No cards were exported.")
        return

    # Prompt for theme
    theme, ok = QInputDialog.getText(mw, "Memory Palace Theme", "Enter a theme for the memory palace:")
    print("Theme dialog result:", theme, ok)
    if not ok or not theme.strip():
        QMessageBox.warning(mw, "No Theme", "Operation cancelled: No theme provided.")
        return

    jwt_token = get_cranky_token()
    if not jwt_token:
        QMessageBox.warning(mw, "Not logged in", "Please log in to Cranky first!")
        return
    headers = {"Authorization": f"Bearer {jwt_token}"}

    # # Show progress dialog BEFORE background job, force repaint!
  
    progress_dialog = QProgressDialog(
        "Generating scene (this may take several minutes)...", None, 0, 0, mw
    )
    progress_dialog.setWindowTitle("Cranky Export")
    progress_dialog.setCancelButton(None)
    progress_dialog.setMinimumDuration(0)
    progress_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
    progress_dialog.show()

    for _ in range(5):
        QApplication.processEvents()
        import time
        time.sleep(0.01)

    def background_job(progress):
        print("[Cranky] background_job started!")
        session_id = None
        try:

            if not exported_cards:
                mw.taskman.run_on_main(lambda: QMessageBox.warning(mw, "Export Failed", "No cards were exported."))
                progress_dialog.cancel()
                return

            # Scene creation
            try:
                resp = requests.post(
                    f"{API_BASE_BACK}/v2/generate_scene",
                    json={"theme": theme, "cards": exported_cards, "deck_name": deck},
                    headers=headers, timeout=1000
                )
                resp.raise_for_status()
                session_id = resp.json()["session_id"]
                print(f"[Cranky] Session ID received: {session_id}")
            except Exception as e:
                mw.taskman.run_on_main(lambda: show_server_error("Scene Creation Error", str(e)))
                progress_dialog.cancel()
                return

            # Media upload (not critical)
            try:
                media_src = os.path.join(VIEWER_DIR, "media")
                print(f"[Cranky] Media folder: {media_src}")
                if os.path.exists(media_src):
                    files = []
                    for fname in os.listdir(media_src):
                        path = os.path.join(media_src, fname)
                        try:
                            f = open(path, 'rb')
                            files.append(('files', (fname, f)))
                            print(f"[Cranky] Prepared for upload: {fname}")
                        except Exception as e:
                            print(f"[Cranky] Error opening file {fname}: {e}")
                    if files:
                        upload_url = f"{API_BASE_BACK}/upload_media/{session_id}"
                        try:
                            resp = requests.post(upload_url, files=files, headers=headers)
                            if resp.status_code == 200:
                                print(f"✔️ Uploaded {len(files)} media files to server.")
                            else:
                                print(f"[Cranky] Media upload failed: {resp.status_code} {resp.text}")
                            print(f"[Cranky] Upload response: {resp.status_code} {resp.text}")
                        finally:
                            for _, (_, fh) in files:
                                try:
                                    fh.close()
                                except:
                                    pass
                    else:
                        print("[Cranky] No media files to upload.")
                else:
                    print("[Cranky] Media folder does not exist.")
            except Exception as e:
                print(f"[Cranky] Media Upload Error: {e}")
                # No popup or abort; continue

            # Poll status until complete (no progress label/statusbar updates)
            print(f"[Cranky] Begin polling status for session {session_id}")
            max_tries = 1000
            for i in range(max_tries):
                time.sleep(2)
                QApplication.processEvents()
                try:
                    poll_resp = requests.get(f"{API_BASE_BACK}/v2/status/{session_id}", headers=headers, timeout=30)
                    if poll_resp.status_code != 200:
                        print(f"[Cranky] Polling non-200 status: {poll_resp.status_code} {poll_resp.text}")
                        continue  # Keep polling
                    status = poll_resp.json().get("status", "pending")
                    print(f"[Cranky] Status: {status}")
                    if "complete" in status.lower():
                        print("[Cranky] Polling complete")
                        break
                except Exception as e:
                    mw.taskman.run_on_main(lambda: show_server_error("Status Poll Error", str(e)))
                    progress_dialog.cancel()
                    return
            else:
                mw.taskman.run_on_main(lambda: show_server_error("Timeout", "Scene generation took too long."))
                progress_dialog.cancel()
                return

            #  Workflow complete - open dashboard in browser!
            token = get_cranky_token()
            url = f"{API_BASE_FRONT}/?token={token}"
            def finish_gui():
                progress_dialog.cancel()
                import webbrowser
                webbrowser.open(url)
                QMessageBox.information(mw, "Workflow Complete", "Your Cranky Dashboard was opened in your browser.")
            mw.taskman.run_on_main(finish_gui)

        except Exception as e:
            print("[Cranky] Exception in background_job:", e)
            mw.taskman.run_on_main(lambda: show_server_error("Workflow error", str(e)))
            progress_dialog.cancel()

    # Start background job with a tiny delay so Qt can finish window setup/painting
    QTimer.singleShot(100, lambda: mw.taskman.run_in_background("Cranky Export", background_job))
    

# Register actions
action = QAction("Cranky Memory Palace", mw)
action.triggered.connect(on_menu)
mw.form.menuTools.addAction(action)

#add_cranky_login_menu()  # Login QAction already handled here
