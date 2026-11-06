"""
Trendy Shop Monitor - Calendario de Adviento & Producto 1016
===========================================================
Monitorea periódicamente el catálogo de Maquillaje Trendy Shop:
1. Detecta nuevos productos con palabras clave: 'adviento', 'wonderland', etc.
2. Alerta sobre cambios en parámetros del producto 1016 ("Unidad De Prueba Ecommerce").
3. Enumera cada 30 minutos todos los productos que coincidan con la búsqueda.

Puede ejecutarse:
- En bucle continuo (cada 30 min): python trendy_monitor.py
- En una sola pasada (para Cron Jobs / Programador de Tareas): python trendy_monitor.py --once
"""

import os
import sys
import time
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Tuple

# Intento de importar requests, con fallback a urllib si no está instalado
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error
    HAS_REQUESTS = False

# ==========================================================
# CONFIGURACIÓN
# ==========================================================
CATALOG_URL = "https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?_from=250&_to=299"
PRODUCT_1016_DIRECT_URL = "https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?fq=productId:1016"

# Palabras clave a buscar en productName o productTitle (en minúsculas)
KEYWORDS = [
    "adviento",
    "calendario de adviento",
    "calendario adviento",
    "calendario-adviento",
    "wonderland",
    "calendario de adviento wonderland",
]

# ID y nombre del producto de control
TARGET_PRODUCT_ID = "1016"
TARGET_PRODUCT_NAME_KEYWORD = "unidad de prueba ecommerce"

# Intervalo de revisión en segundos (30 minutos = 1800 segundos)
CHECK_INTERVAL_SECONDS = 30 * 60

# Rutas de archivos de estado y registro
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "trendy_state.json")
LOG_FILE = os.path.join(BASE_DIR, "trendy_monitor.log")

# Opciones opcionales de alerta externa (Discord o Telegram)
# Puedes definirlos aquí o pasarlos como variables de entorno
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("TrendyMonitor")

# Encabezados HTTP simulando navegador real para evitar bloqueos por parte de Cloudflare / VTEX
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"
}


# ==========================================================
# PETICIONES HTTP
# ==========================================================
def http_get_json(url: str, timeout: int = 25) -> Any:
    """Realiza una petición GET y retorna el JSON parseado."""
    if HAS_REQUESTS:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        return response.json()
    else:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content)


def send_external_alert(message: str) -> None:
    """Envía alerta a Discord o Telegram si están configurados."""
    # 1. Alerta a Discord Webhook
    if DISCORD_WEBHOOK_URL:
        try:
            payload = json.dumps({"content": message}).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            if HAS_REQUESTS:
                requests.post(DISCORD_WEBHOOK_URL, data=payload, headers=headers, timeout=10)
            else:
                req = urllib.request.Request(DISCORD_WEBHOOK_URL, data=payload, headers=headers)
                urllib.request.urlopen(req, timeout=10)
            logger.info("Notificación enviada a Discord exitosamente.")
        except Exception as e:
            logger.error(f"Error al enviar notificación a Discord: {e}")

    # 2. Alerta a Telegram Bot
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = json.dumps({
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown"
            }).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            if HAS_REQUESTS:
                requests.post(tg_url, data=payload, headers=headers, timeout=10)
            else:
                req = urllib.request.Request(tg_url, data=payload, headers=headers)
                urllib.request.urlopen(req, timeout=10)
            logger.info("Notificación enviada a Telegram exitosamente.")
        except Exception as e:
            logger.error(f"Error al enviar notificación a Telegram: {e}")


# ==========================================================
# GESTIÓN DE ESTADO PERSISTENTE
# ==========================================================
def load_state() -> Dict[str, Any]:
    """Carga el estado anterior desde el archivo JSON local."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"No se pudo leer el archivo de estado {STATE_FILE}: {e}")
    return {
        "known_keyword_product_ids": [],
        "product_1016_snapshot": None,
        "last_run": None
    }


def save_state(state: Dict[str, Any]) -> None:
    """Guarda el estado actualizado en el archivo JSON."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error al guardar estado en {STATE_FILE}: {e}")


# ==========================================================
# LÓGICA DE DETECCIÓN Y COMPARACIÓN
# ==========================================================
def matches_keywords(product: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Evalúa si productName o productTitle contienen alguna palabra clave."""
    name = str(product.get("productName") or "").lower()
    title = str(product.get("productTitle") or "").lower()
    full_text = f"{name} {title}"

    matched = []
    for kw in KEYWORDS:
        if kw.lower() in full_text:
            matched.append(kw)

    return (len(matched) > 0, matched)


def sanitize_product_data(product: Dict[str, Any]) -> Dict[str, Any]:
    """
    Limpia campos efímeros o dinámicos generados por VTEX en cada llamada
    (por ejemplo: PriceToken de JWT con timestamp de expiración) para evitar falsas alarmas.
    """
    if not isinstance(product, dict):
        return product

    clean = {}
    for k, v in product.items():
        # Ignorar tokens dinámicos de sesión o parámetros de caché volátiles
        if k in ["PriceToken", "CacheVersionUsedToCallCheckout"]:
            continue
        if isinstance(v, dict):
            clean[k] = sanitize_product_data(v)
        elif isinstance(v, list):
            clean[k] = [sanitize_product_data(item) if isinstance(item, dict) else item for item in v]
        else:
            clean[k] = v
    return clean


def compare_parameters(old: Any, new: Any, path: str = "") -> List[str]:
    """Compara recursivamente dos estructuras y devuelve una lista de diferencias descriptivas."""
    diffs = []
    if type(old) != type(new):
        return [f"{path}: tipo cambió de {type(old).__name__} a {type(new).__name__}"]

    if isinstance(old, dict):
        all_keys = set(old.keys()).union(set(new.keys()))
        for k in sorted(all_keys):
            sub_path = f"{path}.{k}" if path else k
            if k not in old:
                diffs.append(f"➕ Parámetro agregado [{sub_path}] = {new[k]}")
            elif k not in new:
                diffs.append(f"➖ Parámetro eliminado [{sub_path}] (era: {old[k]})")
            else:
                diffs.extend(compare_parameters(old[k], new[k], sub_path))
    elif isinstance(old, list):
        if len(old) != len(new):
            diffs.append(f"{path}: cantidad de elementos cambió ({len(old)} -> {len(new)})")
        for i, (item_old, item_new) in enumerate(zip(old, new)):
            diffs.extend(compare_parameters(item_old, item_new, f"{path}[{i}]"))
    else:
        if old != new:
            diffs.append(f"✏️ [{path}]: '{old}' ➔ '{new}'")

    return diffs


# ==========================================================
# CICLO PRINCIPAL DE MONITOREO
# ==========================================================
def run_monitoring_cycle() -> None:
    """Ejecuta una iteración completa de verificación."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("=" * 70)
    logger.info(f"INICIANDO REVISIÓN DE CATÁLOGO TRENDY SHOP - {now_str}")
    logger.info(f"URL: {CATALOG_URL}")
    logger.info("=" * 70)

    state = load_state()
    known_keyword_ids = set(state.get("known_keyword_product_ids", []))
    old_1016_snapshot = state.get("product_1016_snapshot")

    # 1. Consultar el rango 250 a 299 del catálogo
    try:
        products = http_get_json(CATALOG_URL)
        if not isinstance(products, list):
            logger.error(f"Respuesta inesperada de la API (no es lista): {type(products)}")
            return
    except Exception as e:
        logger.error(f"Error al consultar la API de catálogo: {e}")
        return

    logger.info(f"Productos recibidos en el bloque [250..299]: {len(products)}")

    # 2. Evaluar productos coincidentes con las palabras clave
    matching_products = []
    new_matching_products = []
    product_1016_found = None

    for p in products:
        pid = str(p.get("productId", ""))
        pname = p.get("productName", "Sin nombre")

        # Verificar si es el producto 1016 dentro del bloque
        if pid == TARGET_PRODUCT_ID or TARGET_PRODUCT_NAME_KEYWORD in pname.lower():
            product_1016_found = p

        # Evaluar palabras clave
        is_match, matched_kws = matches_keywords(p)
        if is_match:
            matching_products.append((p, matched_kws))
            if pid not in known_keyword_ids:
                new_matching_products.append((p, matched_kws))
                known_keyword_ids.add(pid)

    # 3. Enumerar en una lista los productos que correspondan a los parámetros de búsqueda
    print("\n" + "-" * 70)
    print(f"📋 LISTADO DE PRODUCTOS COINCIDENTES EN ESTE CICLO ({len(matching_products)} encontrados):")
    if matching_products:
        for idx, (p, kws) in enumerate(matching_products, 1):
            pid = p.get("productId", "N/A")
            name = p.get("productName", "Sin nombre")
            link = p.get("link", f"https://www.maquillajetrendyshop.com/{p.get('linkText', '')}/p")
            print(f"  [{idx}] ID: {pid} | Nombre: {name}")
            print(f"      Palabras detectadas: {', '.join(kws)}")
            print(f"      Enlace: {link}")
    else:
        print("  (Ningún producto en este bloque contiene 'adviento' o 'wonderland')")
    print("-" * 70 + "\n")

    # 4. Alertar si se agregó un NUEVO producto con palabras clave
    if new_matching_products:
        alert_lines = ["🚨 ¡ALERTA: NUEVO PRODUCTO DE ADVIENTO / WONDERLAND DETECTADO! 🚨"]
        for p, kws in new_matching_products:
            pid = p.get("productId", "N/A")
            name = p.get("productName", "Sin nombre")
            link = p.get("link", f"https://www.maquillajetrendyshop.com/{p.get('linkText', '')}/p")
            alert_lines.append(f"\n• ID: {pid}\n  Nombre: {name}\n  Coincidencias: {', '.join(kws)}\n  Link: {link}")
        
        full_alert = "\n".join(alert_lines)
        logger.warning(full_alert)
        send_external_alert(full_alert)

    # 5. Monitorear el Producto 1016 ("Unidad De Prueba Ecommerce")
    # Si no apareció en el bloque 250..299 (puede haberse desplazado de página con nuevos lanzamientos),
    # hacemos una consulta directa para garantizar que NUNCA se pierda su monitoreo.
    if not product_1016_found:
        try:
            direct_res = http_get_json(PRODUCT_1016_DIRECT_URL)
            if isinstance(direct_res, list) and len(direct_res) > 0:
                product_1016_found = direct_res[0]
                logger.info("ℹ️ Producto 1016 consultado mediante endpoint directo (no estaba en el rango 250..299).")
        except Exception as e:
            logger.warning(f"No se pudo consultar el producto 1016 directamente: {e}")

    if product_1016_found:
        current_1016_sanitized = sanitize_product_data(product_1016_found)

        # Extraer datos de interés para log rápido
        first_item = (product_1016_found.get("items") or [{}])[0]
        first_seller = (first_item.get("sellers") or [{}])[0]
        offer = first_seller.get("commertialOffer") or {}
        price = offer.get("Price", "N/A")
        stock = offer.get("AvailableQuantity", "N/A")
        available = offer.get("IsAvailable", "N/A")

        if old_1016_snapshot is None:
            logger.info("ℹ️ Primer registro guardado para Producto 1016 ('Unidad De Prueba Ecommerce').")
            logger.info(f"   Valores actuales: Precio=${price} | Stock={stock} | Disponible={available}")
            state["product_1016_snapshot"] = current_1016_sanitized
        else:
            # Comparar parámetros contra la última captura
            differences = compare_parameters(old_1016_snapshot, current_1016_sanitized)
            if differences:
                alert_p1016 = [
                    "⚠️ ¡ALERTA: ACTUALIZACIÓN EN PRODUCTO 1016 (Unidad De Prueba Ecommerce)! ⚠️",
                    f"Fecha: {now_str}",
                    f"Resumen actual: Precio=${price} | Stock={stock} | Disponible={available}",
                    "\nParámetros modificados detectados:"
                ]
                for diff in differences[:20]:  # Mostrar hasta 20 diferencias
                    alert_p1016.append(f"  {diff}")
                if len(differences) > 20:
                    alert_p1016.append(f"  ... y {len(differences) - 20} cambios adicionales.")

                full_alert_1016 = "\n".join(alert_p1016)
                logger.warning(full_alert_1016)
                send_external_alert(full_alert_1016)

                # Actualizar snapshot al nuevo estado
                state["product_1016_snapshot"] = current_1016_sanitized
            else:
                logger.info(f"✅ Producto 1016 sin cambios (Precio: ${price}, Stock: {stock}, Disponible: {available}).")
    else:
        logger.warning("⚠️ No se pudo obtener información del Producto 1016 en este ciclo.")

    # Guardar estado actualizado
    state["known_keyword_product_ids"] = list(known_keyword_ids)
    state["last_run"] = now_str
    save_state(state)
    logger.info("Fin de la revisión. Estado guardado.")


# ==========================================================
# PUNTO DE ENTRADA
# ==========================================================
def main():
    # Si se pasa el argumento --once, corre una sola vez y finaliza (útil para Cron / Tareas Programadas)
    if "--once" in sys.argv:
        run_monitoring_cycle()
        return

    logger.info("Iniciando Trendy Monitor en modo continuo (cada 30 minutos).")
    logger.info("Presiona Ctrl + C en cualquier momento para detener el programa.\n")

    try:
        while True:
            run_monitoring_cycle()
            logger.info(f"Próxima revisión en 30 minutos ({CHECK_INTERVAL_SECONDS} segundos). Esperando...\n")
            time.sleep(CHECK_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("\nPrograma detenido manualmente por el usuario. ¡Hasta luego!")


if __name__ == "__main__":
    main()
