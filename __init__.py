# __init__.py


from aqt import mw
from aqt.qt import QAction  # ✅ Correct Qt import for Anki

import threading

def cranky_safe_excepthook(args):
    print(f"[Cranky] Thread exception in {args.thread.name}: {args.exc_type.__name__}: {args.exc_value}")

threading.excepthook = cranky_safe_excepthook

# Hook run_on_main for debugging
_original_run_on_main = mw.taskman.run_on_main

def debug_run_on_main(func):
    print("[Cranky] run_on_main scheduled:", func)
    return _original_run_on_main(func)

mw.taskman.run_on_main = debug_run_on_main



print("Cranky addon: __init__.py starting")

try:
    # UI setup
    from .ui import on_menu, add_cranky_login_menu

    # Add menu items
    # cranky_action = QAction("Cranky Deck/Tag Export", mw)
    # cranky_action.triggered.connect(on_menu)
    # mw.form.menuTools.addAction(cranky_action)

    # add_cranky_login_menu()

    print("Cranky addon: Menu actions registered")

except Exception as e:
    print("CRANKY INIT ERROR:", e)
    import traceback
    traceback.print_exc()
    raise

print("Cranky addon: __init__.py loaded completely")

