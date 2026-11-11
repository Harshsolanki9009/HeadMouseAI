"""Debug CameraCapture.initialize() — trace each iteration."""
import sys, os, time
sys.path.insert(0, r"C:\Users\Admin\HeadMouseAI")
os.chdir(r"C:\Users\Admin\HeadMouseAI")
from core.camera import CameraCapture
import cv2

cap = CameraCapture()
print("params:", cap.index, cap.width, cap.height)
print("starting initialize...")

# Replicate initialize() exactly, but with tracing
for attempt in range(3):
    time.sleep(0.4 * attempt)
    for idx in [cap.index, cap.index + 1, cap.index - 1]:
        try:
            c = cv2.VideoCapture(idx)
            print(f"  attempt={attempt} idx={idx}: opened={c.isOpened()}")
            if c.isOpened():
                try:
                    c.set(cv2.CAP_PROP_FRAME_WIDTH, cap.width)
                    c.set(cv2.CAP_PROP_FRAME_HEIGHT, cap.height)
                    c.set(cv2.CAP_PROP_BRIGHTNESS, 100)
                    c.set(cv2.CAP_PROP_EXPOSURE, -1)
                    c.set(cv2.CAP_PROP_FOCUS, -1)
                    cw = int(c.get(cv2.CAP_PROP_FRAME_WIDTH))
                    ch = int(c.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    print(f"    dims: {cw}x{ch}")
                    if cw > 0 and ch > 0:
                        cap._cap = c
                        cap.is_running = True
                        print("    -> SET AS CAP OK")
                        ret, fr = c.read()
                        print(f"    frame read ret={ret} shape={fr.shape if fr is not None else None}")
                        cap.close()
                        break
                except Exception as e:
                    print(f"    prop error: {e}")
                    if c:
                        c.release()
            else:
                if c:
                    try: c.release()
                    except: pass
        except Exception as e:
            print(f"  error idx={idx}: {type(e).__name__}: {e}")
            if 'c' in locals() and c:
                try: c.release()
                except: pass
    if cap.is_running:
        break

print("is_running:", cap.is_running)
