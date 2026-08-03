import json
import signal
import atexit
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.recorder import RadioRecorder

from app.logger import get_logger
from app.settings import CONFIG_DIR, TIMEZONE

logger = get_logger("scheduler")

CONFIG_FILE = CONFIG_DIR / "radios.json"

class RadioScheduler:
    """
    Scheduler principal del DVR de radio.

    ```
    Responsabilidades:
    - Cargar configuración.
    - Fusionar configuración global.
    - Programar bloques horarios.
    - Administrar instancias de RadioRecorder.
    - Monitorear salud de las grabaciones.
    - Apagado limpio del sistema.
    """

    def __init__(self):

        self.scheduler = BlockingScheduler(timezone=TIMEZONE)

        self.recorders = {}

        self.config = self.load_config()

        self._shutting_down = False

        self._install_signal_handlers()

        self._schedule_health_monitor()

    # ---------------------------------------------------------
    # Señales
    # ---------------------------------------------------------

    def _install_signal_handlers(self):

        signal.signal(signal.SIGTERM, self._signal_handler)

        signal.signal(signal.SIGINT, self._signal_handler)

        if hasattr(signal, "SIGHUP"):

            signal.signal(signal.SIGHUP, self._signal_handler)

        atexit.register(self.shutdown)

    def _signal_handler(self, signum, frame):

        logger.info(
            f"Señal recibida: {signum}. Cerrando scheduler."
        )

        self.shutdown()

    # ---------------------------------------------------------
    # Configuración
    # ---------------------------------------------------------

    def load_config(self):

        if not CONFIG_FILE.exists():

            raise FileNotFoundError(
                f"No existe el archivo de configuración: {CONFIG_FILE}"
            )

        with open(CONFIG_FILE, "r", encoding="utf-8") as f:

            config = json.load(f)

        segmento_default = config.get(
            "segmento_minutos",
            30
        )

        audio = config.get("formato_audio", {})

        sample_rate_default = audio.get(
            "sample_rate",
            16000
        )

        channels_default = audio.get(
            "channels",
            1
        )

        codec_default = audio.get(
            "codec",
            "pcm_s16le"
        )

        stations = config.get("emisoras", [])

        if not stations:

            raise RuntimeError(
                "No existen emisoras configuradas."
            )

        for station in stations:

            station.setdefault(
                "segmento_minutos",
                segmento_default
            )

            station.setdefault(
                "sample_rate",
                sample_rate_default
            )

            station.setdefault(
                "channels",
                channels_default
            )

            station.setdefault(
                "codec",
                codec_default
            )

        return config

    # ---------------------------------------------------------
    # Validación
    # ---------------------------------------------------------

    def validate_station(self, station):

        required = [
            "nombre",
            "url",
            "segmento_minutos",
            "sample_rate",
            "channels",
        ]

        for field in required:

            if field not in station:

                raise ValueError(
                    f"Falta el campo '{field}' en la emisora {station.get('nombre')}"
                )

    # ---------------------------------------------------------
    # Grabaciones
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
    # Monitoreo
    # ---------------------------------------------------------

    def _schedule_health_monitor(self):

        self.scheduler.add_job(
            func=self.health_check,
            trigger="interval",
            minutes=1,
            id="health_monitor",
            replace_existing=True,
        )

    def health_check(self):

        for name, recorder in list(self.recorders.items()):

            if not recorder.is_running():

                logger.warning(
                    f"La grabación de {name} terminó inesperadamente."
                )

                try:

                    recorder.stop()

                except Exception:

                    logger.exception(
                        f"Error limpiando grabación de {name}"
                    )

                self.recorders.pop(name, None)

    # ---------------------------------------------------------
    # Programación
    # ---------------------------------------------------------

    def schedule_blocks(
        self,
        station,
        section_name,
        day_expression,
    ):

        section = station.get(section_name)

        if not section:

            return

        if not section.get("activo", False):

            return

        for block in section.get("bloques", []):

            start_h, start_m, start_s = map(
                int,
                block["inicio"].split(":")
            )

            end_h, end_m, end_s = map(
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
                    second=start_s,
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
                    second=end_s,
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
    # Construcción
    # ---------------------------------------------------------

    def build(self):

        stations = self.config.get("emisoras", [])

        total_jobs = 0

        for station in stations:

            if not station.get("activo", True):

                continue

            self.validate_station(station)

            before = len(self.scheduler.get_jobs())

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

            after = len(self.scheduler.get_jobs())

            total_jobs += after - before

        logger.info(
            f"Scheduler configurado con {total_jobs} trabajos."
        )

    # ---------------------------------------------------------
    # Ejecución
    # ---------------------------------------------------------

    def start(self):

        logger.info(
            "Iniciando Radio Scheduler (hora de Perú)"
        )

        self.build()

        logger.info(
            f"Zona horaria: {TIMEZONE}"
        )

        try:

            self.scheduler.start()

        except (KeyboardInterrupt, SystemExit):

            logger.info(
                "Interrupción recibida."
            )

        finally:

            self.shutdown()

    # ---------------------------------------------------------
    # Apagado
    # ---------------------------------------------------------

    def shutdown(self):

        if self._shutting_down:

            return

        self._shutting_down = True

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

        try:

            if self.scheduler.running:

                self.scheduler.shutdown(wait=False)

        except Exception:

            pass

        logger.info(
            "Scheduler detenido correctamente."
        )


def main():
    scheduler = RadioScheduler()
    scheduler.start()


if __name__ == "__main__":
    main()
