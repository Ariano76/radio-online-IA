import json
from pathlib import Path
from zoneinfo import ZoneInfo
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from app.recorder import RadioRecorder
from app.logger import get_logger
from app.settings import CONFIG_DIR

logger = get_logger("scheduler")

CONFIG_FILE = CONFIG_DIR / "radios.json"
TIMEZONE = ZoneInfo("America/Lima")

class RadioScheduler:
# 
# Planificador principal del DVR de radio.
# Responsabilidades:
# - Cargar la configuración de emisoras.
# - Programar los bloques horarios.
# - Crear y destruir instancias de RadioRecorder.
# - Mantener el registro de sesiones activas.


    def __init__(self):

        self.scheduler = BlockingScheduler(timezone=TIMEZONE)
        self.recorders = {}
        self.config = self.load_config()

    # ---------------------------------------------------------
    # Configuración
    # ---------------------------------------------------------

    def load_config(self):

        if not CONFIG_FILE.exists():
            raise FileNotFoundError(
                f"No existe el archivo de configuración: {CONFIG_FILE}"
            )

        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    # ---------------------------------------------------------
    # Control de grabaciones
    # ---------------------------------------------------------

    def start_station(self, station):

        name = station["nombre"]
        recorder = self.recorders.get(name)
        if recorder and recorder.is_running():
            logger.warning(
                f"{name} ya tiene una grabación activa."
            )
            return

        logger.info(
            f"Iniciando bloque programado para {name}"
        )

        recorder = RadioRecorder(station)

        if recorder.start():
            self.recorders[name] = recorder
            logger.info(
                f"Grabación iniciada para {name}"
            )
        else:
            logger.error(
                f"No fue posible iniciar la grabación de {name}"
            )

    def stop_station(self, station):

        name = station["nombre"]
        recorder = self.recorders.get(name)
        if recorder is None:
            logger.info(
                f"No existe una grabación activa para {name}"
            )
            return

        logger.info(
            f"Finalizando bloque programado para {name}"
        )

        recorder.stop()
        self.recorders.pop(name, None)
        logger.info(
            f"Grabación detenida para {name}"
        )

    # ---------------------------------------------------------
    # Programación
    # ---------------------------------------------------------

    def schedule_blocks(self, station, section_name, day_expression):

        section = station.get(section_name)
        if not section:
            return

        if not section.get("activo", False):
            return

        blocks = section.get("bloques", [])
        for block in blocks:
            start_h, start_m, _ = map(
                int,
                block["inicio"].split(":")
            )
            end_h, end_m, _ = map(
                int,
                block["fin"].split(":")
            )
            start_job = (
                f"start_{station['nombre']}_{section_name}_{block['inicio']}"
            )
            stop_job = (
                f"stop_{station['nombre']}_{section_name}_{block['fin']}"
            )
            self.scheduler.add_job(
                func=self.start_station,
                trigger=CronTrigger(
                    day_of_week=day_expression,
                    hour=start_h,
                    minute=start_m,
                    timezone=TIMEZONE,
                ),
                args=[station],
                id=start_job,
                replace_existing=True,
            )
            self.scheduler.add_job(
                func=self.stop_station,
                trigger=CronTrigger(
                    day_of_week=day_expression,
                    hour=end_h,
                    minute=end_m,
                    timezone=TIMEZONE,
                ),
                args=[station],
                id=stop_job,
                replace_existing=True,
            )
            logger.info(
                f"Programado {station['nombre']}: {block['inicio']} - {block['fin']} ({section_name})"
            )

    # ---------------------------------------------------------
    # Construcción del scheduler
    # ---------------------------------------------------------

    def build(self):

        stations = self.config.get("emisoras", [])
        for station in stations:
            if not station.get("activo", True):
                continue

            self.schedule_blocks(
                station,
                "lunes_viernes",
                "mon-fri"
            )
            self.schedule_blocks(
                station,
                "sabado",
                "sat"
            )
            self.schedule_blocks(
                station,
                "domingo",
                "sun"
            )

    # ---------------------------------------------------------
    # Ejecución
    # ---------------------------------------------------------

    def start(self):

        logger.info(
            "Iniciando Radio Scheduler (hora de Perú)"
        )
        self.build()

        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info(
                "Deteniendo scheduler..."
            )
            self.shutdown()

    def shutdown(self):

        logger.info(
            "Finalizando grabaciones activas..."
        )

        for recorder in list(self.recorders.values()):
            try:
                recorder.stop()
            except Exception:
                logger.exception(
                    "Error deteniendo una grabación activa."
                )

        self.recorders.clear()

        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        logger.info(
            "Scheduler detenido correctamente."
        )

def main():
    scheduler = RadioScheduler()
    scheduler.start()


if __name__ == "__main__":
    main()
