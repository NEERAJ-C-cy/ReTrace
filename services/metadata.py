import shutil
import cv2
from PIL import Image, ExifTags
NOTE = ("Metadata is easy to remove or edit, and most social platforms strip it. "
        "Missing metadata proves nothing; present metadata is a claim made by the file.")
def image_metadata(path):
    meta = {}
    with Image.open(path) as im:
        meta["format"] = im.format
        meta["size"] = f"{im.width}x{im.height}"
        exif = im.getexif()
        for tag_id, val in exif.items():
            if isinstance(val, bytes):
                continue
            meta[ExifTags.TAGS.get(tag_id, str(tag_id))] = str(val)
        try:                                   # capture time lives in the Exif sub-block 

            for tag_id, val in exif.get_ifd(0x8769).items():
                name = ExifTags.TAGS.get(tag_id, str(tag_id))
                if name in ("DateTimeOriginal", "DateTimeDigitized"):
                    meta[name] = str(val)
        except Exception:
            pass
        meta["has_exif"] = len(exif) > 0
        return meta
def video_metadata(path):
        cap = cv2.VideoCapture(str(path))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        meta = {"size": f" {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}",
        "fps": round(fps, 2) if fps else None,
        "duration_s": round(frames / fps, 1) if fps and frames > 0 else 
        None}
        cap.release()
        meta["ffprobe_available"] = shutil.which("ffprobe") is not None   #  optional deeper tags
       
        return meta
def extract_metadata(path, media_type):
        meta = image_metadata(path) if media_type == "image"else video_metadata(path)
        meta["_note"] = NOTE
        return meta