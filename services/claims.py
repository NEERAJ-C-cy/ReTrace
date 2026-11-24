import csv
import re
from datetime import datetime
from dateparser.search import search_dates

EVENT_KEYWORDS = {
    "flood": ["flood", "flooding", "inundat", "waterlogg", "submerged"],
    "protest": ["protest", "rally", "demonstrat", "agitation", "procession"],
    "raid": ["raid", "police operation", "crackdown", "arrest"],
    "earthquake": ["earthquake", "quake", "tremor"],
    "fire": ["fire", "blaze"],
    "accident": ["accident", "crash", "collision"],
}


def event_types(text):
    low = (text or "").lower()
    return [
        ev for ev, words in EVENT_KEYWORDS.items()
        if any(re.search(r"\b" + w, low) for w in words)
    ]


class Gazetteer:
    def __init__(self, path):
        self.parent = {}
        self.patterns = []  # (canonical name, compiled regex)
        with open(path, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                name = row["name"].strip()
                self.parent[name.lower()] = (row["parent"] or "").strip()
                aliases = [a for a in (row["aliases"] or "").split("|") if a]
                for alias in [name] + aliases:
                    # short ALL-CAPS aliases (US, UK) are case-sensitive so 'us' does not match
                    flags = 0 if (alias.isupper() and len(alias) <= 3) else re.IGNORECASE
                    self.patterns.append(
                        (name, re.compile(r"\b" + re.escape(alias) + r"\b", flags))
                    )

    def find_places(self, text):
        found = []
        for name, pat in self.patterns:
            if pat.search(text or "") and name not in found:
                found.append(name)
        return found

    def canonical(self, text):
        for name, pat in self.patterns:
            if pat.fullmatch((text or "").strip()):
                return name
        return (text or "").strip()  # unknown place: keep as typed

    def chain(self, text):
        """A place and all its parents, e.g. Mumbai -> [Mumbai, Maharashtra, India]."""
        cur, out = self.canonical(text), []
        while cur and cur not in out:
            out.append(cur)
            cur = self.parent.get(cur.lower(), "")
        return out


def _to_dt(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def parse_claims(
    gaz,
    caption="",
    claimed_date="",
    claimed_location="",
    claimed_event="",
    post_date="",
):
    text = " ".join(x for x in (caption, claimed_event) if x)
    base = _to_dt(post_date) or datetime.now()

    date_value, date_source = None, None
    if claimed_date:  # the form field wins
        date_value, date_source = claimed_date, "form"
    elif text.strip():
        found = search_dates(
            text,
            languages=["en"],
             settings={
                "RELATIVE_BASE": base,
                "PREFER_DATES_FROM": "past",
                "STRICT_PARSING": True,  # अधूरे नंबरों या 'may' जैसे शब्दों को तारीख़ बनने से रोकता है
                "DATE_ORDER": "DMY",
            },)
           
        if found:
            date_value = found[0][1].date().isoformat()
            date_source = f"caption: '{found[0][0]}'"

    if claimed_location.strip():
        places, place_source = [gaz.canonical(claimed_location)], "form"
    else:
        places, place_source = gaz.find_places(text), "caption"

    return {
        "caption": caption,
        "date": date_value,
        "date_source": date_source,
        "places": places,
        "place_source": place_source,
        "events": event_types(text),
    }
