# CaciqueX VIP Bot

Esta carpeta contiene una copia independiente del bot para un repositorio privado de GitHub. Conserva los destinos y botones existentes de 🏆🎟GoldPass y Freeclub, además de las funciones actuales del bot y las mejoras del panel `/admin`.

## Archivos

- `main.py`: código del bot, panel de administración y webhook.
- `botones_goldpass.json` y `botones_freeclub.json`: botones actuales de ambos destinos.
- `portada.jpg` y `welcome-photo.jpg`: imágenes usadas por el bot.
- `pyproject.toml` y `uv.lock`: dependencias y versiones fijadas.
- `.gitignore`: excluye datos locales y secretos.

`generated-icon.png` se omite porque el código no lo utiliza. La carpeta comprimida tiene menos de 100 archivos.

## Cambios del panel `/admin`

- **Ver y administrar botones** muestra una vista previa con el teclado real y permite crear o eliminar botones.
- **Enviar a grupo o canal** permite elegir entre 🏆🎟GoldPass, Freeclub y los destinos adicionales que se agreguen.
- **Grupos y canales** conserva los destinos existentes y permite agregar más. El bot debe estar en el grupo o ser administrador del canal para publicar.
- **Mensajes recurrentes** permite elegir un destino y un intervalo (`30m`, `2h`, `1d`, etc.). El primer envío ocurre al terminar el intervalo; cuando se publica el siguiente, el bot intenta borrar el recurrente anterior de ese destino. Para borrar mensajes, Telegram debe concederle al bot los permisos necesarios.

Las publicaciones recurrentes y los destinos adicionales se guardan en `config.json`, que se genera durante el uso y no se incluye en el ZIP.

## Instalación y webhook

Usa Python 3.11 o posterior y ejecuta `uv sync --locked` desde esta carpeta. El comando de inicio es `uv run main.py`.

En Render configura `TELEGRAM_TOKEN`, `GEMINI_API_KEY` y `RENDER_EXTERNAL_URL` (o `WEBHOOK_URL`) como variables de entorno del servicio. `GEMINI_API_KEY` debe contener únicamente la clave completa de Google AI Studio; no se necesita el nombre ni el número del proyecto. No guardes claves en GitHub. Sin la clave de Gemini, el bot conserva el saludo de texto de respaldo en vez de personalizarlo.

La llamada a Gemini espera hasta 30 segundos. Puedes cambiarlo en Render con `GEMINI_TIMEOUT_SECONDS` (se limita a 10–60 segundos). Para respuestas más rápidas, puedes configurar `GEMINI_MODEL=gemini-3.5-flash-lite`; el modelo predeterminado es `gemini-3.8-flash`. Si Gemini devuelve `503 UNAVAILABLE`, el bot reintenta hasta dos veces con espera progresiva antes de usar el saludo de respaldo.

La respuesta contextual usa solo el primer mensaje o pie de foto de cada persona; no conserva el texto ni envía el historial. Gemini detecta el idioma del mensaje y responde en ese idioma, con un tono informal y slang natural para esa lengua; en español usa un toque venezolano. Evita forzar jerga, inventar datos o sonar como atención al cliente, y adapta la invitación al canal gratuito al mismo idioma. La foto y los botones se mantienen. Si Gemini no responde, se usa el saludo estático de respaldo.

En el flujo privado de acceso, `/start` pregunta primero el idioma (español, inglés, portugués o italiano) y Gemini puede conversar en ese idioma antes de abrir los métodos. La bienvenida incluye una invitación a pulsar el botón inferior; si Gemini falla, se usa un saludo localizado con esa misma indicación. En `/admin` → **Métodos de pago e imagen** → **Bienvenida de /start** puedes cambiar la foto y guardar instrucciones de estilo para Gemini; también puedes ver una vista previa en español. La foto de esta bienvenida se guarda por separado de la portada de pagos y del saludo de Telegram Business. La sesión conserva solo hasta cinco turnos recientes en memoria del proceso y caduca a los 30 minutos; no se guarda el historial en los archivos de datos. Gemini solo decide si el texto expresa claramente que la persona quiere ver los métodos: el menú, sus botones, comprobantes, aprobaciones y acceso siguen bajo el flujo existente del bot. El precio que se muestra es **$2 USD al mes**. Si Gemini falla, se envía una respuesta breve de respaldo y el botón para abrir los métodos sigue disponible.

El texto que invita a elegir un método de pago se genera en el idioma seleccionado y se agrega por separado del precio fijo. Si Gemini tarda o falla, el menú aparece con una frase localizada de respaldo; el precio, los métodos, las aprobaciones y el acceso no dependen de Gemini.

En `/admin` → **Métodos de pago e imagen** → **Compartir asistente**, escribe instrucciones para Gemini y revisa la invitación antes de enviarla. La foto es editable y distinta de la portada de pagos. Activa el modo inline en BotFather con `/setinline` para el bot cuyo token está en `TELEGRAM_TOKEN`. Para compartir, pulsa el botón, elige el chat y toca la tarjeta de foto que aparece; no envíes el texto `@bot compartir` como un mensaje. Si no aparece la tarjeta, revisa primero que inline mode esté activo para el bot correcto. El resultado enviado contiene solo la foto, el texto generado y el botón de inicio. El borrador dura hasta una hora y solo el administrador puede consultar el resultado. El botón enviado al contacto abre `https://t.me/CaciqueXmembot?start=payment`, así que ese usuario debe ser el bot que atiende el flujo de pago.

Después del despliegue, el administrador puede enviar `/gemini_test` al bot para probar la conexión desde Render. Solo responde al `ADMIN_ID` configurado y hace una solicitud normal a Gemini, facturada según la cuenta de Google. El comando no se ejecuta automáticamente. Un error `TimeoutError` significa que no llegó respuesta dentro del tiempo configurado; no demuestra que la clave sea incorrecta. Si continúa con 30–60 segundos, revisa el acceso de red saliente de Render y el estado del proyecto/cuota en AI Studio.

**No ejecutes esta copia con el token activo si quieres conservar el webhook actual.** Al arrancar, el código llama a `set_webhook` con la URL configurada y Telegram reemplaza la URL previa para ese token. Este ZIP solo prepara los archivos: no inicia el bot, no registra un webhook nuevo ni cambia la configuración activa.

## Datos locales

El ZIP completo incluye una copia de los archivos JSON presentes en este espacio de trabajo, incluidos ajustes de pago y registros de usuarios. Pueden contener información financiera o identificadores; guarda el archivo y el repositorio como privados y no lo publiques. Si Render tiene archivos más recientes en un disco persistente, conserva esos archivos y actualiza solo el código; no los reemplaces con esta copia local. Configura `BOT_DATA_DIR` para que apunte al disco persistente de Render.

### Guardar las imágenes con Supabase en Render

El identificador de la foto del menú de pagos, el de la bienvenida de `/start` y las instrucciones de esa bienvenida se guardan en Supabase cuando se configuran las variables siguientes en **Render → servicio → Environment**:

- `SUPABASE_URL`: URL del proyecto de Supabase.
- `SUPABASE_SECRET_KEY`: clave secreta del proyecto (normalmente empieza con `sb_secret_`). Si tu proyecto solo muestra la clave antigua `service_role`, el bot también la acepta mediante `SUPABASE_SERVICE_ROLE_KEY`. No pongas ninguna clave en GitHub ni la compartas por chat.

Antes del primer uso, abre el **SQL Editor** del proyecto Supabase, ejecuta el contenido de `supabase/schema.sql` una sola vez y despliega el bot. Si los antiguos archivos `config.json` o `payment_config.json` siguen presentes al iniciar, el bot copia de ellos las referencias de fotos a Supabase cuando la tabla todavía no tiene ajustes. Luego Supabase es la fuente persistente de esas referencias.

En la sección de fotos del panel de administración, el bot indica si Supabase respondió o si falta configurarlo. Si Supabase no responde al guardar una foto, el bot debe avisarlo y no confirmar el cambio como guardado. El plan gratuito de Supabase puede pausar un proyecto tras siete días con poca actividad; su documentación indica que se puede reanudar con sus datos y configuración durante un año. Tras una pausa, puede ser necesario reanudar el proyecto desde su panel.

La tabla `bot_persistent_settings` guarda las referencias de las fotos y los ajustes visuales; `bot_subscription_records` conserva el registro de accesos pagados y Free GoldPass cuando Supabase está configurado. Los métodos de pago, destinos y otros archivos de configuración siguen usando el almacenamiento local de Render, por lo que conviene conservar el disco persistente del servicio y no reemplazar sus archivos de estado al actualizar el código.

### Renovaciones con Telegram Stars

Al vencer una suscripción, el bot intenta retirar al usuario del canal privado y le ofrece **300 Stars** o los otros métodos de pago. Stars usa una factura real de Telegram (`XTR`), no un enlace de invitación; el pago confirmado extiende el acceso 30 días y registra el identificador del cargo para evitar duplicarlo. El usuario recibe un botón de acceso personal que solo funciona para su cuenta.

Si Telegram rechaza una expulsión, el bot conserva el vencimiento pendiente en el historial y vuelve a intentarlo cada minuto. Para completar la expulsión, el bot debe ser administrador de `-1003914257220` con permiso para restringir miembros. Para emitir enlaces personales, también necesita permiso para invitar usuarios.

Si falla el acceso, el administrador puede enviar `/goldpass_check` en el chat privado del bot. El diagnóstico muestra qué bot está usando Render, qué canal reconoce Telegram y si tiene permisos para invitar o expulsar; nunca muestra el token.
