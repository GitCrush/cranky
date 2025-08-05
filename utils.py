# utils.py

import os
import shutil
from .config import VIEWER_DIR

def clean_media_folder():
    media_dir = os.path.join(VIEWER_DIR, "media")
    print("Cleaning media folder:", media_dir)
    print("CWD:", os.getcwd())
    if os.path.exists(media_dir):
        for fname in os.listdir(media_dir):
            fpath = os.path.join(media_dir, fname)
            try:
                if os.path.isfile(fpath):
                    os.remove(fpath)
                elif os.path.isdir(fpath):
                    shutil.rmtree(fpath)
            except Exception as e:
                print(f"⚠️ Failed to delete {fpath}: {e}")
