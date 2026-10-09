# Bot de Telegram — carpeta para GitHub

Esta carpeta es una copia independiente del bot. Contiene sus archivos de código, dependencias, botones y fotos necesarios para conservar las funciones actuales, incluido el saludo de Telegram Business.

**La carpeta original `telegram-bot/` y el ZIP recibido no se modificaron.**

## Archivos incluidos

- `main.py`: comandos, pagos, administración, webhook y saludo automático de Telegram Business.
- `botones_freeclub.json` y `botones_goldpass.json`: botones y enlaces de cada canal.
- `portada.jpg` y `welcome-photo.jpg`: imágenes usadas por el bot.
- `pyproject.toml` y `uv.lock`: dependencias y versiones fijadas.
- `.gitignore`: excluye secretos y datos que se generan durante la ejecución.

El paquete tiene menos de 100 archivos. Se omitió `generated-icon.png` porque el código no lo usa.

## Preparación

1. Sube **solo el contenido de esta carpeta** a un repositorio privado de GitHub; no subas la raíz completa del proyecto.
2. Usa Python 3.11 o posterior y ejecuta `uv sync --locked` para instalar las dependencias.
3. Configura `TELEGRAM_TOKEN` y la URL pública en las variables seguras del servidor. No escribas el token en un archivo que vayas a subir.
4. Ejecuta `uv run python main.py` desde esta carpeta, porque algunos archivos se buscan usando rutas relativas.

El archivo `main.py` registra el webhook al arrancar, usando `RENDER_EXTERNAL_URL` o `WEBHOOK_URL`. Como pediste conservar el webhook actual, **no inicies esta copia con el token del bot activo**: podría redirigir las actualizaciones de Telegram. La carpeta está preparada para GitHub, pero no se ha conectado ni activado.

## Datos locales

`config.json`, `usuarios.json` y `business_welcome_users.json` se crean o modifican mientras el bot funciona. `.gitignore` los excluye junto con `.env`, las bases de datos locales y los archivos temporales.

El código contiene la configuración de pagos, contacto y enlaces actual. Mantén este repositorio **privado**.
