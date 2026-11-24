import re
import shutil
import os
import cv2
import numpy as np
from PIL import Image, ImageOps
import pytesseract
from pytesseract import Output
from dateparser.search import search_dates
import config

def find_tesseract():
    configured = getattr(config, "TESSERACT_CMD", None)
    candidates = [
        configured,
        shutil.which("tesseract"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


tesseract_cmd = find_tesseract()
if tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

YEAR = re.compile(r"\b(19|20)\d{2}\b")
DATE_SEP = re.compile(r"[/\-.]")


def available_tesseract_languages():
    configured = getattr(config, "TESSDATA_DIR", None)
    if configured:
        tessdata = str(configured)
    elif tesseract_cmd:
        tessdata = os.path.join(os.path.dirname(tesseract_cmd), "tessdata")
    else:
        return set()
    if not os.path.isdir(tessdata):
        return set()
    return {
        os.path.splitext(name)[0]
        for name in os.listdir(tessdata)
        if name.endswith(".traineddata")
    }


OCR_LANGUAGES = (
    "+".join(
        lang
        for lang in ("eng", "hin")
        if lang in available_tesseract_languages() or lang == "eng"
    )
)


def load_oriented_bgr(path):
    """Load an image with EXIF auto-rotation applied and return BGR numpy array."""
    pil_img = Image.open(path)
    pil_img = ImageOps.exif_transpose(pil_img).convert("RGB")
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def preprocess(img_bgr):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    _, w = gray.shape[:2]
    if w < 1200:
        scale = 1200 / float(w)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    elif w > 1400:
        scale = 1400 / float(w)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    blurred = cv2.GaussianBlur(gray, (0, 0), 1.0)
    sharp = cv2.addWeighted(gray, 1.35, blurred, -0.35, 0)
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    adaptive = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        9,
    )
    return (
        otsu,
        adaptive,
        cv2.cvtColor(sharp, cv2.COLOR_GRAY2BGR),
    )


def _clean_word(text):
    text = text.strip()
    text = re.sub(r"[^A-Za-z0-9%.,+:/\-\u0900-\u097F]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _line_quality(lines, confidences):
    text = " ".join(lines)
    letters = sum(ch.isalpha() for ch in text)
    digits = sum(ch.isdigit() for ch in text)
    words = [w for w in text.split() if len(w) >= 2]
    average_conf = sum(confidences) / len(confidences) if confidences else 0.0
    readable = letters + digits
    return readable + len(words) * 3 + average_conf * 0.15


def _has_reliable_text(lines, confidences):
    if not lines:
        return False
    text = " ".join(lines)
    compact = re.sub(r"\s+", " ", text).strip()
    tokens = [token for token in compact.split() if len(token) >= 3]
    average_conf = sum(confidences) / len(confidences) if confidences else 0.0
    letter_or_digit = sum(ch.isalnum() for ch in compact)

    return (
        len(compact) >= 16
        and len(lines) >= 2
        and len(tokens) >= 3
        and letter_or_digit >= 12
        and average_conf >= 58.0
    )


def _read_single_orientation(img_bgr, min_conf=25, variant_index=2, psm="11"):
    # Use one well-preprocessed variant and one sparse-text mode. Running
    # multiple modes and thresholds on every frame was an order of magnitude
    # slower than the OCR result justified.
    variant = preprocess(img_bgr)[variant_index]
    tessdata_dir = getattr(config, "TESSDATA_DIR", None)
    tessdata_option = f"--tessdata-dir {str(tessdata_dir).replace(chr(92), '/')}" if tessdata_dir else ""
    data = pytesseract.image_to_data(
        variant,
        config=f"{tessdata_option} --oem 1 --psm {psm} -c preserve_interword_spaces=1",
        lang=OCR_LANGUAGES,
        output_type=Output.DICT,
        timeout=12,
    )
    grouped = {}
    confidences = []
    for i, (text, conf) in enumerate(zip(data["text"], data["conf"])):
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            continue
        clean = _clean_word(text)
        letter_count = sum(ch.isalpha() for ch in clean)
        digit_count = sum(ch.isdigit() for ch in clean)
        usable = (
            len(clean) >= 2
            and conf >= min_conf
            and (letter_count >= 2 or digit_count >= 3)
        )
        if usable:
            line_key = (
                data["block_num"][i],
                data["par_num"][i],
                data["line_num"][i],
            )
            grouped.setdefault(line_key, []).append(
                (int(data["left"][i]), clean, conf)
            )
            confidences.append(conf)

    lines = []
    line_confidences = []
    for line_words in grouped.values():
        line_words.sort(key=lambda item: item[0])
        line = " ".join(word for _, word, _ in line_words)
        line = re.sub(r"\s+", " ", line).strip()
        if line and line not in lines:
            lines.append(line)
            line_confidences.extend(conf for _, _, conf in line_words)
    return lines, line_confidences


def ocr_image(img_bgr, min_conf=45, try_orientations=False):
    """OCR an image; videos use the upright fast path."""
    try:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        upright = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        if not try_orientations:
            best_words, confidences = _read_single_orientation(upright, min_conf=max(min_conf, 55))
        else:
            rotations = (
                ("0", upright),
                ("90", cv2.rotate(upright, cv2.ROTATE_90_CLOCKWISE)),
                ("180", cv2.rotate(upright, cv2.ROTATE_180)),
                ("270", cv2.rotate(upright, cv2.ROTATE_90_COUNTERCLOCKWISE)),
            )
            best_words = []
            best_score = -1.0
            confidences = []
            for _, rotated in rotations:
                words, current_confidences = _read_single_orientation(
                    rotated,
                    min_conf=max(min_conf, 55),
                )
                score = _line_quality(words, current_confidences)
                if score > best_score:
                    best_score = score
                    best_words = words
                    confidences = current_confidences
    except (pytesseract.TesseractNotFoundError, FileNotFoundError):
        return {"available": False, "text": ""}

    if not _has_reliable_text(best_words, confidences):
        return {"available": True, "text": ""}
    return {"available": True, "text": " ".join(best_words)}


def find_dates_in_text(text):
    """Extract complete dates (day, month, year) and ignore standalone 4-digit numbers."""
    if not text.strip():
        return []
    found = search_dates(
        text,
        languages=["en"],
        settings={
            "STRICT_PARSING": True,
            "PREFER_DATES_FROM": "past",
            "DATE_ORDER": "DMY",
        },
    ) or []

    results = []
    for s, d in found:
        clean_s = s.strip()
        if len(clean_s) >= 6 and YEAR.search(clean_s) and DATE_SEP.search(clean_s):
            results.append({"text": clean_s, "date": d.date().isoformat()})
    return results


def frame_sharpness(frame_bgr):
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def redact_sensitive_text(text):
    """Mask Aadhaar, VID, mobile and PIN-like identity numbers."""
    text = re.sub(
        r"\b\d{4}\s*\d{4}\s*\d{4}\b",
        lambda m: "XXXX XXXX " + re.sub(r"\D", "", m.group(0))[-4:],
        text,
    )
    text = re.sub(
        r"\b\d{4}\s*\d{4}\s*\d{4}\s*\d{4}\b",
        lambda m: "XXXX XXXX XXXX " + re.sub(r"\D", "", m.group(0))[-4:],
        text,
    )
    text = re.sub(r"\b[6-9]\d{9}\b", lambda m: "XXXXX" + m.group(0)[-5:], text)
    return text


def extract_identity_fields(text):
    fields = {}
    compact = re.sub(r"\s+", " ", text)

    dob_match = re.search(r"\b(?:DOB|D\.O\.B\.?|Date of birth)\s*[:\-]?\s*(\d{2}[\/\-.]\d{2}[\/\-.]\d{4})", compact, re.I)
    if dob_match:
        fields["dob"] = dob_match.group(1)

    gender_match = re.search(r"\b(MALE|FEMALE|OTHER)\b", compact, re.I)
    if gender_match:
        fields["gender"] = gender_match.group(1).upper()

    aadhaar_match = re.search(r"\b\d{4}\s*\d{4}\s*\d{4}\b", compact)
    if aadhaar_match:
        digits = re.sub(r"\D", "", aadhaar_match.group(0))
        fields["aadhaar"] = "XXXX XXXX " + digits[-4:]

    vid_match = re.search(r"\b\d{4}\s*\d{4}\s*\d{4}\s*\d{4}\b", compact)
    if vid_match:
        digits = re.sub(r"\D", "", vid_match.group(0))
        fields["vid"] = "XXXX XXXX XXXX " + digits[-4:]

    name_match = re.search(
        r"\b(?:Name|Name of)\s*[:\-]\s*([A-Za-z][A-Za-z .]{2,50})",
        compact,
        re.I,
    )
    if not name_match:
        name_match = re.search(
            r"\b([A-Z][a-z]+(?: [A-Z][a-z]+){1,3})\b\s+(?:wer\s+)?DOB\b",
            compact,
        )
    if not name_match:
        name_match = re.search(
            r"\b([A-Z][a-z]+(?: [A-Z][a-z]+){1,3})\b",
            compact,
        )
    if name_match:
        fields["name"] = re.sub(r"\s{2,}", " ", name_match.group(1).strip())

    return fields


def ocr_media(path, media_type, frames=None, max_frames=None):
    """OCR an image, or evenly spaced frames of a video."""
    if max_frames is None:
        max_frames = getattr(config, "OCR_MAX_FRAMES", 20)
    if media_type == "image":
        try:
            imgs = [load_oriented_bgr(str(path))]
        except Exception:
            imgs = [cv2.imread(str(path))]
    else:
        if frames is None:
            from services.video import sample_frames
            frames = sample_frames(
                path,
                getattr(config, "OCR_FRAME_INTERVAL_S", 0.5),
                config.MAX_FRAMES,
            )
        sharpest = sorted(
            frames,
            key=lambda item: frame_sharpness(item[2]),
            reverse=True,
        )
        imgs = [frame for _, _, frame in sharpest[:max_frames]]

    seen, parts, available = set(), [], True
    for img in imgs:
        if img is None:
            continue
        r = ocr_image(img, try_orientations=(media_type == "image"))
        available = available and r["available"]
        if r["text"]:
            normalized = re.sub(r"\s+", " ", r["text"]).strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                parts.append(r["text"])

    text = redact_sensitive_text("\n".join(parts))
    return {
        "available": available,
        "text": text,
        "dates": find_dates_in_text(text),
        "fields": extract_identity_fields(text),
    }
