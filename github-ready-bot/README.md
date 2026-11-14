# CaciqueX VIP Bot

Esta carpeta contiene una copia independiente del bot para un repositorio privado de GitHub. Conserva los destinos y botones existentes de GoldPass y Freeclub, además de las funciones actuales del bot y las mejoras del panel `/admin`.

## Archivos

- `main.py`: código del bot, panel de administración y webhook.
- `botones_goldpass.json` y `botones_freeclub.json`: botones actuales de ambos destinos.
- `portada.jpg` y `welcome-photo.jpg`: imágenes usadas por el bot.
- `pyproject.toml` y `uv.lock`: dependencias y versiones fijadas.
- `.gitignore`: excluye datos locales y secretos.

`generated-icon.png` se omite porque el código no lo utiliza. La carpeta comprimida tiene menos de 100 archivos.

## Cambios del panel `/admin`

- **Ver y administrar botones** muestra una vista previa con el teclado real y permite crear o eliminar botones.
- **Enviar a grupo o canal** permite elegir entre GoldPass, Freeclub y los destinos adicionales que se agreguen.
- **Grupos y canales** conserva los destinos existentes y permite agregar más. El bot debe estar en el grupo o ser administrador del canal para publicar.
- **Mensajes recurrentes** permite elegir un destino y un intervalo (`30m`, `2h`, `1d`, etc.). El primer envío ocurre al terminar el intervalo; cuando se publica el siguiente, el bot intenta borrar el recurrente anterior de ese destino. Para borrar mensajes, Telegram debe concederle al bot los permisos necesarios.

Las publicaciones recurrentes y los destinos adicionales se guardan en `config.json`, que se genera durante el uso y no se incluye en el ZIP.

## Instalación y webhook

Usa Python 3.11 o posterior y ejecuta `uv sync --locked` desde esta carpeta. El comando de inicio es `uv run main.py`.

En Render configura `TELEGRAM_TOKEN`, `GEMINI_API_KEY` y `RENDER_EXTERNAL_URL` (o `WEBHOOK_URL`) como variables de entorno del servicio. `GEMINI_API_KEY` debe contener únicamente la clave completa de Google AI Studio; no se necesita el nombre ni el número del proyecto. No guardes claves en GitHub. Sin la clave de Gemini, el bot conserva el saludo de texto de respaldo en vez de personalizarlo.

La respuesta contextual usa solo el primer mensaje o pie de foto de cada persona; no conserva el texto ni envía el historial. Gemini genera una frase breve y el bot añade la invitación fija, la foto y los botones.

Después del despliegue, el administrador puede enviar `/gemini_test` al bot para probar la conexión desde Render. Solo responde al `ADMIN_ID` configurado y hace una solicitud normal a Gemini, facturada según la cuenta de Google. El comando no se ejecuta automáticamente.

**No ejecutes esta copia con el token activo si quieres conservar el webhook actual.** Al arrancar, el código llama a `set_webhook` con la URL configurada y Telegram reemplaza la URL previa para ese token. Este ZIP solo prepara los archivos: no inicia el bot, no registra un webhook nuevo ni cambia la configuración activa.

## Datos locales

`config.json`, `payment_config.json`, `usuarios.json`, `business_welcome_users.json` y las bases de datos locales se crean o modifican durante la ejecución y están excluidos del ZIP. Conserva las copias del servicio de Render: pueden contener destinos, pagos, suscripciones y registros que no deben reemplazarse al subir este código. Mantén el repositorio privado porque el código contiene enlaces actuales del bot.
