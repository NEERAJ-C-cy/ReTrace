import sys
import cv2

src, dst = sys.argv[1], sys.argv[2]
cap = cv2.VideoCapture(src)

if not cap.isOpened():
    raise ValueError(f"Cannot open source video: {src}")

fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) * 0.6)
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) * 0.6)

out = cv2.VideoWriter(dst, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

try:
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        out.write(cv2.resize(frame, (w, h)))
finally:
    cap.release()
    out.release()
