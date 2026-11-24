import json
from pathlib import Path

LIMITATIONS = [
    "Visual similarity does not prove the origin, authenticity or falsity of the media or of any claim.",
    "The historical database is small and incomplete. No match does not mean the media is new.",
    "Dates and places of historical items are only as reliable as their recorded sources.",
    "Metadata and on-screen text can be missing, removed or edited.",
    "'Consistent' means no contradiction was found in the available evidence. It does not confirm the claim.",
]

VERDICT_TEXT = {
    "Historical Media Match Found": (
        "A visually matching item exists in the historical database. "
        "No claim was supplied, or the stored context was too sparse to compare."
    ),
    "Potential Context Misuse": (
        "A strong visual match exists and the claim conflicts with the matched item's "
        "recorded date, place or event. Review the evidence before drawing conclusions."
    ),
    "Context Inconsistent": (
        "The claim conflicts with the matched item's context, but the visual match is weak, "
        "so the conflict may not apply."
    ),
    "Context Consistent with Available Evidence": (
        "A strong match exists and no contradiction was found in the fields that could be compared. "
        "This does not confirm the claim."
    ),
    "Insufficient Evidence": (
        "No strong match was found. This does not mean the media is new or that the claim is true."
    ),
}

MATCH_SQL = """
SELECT m.media_id, m.similarity, m.distance, m.matched_frames,
       m.total_frames, m.match_type,
       h.title, h.source_name, h.source_url, h.published_date, h.event_date,
       h.location_text, h.country, h.description, h.file_path, h.media_type AS hist_type
FROM case_matches m
JOIN historical_media h ON h.id = m.media_id
WHERE m.case_id = %s
ORDER BY m.similarity DESC
"""


def build_report(conn, case_id):
    conn, cur = conn
    cur.execute("SELECT * FROM cases WHERE id=%s", (case_id,))
    case = cur.fetchone()
    if case is None:
        return None

    reasons = case["verdict_reasons"] or ""
    raw_ref = reasons.split("=")[1] if reasons.startswith("reference_media_id=") else None
    ref_id = int(raw_ref) if raw_ref and raw_ref.isdigit() else raw_ref

    cur.execute(MATCH_SQL, (case_id,))
    matches = [dict(r) for r in cur.fetchall()]
    reference = None
    for m in matches:
        m["thumb_url"] = f"/media/historical/{m['file_path']}"
        m["is_reference"] = (m["media_id"] == ref_id)
        if m["is_reference"]:
            reference = m

    cur.execute(
        """SELECT * FROM case_findings WHERE case_id=%s ORDER BY
           CASE severity WHEN 'conflict' THEN 0 WHEN 'warning' THEN 1
           WHEN 'info' THEN 2 ELSE 3 END, id""",
        (case_id,),
    )
    findings = [dict(r) for r in cur.fetchall()]

    extra = json.loads(case["metadata_json"] or "{}")
    verdict = case["verdict"] or ""

    claims = extra.get("claims", {})
    events = []
    for m in matches:
        if m["published_date"]:
            events.append(
                {
                    "date": m["published_date"],
                    "kind": "history",
                    "label": f"Published: {m['title'] or 'untitled'} ({m['source_name'] or 'source not recorded'})",
                }
            )
        if m["event_date"]:
            events.append(
                {
                    "date": m["event_date"],
                    "kind": "history",
                    "label": f"Event date recorded for: {m['title'] or 'untitled'}",
                }
            )
    if claims.get("date"):
        events.append(
            {
                "date": claims["date"],
                "kind": "claim",
                "label": "Date claimed for this media",
            }
        )
    if case["post_date"]:
        events.append(
            {
                "date": case["post_date"],
                "kind": "post",
                "label": "Date the media was posted (as entered)",
            }
        )
    timeline = sorted(events, key=lambda e: e["date"])  # ISO dates sort correctly as text

    return {
        "case": dict(case),
        "upload_url": f"/media/upload/{Path(case['upload_path']).name}",
        "verdict_class": verdict.lower().replace(" ", "-"),
        "verdict_text": VERDICT_TEXT.get(verdict, ""),
        "matches": matches,
        "reference": reference,
        "findings": findings,
        "claims": claims,
        "timeline": timeline,
        "metadata": extra.get("metadata", {}),
        "ocr_dates": extra.get("ocr_dates", []),
        "ocr_fields": extra.get("ocr_fields", {}),
        "external": extra.get("external", []),
        "limitations": LIMITATIONS,
    }
