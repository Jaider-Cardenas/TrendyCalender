/**
 * Trendy Shop Monitor - Monitoreo Integral de Catálogo (Node.js)
 * ==============================================================
 * Monitorea los 6 bloques de productos del catálogo de Trendy Shop (0..299):
 * 1. Revisa todos los productos en los rangos 0..49, 50..99, 100..149, 150..199, 200..249, 250..299.
 * 2. Avisa cuando se agregan nuevos productos al catálogo.
 * 3. Detecta y lista productos con palabras clave: 'adviento', 'wonderland', etc.
 * 4. Alerta sobre cambios en el producto 1016 ("Unidad De Prueba Ecommerce").
 * 5. Registra cada alerta en 'alertas_trendy.txt' con fecha, hora y detalle de cambios.
 */

const fs = require('fs');
const path = require('path');

const CATALOG_URLS = [
    "https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?_from=0&_to=49",
    "https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?_from=50&_to=99",
    "https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?_from=100&_to=149",
    "https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?_from=150&_to=199",
    "https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?_from=200&_to=249",
    "https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?_from=250&_to=299"
];

const PRODUCT_1016_DIRECT_URL = "https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?fq=productId:1016";

const KEYWORDS = [
    "adviento",
    "calendario de adviento",
    "calendario adviento",
    "calendario-adviento",
    "wonderland",
    "calendario de adviento wonderland"
];

const TARGET_PRODUCT_ID = "1016";
const TARGET_PRODUCT_NAME_KEYWORD = "unidad de prueba ecommerce";
const CHECK_INTERVAL_MS = 30 * 60 * 1000; // 30 minutos
const REQUEST_DELAY_MS = 500; // Pausa de 500ms entre bloques

const STATE_FILE = path.join(__dirname, 'trendy_state.json');
const LOG_FILE = path.join(__dirname, 'trendy_monitor.log');
const ALERTS_FILE = path.join(__dirname, 'alertas_trendy.txt');

const DISCORD_WEBHOOK_URL = process.env.DISCORD_WEBHOOK_URL || "";
const TELEGRAM_BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN || "";
const TELEGRAM_CHAT_ID = process.env.TELEGRAM_CHAT_ID || "";

const HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"
};

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function getNowString() {
    return new Date().toISOString().replace('T', ' ').substring(0, 19);
}

function log(msg, level = 'INFO') {
    const time = getNowString();
    const line = `[${time}] ${level}: ${msg}`;
    console.log(line);
    try {
        fs.appendFileSync(LOG_FILE, line + '\n', 'utf8');
    } catch (e) {}
}

function appendAlertToTextFile(alertType, lines) {
    const time = getNowString();
    const block = [
        "=".repeat(80),
        `FECHA Y HORA: ${time}`,
        `TIPO DE ALERTA: ${alertType}`,
        "-".repeat(80),
        ...lines,
        "=".repeat(80) + "\n\n"
    ].join('\n');

    try {
        fs.appendFileSync(ALERTS_FILE, block, 'utf8');
        log(`📝 Alerta anotada en '${path.basename(ALERTS_FILE)}'.`);
    } catch (e) {
        log(`Error escribiendo en ${ALERTS_FILE}: ${e.message}`, 'ERROR');
    }
}

async function sendAlert(message) {
    if (DISCORD_WEBHOOK_URL) {
        try {
            await fetch(DISCORD_WEBHOOK_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: message })
            });
            log("Notificación enviada a Discord.");
        } catch (e) {
            log(`Error Discord: ${e.message}`, 'ERROR');
        }
    }

    if (TELEGRAM_BOT_TOKEN && TELEGRAM_CHAT_ID) {
        try {
            const tgUrl = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`;
            await fetch(tgUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    chat_id: TELEGRAM_CHAT_ID,
                    text: message,
                    parse_mode: 'Markdown'
                })
            });
            log("Notificación enviada a Telegram.");
        } catch (e) {
            log(`Error Telegram: ${e.message}`, 'ERROR');
        }
    }
}

function loadState() {
    if (fs.existsSync(STATE_FILE)) {
        try {
            return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8'));
        } catch (e) {
            log(`No se pudo leer estado: ${e.message}`, 'WARN');
        }
    }
    return {
        known_catalog_product_ids: [],
        known_keyword_product_ids: [],
        product_1016_snapshot: null,
        is_baseline_established: false,
        last_run: null
    };
}

function saveState(state) {
    try {
        fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2), 'utf8');
    } catch (e) {
        log(`Error guardando estado: ${e.message}`, 'ERROR');
    }
}

function extractSummary(p) {
    const pid = String(p.productId || 'N/A');
    const name = p.productName || 'Sin nombre';
    const link = p.link || `https://www.maquillajetrendyshop.com/${p.linkText || ''}/p`;
    const item = (p.items || [])[0] || {};
    const seller = (item.sellers || [])[0] || {};
    const offer = seller.commertialOffer || {};

    return {
        id: pid,
        name: name,
        link: link,
        price: offer.Price ?? 'N/A',
        stock: offer.AvailableQuantity ?? 'N/A',
        available: offer.IsAvailable ?? 'N/A'
    };
}

function matchesKeywords(product) {
    const name = (product.productName || '').toLowerCase();
    const title = (product.productTitle || '').toLowerCase();
    const full = `${name} ${title}`;

    const matched = [];
    for (const kw of KEYWORDS) {
        if (full.includes(kw.toLowerCase())) {
            matched.push(kw);
        }
    }
    return { isMatch: matched.length > 0, matched };
}

function sanitizeProduct(product) {
    if (!product || typeof product !== 'object') return product;
    if (Array.isArray(product)) return product.map(sanitizeProduct);

    const clean = {};
    for (const [k, v] of Object.entries(product)) {
        if (k === 'PriceToken' || k === 'CacheVersionUsedToCallCheckout') continue;
        clean[k] = sanitizeProduct(v);
    }
    return clean;
}

function findDiffs(oldObj, newObj, path = '') {
    const diffs = [];
    if (typeof oldObj !== typeof newObj) {
        return [`${path}: tipo cambió de ${typeof oldObj} a ${typeof newObj}`];
    }
    if (oldObj && typeof oldObj === 'object') {
        if (Array.isArray(oldObj) && Array.isArray(newObj)) {
            if (oldObj.length !== newObj.length) {
                diffs.push(`${path}: cantidad de elementos (${oldObj.length} -> ${newObj.length})`);
            }
            const minLen = Math.min(oldObj.length, newObj.length);
            for (let i = 0; i < minLen; i++) {
                diffs.push(...findDiffs(oldObj[i], newObj[i], `${path}[${i}]`));
            }
        } else {
            const allKeys = new Set([...Object.keys(oldObj || {}), ...Object.keys(newObj || {})]);
            for (const k of Array.from(allKeys).sort()) {
                const subPath = path ? `${path}.${k}` : k;
                if (!(k in oldObj)) {
                    diffs.push(`➕ Parámetro agregado [${subPath}] = ${JSON.stringify(newObj[k])}`);
                } else if (!(k in newObj)) {
                    diffs.push(`➖ Parámetro eliminado [${subPath}] (era: ${JSON.stringify(oldObj[k])})`);
                } else {
                    diffs.push(...findDiffs(oldObj[k], newObj[k], subPath));
                }
            }
        }
    } else {
        if (oldObj !== newObj) {
            diffs.push(`✏️ [${path}]: '${oldObj}' ➔ '${newObj}'`);
        }
    }
    return diffs;
}

async function runMonitoringCycle() {
    const now = getNowString();
    log("============================================================================");
    log(`INICIANDO REVISIÓN COMPLETA DEL CATÁLOGO TRENDY SHOP - ${now}`);
    log(`Revisando ${CATALOG_URLS.length} bloques de productos (índices 0 al 299)...`);
    log("============================================================================");

    const state = loadState();
    const knownCatalogIds = new Set(state.known_catalog_product_ids || []);
    const knownKeywordIds = new Set(state.known_keyword_product_ids || []);
    let old1016 = state.product_1016_snapshot;
    let isBaseline = state.is_baseline_established;

    const allCurrentProducts = new Map();
    let totalFetched = 0;

    for (let i = 0; i < CATALOG_URLS.length; i++) {
        const url = CATALOG_URLS[i];
        try {
            log(`[${i + 1}/${CATALOG_URLS.length}] Consultando: ${url}`);
            const res = await fetch(url, { headers: HEADERS });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const batch = await res.json();
            if (Array.isArray(batch)) {
                totalFetched += batch.length;
                for (const p of batch) {
                    const pid = String(p.productId || '');
                    if (pid && !allCurrentProducts.has(pid)) {
                        allCurrentProducts.set(pid, p);
                    }
                }
            }
        } catch (e) {
            log(`Error en bloque ${i + 1}: ${e.message}`, 'ERROR');
        }
        await sleep(REQUEST_DELAY_MS);
    }

    log(`Total productos recibidos: ${totalFetched} | Productos únicos consolidados: ${allCurrentProducts.size}`);

    const matchingKeywords = [];
    const newKeywordProducts = [];
    const newlyAddedCatalog = [];
    let p1016 = null;

    for (const [pid, p] of allCurrentProducts.entries()) {
        const s = extractSummary(p);
        const pname = s.name.toLowerCase();

        if (pid === TARGET_PRODUCT_ID || pname.includes(TARGET_PRODUCT_NAME_KEYWORD)) {
            p1016 = p;
        }

        const { isMatch, matched } = matchesKeywords(p);
        if (isMatch) {
            matchingKeywords.push({ product: p, matched });
            if (!knownKeywordIds.has(pid)) {
                newKeywordProducts.push({ product: p, matched });
                knownKeywordIds.add(pid);
            }
        }

        if (isBaseline && !knownCatalogIds.has(pid)) {
            newlyAddedCatalog.push(p);
            knownCatalogIds.add(pid);
        }
    }

    // 3. ENUMERAR CADA 30 MINUTOS
    console.log("\n" + "-".repeat(75));
    console.log(`📋 PRODUCTOS QUE COINCIDEN CON LA BÚSQUEDA ('adviento' / 'wonderland'):`);
    console.log(`   Total encontrados en los 6 bloques: ${matchingKeywords.length}`);
    console.log("-".repeat(75));
    if (matchingKeywords.length > 0) {
        matchingKeywords.forEach(({ product, matched }, idx) => {
            const s = extractSummary(product);
            console.log(`  [${idx + 1}] ID: ${s.id} | Nombre: ${s.name}`);
            console.log(`      Precio: $${s.price} | Stock: ${s.stock} | Disponible: ${s.available}`);
            console.log(`      Palabras detectadas: ${matched.join(', ')}`);
            console.log(`      Enlace: ${s.link}`);
        });
    } else {
        console.log("  (Ningún producto en los rangos 0..299 contiene 'adviento' o 'wonderland')");
    }
    console.log("-".repeat(75) + "\n");

    // 4. LÍNEA BASE
    if (!isBaseline) {
        for (const pid of allCurrentProducts.keys()) {
            knownCatalogIds.add(pid);
        }
        state.is_baseline_established = true;
        log(`✅ Línea base registrada: ${knownCatalogIds.size} productos almacenados.`);

        const initLines = [
            `Inicio de monitoreo en 6 bloques (0 a 299).`,
            `Total de productos registrados como línea base: ${knownCatalogIds.size}.`,
            `Productos con palabras clave detectados inicialmente: ${matchingKeywords.length}.`
        ];
        if (matchingKeywords.length > 0) {
            initLines.push("\nProductos con 'adviento' o 'wonderland' existentes:");
            matchingKeywords.forEach(({ product }) => {
                const s = extractSummary(product);
                initLines.push(`  • ID ${s.id}: ${s.name} (Precio: $${s.price}, Stock: ${s.stock})`);
            });
        }
        appendAlertToTextFile("INICIO DE MONITOREO Y LÍNEA BASE", initLines);
    }

    // 5. NUEVOS PRODUCTOS AGREGADOS AL CATÁLOGO
    if (newlyAddedCatalog.length > 0) {
        const lines = [`Se detectaron ${newlyAddedCatalog.length} NUEVOS productos agregados al catálogo:\n`];
        for (const p of newlyAddedCatalog) {
            const s = extractSummary(p);
            const { isMatch, matched } = matchesKeywords(p);
            const kwNote = isMatch ? ` 🌟 ¡COINCIDE CON: ${matched.join(', ')}!` : '';
            lines.push(
                `• ID: ${s.id} | Nombre: ${s.name}${kwNote}\n` +
                `  Precio: $${s.price} | Stock: ${s.stock} | Disponible: ${s.available}\n` +
                `  Enlace: ${s.link}\n`
            );
        }
        const fullAlert = lines.join('\n');
        log("🚨 ¡NUEVOS PRODUCTOS EN EL CATÁLOGO!\n" + fullAlert, 'WARN');
        appendAlertToTextFile("NUEVO(S) PRODUCTO(S) AGREGADO(S) AL CATÁLOGO", lines);
        await sendAlert("🚨 ¡NUEVO PRODUCTO AGREGADO A TRENDY SHOP!\n" + fullAlert);
    }

    // 6. NUEVOS PRODUCTOS CON PALABRAS CLAVE
    if (newKeywordProducts.length > 0 && newlyAddedCatalog.length === 0) {
        const kwLines = [`Se detectaron ${newKeywordProducts.length} producto(s) nuevos con palabras clave de Adviento / Wonderland:\n`];
        for (const { product, matched } of newKeywordProducts) {
            const s = extractSummary(product);
            kwLines.push(
                `• ID: ${s.id} | Nombre: ${s.name}\n` +
                `  Palabras clave: ${matched.join(', ')}\n` +
                `  Precio: $${s.price} | Stock: ${s.stock}\n` +
                `  Enlace: ${s.link}\n`
            );
        }
        const fullKw = kwLines.join('\n');
        log("🚨 " + fullKw, 'WARN');
        appendAlertToTextFile("NUEVO PRODUCTO DE ADVIENTO / WONDERLAND DETECTADO", kwLines);
        await sendAlert("🚨 " + fullKw);
    }

    // 7. PRODUCTO 1016
    if (!p1016) {
        try {
            const resDirect = await fetch(PRODUCT_1016_DIRECT_URL, { headers: HEADERS });
            if (resDirect.ok) {
                const arr = await resDirect.json();
                if (Array.isArray(arr) && arr.length > 0) {
                    p1016 = arr[0];
                    log("ℹ️ Producto 1016 consultado mediante endpoint directo.");
                }
            }
        } catch (e) {
            log(`Error consultando producto 1016: ${e.message}`, 'WARN');
        }
    }

    if (p1016) {
        const sanitized = sanitizeProduct(p1016);
        const s1016 = extractSummary(p1016);

        if (!old1016) {
            log(`ℹ️ Primer registro guardado para Producto 1016 (Precio: $${s1016.price}, Stock: ${s1016.stock}, Disp: ${s1016.available}).`);
            state.product_1016_snapshot = sanitized;
        } else {
            const diffs = findDiffs(old1016, sanitized);
            if (diffs.length > 0) {
                const changeLines = [
                    `El producto de control ID ${TARGET_PRODUCT_ID} ('${s1016.name}') fue modificado.`,
                    `Resumen actual: Precio=$${s1016.price} | Stock=${s1016.stock} | Disponible=${s1016.available}`,
                    `Enlace: ${s1016.link}`,
                    "\nParámetros modificados detectados:",
                    ...diffs.slice(0, 25)
                ];
                if (diffs.length > 25) {
                    changeLines.append(`  ... y ${diffs.length - 25} cambios adicionales.`);
                }
                const alertMsg = changeLines.join('\n');
                log("⚠️ ¡CAMBIOS EN PRODUCTO 1016 DETECTADOS!\n" + alertMsg, 'WARN');
                appendAlertToTextFile("PRODUCTO 1016 MODIFICADO (Unidad De Prueba Ecommerce)", changeLines);
                await sendAlert("⚠️ ¡ACTUALIZACIÓN EN PRODUCTO 1016 TRENDY SHOP!\n" + alertMsg);
                state.product_1016_snapshot = sanitized;
            } else {
                log(`✅ Producto 1016 sin modificaciones (Precio: $${s1016.price}, Stock: ${s1016.stock}, Disp: ${s1016.available}).`);
            }
        }
    } else {
        log("⚠️ No fue posible obtener datos del Producto 1016.", 'WARN');
    }

    state.known_catalog_product_ids = Array.from(knownCatalogIds);
    state.known_keyword_product_ids = Array.from(knownKeywordIds);
    state.last_run = now;
    saveState(state);
    log("Fin de la revisión. Catálogo y estado guardados con éxito.\n");
}

async function main() {
    const isOnce = process.argv.includes('--once');
    if (isOnce) {
        await runMonitoringCycle();
        return;
    }

    log("Iniciando Trendy Shop Monitor en modo continuo (cada 30 minutos).");
    log(`Archivo de alertas: ${ALERTS_FILE}`);
    await runMonitoringCycle();
    setInterval(runMonitoringCycle, CHECK_INTERVAL_MS);
}

main();
