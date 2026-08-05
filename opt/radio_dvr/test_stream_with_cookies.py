#!/usr/bin/env python3
"""
Script para probar la descarga del stream de Emisoras Co
con manejo manual de redirección 302 y cookies de sesión.
"""

import requests
import sys
import os

# ── CONFIGURACIÓN ──
STREAM_URL = "https://mdstrm.com/audio/6839e261d2efddf5bfbc2d3d/icecast.audio?property=emisorasco"
OUTPUT_FILE = "/tmp/test_emisorasco_cookies.aac"
TIMEOUT = 30

# Headers que simulan un navegador real
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",  # evita compresión en stream
    "Referer": "https://www.emisorasco.com/",
    "Origin": "https://www.emisorasco.com",
    "Connection": "keep-alive",
}

def main():
    session = requests.Session()
    session.headers.update(HEADERS)

    print("=" * 60)
    print("PASO 1: Petición inicial a mdstrm.com")
    print("=" * 60)

    try:
        # allow_redirects=False para capturar manualmente el 302 y las cookies
        resp1 = session.get(
            STREAM_URL,
            allow_redirects=False,
            timeout=TIMEOUT,
            stream=False,
        )
    except Exception as e:
        print(f"[ERROR] Falló la conexión inicial: {e}")
        sys.exit(1)

    print(f"Status Code: {resp1.status_code}")
    print(f"Headers de respuesta:")
    for k, v in resp1.headers.items():
        print(f"  {k}: {v}")

    # Extraer cookies que el servidor nos envió
    print(f"\nCookies recibidas en paso 1:")
    for cookie in session.cookies:
        print(f"  {cookie.name}={cookie.value[:20]}... (domain={cookie.domain})")

    if resp1.status_code not in (301, 302, 307, 308):
        print(f"\n[AVISO] Se esperaba 302, se recibió {resp1.status_code}")
        # Aún así intentamos continuar si hay body
        if resp1.status_code == 200:
            print("El servidor respondió 200 directamente. Guardando...")
            with open(OUTPUT_FILE, "wb") as f:
                for chunk in resp1.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            print(f"Archivo guardado en: {OUTPUT_FILE}")
            return

    redirect_url = resp1.headers.get("Location")
    if not redirect_url:
        print("[ERROR] No se encontró header 'Location' en la respuesta 302")
        sys.exit(1)

    print(f"\nURL de redirección: {redirect_url[:100]}...")

    # ─────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PASO 2: Petición al CDN con cookies de sesión")
    print("=" * 60)

    try:
        # La session ya lleva las cookies automáticamente
        resp2 = session.get(
            redirect_url,
            timeout=TIMEOUT,
            stream=True,
            headers={
                # Reforzamos el Referer para el CDN
                "Referer": "https://mdstrm.com/",
            }
        )
    except requests.exceptions.Timeout:
        print(f"[ERROR] Timeout al conectar con el CDN después de {TIMEOUT}s")
        print("Esto confirma que el CDN no responde desde tu servidor.")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Falló la conexión al CDN: {e}")
        sys.exit(1)

    print(f"Status Code del CDN: {resp2.status_code}")
    print(f"Content-Type: {resp2.headers.get('Content-Type', 'N/A')}")

    if resp2.status_code != 200:
        print(f"[ERROR] El CDN respondió con status {resp2.status_code}")
        print("Body de respuesta:")
        print(resp2.text[:500])
        sys.exit(1)

    # Guardar el stream
    print(f"\nDescargando stream a: {OUTPUT_FILE}")
    bytes_written = 0
    try:
        with open(OUTPUT_FILE, "wb") as f:
            for chunk in resp2.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    bytes_written += len(chunk)
                    if bytes_written % (1024 * 1024) == 0:
                        print(f"  Descargados: {bytes_written / 1024:.0f} KB...", end="\r")
    except KeyboardInterrupt:
        print("\n[INTERRUMPIDO] por el usuario")
    finally:
        print(f"\nTotal descargado: {bytes_written / 1024:.1f} KB")
        if bytes_written > 0:
            print(f"[ÉXITO] Archivo guardado en: {OUTPUT_FILE}")
        else:
            print("[ADVERTENCIA] El archivo está vacío")
            if os.path.exists(OUTPUT_FILE):
                os.remove(OUTPUT_FILE)

    # Cerrar sesión
    session.close()


if __name__ == "__main__":
    main()