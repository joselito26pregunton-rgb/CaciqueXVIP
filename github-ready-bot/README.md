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

La llamada a Gemini espera hasta 30 segundos. Puedes cambiarlo en Render con `GEMINI_TIMEOUT_SECONDS` (se limita a 10–60 segundos). Para respuestas más rápidas, puedes configurar `GEMINI_MODEL=gemini-3.5-flash-lite`; el modelo predeterminado es `gemini-3.8-flash`. Si Gemini devuelve `503 UNAVAILABLE`, el bot reintenta hasta dos veces con espera progresiva antes de usar el saludo de respaldo.

La respuesta contextual usa solo el primer mensaje o pie de foto de cada persona; no conserva el texto ni envía el historial. Gemini detecta el idioma del mensaje y responde en ese idioma, con un tono informal y slang natural para esa lengua; en español usa un toque venezolano. Evita forzar jerga, inventar datos o sonar como atención al cliente, y adapta la invitación al canal gratuito al mismo idioma. La foto y los botones se mantienen. Si Gemini no responde, se usa el saludo estático de respaldo.

En el flujo privado de acceso, `/start` pregunta primero el idioma (español, inglés, portugués o italiano) y Gemini puede conversar en ese idioma antes de abrir los métodos. La sesión conserva solo hasta cinco turnos recientes en memoria del proceso y caduca a los 30 minutos; no se guarda el historial en los archivos de datos. Gemini solo decide si el texto expresa claramente que la persona quiere ver los métodos: el menú, sus botones, comprobantes, aprobaciones y acceso siguen bajo el flujo existente del bot. El precio que se muestra es **$2 USD al mes**. Si Gemini falla, se envía una respuesta breve de respaldo y el botón para abrir los métodos sigue disponible.

En `/admin` → **Métodos de pago e imagen** → **Compartir asistente**, Gemini genera el texto de invitación y se muestra una vista previa con una foto editable y un botón al flujo `/start payment`. El botón de compartir usa el modo inline de Telegram: activa ese modo en BotFather con `/setinline` para el bot cuyo token está en `TELEGRAM_TOKEN`. Luego, en la vista previa, pulsa **Elegir contacto para compartir**, selecciona un chat y toca el resultado de foto para enviarlo. El texto/foto de la vista previa se conserva temporalmente en memoria hasta una hora y la consulta inline está restringida al administrador. La imagen de esta invitación es independiente de la portada de pagos. El botón enviado al contacto abre `https://t.me/CaciqueXmembot?start=payment`, así que ese usuario debe ser el bot que atiende el flujo de pago.

Después del despliegue, el administrador puede enviar `/gemini_test` al bot para probar la conexión desde Render. Solo responde al `ADMIN_ID` configurado y hace una solicitud normal a Gemini, facturada según la cuenta de Google. El comando no se ejecuta automáticamente. Un error `TimeoutError` significa que no llegó respuesta dentro del tiempo configurado; no demuestra que la clave sea incorrecta. Si continúa con 30–60 segundos, revisa el acceso de red saliente de Render y el estado del proyecto/cuota en AI Studio.

**No ejecutes esta copia con el token activo si quieres conservar el webhook actual.** Al arrancar, el código llama a `set_webhook` con la URL configurada y Telegram reemplaza la URL previa para ese token. Este ZIP solo prepara los archivos: no inicia el bot, no registra un webhook nuevo ni cambia la configuración activa.

## Datos locales

`config.json`, `payment_config.json`, `usuarios.json`, `business_welcome_users.json` y las bases de datos locales se crean o modifican durante la ejecución y están excluidos del ZIP. Conserva las copias del servicio de Render: pueden contener destinos, pagos, suscripciones y registros que no deben reemplazarse al subir este código. Mantén el repositorio privado porque el código contiene enlaces actuales del bot.
