import sqlite3
from pathlib import Path


from app.settings import DB_PATH

class Database:

    def __init__(self):
            self.conn = sqlite3.connect(DB_PATH)
            self.create_tables()

    def create_tables(self):
        cur = self.conn.cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS recording_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station TEXT,
                scheduled_start TEXT,
                scheduled_end TEXT,
                real_start TEXT,
                real_end TEXT,
                status TEXT,
                reconnects INTEGER DEFAULT 0,
                notes TEXT
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS recording_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                event_time TEXT,
                event_type TEXT,
                description TEXT
            )
            """
        )

        self.conn.commit()

    def create_session(self, station, start, end):
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO recording_sessions (
                station,
                scheduled_start,
                scheduled_end,
                status
            ) VALUES (?, ?, ?, ?)
            """,
            (station, start, end, "SCHEDULED")
        )

        self.conn.commit()

        return cur.lastrowid

    def close(self):
        self.conn.close()

