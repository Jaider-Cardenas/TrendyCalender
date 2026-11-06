# 🛍️ Trendy Shop Monitor (Adviento, Wonderland & Producto 1016)

Monitor automatizado del catálogo de Trendy Shop diseñado para vigilar **300 productos** (bloques de 0 a 299) a través de sus 6 enlaces oficiales de la API:
1. `.../search?_from=0&_to=49`
2. `.../search?_from=50&_to=99`
3. `.../search?_from=100&_to=149`
4. `.../search?_from=150&_to=199`
5. `.../search?_from=200&_to=249`
6. `.../search?_from=250&_to=299`

---

## 🎯 ¿Qué Hace el Programa?

1. **Revisión Continua de los 6 Enlaces**:
   - Descarga y consolida los productos de los 6 bloques en cada ciclo (cada 30 minutos).
   - Elimina duplicados si un producto aparece en el límite de paginación.

2. **Detección de Nuevos Productos Agregados**:
   - En la primera ejecución registra la **línea base** de productos existentes en la tienda.
   - En las siguientes ejecuciones, si detecta cualquier producto nuevo que antes no existía en el catálogo, **emite una alerta inmediata**.
   - Si el nuevo producto contiene palabras clave como `adviento` o `wonderland`, lo resalta con prioridad máxima.

3. **Búsqueda por Palabras Clave y Enumeración cada 30 min**:
   - Busca en `productName` y `productTitle` las palabras:
     `adviento`, `calendario de adviento`, `calendario adviento`, `calendario-adviento`, `wonderland`, `calendario de adviento wonderland`.
   - **Enumera en consola** en cada ciclo la lista de todos los productos encontrados que coincidan con estos términos.

4. **Monitoreo del Producto 1016 ("Unidad De Prueba Ecommerce")**:
   - Vigila sus parámetros comerciales (`Price`, `AvailableQuantity`, `IsAvailable`, título, descripción, etc.).
   - Limpia tokens dinámicos de sesión de VTEX (`PriceToken`) para evitar falsos positivos.
   - Si cambia algún valor, detalla exactamente el antes y después (ej. `AvailableQuantity: 0 ➔ 100`).
   - Posee un mecanismo de consulta directa que garantiza que nunca se pierda aunque el producto sea empujado fuera de los primeros 300 ítems.

5. **Archivo Dedicado de Alertas (`alertas_trendy.txt`)**:
   - Crea y actualiza un archivo de texto en el que anota de forma permanente:
     - 🕒 **Fecha y hora exacta** del evento.
     - 🆕 **Nuevos productos que agregaron**.
     - ✏️ **Productos que fueron cambiados** (parámetros modificados).
     - 🔍 **Productos detectados** con palabras clave de Adviento / Wonderland.

---

## 📁 Estructura de Archivos

```
trendy_monitor/
├── trendy_monitor.py      # Versión en Python (Recomendada para la nube: PythonAnywhere, GitHub Actions)
├── trendy_monitor.ps1     # Versión nativa en PowerShell (Lista para usar en Windows sin instalar nada)
├── trendy_monitor.js      # Versión en Node.js (fetch nativo para Vercel o servidores Node)
├── run_monitor.bat        # Lanzador inteligente para Windows (doble clic)
├── alertas_trendy.txt     # Historial permanente de alertas con fecha, hora y detalles
├── trendy_state.json      # Base de datos local del estado previo y catálogo
├── trendy_monitor.log     # Registro técnico de todas las revisiones
└── .github/
    └── workflows/
        └── trendy_monitor.yml # Automatización en la nube (GitHub Actions)
```

---

## 🚀 Cómo Ejecutarlo

### Método 1: En tu Windows (Inmediato, Sin Instalar Nada)
Haz doble clic en [`run_monitor.bat`](file:///C:/Users/Tic/.gemini/antigravity/scratch/trendy_monitor/run_monitor.bat) o corre en PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File .\trendy_monitor.ps1
```
*(Si quieres que corra una sola vez y finalice, agrega `-Once`)*.

### Método 2: Con Python
```bash
python trendy_monitor.py
```
*(Para una sola pasada: `python trendy_monitor.py --once`)*.

### Método 3: En la Nube 100% Gratis con GitHub Actions
1. Sube estos archivos a tu repositorio de GitHub.
2. El archivo `.github/workflows/trendy_monitor.yml` ejecutará la revisión cada 30 minutos de forma automática sin consumir recursos de tu computadora.
3. Si configuras un Webhook de Discord o Bot de Telegram en los Secrets del repositorio, recibirás las alertas en tu celular al momento.
