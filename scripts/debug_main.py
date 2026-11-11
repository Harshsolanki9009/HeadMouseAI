"""Debug print of main.py internals on startup."""
import sys, os
sys.path.insert(0, r"C:\Users\Admin\HeadMouseAI")
os.chdir(r"C:\Users\Admin\HeadMouseAI")
import main
print("has _run_with_camera_and_fallback:", hasattr(main.Phase1App, '_run_with_camera_and_fallback'))
app = main.Phase1App()
print("camera_ok attr:", hasattr(app, 'camera_ok'))
print("error_message attr:", hasattr(app, 'error_message'))
