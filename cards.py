import json
import os
import re
from aqt import mw
from PyQt6 import QtWidgets
import sys
import base64
from .tag_input_widget import TagInputWidget  
import random
from heapq import nlargest
import re
import html as html_lib
import struct
import struct
import os

USE_MOCK_CARDS = False

SCRATCHY_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(SCRATCHY_DIR, "viewer/media")
OUTPUT_PATH = os.path.join(SCRATCHY_DIR, "cards_retrieved.json")

os.makedirs(MEDIA_DIR, exist_ok=True)

print("cards.py loaded")

def strip_clozes(text):
    return re.sub(r'{{c\d+::(.*?)(::.*?)?}}', r'\1', text)


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
        media_path = mw.col.media.dir()
        abs_path = os.path.join(media_path, filename)
        if os.path.exists(abs_path):
            safe_name = sanitize_filename_base64(filename)
            dest_path = os.path.join(MEDIA_DIR, safe_name)
            with open(abs_path, "rb") as src, open(dest_path, "wb") as dst:
                dst.write(src.read())
            print(f"✅ Copied media file: {safe_name}")
            return safe_name

    except Exception as e:
        print(f"⚠️ Could not download media {filename}: {e}")
    return None


def fetch_cards_by_criteria(deck, tags, selection_mode, limit=25):
    try:
      
        # Build query
        query_parts = []
        if deck and deck != "all" and deck != "-none-":
            query_parts.append(f'deck:"{deck}"')
        for tag in tags:
            query_parts.append(f'tag:"{tag}"')
        # No is:review or is:new for these modes!
        query = " ".join(query_parts)
        card_ids = mw.col.find_cards(query)

        if not card_ids:
            print("No cards found")
            return []

        def fetch_top_cards(card_ids, key):
            best_cards_by_note = {}
            for cid in card_ids:
                card = mw.col.get_card(cid)
                note_id = card.nid
                val = getattr(card, key, 0)
                if note_id not in best_cards_by_note or val > getattr(best_cards_by_note[note_id], key, 0):
                    best_cards_by_note[note_id] = card
            from heapq import nlargest
            return nlargest(limit, best_cards_by_note.values(), key=lambda c: getattr(c, key, 0))

        if selection_mode == "Random":
            import random
            chosen_ids = random.sample(card_ids, min(limit, len(card_ids)))
            top_cards = [mw.col.get_card(cid) for cid in chosen_ids]
        elif selection_mode == "Most Repetitions":
            top_cards = fetch_top_cards(card_ids, "reps")
        else:  # Most Lapses
            top_cards = fetch_top_cards(card_ids, "lapses")


        def fetch_top_cards(card_ids, key):
            best_cards_by_note = {}
            batch_size = 500
            for i in range(0, len(card_ids), batch_size):
                batch = card_ids[i:i + batch_size]
                for cid in batch:
                    card = mw.col.get_card(cid)
                    note_id = card.nid
                    val = getattr(card, key, 0)
                    if note_id not in best_cards_by_note or val > getattr(best_cards_by_note[note_id], key, 0):
                        best_cards_by_note[note_id] = card
            return nlargest(25, best_cards_by_note.values(), key=lambda c: getattr(c, key, 0))


        if selection_mode == "Random":
            random_ids = random.sample(card_ids, min(25, len(card_ids)))
            top_cards = [mw.col.get_card(cid) for cid in random_ids]
        elif selection_mode == "Most Repetitions":
            top_cards = fetch_top_cards(card_ids, "reps")
        else:  # Most Lapses
            top_cards = fetch_top_cards(card_ids, "lapses")


        note_ids = [c.nid for c in top_cards]
        notes = [mw.col.get_note(nid) for nid in note_ids]
        note_map = {n.id: n for n in notes}

        selected = []
        model_templates_cache = {}

        for c in top_cards:
            nid = c.nid
            note = note_map.get(nid)
            if not note:
                continue

            # Get main fields
            front_val, answer_vals, is_cloze = get_main_fields_for_note(note, model_templates_cache)
            # Clean up
            front = strip_html_tags_preserve_formatting(strip_clozes(front_val))
            back = "\n\n".join(strip_html_tags_preserve_formatting(strip_clozes(ans)) for ans in answer_vals if ans.strip())

            flds = dict(note.items())  # Now {fieldname: value}
            media_sources = set()
            for val in flds.values():
                media_sources.update(extract_media_names(val))

            downloaded = []
            for filename in media_sources:
                path = download_media_file(filename)
                if not path:
                    continue
                full_path = os.path.join(MEDIA_DIR, path)
                ext = os.path.splitext(path)[1].lower()
                if ext in ('.png', '.jpg', '.jpeg', '.gif','.webp'):
                    try:                  
                        downloaded.append(path)
                    except Exception as e:
                        print(f"⚠️ Could not download image: {path} ({e})")
                else:
                    downloaded.append(path)  # Always include non-image files (SVG, audio, etc.)

            selected.append({
                "uid": str(nid),
                "front": front,
                "back": back,
                "images": downloaded
            })

        with open(OUTPUT_PATH, "w") as f:
            json.dump(selected, f, indent=2, ensure_ascii=False)
        return selected

    except Exception as e:
        return []


def get_main_fields_for_note(note, model_templates_cache):
    flds = dict(note.items())
    model_id = note.mid
    model = mw.col.models.get(model_id)
    model_name = model['name']

    if model_name not in model_templates_cache:
        templates = model['tmpls']
        if not templates:
            return "", [], False
        first_template = templates[0]
        t_front = first_template['qfmt']
        t_back = first_template['afmt']
        # Detect cloze: look for {{cloze:...}} in front template
        cloze_match = re.search(r"{{.*cloze:([\w-]+)\s*}}", t_front, re.IGNORECASE)
        if cloze_match:
            model_templates_cache[model_name] = {
                "is_cloze": True,
                "cloze_field": cloze_match.group(1),
                "t_back": t_back,
            }
        else:
            field_re = re.compile(r"{{\s*([\w-]+)\s*}}", re.IGNORECASE)
            front_fields = set(field_re.findall(t_front))
            back_fields = [f for f in field_re.findall(t_back) if f not in front_fields]
            q_field = next(iter(front_fields), None)
            model_templates_cache[model_name] = {
                "is_cloze": False,
                "t_front": t_front,
                "t_back": t_back,
                "question_field": q_field,
                "answer_fields": back_fields,
            }
    info = model_templates_cache[model_name]

    if info.get("is_cloze"):
        cloze_field = info["cloze_field"]
        t_back = info["t_back"]
        question = flds.get(cloze_field, "")
        answer = question
        extra_field = None
        for k in flds:
            if k.lower() == "extra":
                extra_field = k
                break
        if extra_field and flds[extra_field].strip():
            answer += "\n\n" + flds[extra_field]
        if question.strip() == answer.strip():
            candidates = {k: v for k, v in flds.items() if k != cloze_field and v.strip()}
            if candidates:
                most_content_field = max(
                    candidates, key=lambda k: len(candidates[k].replace(' ', '').replace('\n', ''))
                )
                if candidates[most_content_field] not in answer:
                    answer += "\n\n" + candidates[most_content_field]
        return question, [answer], True
    else:
        t_front = info["t_front"]
        t_back = info["t_back"]
        q_field = info.get("question_field")
        answer_fields = info.get("answer_fields", [])
        q_val = flds.get(q_field, "") if q_field else ""
        a_vals = [flds.get(f, "") for f in answer_fields if flds.get(f, "")]
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
