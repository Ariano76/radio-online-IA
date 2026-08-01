import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from app.settings import DB_PATH
from app.logger import get_logger

logger = get_logger("database")

class Database:
    """
    Capa de persistencia del DVR.

    SQLite es la única fuente de verdad del sistema.

    Registra:
    - sesiones de grabación;
    - segmentos WAV;
    - estado del procesamiento;
    - metadatos del pipeline de IA.
    """

    def __init__(self):
        self.db_path = DB_PATH
        self.initialize()

    # ---------------------------------------------------------
    # Conexión
    # ---------------------------------------------------------

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        try:
            yield conn
            conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

    # ---------------------------------------------------------
    # Inicialización
    # ---------------------------------------------------------

    def initialize(self):
        with self.connection() as conn:

            conn.execute(
                """
                PRAGMA journal_mode=WAL;
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS recording_sessions (
                    session_id TEXT PRIMARY KEY,
                    station_name TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    status TEXT NOT NULL,
                    session_directory TEXT,
                    total_segments INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS recording_segments (
                    segment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    station_name TEXT NOT NULL,
                    wav_path TEXT NOT NULL,
                    mp3_path TEXT,
                    started_at TEXT,
                    ended_at TEXT,
                    duration_seconds REAL,
                    file_size INTEGER,
                    sha256 TEXT,
                    processed INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id)
                    REFERENCES recording_sessions(session_id)
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS processing_status (
                    segment_id INTEGER PRIMARY KEY,
                    mp3_converted INTEGER DEFAULT 0,
                    transcription_done INTEGER DEFAULT 0,
                    diarization_done INTEGER DEFAULT 0,
                    music_removed INTEGER DEFAULT 0,
                    commercials_removed INTEGER DEFAULT 0,
                    personality_extracted INTEGER DEFAULT 0,
                    llm_ready INTEGER DEFAULT 0,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(segment_id)
                    REFERENCES recording_segments(segment_id)
                )
                """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_station
                ON recording_sessions(station_name)
                """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_segments_session
                ON recording_segments(session_id)
                """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_segments_processed
                ON recording_segments(processed)
                """
            )

        logger.info("Base de datos inicializada correctamente.")

    # ---------------------------------------------------------
    # Sesiones
    # ---------------------------------------------------------

    def create_session(
        self,
        session_id,
        station_name,
        started_at,
        session_directory,
    ):
        with self.connection() as conn:

            conn.execute(
                """
                INSERT INTO recording_sessions (
                    session_id,
                    station_name,
                    started_at,
                    status,
                    session_directory
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    station_name,
                    started_at.isoformat(),
                    "RUNNING",
                    str(session_directory),
                ),
            )

    def close_session(self, session_id):
        with self.connection() as conn:

            conn.execute(
                """
                UPDATE recording_sessions
                SET
                    ended_at = ?,
                    status = 'COMPLETED'
                WHERE session_id = ?
                """,
                (
                    datetime.utcnow().isoformat(),
                    session_id,
                ),
            )

    # ---------------------------------------------------------
    # Segmentos
    # ---------------------------------------------------------

    def add_segment(
        self,
        session_id,
        station_name,
        wav_path,
        started_at=None,
        ended_at=None,
        duration_seconds=None,
        file_size=None,
        sha256=None,
    ):
        with self.connection() as conn:

            cursor = conn.execute(
                """
                INSERT INTO recording_segments (
                    session_id,
                    station_name,
                    wav_path,
                    started_at,
                    ended_at,
                    duration_seconds,
                    file_size,
                    sha256
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    station_name,
                    str(wav_path),
                    (
                        started_at.isoformat()
                        if started_at
                        else None
                    ),
                    (
                        ended_at.isoformat()
                        if ended_at
                        else None
                    ),
                    duration_seconds,
                    file_size,
                    sha256,
                ),
            )

            segment_id = cursor.lastrowid

            conn.execute(
                """
                INSERT INTO processing_status (
                    segment_id
                )
                VALUES (?)
                """,
                (segment_id,),
            )

            conn.execute(
                """
                UPDATE recording_sessions
                SET total_segments = total_segments + 1
                WHERE session_id = ?
                """,
                (session_id,),
            )

            return segment_id

    # ---------------------------------------------------------
    # Estado del procesamiento
    # ---------------------------------------------------------

    def mark_mp3_converted(
        self,
        segment_id,
        mp3_path,
    ):
        with self.connection() as conn:

            conn.execute(
                """
                UPDATE recording_segments
                SET
                    mp3_path = ?,
                    processed = 1
                WHERE segment_id = ?
                """,
                (
                    str(mp3_path),
                    segment_id,
                ),
            )

            conn.execute(
                """
                UPDATE processing_status
                SET
                    mp3_converted = 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE segment_id = ?
                """,
                (segment_id,),
            )

    def update_processing_flag(
        self,
        segment_id,
        field,
        value=1,
    ):
        allowed = {
            "transcription_done",
            "diarization_done",
            "music_removed",
            "commercials_removed",
            "personality_extracted",
            "llm_ready",
        }

        if field not in allowed:
            raise ValueError(f"Campo inválido: {field}")

        with self.connection() as conn:

            conn.execute(
                f"""
                UPDATE processing_status
                SET
                    {field} = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE segment_id = ?
                """,
                (
                    value,
                    segment_id,
                ),
            )

    # ---------------------------------------------------------
    # Consultas
    # ---------------------------------------------------------

    def get_pending_segments(self):
        with self.connection() as conn:

            rows = conn.execute(
                """
                SELECT *
                FROM recording_segments
                WHERE processed = 0
                ORDER BY created_at
                """
            ).fetchall()

            return [dict(row) for row in rows]

