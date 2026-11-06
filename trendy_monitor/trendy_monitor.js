/**
 * Trendy Shop Monitor - Calendario de Adviento & Producto 1016 (Node.js)
 * =====================================================================
 * Utiliza fetch nativo (Node.js 18+) para consultar la API de Trendy Shop.
 * Ejecución continua: node trendy_monitor.js
 * Ejecución única (Cron / Tarea Programada): node trendy_monitor.js --once
 */

const fs = require('fs');
const path = require('path');

const CATALOG_URL = "https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?_from=250&_to=299";
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

const STATE_FILE = path.join(__dirname, 'trendy_state.json');
const LOG_FILE = path.join(__dirname, 'trendy_monitor.log');

const DISCORD_WEBHOOK_URL = process.env.DISCORD_WEBHOOK_URL || "";
const TELEGRAM_BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN || "";
const TELEGRAM_CHAT_ID = process.env.TELEGRAM_CHAT_ID || "";

const HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"
};

function log(msg, level = 'INFO') {
    const time = new Date().toISOString().replace('T', ' ').substring(0, 19);
    const line = `[${time}] ${level}: ${msg}`;
    console.log(line);
    try {
        fs.appendFileSync(LOG_FILE, line + '\n', 'utf8');
    } catch (e) {
        // Ignorar si falla escritura
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
            log("Notificación enviada a Discord exitosamente.");
        } catch (e) {
            log(`Error enviando a Discord: ${e.message}`, 'ERROR');
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
            log("Notificación enviada a Telegram exitosamente.");
        } catch (e) {
            log(`Error enviando a Telegram: ${e.message}`, 'ERROR');
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
        known_keyword_product_ids: [],
        product_1016_snapshot: null,
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
    if (Array.isArray(product)) {
        return product.map(sanitizeProduct);
    }
    const clean = {};
    for (const [k, v] of Object.entries(product)) {
        // Eliminar tokens dinámicos efímeros de JWT de VTEX
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

async function runCycle() {
    log("======================================================================");
    log(`INICIANDO REVISIÓN DE CATÁLOGO TRENDY SHOP - ${new Date().toISOString()}`);
    log(`URL: ${CATALOG_URL}`);
    log("======================================================================");

    const state = loadState();
    const knownIds = new Set(state.known_keyword_product_ids || []);
    let old1016 = state.product_1016_snapshot;

    let products = [];
    try {
        const res = await fetch(CATALOG_URL, { headers: HEADERS });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        products = await res.json();
    } catch (e) {
        log(`Error al consultar catálogo: ${e.message}`, 'ERROR');
        return;
    }

    log(`Productos recibidos en bloque [250..299]: ${products.length}`);

    const matching = [];
    const newMatching = [];
    let p1016 = null;

    for (const p of products) {
        const pid = String(p.productId || '');
        const pname = (p.productName || '').toLowerCase();

        if (pid === TARGET_PRODUCT_ID || pname.includes(TARGET_PRODUCT_NAME_KEYWORD)) {
            p1016 = p;
        }

        const { isMatch, matched } = matchesKeywords(p);
        if (isMatch) {
            matching.push({ product: p, matched });
            if (!knownIds.has(pid)) {
                newMatching.push({ product: p, matched });
                knownIds.add(pid);
            }
        }
    }

    console.log("\n----------------------------------------------------------------------");
    console.log(`📋 LISTADO DE PRODUCTOS COINCIDENTES EN ESTE CICLO (${matching.length} encontrados):`);
    if (matching.length > 0) {
        matching.forEach(({ product, matched }, i) => {
            console.log(`  [${i + 1}] ID: ${product.productId} | Nombre: ${product.productName}`);
            console.log(`      Palabras detectadas: ${matched.join(', ')}`);
            console.log(`      Enlace: ${product.link || 'https://www.maquillajetrendyshop.com/' + product.linkText + '/p'}`);
        });
    } else {
        console.log("  (Ningún producto en este bloque contiene 'adviento' o 'wonderland')");
    }
    console.log("----------------------------------------------------------------------\n");

    if (newMatching.length > 0) {
        const lines = ["🚨 ¡ALERTA: NUEVO PRODUCTO DE ADVIENTO / WONDERLAND DETECTADO! 🚨"];
        for (const { product, matched } of newMatching) {
            lines.push(`• ID: ${product.productId}\n  Nombre: ${product.productName}\n  Coincidencias: ${matched.join(', ')}\n  Link: ${product.link}`);
        }
        const fullAlert = lines.join('\n');
        log(fullAlert, 'WARN');
        await sendAlert(fullAlert);
    }

    if (!p1016) {
        try {
            const resDirect = await fetch(PRODUCT_1016_DIRECT_URL, { headers: HEADERS });
            if (resDirect.ok) {
                const arr = await resDirect.json();
                if (Array.isArray(arr) && arr.length > 0) {
                    p1016 = arr[0];
                    log("ℹ️ Producto 1016 consultado mediante endpoint directo (no estaba en el rango 250..299).");
                }
            }
        } catch (e) {
            log(`Error consultando producto 1016 directo: ${e.message}`, 'WARN');
        }
    }

    if (p1016) {
        const sanitized = sanitizeProduct(p1016);
        const firstSeller = p1016.items?.[0]?.sellers?.[0]?.commertialOffer || {};
        const price = firstSeller.Price ?? 'N/A';
        const stock = firstSeller.AvailableQuantity ?? 'N/A';
        const available = firstSeller.IsAvailable ?? 'N/A';

        if (!old1016) {
            log(`ℹ️ Primer registro guardado para Producto 1016 (Precio: $${price}, Stock: ${stock}, Disp: ${available}).`);
            state.product_1016_snapshot = sanitized;
        } else {
            const diffs = findDiffs(old1016, sanitized);
            if (diffs.length > 0) {
                const alertMsg = [
                    "⚠️ ¡ALERTA: ACTUALIZACIÓN EN PRODUCTO 1016 (Unidad De Prueba Ecommerce)! ⚠️",
                    `Resumen actual: Precio=$${price} | Stock=${stock} | Disponible=${available}`,
                    "\nParámetros modificados detectados:",
                    ...diffs.slice(0, 20)
                ].join('\n');
                log(alertMsg, 'WARN');
                await sendAlert(alertMsg);
                state.product_1016_snapshot = sanitized;
            } else {
                log(`✅ Producto 1016 sin cambios (Precio: $${price}, Stock: ${stock}, Disp: ${available}).`);
            }
        }
    } else {
        log("⚠️ No se pudo obtener información del Producto 1016.", 'WARN');
    }

    state.known_keyword_product_ids = Array.from(knownIds);
    state.last_run = new Date().toISOString();
    saveState(state);
    log("Fin de la revisión. Estado guardado.\n");
}

async function main() {
    const isOnce = process.argv.includes('--once');
    if (isOnce) {
        await runCycle();
        return;
    }

    log("Iniciando Trendy Monitor en modo continuo (cada 30 minutos).");
    await runCycle();
    setInterval(runCycle, CHECK_INTERVAL_MS);
}

main();
