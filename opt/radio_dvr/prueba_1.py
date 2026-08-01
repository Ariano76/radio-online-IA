from app.recorder import RadioRecorder

station = {
    "nombre": "radio_local",
    "url": "https://mdstrm.com/audio/6839e261d2efddf5bfbc2d3d/icecast.audio?property=emisorasco",
    "segmento_minutos": 30
}

rec = RadioRecorder(station)

rec.start(
    "2026-07-31 17:46:00",
    "2026-07-31 17:55:00")

# esperar...
# rec.stop()