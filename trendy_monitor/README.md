# 🛍️ Trendy Shop Monitor (Adviento & Producto 1016)

Script en **Python** (y **Node.js**) diseñado para monitorear automáticamente el catálogo de Trendy Shop, detectar nuevos productos relacionados con **"Adviento"** y **"Wonderland"**, y alertar sobre cambios de parámetros en el producto de prueba **1016** (`Unidad De Prueba Ecommerce`).

---

## 📋 Características Principales

1. **Búsqueda Inteligente de Palabras Clave**:
   - Analiza los campos `productName` y `productTitle` (en minúsculas).
   - Palabras clave evaluadas: `adviento`, `calendario de adviento`, `calendario adviento`, `calendario-adviento`, `wonderland`, `calendario de adviento wonderland`.
   - Mantiene un registro de productos ya conocidos para alertar únicamente cuando se agregue un **nuevo** producto.
   - **Enumera cada 30 minutos** la lista completa de productos que coinciden con los términos de búsqueda.

2. **Seguimiento del Producto 1016 ("Unidad De Prueba Ecommerce")**:
   - Detecta si el producto está en el rango o lo consulta mediante endpoint directo si fue desplazado por nuevos productos.
   - Limpia tokens dinámicos de sesión (como `PriceToken` de JWT) para **evitar falsos positivos**.
   - Compara recursivamente todos los parámetros: precio, stock (`AvailableQuantity`), disponibilidad (`IsAvailable`), descripción, variaciones y especificaciones.
   - Emite una alerta detallando exactamente qué campo cambió (ejemplo: `Precio: $800 ➔ $150.000` o `AvailableQuantity: 0 ➔ 100`).

3. **Ejecución Flexible**:
   - **Modo continuo** (`python trendy_monitor.py`): Ejecución cada 30 minutos con `time.sleep`.
   - **Modo único** (`python trendy_monitor.py --once`): Corre una sola vez, guarda el estado y finaliza. Ideal para **Cron Jobs en la nube** o el **Programador de Tareas de Windows**.

4. **Notificaciones Opcionales (Discord / Telegram)**:
   - Además de mostrar en consola y guardar en `trendy_monitor.log`, puedes recibir alertas instantáneas en tu celular mediante un Webhook de Discord o un Bot de Telegram.

---

## 🚀 Requisitos e Instalación

### Opción A: Python (Recomendado)

1. Verifica tener instalado **Python 3.8+**:
   ```bash
   python --version
   ```
   *(Si no lo tienes en Windows, puedes instalarlo con: `winget install Python.Python.3.12`)*

2. Instala la librería `requests`:
   ```bash
   pip install -r requirements.txt
   ```
   *(Nota: Si no instalas requests, el script tiene un fallback automático usando la librería estándar `urllib`).*

3. Prueba una revisión inmediata:
   ```bash
   python trendy_monitor.py --once
   ```

4. Ejecútalo en bucle cada 30 minutos:
   ```bash
   python trendy_monitor.py
   ```

---

## 🌐 Opciones de Ejecución Automática (Gratis)

### Opción 1: GitHub Actions (En la Nube, 100% Gratis, Sin Servidor)
> ⭐ **La mejor opción si no quieres dejar tu PC encendida.**

El repositorio incluye el archivo listo en `.github/workflows/trendy_monitor.yml`:
1. Sube esta carpeta a un repositorio en **GitHub**.
2. GitHub Actions ejecutará automáticamente el script cada 30 minutos usando el cron `*/30 * * * *`.
3. *(Opcional)* En tu repositorio de GitHub ve a **Settings > Secrets and variables > Actions** y añade:
   - `DISCORD_WEBHOOK_URL`: (la URL de tu webhook de Discord)
   - O `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`
4. ¡Listo! Recibirás las alertas directo en tu celular sin gastar un centavo ni tener ninguna máquina encendida.

---

### Opción 2: PythonAnywhere (En la Nube, Gratuito)
1. Crea una cuenta gratuita en [PythonAnywhere.com](https://www.pythonanywhere.com/).
2. Sube el archivo `trendy_monitor.py`.
3. Ve a la pestaña **Tasks**.
4. En **Scheduled Tasks**, crea una tarea que se ejecute periódicamente con el comando:
   ```bash
   python3 /home/tu_usuario/trendy_monitor.py --once
   ```
   *(En la cuenta gratuita permite programar tareas diarias o puedes dejar un script Always-on con el bucle normal).*

---

### Opción 3: Programador de Tareas de Windows 10 / 11 (Local)
Si prefieres que se ejecute en tu propia computadora:

1. Presiona `Win + R`, escribe `taskschd.msc` y presiona Enter para abrir el **Programador de Tareas**.
2. En el panel derecho, haz clic en **Crear tarea básica...**
3. **Nombre**: `Trendy Shop Monitor`.
4. **Desencadenador**: Selecciona **Al iniciar sesión** o **Diariamente**.
5. En la configuración del desencadenador, marca **Repetir cada**: `30 minutos` durante `Indefinidamente`.
6. **Acción**: Selecciona **Iniciar un programa**.
   - **Programa o script**: `python` (o la ruta completa a tu `python.exe`).
   - **Agregar argumentos**: `trendy_monitor.py --once`
   - **Iniciar en**: La ruta de la carpeta del script (ejemplo: `C:\Users\Tic\.gemini\antigravity\scratch\trendy_monitor`).
7. Haz clic en **Finalizar**. La tarea se ejecutará en segundo plano cada 30 minutos sin molestarte.

---

## 🔔 Configuración de Notificaciones en Celular (Opcional)

Si deseas recibir las alertas en tiempo real en tu teléfono:

### Discord Webhook:
1. En tu servidor de Discord: **Editar Canal > Integraciones > Webhooks > Crear Webhook**.
2. Copia la URL del Webhook.
3. Puedes pegarla en la variable `DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/..."` dentro de `trendy_monitor.py` o configurarla como variable de entorno.

### Telegram:
1. Crea un bot con [@BotFather](https://t.me/botfather) y obtén tu token.
2. Obtén tu Chat ID con [@userinfobot](https://t.me/userinfobot).
3. Pega los valores en `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`.

---

## 📁 Estructura del Proyecto

```
trendy_monitor/
├── trendy_monitor.py      # Script principal en Python
├── trendy_monitor.js      # Versión alternativa en Node.js (fetch nativo)
├── run_monitor.bat        # Lanzador rápido para Windows
├── requirements.txt       # Dependencias de Python
├── trendy_state.json      # Guarda el estado de productos y snapshot de 1016
├── trendy_monitor.log     # Historial de revisiones y alertas emitidas
├── .github/
│   └── workflows/
│       └── trendy_monitor.yml  # Automatización gratuita en GitHub Actions
└── README.md              # Documentación y guía de despliegue
```
