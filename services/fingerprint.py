import cv2
import imagehash
from PIL import Image, ImageOps
import config

ORIENTATIONS = (
    ("0", 0),
    ("90", 1),
    ("180", 2),
    ("270", 3),
)


def rotated_images(img):
    """Yield each cardinal orientation of a PIL image."""
    yield 0, img
    yield 90, img.transpose(Image.Transpose.ROTATE_90)
    yield 180, img.transpose(Image.Transpose.ROTATE_180)
    yield 270, img.transpose(Image.Transpose.ROTATE_270)


def hash_pil(img):
    """Return pHash, dHash and aHash of a PIL image as hex strings."""
    img = img.convert("RGB")
    return {
       "phash": str(imagehash.phash(img)),     # DCT based      
       "dhash": str(imagehash.dhash(img)),      # gradient based    
      "ahash": str(imagehash.average_hash(img)),   # mean based
    }


def hashes_for_orientations(img):
    """Hash a PIL image at 0, 90, 180 and 270 degrees."""
    hashes = []
    for orientation, rotated in rotated_images(img):
        hashes.append({"orientation": orientation, **hash_pil(rotated)})
    return hashes

def frame_to_pil(frame_bgr):
     """OpenCV frames are BGR; Pillow wants RGB."""
     return Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))

def fingerprints_for(path, media_type):
    """List of fingerprints: 1 for an image, many for a video."""
    if media_type == "image":
     with Image.open(path) as im:
          im = ImageOps.exif_transpose(im)   # apply phone rotation flag
          out = []
          for h in hashes_for_orientations(im):
              out.append({"frame_index": 0, "timestamp_s": 0.0, **h})
     return out

    from services.video import sample_frames   # added in Phase 12
    out = []
    for idx, ts, frame in sample_frames(path, config.FRAME_INTERVAL_S, config.MAX_FRAMES):
       pil_frame = frame_to_pil(frame)
       for h in hashes_for_orientations(pil_frame):
           out.append({"frame_index": idx, "timestamp_s": round(ts, 2), **h})
    return out