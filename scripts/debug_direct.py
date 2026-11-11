"""Directly call fallback window to surface any exception."""
import sys, os, traceback
sys.path.insert(0, r"C:\Users\Admin\HeadMouseAI")
os.chdir(r"C:\Users\Admin\HeadMouseAI")
from main import Phase1App

app = Phase1App()
app.error_message = "test error: → arrow here"
try:
    print("CALLING _show_fallback_window", flush=True)
    app._show_fallback_window()
    print("RETURNED NORMALLY", flush=True)
except Exception:
    traceback.print_exc()
