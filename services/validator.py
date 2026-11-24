import hashlib, uuid
from pathlib import Path
import cv2
from PIL import Image
from werkzeug.utils import secure_filename
import config
Image.MAX_IMAGE_PIXELS = 50_000_000   # reject decompression bombs
class ValidationError(Exception):
    pass
# the first bytes of a genuine file identify its real format
SIGNATURES = {
    "jpg":  lambda h: h.startswith(b"\xff\xd8\xff"),
    "jpeg": lambda h: h.startswith(b"\xff\xd8\xff"),
    "png":  lambda h: h.startswith(b"\x89PNG\r\n\x1a\n"),
    "webp": lambda h: h[:4] == b"RIFF" and h[8:12] == b"WEBP",
    "mp4":  lambda h: h[4:8] == b"ftyp",
    "mov":  lambda h: h[4:8] == b"ftyp",
    "avi":  lambda h: h[:4] == b"RIFF" and h[8:12] == b"AVI ",
    "mkv":  lambda h: h.startswith(b"\x1a\x45\xdf\xa3"),
}
def validate_and_save(file_storage, dest_dir=config.UPLOADS):
    original = secure_filename(file_storage.filename or "")
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if ext in config.ALLOWED_IMAGE:
        kind, limit_mb = "image", config.MAX_IMAGE_MB
    elif ext in config.ALLOWED_VIDEO:
        kind, limit_mb = "video", config.MAX_VIDEO_MB
    else:
         raise ValidationError(f"Unsupported file type: .{ext or '(none)'}")
    head = file_storage.stream.read(16)
    file_storage.stream.seek(0)
    if not SIGNATURES[ext](head):
        raise ValidationError("File content does not match its extension.")
    stored_name = f"{uuid.uuid4().hex}.{ext}"   # random name, never the user's 

    dest = Path(dest_dir) / stored_name
    sha, size, too_big = hashlib.sha256(), 0, False
    with open(dest, "wb") as out:                 # stream to disk in 1 MB pieces

        while True:
            chunk = file_storage.stream.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > limit_mb * 1024 * 1024:
                too_big = True
                break
            sha.update(chunk)
            out.write(chunk)
    if too_big:
        dest.unlink(missing_ok=True)
        raise ValidationError(f"File larger than {limit_mb} MB.")
    try:                                          # make sure it really decodes

        if kind == "image":
            with Image.open(dest) as im:
                im.verify()
        else:
            cap = cv2.VideoCapture(str(dest))
            ok, _ = cap.read()
            cap.release()
            if not ok:
                raise ValueError("unreadable video")
    except Exception:
        dest.unlink(missing_ok=True)
        raise ValidationError("The file is damaged or cannot be decoded.")
    return {"path": dest, "stored_name": stored_name, "media_type": kind,
            "sha256": sha.hexdigest(), "size": size, "original_name": 
original}