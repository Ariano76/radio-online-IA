import json
from pathlib import Path
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo
from app.recorder import RadioRecorder
from app.logger import get_logger

logger = get_logger("scheduler")

CONFIG_FILE = Path("/opt/radio_dvr/config/radios.json")

TIMEZONE = ZoneInfo("America/Lima")

recorders = {}

def load_config():
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def start_station(station):
    name = station["nombre"]

    if name in recorders:
        logger.warning(f"{name} ya está grabando")
        return

    rec = RadioRecorder(station)
    rec.start()
    recorders[name] = rec

    logger.info(f"Grabación iniciada: {name}")

def stop_station(station):
    name = station["nombre"]

    if name not in recorders:
        return

    recorders[name].stop()
    del recorders[name]

    logger.info(f"Grabación detenida: {name}")

def schedule_blocks(scheduler, station, day_name, day_numbers):
    config = station.get(day_name)

    if not config:
        return

    if not config.get("activo", False):
        return

    for block in config.get("bloques", []):

        start_h, start_m, _ = map(int, block["inicio"].split(":"))
        end_h, end_m, _ = map(int, block["fin"].split(":"))

        scheduler.add_job(
            start_station,
            CronTrigger(
                day_of_week=day_numbers,
                hour=start_h,
                minute=start_m,
                timezone=TIMEZONE
            ),
            args=[station],
            id=f"start_{station['nombre']}_{day_name}_{block['inicio']}"
        )

        scheduler.add_job(
            stop_station,
            CronTrigger(
                day_of_week=day_numbers,
                hour=end_h,
                minute=end_m,
                timezone=TIMEZONE
            ),
            args=[station],
            id=f"stop_{station['nombre']}_{day_name}_{block['fin']}"
        )

def build_scheduler():
    config = load_config()

    scheduler = BlockingScheduler(timezone=TIMEZONE)

    for station in config["emisoras"]:

        if not station.get("activo", True):
            continue

        schedule_blocks(scheduler, station, "lunes_viernes", "mon-fri")
        schedule_blocks(scheduler, station, "sabado", "sat")
        schedule_blocks(scheduler, station, "domingo", "sun")

    return scheduler

if __name__ == "__main__":
    scheduler = build_scheduler()

    logger.info("Scheduler iniciado (hora de Perú)")

    scheduler.start()