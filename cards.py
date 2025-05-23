# cards.py (patched with deck + tag selector and enlarged GUI)
import json
import os
import re
import requests
from PyQt6 import QtWidgets
import sys
import base64
from tag_input_widget import TagInputWidget  

USE_MOCK_CARDS = False

SCRATCHY_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(SCRATCHY_DIR, "viewer/media")
OUTPUT_PATH = os.path.join(SCRATCHY_DIR, "cards_retrieved.json")

os.makedirs(MEDIA_DIR, exist_ok=True)


def strip_clozes(text):
    return re.sub(r'{{c\d+::(.*?)(::.*?)?}}', r'\1', text)

def strip_html_tags_preserve_formatting(text):
    text = re.sub(r'<li[^>]*>', '\n• ', text)
    text = re.sub(r'</li>', '', text)
    text = re.sub(r'</?(ul|ol)[^>]*>', '\n', text)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'</?(div|p)[^>]*>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def extract_media_names(html):
    return re.findall(r'src="([^"]+)"', html) + re.findall(r'\[sound:([^\]]+)\]', html)

def sanitize_filename_base64(filename):
    name, ext = os.path.splitext(filename)
    encoded = base64.urlsafe_b64encode(name.encode()).decode()
    return f"{encoded}{ext}"

def download_media_file(filename):
    try:
        response = requests.post("http://localhost:8765", json={
            "action": "retrieveMediaFile",
            "version": 6,
            "params": {"filename": filename}
        })
        result = response.json().get("result")
        if result:
            safe_name = sanitize_filename_base64(filename)
            path = os.path.join(MEDIA_DIR, safe_name)
            with open(path, "wb") as f:
                f.write(base64.b64decode(result))
            print(f"✅ Downloaded media file: {safe_name}")
            return safe_name
    except Exception as e:
        print(f"⚠️ Could not download media {filename}: {e}")
    return None


def fetch_cards():
    try:
        deck_names = requests.post("http://localhost:8765", json={
            "action": "deckNames",
            "version": 6
        }).json()["result"]

        tags = requests.post("http://localhost:8765", json={
            "action": "getTags",
            "version": 6
        }).json()["result"]

        app = QtWidgets.QApplication(sys.argv)
        dialog = QtWidgets.QDialog()
        dialog.setWindowTitle("Select Deck and Tags")
        dialog.setFixedSize(700, 300)

        layout = QtWidgets.QVBoxLayout(dialog)
        deck_combo = QtWidgets.QComboBox()
        deck_combo.addItem("-none-")
        deck_combo.addItems(deck_names)

        layout.addWidget(QtWidgets.QLabel("Select Deck:"))
        layout.addWidget(deck_combo)

        layout.addWidget(QtWidgets.QLabel("Select Tags:"))

        tag_widget = TagInputWidget(tags)
        layout.addWidget(tag_widget)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(QtWidgets.QLabel("Select Card Selection Mode:"))
        mode_combo = QtWidgets.QComboBox()
        mode_combo.addItems(["Most Lapses", "Most Repetitions", "Random"])
        layout.addWidget(mode_combo)

        card_count_label = QtWidgets.QLabel("Cards in scope: 0")
        layout.addWidget(card_count_label)

        layout.addWidget(button_box)

        def update_card_count():
            selected_tags = tag_widget.get_tags()
            tag_query = " ".join([f"tag:{tag}" for tag in selected_tags])
            deck = deck_combo.currentText()
            selection_mode = mode_combo.currentText()

            if deck == "-none-":
                query = tag_query
            elif selection_mode == "Random":
                query = f'deck:"{deck}" {tag_query}'
            else:
                query = f'deck:"{deck}" is:review {tag_query}'

            try:
                card_ids = requests.post("http://localhost:8765", json={
                    "action": "findCards",
                    "version": 6,
                    "params": {"query": query.strip()}
                }).json()["result"]
                card_count_label.setText(f"Cards in scope: {len(card_ids)}")
            except:
                card_count_label.setText("Cards in scope: error")

        deck_combo.currentIndexChanged.connect(update_card_count)
        tag_widget.tagChanged.connect(update_card_count)
        mode_combo.currentIndexChanged.connect(update_card_count)
        update_card_count()
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)

        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            print("🛑 User cancelled selection. Exiting program.")
            sys.exit(0)

        deck = deck_combo.currentText()
        selection_mode = mode_combo.currentText()
        selected_tags = tag_widget.get_tags()

        query_parts = []
        if deck != "-none-":
            query_parts.append(f'deck:"{deck}"')
        for tag in selected_tags:
            query_parts.append(f'tag:"{tag}"')
        if selection_mode != "Random":
            query_parts.append("is:review")

        query = " ".join(query_parts)
        print("🔍 AnkiConnect query:", query)
        
        card_ids = requests.post("http://localhost:8765", json={
            "action": "findCards",
            "version": 6,
            "params": {"query": query}
        }).json()["result"]

        if not card_ids:
            raise ValueError("No cards found")

        card_infos = requests.post("http://localhost:8765", json={
            "action": "cardsInfo",
            "version": 6,
            "params": {"cards": card_ids}
        }).json()["result"]

        best_cards_by_note = {}
        for c in card_infos:
            note_id = c["note"]
            if note_id not in best_cards_by_note or c.get("lapses", 0) > best_cards_by_note[note_id].get("lapses", 0):
                best_cards_by_note[note_id] = c

        if selection_mode == "Most Repetitions":
            top_cards = sorted(best_cards_by_note.values(), key=lambda c: c.get("reps", 0), reverse=True)[:25]
        elif selection_mode == "Random":
            import random
            top_cards = random.sample(list(best_cards_by_note.values()), min(25, len(best_cards_by_note)))
        else:
            top_cards = sorted(best_cards_by_note.values(), key=lambda c: c.get("lapses", 0), reverse=True)[:25]

        note_ids = [c["note"] for c in top_cards]
        notes = requests.post("http://localhost:8765", json={
            "action": "notesInfo",
            "version": 6,
            "params": {"notes": note_ids}
        }).json()["result"]

        note_map = {n["noteId"]: n for n in notes}
        selected = []

        for c in top_cards:
            nid = c["note"]
            note = note_map.get(nid)
            if not note:
                continue
            flds = note.get("fields", {})
            raw_front = flds.get("Text", {}).get("value", "")
            raw_back = flds.get("Extra", {}).get("value", "")
            front = strip_html_tags_preserve_formatting(strip_clozes(raw_front))
            back = strip_html_tags_preserve_formatting(strip_clozes(raw_back))

            media_sources = set()
            # Always include media from Text and Extra fields
            raw_text = flds.get("Text", {}).get("value", "")
            raw_extra = flds.get("Extra", {}).get("value", "")
            media_sources.update(extract_media_names(raw_text))
            media_sources.update(extract_media_names(raw_extra))

            # Optionally scan all other fields for additional images
            for fname, field in flds.items():
                if fname in ("Text", "Extra"):
                    continue
                val = field.get("value", "")
                media_sources.update(extract_media_names(val))

            downloaded = []
            for filename in media_sources:
                path = download_media_file(filename)
                if not path:
                    continue
                full_path = os.path.join(MEDIA_DIR, path)
                try:
                    from PIL import Image
                    with Image.open(full_path) as img:
                        if img.width >= 150 or img.height >= 150:
                            downloaded.append(path)
                        else:
                            print(f"⚠️ Skipping small image: {path} ({img.width}x{img.height})")
                except Exception as e:
                    print(f"⚠️ Could not check image: {path} ({e})")

            selected.append({
                "uid": str(nid),
                "front": front,
                "back": back,
                "images": downloaded
            })

        return selected

    except Exception as e:
        print(f"❌ Anki Connect Error: {e}")
        return []

def get_cards(force_refresh=False):
    if not force_refresh and os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, "r") as f:
            return json.load(f)

    cards = MOCK_CARDS if USE_MOCK_CARDS else fetch_cards()

    if cards:
        with open(OUTPUT_PATH, "w") as f:
            json.dump(cards, f, indent=2, ensure_ascii=False)
    return cards



