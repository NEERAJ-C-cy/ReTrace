import mysql.connector
import hashlib
import config


def get_conn():
    """
    Create and return a MySQL connection and dictionary cursor.
    """
    try:
        conn = mysql.connector.connect(
            host="localhost",
            port=3306,
            user="root",
            password="2007",
            database="fact_check_db"
        )
        cursor = conn.cursor(dictionary=True)
        return conn, cursor

    except mysql.connector.Error as e:
        print(f"MySQL connection error: {e}")
        return None, None


def init_db():
    """
    Create all required tables if they do not already exist.
    """
    conn, cursor = get_conn()
    if conn is None or cursor is None:
        return

    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cases (
                id INT AUTO_INCREMENT PRIMARY KEY,
                upload_path TEXT NOT NULL,
                original_name VARCHAR(255),
                sha256 CHAR(64) NOT NULL,
                media_type VARCHAR(50) NOT NULL,
                caption TEXT,
                claimed_date VARCHAR(100),
                claimed_location VARCHAR(255),
                claimed_event VARCHAR(255),
                post_date VARCHAR(100),
                ocr_text TEXT,
                metadata_json JSON,
                verdict VARCHAR(100),
                verdict_reasons TEXT,
                status VARCHAR(20) DEFAULT 'queued',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historical_media (
                id INT AUTO_INCREMENT PRIMARY KEY,
                file_path VARCHAR(255) NOT NULL UNIQUE,
                sha256 CHAR(64),
                media_type VARCHAR(50) NOT NULL,
                title VARCHAR(255),
                source_name VARCHAR(255),
                source_url TEXT,
                published_date VARCHAR(100),
                event_date VARCHAR(100),
                location_text VARCHAR(255),
                country VARCHAR(100),
                description TEXT,
                license_note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("SHOW COLUMNS FROM historical_media")
        historical_columns = {row["Field"] for row in cursor.fetchall()}
        if "sha256" not in historical_columns:
            cursor.execute(
                "ALTER TABLE historical_media ADD COLUMN sha256 CHAR(64) NULL AFTER file_path"
            )

        cursor.execute("SHOW INDEX FROM historical_media")
        historical_indexes = {row["Key_name"] for row in cursor.fetchall()}
        if "historical_sha_unique" not in historical_indexes:
            cursor.execute(
                "CREATE UNIQUE INDEX historical_sha_unique "
                "ON historical_media (sha256)"
            )

        cursor.execute(
            "SELECT id, file_path FROM historical_media WHERE sha256 IS NULL"
        )
        missing_hashes = cursor.fetchall()
        for item in missing_hashes:
            media_path = config.HISTORICAL / item["file_path"]
            if media_path.is_file():
                digest = hashlib.sha256(media_path.read_bytes()).hexdigest()
                cursor.execute(
                    "UPDATE historical_media SET sha256=%s WHERE id=%s",
                    (digest, item["id"]),
                )

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fingerprints (
                id INT AUTO_INCREMENT PRIMARY KEY,
                media_id INT NOT NULL,
                frame_index INT DEFAULT 0,
                timestamp_s FLOAT DEFAULT 0.0,
                phash CHAR(64),
                dhash CHAR(64),
                ahash CHAR(64),
                FOREIGN KEY (media_id) REFERENCES historical_media(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS case_matches (
                id INT AUTO_INCREMENT PRIMARY KEY,
                case_id INT NOT NULL,
                media_id INT NOT NULL,
                similarity DOUBLE NOT NULL,
                distance DOUBLE,
                matched_frames INT DEFAULT 1,
                total_frames INT DEFAULT 1,
                match_type VARCHAR(64),
                FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
                FOREIGN KEY (media_id) REFERENCES historical_media(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS case_findings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                case_id INT NOT NULL,
                finding_type VARCHAR(100),
                severity VARCHAR(50),
                detail TEXT,
                FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
            )
        """)

        conn.commit()
    finally:
        cursor.close()
        conn.close()
