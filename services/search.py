import numpy as np
import config


def popcount64(arr):
    """Count the 1-bits in every uint64 of arr."""
    as_bytes = arr.view(np.uint8).reshape(-1, 8)
    return np.unpackbits(as_bytes, axis=1).sum(axis=1)


class HashIndex:
    """All stored fingerprints held in memory as integer arrays."""

    def __init__(self, conn_or_cursor):
        # Support passing either a MySQL cursor or a (conn, cursor) tuple
        if isinstance(conn_or_cursor, tuple):
            _, cur = conn_or_cursor
        elif hasattr(conn_or_cursor, "cursor"):
            cur = conn_or_cursor.cursor(dictionary=True)
        else:
            cur = conn_or_cursor

        cur.execute("SELECT media_id, phash, dhash FROM fingerprints")
        rows = cur.fetchall()

        self.media_ids = np.array([r["media_id"] for r in rows], dtype=np.int64)
        self.p = np.array([int(r["phash"], 16) for r in rows], dtype=np.uint64)
        self.d = np.array([int(r["dhash"], 16) for r in rows], dtype=np.uint64)

    def __len__(self):
        return len(self.media_ids)

    def distances(self, phash_hex, dhash_hex):
        """Average of pHash and dHash Hamming distance to every stored fingerprint."""
        dp = popcount64(self.p ^ np.uint64(int(phash_hex, 16)))  # XOR then count
        dd = popcount64(self.d ^ np.uint64(int(dhash_hex, 16)))
        return (dp + dd) / 2.0

    def distances_for_orientations(self, variants):
        """Minimum average distance over one or more query orientations."""
        result = None
        for variant in variants:
            dist = self.distances(variant["phash"], variant["dhash"])
            result = dist if result is None else np.minimum(result, dist)
        return result


def search(index, query_prints, max_dist=None, top_k=None):
    """Find top matching historical media IDs across one or more query frames."""
    max_dist = config.SIMILAR_MAX if max_dist is None else max_dist
    top_k = top_k or config.TOP_K

    if len(index) == 0 or not query_prints:
        return []

    # A frame at a source timestamp can have up to four orientation variants.
    grouped = {}
    ungrouped = []
    oriented_ungrouped = []
    for q in query_prints:
        if "frame_index" in q:
            key = (q["frame_index"], q.get("timestamp_s", 0.0))
            grouped.setdefault(key, []).append(q)
        elif "orientation" in q:
            oriented_ungrouped.append(q)
        else:
            ungrouped.append([q])

    query_groups = list(grouped.values())
    if oriented_ungrouped:
        query_groups.append(oriented_ungrouped)
    query_groups.extend(ungrouped)
    total_frames = len(query_groups)
    best = {}  # media_id -> {"best": smallest distance, "frames": set of query frames}

    for qi, variants in enumerate(query_groups):
        if hasattr(index, "distances_for_orientations"):
            dist = index.distances_for_orientations(variants)
        else:
            dist = None
            for q in variants:
                current = index.distances(q["phash"], q["dhash"])
                dist = current if dist is None else np.minimum(dist, current)
        for pos in np.where(dist <= max_dist)[0]:
            mid = int(index.media_ids[pos])
            d_val = float(dist[pos])

            if mid not in best:
                best[mid] = {"media_id": mid, "best": d_val, "frames": {qi}}
            else:
                if d_val < best[mid]["best"]:
                    best[mid]["best"] = d_val
                best[mid]["frames"].add(qi)

    # Sort matches by lowest Hamming distance first, then by highest frame hit count
    results = sorted(
        best.values(),
        key=lambda item: (item["best"], -len(item["frames"]))
    )

    exact_max = getattr(config, "EXACT_MAX", 2)
    near_dup_max = getattr(config, "NEAR_DUP_MAX", 8)

    for r in results:
        d_val = r["best"]
        r["distance"] = round(d_val, 2)
        r["similarity"] = round(max(0.0, 1.0 - (d_val / 64.0)), 4)
        r["matched_frames"] = len(r["frames"])
        r["total_frames"] = total_frames
        r["frames"] = sorted(r["frames"])
        if d_val <= exact_max:
            r["match_type"] = "exact"
        elif d_val <= near_dup_max:
            r["match_type"] = "near-duplicate"
        else:
            r["match_type"] = "similar"

    return results[:top_k]
