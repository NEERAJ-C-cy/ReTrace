import csv
import hashlib
import shutil
from pathlib import Path
import sys

# Ensure the root project directory is in Python's path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config
import db
from services.fingerprint import fingerprints_for


CSV_PATH = ROOT_DIR / "dataset" / "historical.csv"
SRC_DIR = ROOT_DIR / "dataset"


def main():
    db.init_db()
    conn, cur = db.get_conn()
    if conn is None or cur is None:
        print("Failed to connect to MySQL.")
        return

    added = 0
    prints = 0

    try:
        config.HISTORICAL.mkdir(parents=True, exist_ok=True)

        with open(CSV_PATH, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                cur.execute(
                    "SELECT id FROM historical_media WHERE file_path = %s",
                    (row["file"],)
                )
                if cur.fetchone():
                    continue  # safe to run twice

                dest = config.HISTORICAL / row["file"]
                shutil.copy2(SRC_DIR / row["file"], dest)
                sha256 = hashlib.sha256(dest.read_bytes()).hexdigest()

                cur.execute(
                    """INSERT INTO historical_media (
                        file_path, sha256, media_type, title, source_name,
                        source_url, published_date, event_date, location_text,
                        country, description, license_note
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        row["file"], sha256, row["type"], row["title"], row["source_name"],
                        row["source_url"], row["published_date"], row["event_date"],
                        row["location"], row["country"], row["description"], row["license"]
                    )
                )
                media_id = cur.lastrowid

                for fp in fingerprints_for(dest, row["type"]):
                    cur.execute(
                        """INSERT INTO fingerprints (
                            media_id, frame_index, timestamp_s,
                            phash, dhash, ahash
                        ) VALUES (%s, %s, %s, %s, %s, %s)""",
                        (
                            media_id, fp["frame_index"], fp["timestamp_s"],
                            fp["phash"], fp["dhash"], fp["ahash"]
                        )
                    )
                    prints += 1

                added += 1

        conn.commit()
        print(f"Added {added} items, {prints} fingerprints.")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
