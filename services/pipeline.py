import json
import threading
import config
import db
from services.fingerprint import fingerprints_for
from services.search import HashIndex, search
from services.ocr import ocr_media
from services.metadata import extract_metadata
from services.claims import Gazetteer, parse_claims
from services.verifier import verify
from services.external import external_search

GAZ = Gazetteer(config.BASE / "dataset" / "gazetteer.csv")
PROGRESS = {}  # case_id -> {"stage": text, "percent": number}; one process only


def _set(case_id, stage, percent):
    PROGRESS[case_id] = {"stage": stage, "percent": percent}


def run_pipeline(case_id):
    conn, cur = db.get_conn()  # each thread needs its own connection
    if conn is None or cur is None:
        _set(case_id, "Error: Database connection failed", 100)
        return

    try:
        cur.execute("UPDATE cases SET status='running' WHERE id=%s", (case_id,))
        conn.commit()

        cur.execute("SELECT * FROM cases WHERE id=%s", (case_id,))
        case = cur.fetchone()
        path, kind = case["upload_path"], case["media_type"]

        _set(case_id, "Fingerprinting media", 15)
        prints = fingerprints_for(path, kind)

        _set(case_id, "Searching historical database", 35)
        matches = search(HashIndex((conn, cur)), prints)

        hist = {}
        for m in matches:
            cur.execute("SELECT * FROM historical_media WHERE id=%s", (m["media_id"],))
            hist[m["media_id"]] = cur.fetchone()

        _set(case_id, "Reading text and metadata", 55)
        ocr = ocr_media(path, kind)
        meta = extract_metadata(path, kind)

        _set(case_id, "Analysing caption", 70)
        claims = parse_claims(
            GAZ,
            case["caption"] or "",
            case["claimed_date"] or "",
            case["claimed_location"] or "",
            case["claimed_event"] or "",
            case["post_date"] or "",
        )

        _set(case_id, "Comparing claim with evidence", 85)
        verdict, findings, ref = verify(claims, matches, hist, ocr, GAZ)
        external = external_search(path) if getattr(config, "ENABLE_EXTERNAL", False) else []

        for m in matches:
            cur.execute(
                """INSERT INTO case_matches
                   (case_id, media_id, similarity, distance, matched_frames, total_frames, match_type)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    case_id,
                    m["media_id"],
                    m["similarity"],
                    m["distance"],
                    m["matched_frames"],
                    m["total_frames"],
                    m["match_type"],
                ),
            )

        for f in findings:
            cur.execute(
                """INSERT INTO case_findings (case_id, finding_type, severity, detail)
                   VALUES (%s, %s, %s, %s)""",
                (case_id, f["finding_type"], f["severity"], f["detail"]),
            )

        cur.execute(
            """UPDATE cases
               SET ocr_text=%s, metadata_json=%s, verdict=%s, verdict_reasons=%s, status='done'
               WHERE id=%s""",
            (
                ocr["text"],
                json.dumps(
                    {
                        "metadata": meta,
                        "claims": claims,
                        "ocr_dates": ocr["dates"],
                        "ocr_fields": ocr["fields"],
                        "external": external,
                    }
                ),
                verdict,
                f"reference_media_id={ref['media_id']}" if ref else "",
                case_id,
            ),
        )
        conn.commit()
        _set(case_id, "Done", 100)

    except Exception as e:  # never leave a case stuck in 'running'
        cur.execute(
            "UPDATE cases SET status='error', verdict_reasons=%s WHERE id=%s",
            (str(e), case_id),
        )
        conn.commit()
        _set(case_id, f"Error: {e}", 100)
    finally:
        cur.close()
        conn.close()


def start_async(case_id):
    threading.Thread(target=run_pipeline, args=(case_id,), daemon=True).start()
