"""
Trendy Shop Monitor - Monitoreo Integral de Catálogo (0..299)
=============================================================
Monitorea periódicamente las páginas 0 a 299 del catálogo de Trendy Shop:
1. Consulta los 6 bloques de productos: 0..49, 50..99, 100..149, 150..199, 200..249 y 250..299.
2. Detecta si se agregan NUEVOS productos al catálogo en general y avisa.
3. Filtra y enumera los productos con palabras clave: 'adviento', 'wonderland', etc.
4. Alerta si el producto 1016 ("Unidad De Prueba Ecommerce") actualiza alguno de sus parámetros.
5. Registra todas las alertas en un archivo de texto dedicado ('alertas_trendy.txt') con fecha,
   hora, productos detectados, productos modificados y nuevos productos agregados.

Modos de ejecución:
- En bucle continuo (cada 30 min): python trendy_monitor.py
- En una sola pasada (para Cron / Programador de Tareas): python trendy_monitor.py --once
"""

import os
import sys
import time
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Tuple, Set

# Intento de importar requests, con fallback a urllib de la librería estándar
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error
    HAS_REQUESTS = False

# ==========================================================
# CONFIGURACIÓN DE URLS Y PARÁMETROS
# ==========================================================
CATALOG_URLS = [
    "https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?_from=0&_to=49",
    "https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?_from=50&_to=99",
    "https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?_from=100&_to=149",
    "https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?_from=150&_to=199",
    "https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?_from=200&_to=249",
    "https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?_from=250&_to=299",
]

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

# Producto de prueba a vigilar
TARGET_PRODUCT_ID = "1016"
TARGET_PRODUCT_NAME_KEYWORD = "unidad de prueba ecommerce"

# Intervalo entre revisiones completas (30 minutos = 1800 segundos)
CHECK_INTERVAL_SECONDS = 30 * 60

# Pausa breve entre peticiones de cada bloque para evitar saturar el servidor (en segundos)
REQUEST_DELAY_SECONDS = 0.5

# Archivos locales de estado, logs y alertas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "trendy_state.json")
LOG_FILE = os.path.join(BASE_DIR, "trendy_monitor.log")
ALERTS_FILE = os.path.join(BASE_DIR, "alertas_trendy.txt")

# Opciones opcionales de alerta externa (Discord o Telegram)
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

# Encabezados HTTP de navegador
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"
}


# ==========================================================
# UTILIDADES HTTP
# ==========================================================
def http_get_json(url: str, timeout: int = 30) -> Any:
    """Realiza una petición GET y retorna la respuesta parseada como JSON."""
    if HAS_REQUESTS:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    else:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            content = response.read().decode("utf-8")
            return json.loads(content)


# ==========================================================
# REGISTRO DE ALERTAS EN ARCHIVO DE TEXTO Y NOTIFICACIONES
# ==========================================================
def append_alert_to_text_file(alert_type: str, lines: List[str]) -> None:
    """
    Añade una entrada estructurada en 'alertas_trendy.txt' con fecha y hora exacta,
    describiendo los productos detectados, agregados o modificados.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry_lines = [
        "=" * 80,
        f"FECHA Y HORA: {now_str}",
        f"TIPO DE ALERTA: {alert_type}",
        "-" * 80
    ]
    entry_lines.extend(lines)
    entry_lines.append("=" * 80 + "\n\n")

    try:
        with open(ALERTS_FILE, "a", encoding="utf-8") as f:
            f.write("\n".join(entry_lines))
        logger.info(f"📝 Alerta registrada en '{os.path.basename(ALERTS_FILE)}'.")
    except Exception as e:
        logger.error(f"Error al escribir en {ALERTS_FILE}: {e}")


def send_external_alert(message: str) -> None:
    """Envía la alerta a Discord o Telegram si están configurados."""
    if DISCORD_WEBHOOK_URL:
        try:
            payload = json.dumps({"content": message}).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            if HAS_REQUESTS:
                requests.post(DISCORD_WEBHOOK_URL, data=payload, headers=headers, timeout=10)
            else:
                req = urllib.request.Request(DISCORD_WEBHOOK_URL, data=payload, headers=headers)
                urllib.request.urlopen(req, timeout=10)
            logger.info("Notificación enviada a Discord.")
        except Exception as e:
            logger.error(f"Error enviando notificación a Discord: {e}")

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
            logger.info("Notificación enviada a Telegram.")
        except Exception as e:
            logger.error(f"Error enviando notificación a Telegram: {e}")


# ==========================================================
# GESTIÓN DEL ESTADO PERSISTENTE
# ==========================================================
def load_state() -> Dict[str, Any]:
    """Carga el estado previo desde el archivo JSON."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"No se pudo leer el archivo de estado {STATE_FILE}: {e}")
    return {
        "known_catalog_product_ids": [],
        "known_keyword_product_ids": [],
        "product_1016_snapshot": None,
        "is_baseline_established": False,
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
# EVALUACIÓN DE PRODUCTOS Y DIFERENCIAS
# ==========================================================
def extract_product_summary(product: Dict[str, Any]) -> Dict[str, Any]:
    """Extrae datos comerciales legibles de un producto."""
    pid = str(product.get("productId", "N/A"))
    name = product.get("productName", "Sin nombre")
    title = product.get("productTitle", "")
    link = product.get("link") or f"https://www.maquillajetrendyshop.com/{product.get('linkText', '')}/p"

    # Datos comerciales de la primera variación / seller
    items = product.get("items") or [{}]
    first_item = items[0] if items else {}
    sellers = first_item.get("sellers") or [{}]
    offer = sellers[0].get("commertialOffer") or {} if sellers else {}

    price = offer.get("Price", "N/A")
    stock = offer.get("AvailableQuantity", "N/A")
    is_available = offer.get("IsAvailable", "N/A")

    return {
        "id": pid,
        "name": name,
        "title": title,
        "link": link,
        "price": price,
        "stock": stock,
        "available": is_available
    }


def matches_keywords(product: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Determina si un producto contiene alguna de las palabras clave buscadas."""
    name = str(product.get("productName") or "").lower()
    title = str(product.get("productTitle") or "").lower()
    full_text = f"{name} {title}"

    matched = []
    for kw in KEYWORDS:
        if kw.lower() in full_text:
            matched.append(kw)

    return (len(matched) > 0, matched)


def sanitize_product_for_diff(product: Dict[str, Any]) -> Dict[str, Any]:
    """
    Elimina tokens dinámicos de sesión (PriceToken) que VTEX renueva
    en cada llamada, evitando falsas alarmas de modificación.
    """
    if not isinstance(product, dict):
        return product

    clean = {}
    for k, v in product.items():
        if k in ["PriceToken", "CacheVersionUsedToCallCheckout"]:
            continue
        if isinstance(v, dict):
            clean[k] = sanitize_product_for_diff(v)
        elif isinstance(v, list):
            clean[k] = [sanitize_product_for_diff(i) if isinstance(i, dict) else i for i in v]
        else:
            clean[k] = v
    return clean


def compare_product_parameters(old: Any, new: Any, path: str = "") -> List[str]:
    """Compara recursivamente dos estructuras y devuelve lista de diferencias legibles."""
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
                diffs.extend(compare_product_parameters(old[k], new[k], sub_path))
    elif isinstance(old, list):
        if len(old) != len(new):
            diffs.append(f"{path}: cantidad de elementos cambió ({len(old)} -> {len(new)})")
        for i, (item_old, item_new) in enumerate(zip(old, new)):
            diffs.extend(compare_product_parameters(item_old, item_new, f"{path}[{i}]"))
    else:
        if old != new:
            diffs.append(f"✏️ [{path}]: '{old}' ➔ '{new}'")

    return diffs


# ==========================================================
# CICLO PRINCIPAL DE MONITOREO
# ==========================================================
def run_monitoring_cycle() -> None:
    """Ejecuta una ronda de revisión a través de los 6 enlaces del catálogo."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("=" * 75)
    logger.info(f"INICIANDO REVISIÓN COMPLETA DEL CATÁLOGO TRENDY SHOP - {now_str}")
    logger.info(f"Revisando {len(CATALOG_URLS)} bloques de productos (índices 0 al 299)...")
    logger.info("=" * 75)

    state = load_state()
    known_catalog_ids = set(state.get("known_catalog_product_ids", []))
    known_keyword_ids = set(state.get("known_keyword_product_ids", []))
    old_1016_snapshot = state.get("product_1016_snapshot")
    is_baseline_established = state.get("is_baseline_established", False)

    # 1. Consultar todos los enlaces y consolidar productos únicos
    all_current_products: Dict[str, Dict[str, Any]] = {}
    total_fetched = 0

    for idx, url in enumerate(CATALOG_URLS, 1):
        try:
            logger.info(f"[{idx}/{len(CATALOG_URLS)}] Consultando: {url}")
            products = http_get_json(url)
            if isinstance(products, list):
                total_fetched += len(products)
                for p in products:
                    pid = str(p.get("productId", ""))
                    if pid and pid not in all_current_products:
                        all_current_products[pid] = p
            else:
                logger.warning(f"Respuesta inesperada en bloque {idx}: no es lista.")
        except Exception as e:
            logger.error(f"Error consultando bloque {idx} ({url}): {e}")

        # Pequeña pausa entre peticiones
        time.sleep(REQUEST_DELAY_SECONDS)

    logger.info(f"Total recibidos: {total_fetched} | Productos únicos consolidados: {len(all_current_products)}")

    # 2. Analizar productos: Palabras clave, Nuevos productos y Producto 1016
    matching_keyword_products: List[Tuple[Dict[str, Any], List[str]]] = []
    new_keyword_products: List[Tuple[Dict[str, Any], List[str]]] = []
    newly_added_catalog_products: List[Dict[str, Any]] = []
    product_1016_found: Dict[str, Any] = None

    for pid, p in all_current_products.items():
        summary = extract_product_summary(p)
        pname = summary["name"].lower()

        # Detección del producto 1016
        if pid == TARGET_PRODUCT_ID or TARGET_PRODUCT_NAME_KEYWORD in pname:
            product_1016_found = p

        # Detección de palabras clave (adviento, wonderland)
        is_match, matched_kws = matches_keywords(p)
        if is_match:
            matching_keyword_products.append((p, matched_kws))
            if pid not in known_keyword_ids:
                new_keyword_products.append((p, matched_kws))
                known_keyword_ids.add(pid)

        # Detección de NUEVOS productos agregados al catálogo
        if is_baseline_established and pid not in known_catalog_ids:
            newly_added_catalog_products.append(p)
            known_catalog_ids.add(pid)

    # 3. ENUMERAR CADA 30 MINUTOS EN CONSOLA LOS PRODUCTOS COINCIDENTES
    print("\n" + "-" * 75)
    print(f"📋 PRODUCTOS QUE COINCIDEN CON LA BÚSQUEDA ('adviento' / 'wonderland'):")
    print(f"   Total encontrados en los 6 bloques: {len(matching_keyword_products)}")
    print("-" * 75)
    if matching_keyword_products:
        for idx, (p, kws) in enumerate(matching_keyword_products, 1):
            info = extract_product_summary(p)
            print(f"  [{idx}] ID: {info['id']} | Nombre: {info['name']}")
            print(f"      Precio: ${info['price']} | Stock: {info['stock']} | Disponible: {info['available']}")
            print(f"      Palabras clave: {', '.join(kws)}")
            print(f"      Enlace: {info['link']}")
    else:
        print("  (Ningún producto en los rangos 0..299 contiene 'adviento' o 'wonderland')")
    print("-" * 75 + "\n")

    # 4. GESTIONAR PRIMERA EJECUCIÓN (LÍNEA BASE)
    if not is_baseline_established:
        # Registramos todos los productos actuales como línea base
        for pid in all_current_products.keys():
            known_catalog_ids.add(pid)
        state["is_baseline_established"] = True
        logger.info(f"✅ Línea base registrada: {len(known_catalog_ids)} productos almacenados como punto de partida.")

        # Anotar en el archivo de texto la inicialización
        init_lines = [
            f"Inicio formal del monitoreo de catálogo en 6 bloques (0 a 299).",
            f"Total de productos en el catálogo inicial: {len(known_catalog_ids)} productos registrados.",
            f"Productos con palabras clave detectados inicialmente: {len(matching_keyword_products)}."
        ]
        if matching_keyword_products:
            init_lines.append("\nProductos con 'adviento' o 'wonderland' existentes:")
            for p, kws in matching_keyword_products:
                s = extract_product_summary(p)
                init_lines.append(f"  • ID {s['id']}: {s['name']} (Precio: ${s['price']}, Stock: {s['stock']})")

        append_alert_to_text_file("INICIO DE MONITOREO Y LÍNEA BASE", init_lines)

    # 5. ALERTA: NUEVOS PRODUCTOS AGREGADOS AL CATÁLOGO
    if newly_added_catalog_products:
        alert_lines = [
            f"Se detectaron {len(newly_added_catalog_products)} NUEVOS productos agregados al catálogo:\n"
        ]
        for p in newly_added_catalog_products:
            s = extract_product_summary(p)
            is_match, matched_kws = matches_keywords(p)
            kw_note = f" 🌟 ¡COINCIDE CON: {', '.join(matched_kws)}!" if is_match else ""
            alert_lines.append(
                f"• ID: {s['id']} | Nombre: {s['name']}{kw_note}\n"
                f"  Precio: ${s['price']} | Stock: {s['stock']} | Disponible: {s['available']}\n"
                f"  Enlace: {s['link']}\n"
            )

        full_alert = "\n".join(alert_lines)
        logger.warning("🚨 ¡NUEVOS PRODUCTOS DETECTADOS EN EL CATÁLOGO!\n" + full_alert)
        append_alert_to_text_file("NUEVO(S) PRODUCTO(S) AGREGADO(S) AL CATÁLOGO", alert_lines)
        send_external_alert("🚨 ¡NUEVO PRODUCTO AGREGADO A TRENDY SHOP!\n" + full_alert)

    # 6. ALERTA: NUEVO PRODUCTO COINCIDENTE CON ADVIENTO / WONDERLAND
    # (Si no fue reportado arriba como nuevo producto general)
    if new_keyword_products and not newly_added_catalog_products:
        kw_alert_lines = [
            f"Se detectaron {len(new_keyword_products)} producto(s) nuevos con palabras clave de Adviento / Wonderland:\n"
        ]
        for p, kws in new_keyword_products:
            s = extract_product_summary(p)
            kw_alert_lines.append(
                f"• ID: {s['id']} | Nombre: {s['name']}\n"
                f"  Palabras clave: {', '.join(kws)}\n"
                f"  Precio: ${s['price']} | Stock: {s['stock']}\n"
                f"  Enlace: {s['link']}\n"
            )
        full_kw_alert = "\n".join(kw_alert_lines)
        logger.warning("🚨 " + full_kw_alert)
        append_alert_to_text_file("NUEVO PRODUCTO DE ADVIENTO / WONDERLAND DETECTADO", kw_alert_lines)
        send_external_alert("🚨 " + full_kw_alert)

    # 7. MONITOREO Y ALERTAS SOBRE EL PRODUCTO 1016 ("Unidad De Prueba Ecommerce")
    # Si no apareció en los bloques 0..299 (porque superó el índice 299), se consulta directo
    if not product_1016_found:
        try:
            direct_data = http_get_json(PRODUCT_1016_DIRECT_URL)
            if isinstance(direct_data, list) and len(direct_data) > 0:
                product_1016_found = direct_data[0]
                logger.info("ℹ️ Producto 1016 consultado mediante endpoint directo (está más allá del índice 299).")
        except Exception as e:
            logger.warning(f"No se pudo consultar el producto 1016 directamente: {e}")

    if product_1016_found:
        sanitized_1016 = sanitize_product_for_diff(product_1016_found)
        s1016 = extract_product_summary(product_1016_found)

        if old_1016_snapshot is None:
            logger.info(f"ℹ️ Primer registro guardado para Producto 1016 ('{s1016['name']}').")
            logger.info(f"   Valores iniciales: Precio=${s1016['price']} | Stock={s1016['stock']} | Disp={s1016['available']}")
            state["product_1016_snapshot"] = sanitized_1016
        else:
            diffs = compare_product_parameters(old_1016_snapshot, sanitized_1016)
            if diffs:
                change_lines = [
                    f"El producto de control ID {TARGET_PRODUCT_ID} ('{s1016['name']}') fue modificado.",
                    f"Resumen actual: Precio=${s1016['price']} | Stock={s1016['stock']} | Disponible={s1016['available']}",
                    f"Enlace: {s1016['link']}",
                    "\nParámetros modificados detectados:"
                ]
                for d in diffs[:25]:
                    change_lines.append(f"  {d}")
                if len(diffs) > 25:
                    change_lines.append(f"  ... y {len(diffs) - 25} cambios adicionales.")

                full_p1016_alert = "\n".join(change_lines)
                logger.warning("⚠️ ¡CAMBIOS EN PRODUCTO 1016 DETECTADOS!\n" + full_p1016_alert)
                append_alert_to_text_file("PRODUCTO 1016 MODIFICADO (Unidad De Prueba Ecommerce)", change_lines)
                send_external_alert("⚠️ ¡ACTUALIZACIÓN EN PRODUCTO 1016 TRENDY SHOP!\n" + full_p1016_alert)

                state["product_1016_snapshot"] = sanitized_1016
            else:
                logger.info(f"✅ Producto 1016 sin modificaciones (Precio: ${s1016['price']}, Stock: {s1016['stock']}, Disp: {s1016['available']}).")
    else:
        logger.warning("⚠️ No fue posible obtener datos del Producto 1016 en este ciclo.")

    # 8. GUARDAR ESTADO PERSISTENTE
    state["known_catalog_product_ids"] = list(known_catalog_ids)
    state["known_keyword_product_ids"] = list(known_keyword_ids)
    state["last_run"] = now_str
    save_state(state)
    logger.info("Fin de la revisión. Estado y catálogo guardados con éxito.")


# ==========================================================
# PUNTO DE ENTRADA
# ==========================================================
def main():
    if "--once" in sys.argv:
        run_monitoring_cycle()
        return

    logger.info("Iniciando Trendy Shop Monitor en modo continuo (cada 30 minutos).")
    logger.info(f"Archivo de alertas: {ALERTS_FILE}")
    logger.info("Presiona Ctrl + C para detener el programa.\n")

    try:
        while True:
            run_monitoring_cycle()
            logger.info(f"Próxima revisión en 30 minutos ({CHECK_INTERVAL_SECONDS} seg). En espera...\n")
            time.sleep(CHECK_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("\nPrograma detenido manualmente. ¡Hasta luego!")


if __name__ == "__main__":
    main()
