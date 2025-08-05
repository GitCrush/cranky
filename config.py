# config.py

import os

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
VIEWER_DIR = os.path.join(ADDON_DIR, "viewer")

API_BASE_BACK = "https://api.cranky.app"
API_BASE_FRONT = "https://cranky.app"
CARDS_CACHE = "cards_retrieved.json"
