import os
from pathlib import Path
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    abort,
    send_from_directory,
)
import config
import db
from services.validator import validate_and_save, ValidationError
from services.fingerprint import fingerprints_for
from services.pipeline import start_async, PROGRESS
from services.report import build_report

app = Flask(__name__)
app.secret_key = os.environ.get("RETRACE_SECRET", "dev-only-change-me")
app.config["MAX_CONTENT_LENGTH"] = (config.MAX_VIDEO_MB + 5) * 1024 * 1024
db.init_db()


@app.errorhandler(413)
def too_large(e):
    flash("That file is too large.")
    return redirect(url_for("index"))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    f = request.files.get("media")
    if not f or not f.filename:
        flash("Please choose a file.")
        return redirect(url_for("index"))

    try:
        saved = validate_and_save(f)
    except ValidationError as e:
        flash(str(e))
        return redirect(url_for("index"))

    form = request.form
    conn, cur = db.get_conn()
    try:
        cur.execute(
            """INSERT INTO cases
               (upload_path, original_name, sha256, media_type, caption,
                claimed_date, claimed_location, claimed_event, post_date)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                str(saved["path"]),
                saved["original_name"],
                saved["sha256"],
                saved["media_type"],
                form.get("caption", "").strip(),
                form.get("claimed_date", ""),
                form.get("claimed_location", "").strip(),
                form.get("claimed_event", "").strip(),
                form.get("post_date", ""),
            ),
        )
        case_id = cur.lastrowid
        conn.commit()
    finally:
        cur.close()
        conn.close()

    start_async(case_id)
    return redirect(url_for("progress", case_id=case_id))


@app.route("/progress/<int:case_id>")
def progress(case_id):
    return render_template("progress.html", case_id=case_id)


@app.route("/api/cases/<int:case_id>/status")
def status(case_id):
    conn, cur = db.get_conn()
    try:
        cur.execute("SELECT status FROM cases WHERE id=%s", (case_id,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if row is None:
        abort(404)

    info = PROGRESS.get(case_id, {"stage": "Queued", "percent": 0})
    if row["status"] in ("done", "error"):
        info = {"stage": info.get("stage", "Done"), "percent": 100}
    return jsonify({"status": row["status"], **info})


@app.route("/report/<int:case_id>")
def report(case_id):
    conn, cur = db.get_conn()
    try:
        r = build_report((conn, cur), case_id)
    finally:
        cur.close()
        conn.close()

    if r is None:
        abort(404)
    return render_template("report.html", r=r)


@app.route("/history")
def history():
    conn, cur = db.get_conn()
    try:
        cur.execute(
            """SELECT id, original_name, media_type, verdict, status, created_at
               FROM cases ORDER BY id DESC LIMIT 200"""
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return render_template("history.html", cases=rows)


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.remote_addr not in ("127.0.0.1", "::1"):  # local use only (see Part 9)
        abort(403)

    if request.method == "POST":
        files = [f for f in request.files.getlist("media") if f and f.filename]
        if not files:
            flash("Please choose at least one file.")
            return redirect(url_for("admin"))

        form = request.form
        conn, cur = db.get_conn()
        if conn is None or cur is None:
            flash("Database unavailable.")
            return redirect(url_for("admin"))

        added = 0
        duplicate = 0
        failed = 0
        try:
            for f in files:
                try:
                    saved = validate_and_save(f, dest_dir=config.HISTORICAL)
                except ValidationError as e:
                    failed += 1
                    flash(f"{f.filename}: {e}")
                    continue

                cur.execute(
                    "SELECT id, title FROM historical_media WHERE sha256=%s",
                    (saved["sha256"],),
                )
                existing = cur.fetchone()
                if existing:
                    saved["path"].unlink(missing_ok=True)
                    duplicate += 1
                    existing_title = existing["title"] or f"existing item #{existing['id']}"
                    flash(f"{f.filename}: duplicate of {existing_title}")
                    continue

                shared_title = form.get("title", "").strip()
                title = shared_title or Path(f.filename).stem
                cur.execute(
                    """INSERT INTO historical_media
                       (file_path, sha256, media_type, title, source_name, source_url,
                        published_date, event_date, location_text, country,
                        description, license_note)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        saved["stored_name"],
                        saved["sha256"],
                        saved["media_type"],
                        title,
                        form.get("source_name", "").strip(),
                        form.get("source_url", "").strip(),
                        form.get("published_date", "").strip(),
                        form.get("event_date", "").strip(),
                        form.get("location", "").strip(),
                        form.get("country", "").strip(),
                        form.get("description", "").strip(),
                        form.get("license", "").strip(),
                    ),
                )
                mid = cur.lastrowid

                try:
                    for fp in fingerprints_for(saved["path"], saved["media_type"]):
                        cur.execute(
                            """INSERT INTO fingerprints
                               (media_id, frame_index, timestamp_s, phash, dhash, ahash)
                               VALUES (%s, %s, %s, %s, %s, %s)""",
                            (
                                mid,
                                fp["frame_index"],
                                fp["timestamp_s"],
                                fp["phash"],
                                fp["dhash"],
                                fp["ahash"],
                            ),
                        )
                except Exception as e:
                    cur.execute("DELETE FROM historical_media WHERE id=%s", (mid,))
                    saved["path"].unlink(missing_ok=True)
                    failed += 1
                    flash(f"{f.filename}: fingerprinting failed: {e}")
                    continue

                added += 1

            conn.commit()
            if added:
                suffix = "s" if added != 1 else ""
                flash(f"Added {added} item{suffix} and generated fingerprints.")
        finally:
            cur.close()
            conn.close()

        return redirect(url_for("admin"))

    conn, cur = db.get_conn()
    try:
        cur.execute(
            """SELECT id, title, media_type, published_date, location_text
               FROM historical_media ORDER BY id DESC LIMIT 100"""
        )
        items = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return render_template("admin.html", items=items)


@app.route("/media/<kind>/<name>")
def media(kind, name):
    folder = {"upload": config.UPLOADS, "historical": config.HISTORICAL}.get(kind)
    if folder is None:
        abort(404)
    return send_from_directory(folder, name)  # blocks path traversal for us


if __name__ == "__main__":
    app.run(debug=os.environ.get("RETRACE_DEBUG") == "1")
