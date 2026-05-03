import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")


def get_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS issues (
            id SERIAL PRIMARY KEY,
            item TEXT,
            location TEXT,
            photo_file_id TEXT,
            team TEXT,
            status TEXT,
            reported_by TEXT,
            description TEXT,
            assigned_to TEXT,
            created_at TEXT,
            user_id BIGINT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS status_history (
            id SERIAL PRIMARY KEY,
            issue_id INTEGER,
            status TEXT,
            changed_by TEXT,
            changed_at TEXT,
            reason TEXT
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON issues(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user ON issues(user_id)")

    conn.commit()
    conn.close()


def save_issue(item, location, photo_file_id, team, reported_by, user_id, description):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute("""
            INSERT INTO issues (
                item, location, photo_file_id, team, status,
                reported_by, description, assigned_to, created_at, user_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            item,
            location,
            photo_file_id,
            team,
            "New",
            reported_by,
            description,
            "Not assigned yet",
            datetime.utcnow().isoformat(),
            user_id,
        ))

        issue_id = cursor.fetchone()["id"]
        conn.commit()
        return issue_id

    except Exception as e:
        print("DB Error (save_issue):", e)
        return None

    finally:
        conn.close()


def get_issue_by_id(issue_id):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT * FROM issues WHERE id = %s
    """, (issue_id,))

    issue = cursor.fetchone()
    conn.close()
    return issue


def assign_issue(issue_id, technician_name):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE issues
            SET assigned_to = %s
            WHERE id = %s
        """, (technician_name, issue_id))

        conn.commit()

    except Exception as e:
        print("DB Error (assign_issue):", e)

    finally:
        conn.close()


def update_issue_status(issue_id, status, changed_by=None, reason=None):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE issues
            SET status = %s
            WHERE id = %s
        """, (status, issue_id))

        conn.commit()

    except Exception as e:
        print("DB Error (update_issue_status):", e)

    finally:
        conn.close()

    if changed_by:
        add_status_history(issue_id, status, changed_by, reason)


def get_all_issues():
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT * FROM issues ORDER BY id DESC
    """)

    issues = cursor.fetchall()
    conn.close()
    return issues


def add_status_history(issue_id, status, changed_by, reason=None):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO status_history (
                issue_id, status, changed_by, changed_at, reason
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (
            issue_id,
            status,
            changed_by,
            datetime.utcnow().isoformat(),
            reason,
        ))

        conn.commit()

    except Exception as e:
        print("DB Error (add_status_history):", e)

    finally:
        conn.close()


def get_status_history(issue_id):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT status, changed_by, changed_at, reason
        FROM status_history
        WHERE issue_id = %s
        ORDER BY id ASC
    """, (issue_id,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return "\nNo status updates yet."

    text = ""
    for row in rows:
        text += f"\n- {row['status']} by {row['changed_by']} at {row['changed_at']}"
        if row["reason"]:
            text += f"\n  Reason: {row['reason']}"

    return text


def get_issues_by_status(status):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT id, item, location, photo_file_id, team, reported_by, created_at
        FROM issues
        WHERE status = %s
        ORDER BY id DESC
    """, (status,))

    rows = cursor.fetchall()
    conn.close()
    return rows