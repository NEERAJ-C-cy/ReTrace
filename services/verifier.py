from datetime import date
import config
from services.claims import event_types


def to_date(s):
    """'2019-08-03', '2019-08' or '2019' -> date, otherwise None."""
    if not s:
        return None
    parts = str(s).strip().split("-")
    try:
        return date(
            int(parts[0]),
            int(parts[1]) if len(parts) > 1 else 1,
            int(parts[2]) if len(parts) > 2 else 1,
        )
    except (ValueError, IndexError):
        return None


def finding(kind, severity, detail):
    # severity is one of: agree, info, warning, conflict
    return {"finding_type": kind, "severity": severity, "detail": detail}


def is_strong(match):
    """A strong match is a near-duplicate that covers enough of the upload."""
    ratio = match["matched_frames"] / max(match["total_frames"], 1)
    return (
        match["match_type"] in ("exact", "near-duplicate")
        and ratio >= config.STRONG_FRAME_RATIO
    )


def pick_reference(matches, hist_by_id):
    """Among strong matches use the earliest-dated one: earlier publication is the
    most informative evidence. Otherwise use the closest visual match."""
    pool = [m for m in matches if is_strong(m)] or matches[:1]
    dated = [
        m for m in pool
        if to_date(hist_by_id[m["media_id"]]["published_date"])
    ]
    if dated:
        return min(
            dated,
            key=lambda m: to_date(hist_by_id[m["media_id"]]["published_date"]),
        )
    return pool[0]


def compare_context(claims, hist, ocr, gaz):
    """Compare the claim with ONE historical item -> (findings, number_of_fields_compared)."""
    findings, compared = [], 0
    tol = config.DATE_TOLERANCE_DAYS

    # 1) DATE: the media cannot show an event that happened after it was published
    claimed = to_date(claims.get("date"))
    ref_date = to_date(hist["event_date"]) or to_date(hist["published_date"])
    if claimed and ref_date:
        compared += 1
        gap = (claimed - ref_date).days
        if gap > tol:
            findings.append(
                finding(
                    "date_conflict",
                    "conflict",
                    f"Claimed date {claimed} is {gap} days after the matched item's recorded date "
                    f"({ref_date}). The media existed before the event it is said to show.",
                )
            )
        elif gap < -tol:
            findings.append(
                finding(
                    "date_info",
                    "info",
                    f"Claimed date {claimed} is earlier than the matched item's date ({ref_date}). "
                    "Our database copy may not be the first publication, so this is not a conflict.",
                )
            )
        else:
            findings.append(
                finding(
                    "date_agree",
                    "agree",
                    f"Claimed date {claimed} agrees with the matched item's date ({ref_date}).",
                )
            )

    # 2) PLACE: compare using the place hierarchy (Mumbai is inside Maharashtra, inside India)
    claimed_places = claims.get("places") or []
    hist_loc = hist["location_text"] or hist["country"]
    if claimed_places and hist_loc:
        compared += 1
        hist_chain = set(gaz.chain(hist_loc)) | set(gaz.chain(hist["country"] or ""))
        hist_canon = gaz.canonical(hist_loc)
        same_or_broader = any(gaz.canonical(p) in hist_chain for p in claimed_places)
        more_specific = any(hist_canon in gaz.chain(p) for p in claimed_places)
        all_known = (
            hist_loc.lower() in gaz.parent
            and all(p.lower() in gaz.parent for p in claimed_places)
        )
        names = ", ".join(claimed_places)
        if same_or_broader:
            findings.append(
                finding(
                    "place_agree",
                    "agree",
                    f"Claimed place ({names}) is consistent with the matched item's location ({hist_loc}).",
                )
            )
        elif more_specific:
            findings.append(
                finding(
                    "place_info",
                    "info",
                    f"Claimed place ({names}) is more specific than the matched item's location ({hist_loc}); "
                    "it cannot be confirmed or contradicted.",
                )
            )
        elif all_known:
            findings.append(
                finding(
                    "place_conflict",
                    "conflict",
                    f"Claimed place ({names}) differs from the matched item's recorded location ({hist_loc}).",
                )
            )
        else:
            findings.append(
                finding(
                    "place_unknown",
                    "warning",
                    f"Places ({names} vs {hist_loc}) are not all in the gazetteer, so they could not be "
                    "compared reliably. Add them to gazetteer.csv.",
                )
            )

    # 3) EVENT TYPE
    claimed_events = set(claims.get("events") or [])
    hist_events = set(
        event_types(f"{hist['title'] or ''} {hist['description'] or ''}")
    )
    if claimed_events and hist_events:
        compared += 1
        if claimed_events & hist_events:
            findings.append(
                finding(
                    "event_agree",
                    "agree",
                    f"Claimed event type ({', '.join(sorted(claimed_events))}) matches the matched item.",
                )
            )
        else:
            findings.append(
                finding(
                    "event_conflict",
                    "conflict",
                    f"Claimed event type ({', '.join(sorted(claimed_events))}) differs from the matched "
                    f"item ({', '.join(sorted(hist_events))}).",
                )
            )

    # 4) OCR text inside the media (a weak signal: overlays can be anything)
    if claimed:
        for d in ocr.get("dates", []):
            shown = to_date(d["date"])
            if shown and (claimed - shown).days > tol:
                compared += 1
                findings.append(
                    finding(
                        "ocr_date",
                        "warning",
                        f"Text visible in the media mentions {d['text']!r} ({shown}), earlier than "
                        f"the claimed date {claimed}.",
                    )
                )
                break

    return findings, compared


def verify(claims, matches, hist_by_id, ocr, gaz):
    """Return (verdict, findings, reference_match)."""
    if not matches:
        return (
            "Insufficient Evidence",
            [
                finding(
                    "no_match",
                    "info",
                    "No historical item passed the similarity threshold. This does not mean the media is "
                    "new; it only means our database has no similar item.",
                )
            ],
            None,
        )

    ref = pick_reference(matches, hist_by_id)
    findings, compared = compare_context(claims, hist_by_id[ref["media_id"]], ocr, gaz)
    strong = is_strong(ref)
    conflicts = [f for f in findings if f["severity"] == "conflict"]
    has_claim = bool(
        claims.get("date") or claims.get("places") or claims.get("events")
    )

    if conflicts and strong:
        verdict = "Potential Context Misuse"
    elif conflicts:
        verdict = "Context Inconsistent"
        findings.append(
            finding(
                "weak_match",
                "info",
                "The visual match is weak, so these conflicts may not apply to this media.",
            )
        )
    elif not strong:
        verdict = "Insufficient Evidence"
        findings.append(
            finding(
                "weak_match",
                "info",
                "Only a loose visual similarity was found, which is not enough to compare context.",
            )
        )
    elif has_claim and compared > 0:
        verdict = "Context Consistent with Available Evidence"
    else:
        verdict = "Historical Media Match Found"

    return verdict, findings, ref
