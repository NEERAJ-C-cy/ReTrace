import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from services.claims import Gazetteer, parse_claims
from services.verifier import verify

gaz = Gazetteer(config.BASE / "dataset" / "gazetteer.csv")

hist = {
    1: {
        "published_date": "2019-08-12",
        "event_date": "2019-08-10",
        "location_text": "Kolhapur",
        "country": "India",
        "title": "River flooding in a town",
        "description": "Flooded street",
    }
}

matches = [
    {
        "media_id": 1,
        "distance": 2.0,
        "similarity": 0.9688,
        "matched_frames": 1,
        "total_frames": 1,
        "match_type": "near-duplicate",
    }
]

claims = parse_claims(gaz, caption="Flood in Pune today", post_date="2026-11-01")
verdict, findings, ref = verify(claims, matches, hist, {"dates": [], "text": ""}, gaz)

print(verdict)
for f in findings:
    print(" ", f["severity"], f["finding_type"], "-", f["detail"])
