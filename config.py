from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
UPLOADS  = DATA / "uploads"

HISTORICAL = DATA / "historical"
FRAMES = DATA / "frames"

DB_PATH = DATA / "retrace.db"


for p in (UPLOADS, HISTORICAL, FRAMES):
    p.mkdir(parents=True, exist_ok=True) # create folders if missing

ALLOWED_IMAGE = {"jpg", "jpeg", "png", "webp"}
ALLOWED_VIDEO = {"mp4", "mov", "avi", "mkv"}
MAX_IMAGE_MB = 10
MAX_VIDEO_MB = 100
FRAME_INTERVAL_S = 1.0 # one frame per second
MAX_FRAMES = 120 # safety cap for long videos
OCR_FRAME_INTERVAL_S = 2.0 # evenly sample videos instead of OCRing every frame
OCR_MAX_FRAMES = 4
OCR_MIN_CONF = 55
NEAR_DUP_MAX = 6 # distance <= 6 -> near-duplicate
SIMILAR_MAX = 12 # distance <= 12 -> similar; allows cardinal rotation tolerance
TOP_K = 5
STRONG_FRAME_RATIO = 0.3 # video: share of frames that must match
DATE_TOLERANCE_DAYS = 1
TESSERACT_CMD = None # e.g. r"C:\Program Files\TesseractOCR\tesseract.exe"
TESSDATA_DIR = BASE / "tessdata"
ENABLE_EXTERNAL = False # optional external search stays off