import sqlite3

def normalize_email(email: str) -> str:
    return email.strip().lower()

def normalize_username(username: str) -> str:
    return username.strip().lower()

def init_db(db_path: str = "app.db") -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            username_normalized TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS parent_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            email TEXT NOT NULL,
            email_normalized TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_parent_emails_user_id
        ON parent_emails(user_id);

        CREATE INDEX IF NOT EXISTS idx_parent_emails_email_norm
        ON parent_emails(email_normalized);
        """
    )

    conn.close()

def create_user(db_path: str, username: str, parent_email: str) -> int:
    username_norm = normalize_username(username)
    email_norm = normalize_email(parent_email)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    try:
        cur.execute(
            """
            INSERT INTO users (username, username_normalized)
            VALUES (?, ?);
            """,
            (username, username_norm),
        )
        user_id = cur.lastrowid

        cur.execute(
            """
            INSERT INTO parent_emails (user_id, email, email_normalized)
            VALUES (?, ?, ?);
            """,
            (user_id, parent_email, email_norm),
        )

        conn.commit()
        return int(user_id)

    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise ValueError(f"Username already taken: {username}") from e
    finally:
        conn.close()

def get_user_id_by_username(db_path: str, username: str) -> int | None:
    username_norm = normalize_username(username)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        "SELECT id FROM users WHERE username_normalized = ?;",
        (username_norm,),
    )
    row = cur.fetchone()
    conn.close()

    return int(row[0]) if row else None


def get_parent_email_for_username(db_path: str, username: str) -> str | None:
    username_norm = normalize_username(username)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT pe.email
        FROM users u
        JOIN parent_emails pe ON pe.user_id = u.id
        WHERE u.username_normalized = ?;
        """,
        (username_norm,),
    )

    row = cur.fetchone()
    conn.close()

    return row[0] if row else None

if __name__ == "__main__":
    db_path = "app.db"
    init_db(db_path)
    new_user_id = create_user(db_path, "new_user", "parent@example.com")
    print(f"Created new user with ID: {new_user_id}")
