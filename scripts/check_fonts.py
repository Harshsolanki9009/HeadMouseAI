import os
import sys
sys.path.insert(0, os.path.abspath("."))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from gui.main_window import MainWindow
from config.settings import get_settings

app = QApplication(sys.argv)
win = MainWindow(get_settings())

seen_families = set()
for w in win.findChildren(object):
    if hasattr(w, 'font') and callable(w.font):
        f = w.font()
        seen_families.add(f.family())
        if "Segoe" not in f.family() and f.family() != "":
            print(f"{type(w).__name__}: {f.family()}")

print("All seen font families:", seen_families)
print("Application font:", app.font().family())
