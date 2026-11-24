import cv2


def sample_frames(path, interval_s=1.0, max_frames=120, max_width=640):
    """Return a list of (frame_index, timestamp_seconds, frame_bgr)."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError("Cannot open video")

    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not fps or fps != fps or fps <= 0:  # 0, None or NaN
            fps = 25.0

        step = max(int(round(fps * interval_s)), 1)
        frames = []
        i = 0

        while len(frames) < max_frames:
            if not cap.grab():  # move forward without decoding fully
                break

            if i % step == 0:
                ok, frame = cap.retrieve()  # decode only the frames we keep
                if ok:
                    h, w = frame.shape[:2]
                    if w > max_width:  # shrink large frames to save RAM
                        frame = cv2.resize(frame, (max_width, int(h * max_width / w)))
                    frames.append((i, i / fps, frame))
            i += 1
    finally:
        cap.release()

    if not frames:
        raise ValueError("No frames could be read")

    return frames
