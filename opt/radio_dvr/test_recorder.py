import json
import time
from pathlib import Path

from app.recorder import RadioRecorder
from app.logger import get_logger
from app.settings import CONFIG_DIR

logger = get_logger("test_recorder")

def load_station():
    config_file = CONFIG_DIR / "radios.json"

    if not config_file.exists():
        raise FileNotFoundError(
            f"No existe el archivo: {config_file}"
        )

    with open(config_file, "r", encoding="utf-8") as f:
        config = json.load(f)

    stations = config.get("emisoras", [])

    if not stations:
        raise RuntimeError(
            "No existen emisoras configuradas."
        )

    return stations[0]

def print_status(recorder):
    status = recorder.get_status()

    print("----------------------------------------")
    print(f"Emisora      : {status['station']}")
    print(f"Ejecutando   : {status['running']}")
    print(f"PID          : {status['pid']}")
    print(f"Session ID   : {status['session_id']}")
    print(f"Inicio       : {status['started_at']}")
    print(f"Directorio   : {status['session_directory']}")
    print("----------------------------------------")

def monitor(recorder):
    print()
    print("Monitoreando grabación...")
    print("Presiona CTRL+C para detener la prueba.")
    print()

    last_segment = None

    while True:
        time.sleep(5)

        if not recorder.is_running():
            print()
            print("La grabación terminó inesperadamente.")
            break

        segment = recorder.current_segment()

        if segment != last_segment:
            last_segment = segment

            print(
                f"Nuevo segmento: {segment.name if segment else 'Ninguno'}"
            )

            if segment and segment.exists():
                size_mb = segment.stat().st_size / (1024 * 1024)

                print(
                    f"Tamaño actual: {size_mb:.2f} MB"
                )

def main():
    print()
    print("========================================")
    print("DVR de radio profesional - prueba")
    print("========================================")
    print()

    station = load_station()

    print(f"Emisora: {station['nombre']}")
    print(f"URL    : {station['url']}")
    print(
        f"Segmento: {station.get('segmento_minutos', 30)} minutos"
    )
    print()

    recorder = RadioRecorder(station)

    try:
        if not recorder.start():
            print("No fue posible iniciar la grabación.")
            return

        print("Grabación iniciada correctamente.")
        print_status(recorder)

        monitor(recorder)

    except KeyboardInterrupt:
        print()
        print("Interrupción recibida (CTRL+C).")

    except Exception:
        logger.exception(
            "Error durante la prueba del Recorder."
        )

    finally:
        print()
        print("Deteniendo grabación...")

        recorder.stop()

        print_status(recorder)

        print()
        print("Prueba finalizada.")
        print()

    if __name__ == "__main__":
        main()
