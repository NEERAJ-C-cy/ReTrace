# ReTrace

**AI-Assisted Digital Media Traceability and Context Verification System**

*Trace it before you trust it.*

ReTrace finds earlier appearances of an image or video and checks whether the story attached to it (date, place, event) matches the evidence. It never says "fake" or "real". It reports what it found, how strong the evidence is, and where its limits are.

Built for **wHACKiest 2026** (Ramaiah Institute of Technology, online ideathon, 26–27 Nov 2026).

---

## The problem

Authentic photos and videos are often reposted with a false caption, date or location. The media is genuine, so deepfake detectors cannot catch it. In a study of Indian political WhatsApp groups, about 34% of misinformation images were old images taken out of context and reshared (Garimella & Eckles, *Harvard Misinformation Review*, 2020).

Existing tools each cover one step (reverse image search, metadata viewers, keyframe tools). None compares the caption against the earlier context or keeps a repeatable record.

## What ReTrace does

1. **Validates** the upload (extension, real file signature, size, decodes cleanly).
2. **Fingerprints** it with perceptual hashes (pHash, dHash, aHash). For video, one frame per second is hashed.
3. **Searches** a local historical-media database using Hamming distance. Distance ≤ 4 is a near-duplicate, ≤ 10 is similar.
4. **Extracts** visible text (OCR) and file metadata (EXIF), treated as claims, not proof.
5. **Parses the caption** for dates, places and events.
6. **Verifies** claims against the matched item's recorded context using explainable rules.
7. **Reports** one verdict with evidence, reasoning and confidence limits (HTML, printable to PDF).

### Verdicts

| Verdict | Meaning |
|---|---|
| Insufficient Evidence | No usable match or nothing comparable |
| Historical Media Match Found | An earlier appearance exists, no claim to compare |
| Potential Context Misuse | Earlier appearance conflicts with the claim |
| Context Inconsistent | Clear contradiction in date, place or event |
| Context Consistent with Available Evidence | No contradiction found (this is not proof of truth) |

## Scope

**In scope:** images (JPG, PNG, WEBP), short videos (MP4, MOV, AVI, MKV), a curated local database of 50–200 items, perceptual-hash matching, OCR, EXIF, rule-based caption parsing, exportable report.

**Out of scope:** deepfake or edit detection, crawling the internet, deciding that a claim is true or false, audio analysis.

## Tech stack

| Layer | Tools |
|---|---|
| Frontend | Jinja2, HTML, CSS, JS |
| Backend | Python 3.10+, Flask |
| Matching | OpenCV, ImageHash, NumPy |
| Database | MySQL 8 (PyMySQL) |
| OCR and metadata | Tesseract (pytesseract), Pillow |
| Claim parsing | dateparser, place gazetteer |

Free, open source, CPU-only. Runs on an 8 GB laptop with no GPU and no cloud service.

## Architecture

```
Upload -> Validate -> Fingerprint -> Match + Extract -> Verify -> Verdict + Report

Presentation (HTML/JS)  ->  Flask routes  ->  Services  ->  MySQL + file storage
                                              (validator, fingerprinter, frame extractor,
                                               OCR, metadata, caption parser,
                                               verifier, report builder)
```

## Getting started

### Prerequisites

- Python 3.10 or newer
- MySQL 8 running locally
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed and on your PATH

### Install

```bash
git clone <your-repo-url> retrace
cd retrace
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install flask pillow imagehash opencv-python-headless numpy \
            pytesseract dateparser pymysql jinja2
```

### Run

```bash
python app.py
```

Open <http://127.0.0.1:5000>, upload a file, add the caption, claimed date and location, and read the report.

### Add reference media

Seed the historical database with 50–200 labelled items (image, original date, place, event, source) through the admin page at `/admin` (local access only). Matches are only as good as this archive.

## Limitations

- Mirrored or heavily cropped copies can be missed by perceptual hashes.
- A small database means matches depend on what you seed.
- "Today" in a caption needs the real post date, otherwise a false date conflict can appear.
- An unknown place gives a warning, never a conflict.
- Visual similarity is a lead, not proof.

## Ethics and security

- Runs locally by default. No face recognition and no scraping.
- Uploads are never executed, are stored under random names and are size-capped.
- Prefers precision over recall, and says "Insufficient Evidence" when it should.

## Roadmap

- **Now:** local tool with a curated archive.
- **Next:** shared team archive, CLIP-style embeddings, mirrored-upload matching.
- **Later:** API, browser extension, optional external reverse-search adapter.

## Team: The Alters

| Member | Role | Owns |
|---|---|---|
| **Neeraj Yadav** (Lead) | AI/ML | Perceptual hashing (pHash, dHash, aHash), Hamming-distance matching, verifier and verdict logic, Flask pipeline, overall architecture |
| **Priyanshi Dhakad** | Data mining and research | Curating the 50–200 item historical database, sourcing and labelling dates, places and events, gazetteer and event keyword lists, test cases and evaluation set |
| **Abhisek Malviya** | Social search and bug fixing | Social-media and optional external reverse-search adapter, upload validation and security checks, admin page, testing, bug triage and fixes |
| **Neelaabh Sharma** | Data preprocessing and searching | Image and video preprocessing, frame extraction, OCR and EXIF extraction, caption parsing, loading and querying hashes in MySQL |



## References

- Garimella, K. & Eckles, D. (2020). [Images and Misinformation in Political Groups: Evidence from WhatsApp in India](https://misinforeview.hks.harvard.edu/article/images-and-misinformation-in-political-groups-evidence-from-whatsapp-in-india/). *Harvard Misinformation Review*.
