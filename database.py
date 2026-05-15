import os
import time
import psycopg2
from psycopg2.extras import RealDictCursor

# =========================
# CONFIG
# =========================

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise EnvironmentError(
        "\n\n❌ DATABASE_URL is not set!\n"
        "Please set it in your environment variables.\n"
        "Example: postgresql://user:password@host:5432/dbname\n"
    )

# Fix for Railway/Render — they sometimes give 'postgres://' which psycopg2 doesn't accept
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


# =========================
# CONNECTION
# =========================

def get_connection(retries=5, delay=3):
    """
    Try to connect to the database with retries.
    Useful when the bot starts before the DB container is ready (Docker).
    """
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            return conn
        except psycopg2.OperationalError as e:
            last_error = e
            print(f"[DB] Connection attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                print(f"[DB] Retrying in {delay} seconds...")
                time.sleep(delay)
    raise ConnectionError(
        f"\n\n❌ Could not connect to the database after {retries} attempts.\n"
        f"Last error: {last_error}\n\n"
        f"Make sure:\n"
        f"  1. Your DATABASE_URL is correct: {DATABASE_URL[:40]}...\n"
        f"  2. PostgreSQL is running and reachable.\n"
        f"  3. If using Docker, the 'db' service is healthy before the bot starts.\n"
    )


# =========================
# DATABASE INITIALIZATION
# =========================

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # =========================
    # TICKETS TABLE
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id SERIAL PRIMARY KEY,

            category TEXT,
            item_name TEXT,
            asset_brand TEXT,

            location TEXT,
            issue_description TEXT,

            photo_file_id TEXT,

            status TEXT DEFAULT 'New',

            requester_name TEXT,
            requester_id BIGINT,

            assigned_to TEXT,

            final_diagnosis TEXT,
            rejection_reason TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Add rejection_reason column if it doesn't exist yet (safe migration)
    cursor.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'tickets' AND column_name = 'rejection_reason'
            ) THEN
                ALTER TABLE tickets ADD COLUMN rejection_reason TEXT;
            END IF;
        END$$;
    """)

    # =========================
    # TICKET UPDATES TABLE
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ticket_updates (
            id SERIAL PRIMARY KEY,

            ticket_id INTEGER REFERENCES tickets(id) ON DELETE CASCADE,

            old_status TEXT,
            new_status TEXT,

            updated_by TEXT,

            notes TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =========================
    # ASSETS TABLE
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            id SERIAL PRIMARY KEY,

            asset_type TEXT,
            brand TEXT,
            model TEXT,

            room TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =========================
    # INDEXES
    # =========================
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ticket_status
        ON tickets(status)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ticket_category
        ON tickets(category)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ticket_location
        ON tickets(location)
    """)

    conn.commit()
    conn.close()
    print("[DB] ✅ Database initialized successfully.")


# =========================
# CREATE TICKET
# =========================

def create_ticket(
    category,
    item_name,
    location,
    photo_file_id,
    requester_name,
    requester_id,
    issue_description,
    asset_brand=None
):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute("""
            INSERT INTO tickets (
                category,
                item_name,
                asset_brand,
                location,
                issue_description,
                photo_file_id,
                requester_name,
                requester_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            category,
            item_name,
            asset_brand,
            location,
            issue_description,
            photo_file_id,
            requester_name,
            requester_id
        ))

        ticket_id = cursor.fetchone()["id"]
        conn.commit()
        return ticket_id

    except Exception as e:
        print("DB ERROR [create_ticket]:", e)
        return None

    finally:
        conn.close()


# =========================
# GET TICKET
# =========================

def get_ticket(ticket_id):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute("""
            SELECT *
            FROM tickets
            WHERE id = %s
        """, (ticket_id,))

        return cursor.fetchone()

    except Exception as e:
        print("DB ERROR [get_ticket]:", e)
        return None

    finally:
        conn.close()


# =========================
# UPDATE STATUS
# =========================

def update_ticket_status(
    ticket_id,
    new_status,
    updated_by=None,
    notes=None
):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Get old status
        cursor.execute("""
            SELECT status FROM tickets WHERE id = %s
        """, (ticket_id,))

        row = cursor.fetchone()
        if not row:
            return False

        old_status = row["status"]

        # Update ticket status
        cursor.execute("""
            UPDATE tickets
            SET
                status = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (new_status, ticket_id))

        # If rejecting, also save the rejection reason
        if new_status == "Rejected" and notes:
            cursor.execute("""
                UPDATE tickets
                SET rejection_reason = %s
                WHERE id = %s
            """, (notes, ticket_id))

        # If fixing, also save the final diagnosis
        if new_status == "Fixed" and notes:
            cursor.execute("""
                UPDATE tickets
                SET final_diagnosis = %s
                WHERE id = %s
            """, (notes, ticket_id))

        # Log to history
        cursor.execute("""
            INSERT INTO ticket_updates (
                ticket_id,
                old_status,
                new_status,
                updated_by,
                notes
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (ticket_id, old_status, new_status, updated_by, notes))

        conn.commit()
        return True

    except Exception as e:
        print("DB ERROR [update_ticket_status]:", e)
        return False

    finally:
        conn.close()


# =========================
# ASSIGN TICKET
# =========================

def assign_ticket(ticket_id, technician_name):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE tickets
            SET
                assigned_to = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (technician_name, ticket_id))

        conn.commit()
        return True

    except Exception as e:
        print("DB ERROR [assign_ticket]:", e)
        return False

    finally:
        conn.close()


# =========================
# FINAL DIAGNOSIS
# =========================

def add_final_diagnosis(ticket_id, diagnosis):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE tickets
            SET
                final_diagnosis = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (diagnosis, ticket_id))

        conn.commit()
        return True

    except Exception as e:
        print("DB ERROR [add_final_diagnosis]:", e)
        return False

    finally:
        conn.close()


# =========================
# GET ALL TICKETS
# =========================

def get_all_tickets():
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute("""
            SELECT * FROM tickets ORDER BY id DESC
        """)
        return cursor.fetchall()

    except Exception as e:
        print("DB ERROR [get_all_tickets]:", e)
        return []

    finally:
        conn.close()


# =========================
# GET TICKETS BY STATUS
# =========================

def get_tickets_by_status(status):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute("""
            SELECT * FROM tickets
            WHERE status = %s
            ORDER BY id DESC
        """, (status,))
        return cursor.fetchall()

    except Exception as e:
        print("DB ERROR [get_tickets_by_status]:", e)
        return []

    finally:
        conn.close()


# =========================
# GET TICKET HISTORY
# =========================

def get_ticket_history(ticket_id):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute("""
            SELECT * FROM ticket_updates
            WHERE ticket_id = %s
            ORDER BY id ASC
        """, (ticket_id,))
        return cursor.fetchall()

    except Exception as e:
        print("DB ERROR [get_ticket_history]:", e)
        return []

    finally:
        conn.close()