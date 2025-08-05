from aqt import mw
import random
from anki.cards import Card
from anki.decks import DeckId


def fetch_cards(deck, tags):
    query_parts = []

    if deck and deck.lower() != "all":
        query_parts.append(f'deck:"{deck}"')

    if tags:
        for tag in tags:
            query_parts.append(f'tag:"{tag}"')

    query_parts.append("-is:suspended")  # exclude suspended cards

    query = " ".join(query_parts)
    return mw.col.find_cards(query)

def get_card_data(cids):
    data = []
    for cid in cids:
        card = mw.col.get_card(cid)
        if card.queue == -1:
            continue
        card_type = "new" if card.type == 0 else "review"
        data.append({
            "cid": card.id,
            "due": card.due,
            "ivl": card.ivl,
            "type": card_type,
            "review_timeline": [],
        })
    return data

def simulate_review_timeline(card_data, stretch_pct=0, shift=0, horizon_past=30, horizon_future=90, collapse_overdues=False):
    today = mw.col.sched.today
    stretch_factor = 1 + (stretch_pct / 100.0)
    total_range = horizon_past + horizon_future

    for card in card_data:
        card["original_due"] = card["due"]  

        timeline = [False] * total_range

        if card["type"] != "review":
            card["review_timeline"] = timeline
            continue

        relative = card["due"] - today

        if relative < 0:
            if collapse_overdues:
                transformed = today + shift
            else:
                transformed = card["due"] + shift
        else:
            transformed = today + int(relative * stretch_factor + shift)

        card["due"] = transformed  

        day_index = transformed - today
        timeline_index = day_index + horizon_past

        if 0 <= timeline_index < total_range:
            timeline[timeline_index] = True

        card["review_timeline"] = timeline

    return card_data


def compute_due_matrix(card_data, horizon):
    return [card["review_timeline"] for card in card_data]

def sum_matrix_columns(matrix):
    if not matrix:
        return []
    horizon = len(matrix[0])
    counts = [0] * horizon
    for row in matrix:
        for i in range(horizon):
            if row[i]:
                counts[i] += 1
    return counts

def count_remaining_new_cards(deck_name, tags=None):
    query = f'deck:"{deck_name}" is:new -is:suspended'
    if tags:
        tag_query = " OR ".join([f'tag:"{t}"' for t in tags])
        query += f" AND ({tag_query})"
    return mw.col.count_matching_cards(query)

def apply_transformed_due_dates(card_data, horizon_past=30):
    today = mw.col.sched.today
    undo_entry = mw.col.add_custom_undo_entry("Time Warp")
    for card_info in card_data:
        card = mw.col.get_card(card_info["cid"])
        timeline = card_info.get("review_timeline", [])
        if not timeline or card_info["type"] != "review":
            continue

        try:
            index = timeline.index(True)
            new_due = today + (index - horizon_past)
            card.due = new_due
            mw.col.update_card(card)
            mw.col.merge_undo_entries(undo_entry)
        except ValueError:
            continue

    mw.col.save()
    
def set_all_to_new(card_data):
    for card in card_data:
        card["type"] = "new"
        card["due"] = 0
        
def shuffle_new_cards(card_data):
    new_cards = [card for card in card_data if card["type"] == "new"]
    other_cards = [card for card in card_data if card["type"] != "new"]

    random.shuffle(new_cards)

    # Reassign shuffled cards back to the original list
    card_data[:] = new_cards + other_cards
    
def create_filtered_deck_from_transformed(card_data, deck_name="Simulated Timeline"):
    deck = mw.col.decks.by_name(deck_name)
    if not deck:
        did = mw.col.decks.new_filtered(deck_name)
    else:
        did = deck["id"]

    # Build query from transformed card IDs
    cids = [str(card_info["cid"]) for card_info in card_data if card_info.get("review_timeline")]
    if not cids:
        return

    query = f"cid:{' OR cid:'.join(cids)}"

    deck = mw.col.decks.get(did)
    deck["terms"] = [[query, 1000, "due"]]  # High limit to allow all cards in
    deck["reschedule"] = True
    mw.col.decks.save(deck)
    mw.col.decks.select(did)
    mw.col.sched.rebuild_filtered_deck(did)
    
    

