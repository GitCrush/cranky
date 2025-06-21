import json
import os
import re
import requests
from PyQt6 import QtWidgets
import sys
import base64
from tag_input_widget import TagInputWidget  
import random
from heapq import nlargest

USE_MOCK_CARDS = False

SCRATCHY_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(SCRATCHY_DIR, "viewer/media")
OUTPUT_PATH = os.path.join(SCRATCHY_DIR, "cards_retrieved.json")

os.makedirs(MEDIA_DIR, exist_ok=True)


def strip_clozes(text):
    return re.sub(r'{{c\d+::(.*?)(::.*?)?}}', r'\1', text)

import re
import html as html_lib

def strip_html_tags_preserve_formatting(html):

    html = re.sub(r'<style.*?>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<script.*?>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)   
    html = re.sub(r'</li\s*>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'<li\s*>', '• ', html, flags=re.IGNORECASE)
    html = re.sub(r'<(ul|ol).*?>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'</(ul|ol)>', '\n', html, flags=re.IGNORECASE)   
    html = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'</?div.*?>', '\n', html, flags=re.IGNORECASE)  
    html = re.sub(r'<.*?>', '', html)

    text = html_lib.unescape(html)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def extract_media_names(html):
    return re.findall(r'src="([^"]+)"', html) + re.findall(r'\[sound:([^\]]+)\]', html)

def sanitize_filename_base64(filename):
    name, ext = os.path.splitext(filename)
    encoded = base64.urlsafe_b64encode(name.encode()).decode().rstrip("=")
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

        from heapq import nlargest
        import random

        def fetch_top_cards(card_ids, key):
            best_cards_by_note = {}
            batch_size = 500

            for i in range(0, len(card_ids), batch_size):
                batch = card_ids[i:i + batch_size]
                response = requests.post("http://localhost:8765", json={
                    "action": "cardsInfo",
                    "version": 6,
                    "params": {"cards": batch}
                }).json()["result"]

                for c in response:
                    note_id = c["note"]
                    if note_id not in best_cards_by_note or c.get(key, 0) > best_cards_by_note[note_id].get(key, 0):
                        best_cards_by_note[note_id] = c

            return nlargest(25, best_cards_by_note.values(), key=lambda c: c.get(key, 0))

        if selection_mode == "Random":
            random_ids = random.sample(card_ids, min(25, len(card_ids)))
            card_infos = requests.post("http://localhost:8765", json={
                "action": "cardsInfo",
                "version": 6,
                "params": {"cards": random_ids}
            }).json()["result"]
            top_cards = card_infos

        elif selection_mode == "Most Repetitions":
            top_cards = fetch_top_cards(card_ids, "reps")

        else:  # Most Lapses
            top_cards = fetch_top_cards(card_ids, "lapses")

        note_ids = [c["note"] for c in top_cards]
        notes = requests.post("http://localhost:8765", json={
            "action": "notesInfo",
            "version": 6,
            "params": {"notes": note_ids}
        }).json()["result"]

        note_map = {n["noteId"]: n for n in notes}
        selected = []
        model_templates_cache = {}

        for c in top_cards:
            nid = c["note"]
            note = note_map.get(nid)
            if not note:
                continue

            # Get main fields
            front_val, answer_vals, is_cloze = get_main_fields_for_note(note, model_templates_cache)
            # Clean up
            front = strip_html_tags_preserve_formatting(strip_clozes(front_val))
            back = "\n\n".join(strip_html_tags_preserve_formatting(strip_clozes(ans)) for ans in answer_vals if ans.strip())

            flds = note.get("fields", {})
            media_sources = set()
            for field in flds.values():
                val = field.get("value", "")
                media_sources.update(extract_media_names(val))

            downloaded = []
            for filename in media_sources:
                path = download_media_file(filename)
                if not path:
                    continue
                full_path = os.path.join(MEDIA_DIR, path)
                ext = os.path.splitext(path)[1].lower()
                if ext in ('.png', '.jpg', '.jpeg', '.gif'):
                    try:
                        from PIL import Image
                        with Image.open(full_path) as img:
                            if img.width >= 150 or img.height >= 150:
                                downloaded.append(path)
                            else:
                                print(f"⚠️ Skipping small image: {path} ({img.width}x{img.height})")
                    except Exception as e:
                        print(f"⚠️ Could not check image: {path} ({e})")
                else:
                    downloaded.append(path)  # Always include non-image files (SVG, audio, etc.)

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


def get_main_fields_for_note(note, model_templates_cache):
    flds = note.get("fields", {})
    field_values = {k: v.get("value", "") for k, v in flds.items()}
    model_name = note["modelName"]

    if model_name not in model_templates_cache:
        templates = requests.post("http://localhost:8765", json={
            "action": "modelTemplates",
            "version": 6,
            "params": {"modelName": model_name}
        }).json()["result"]
        if not templates:
            return "", [], False

        first_template = next(iter(templates.values()))
        t_front = first_template["Front"]
        t_back = first_template["Back"]

        cloze_match = re.search(r"{{.*cloze:([\w-]+)\s*}}", t_front, re.IGNORECASE)
        model_templates_cache[model_name] = {
            "is_cloze": bool(cloze_match),
            "cloze_field": cloze_match.group(1) if cloze_match else None,
            "t_back": t_back,
        } if cloze_match else {
            "is_cloze": False,
            "t_front": t_front,
            "t_back": t_back,
        }

    info = model_templates_cache[model_name]
    if info.get("is_cloze"):
        cloze_field = info["cloze_field"]
        t_back = info["t_back"]
        question = field_values.get(cloze_field, "")
        # Default: answer is cloze field value, plus any "Extra" field
        answer = question
        extra_field = None
        # Look for a likely "Extra" field by name
        for k in field_values:
            if k.lower() == "extra":
                extra_field = k
                break
        if extra_field and field_values[extra_field].strip():
            answer += "\n\n" + field_values[extra_field]
        # If after this, answer == question (i.e. no real answer/explanation), add next biggest field
        if question.strip() == answer.strip():
            # Exclude the main cloze field from candidates
            candidates = {k: v for k, v in field_values.items() if k != cloze_field and v.strip()}
            if candidates:
                # Find the field with the most non-space characters (i.e., richest field)
                most_content_field = max(
                    candidates, key=lambda k: len(candidates[k].replace(' ', '').replace('\n', ''))
                )
                # Only append if not already included
                if candidates[most_content_field] not in answer:
                    answer += "\n\n" + candidates[most_content_field]
        return question, [answer], True


    else:
        # Non-cloze: as before (use main front field and all answer fields on back)
        t_front = info["t_front"]
        t_back = info["t_back"]
        field_re = re.compile(r"{{\s*([\w-]+)\s*}}", re.IGNORECASE)
        front_fields = set(field_re.findall(t_front))
        back_fields = [f for f in field_re.findall(t_back) if f not in front_fields]
        q_field = next(iter(front_fields), None)
        q_val = field_values.get(q_field, "") if q_field else ""
        a_vals = [field_values.get(f, "") for f in back_fields if field_values.get(f, "")]
        return q_val, a_vals, False



def get_cards(force_refresh=False):
    if not force_refresh and os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, "r") as f:
            return json.load(f)

    cards = MOCK_CARDS if USE_MOCK_CARDS else fetch_cards()

    if cards:
        with open(OUTPUT_PATH, "w") as f:
            json.dump(cards, f, indent=2, ensure_ascii=False)
    return cards


    # Use cached info
    info = model_templates_cache[model_name]
    if info.get("is_cloze"):
        main = info["cloze_field"]
        answer_fields = [main]
        # find a secondary answer (e.g. Extra)
        field_re = re.compile(r"{{\s*([\w-]+)\s*}}", re.IGNORECASE)
        back_fields = field_re.findall(info["t_back"])
        for f in back_fields:
            if f.lower() != main.lower() and f in flds:
                answer_fields.append(f)
                break  # just one extra
        q_val = flds.get(main, {}).get("value", "")
        a_vals = [flds.get(f, {}).get("value", "") for f in answer_fields if f in flds]
        return q_val, a_vals, True
    else:
        q_field = info["question_field"]
        answer_fields = info["answer_fields"]
        q_val = flds.get(q_field, {}).get("value", "") if q_field else ""
        a_vals = [flds.get(f, {}).get("value", "") for f in answer_fields if f in flds]
        return q_val, a_vals, False
