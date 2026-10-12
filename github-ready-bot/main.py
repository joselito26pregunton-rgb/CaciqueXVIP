import os, threading, time, json, hashlib, hmac, html, random, re, uuid, urllib.parse
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
import telebot
from telebot import types
from tinydb import TinyDB, Query
from flask import Flask, jsonify, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN = os.environ["TELEGRAM_TOKEN"]
ADMIN_ID = "7827130679"
CANAL_ID = "-1003914257220"
CanaL_ID = "-1003561176552"
GROUP_ADMIN_CONTACT_URL = "https://t.me/Ja2610X"
CANAL_INVITE_LINK = "https://t.me/+U7Kk_sC9pToxZjIx"
CANAL_INVITE_LINK_EXTERNO = "https://t.me/+xjHnFXb_QTY0NGEx"
LINK_GRUPO = "https://t.me/+DT-eLLYZ0g8wNmMx"
LINK_CANAL_GRATUITO = "https://t.me/+c6gutVsBfRw4YWUx"
MY_USER = GROUP_ADMIN_CONTACT_URL.rsplit("/", 1)[-1]
BOT_PAGO = "@CaciqueXmembot"
WEBHOOK_PATH = "/telegram-webhook"
WEBHOOK_SECRET = hashlib.sha256(f"telegram-webhook:{TOKEN}".encode()).hexdigest()
WEBHOOK_ALLOWED_UPDATES = [
    "message",
    "business_connection",
    "business_message",
    "callback_query",
    "chat_join_request",
    "chat_member",
    "my_chat_member",
]
app = Flask(__name__)
bot = telebot.TeleBot(TOKEN, parse_mode="Markdown", skip_pending=False)
_send_original = bot.send_message
def _send_compat(*args, **kwargs):
    kwargs.pop("_force_new_message", None)
    return _send_original(*args, **kwargs)
bot.send_message = _send_compat
_SEND_MESSAGE_ORIGINAL = bot.send_message

CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
CONFIG_LOCK = threading.RLock()
PAYMENT_CONFIG_FILE = os.path.join(BASE_DIR, "payment_config.json")
PAYMENT_CONFIG_LOCK = threading.RLock()
db = TinyDB(os.path.join(BASE_DIR, "usuarios.json"))
PANELES_PRIVADOS = db.table("paneles_privados")
TECLADOS_PRIVADOS = db.table("teclados_privados")
PANEL_QUERY = Query()
PANEL_LOCK = threading.RLock()
admin_estado = {}
solicitudes_pendientes = {}
solicitudes_info = {}
user_data = {}
ID_ULTIMA_INVITACION = {}
ULTIMOS_MSGS = {'reglas': None, 'admin': None, 'menu': None, 'compartir': None, 'start': None, 'reportar': None, 'anon': None}
reporte_msgs = {}
BUSINESS_WELCOME_FILE = os.path.join(BASE_DIR, "business_welcome_users.json")
BUSINESS_WELCOME_LOCK = threading.RLock()

# Saludo automático para perfiles conectados mediante Telegram Chat Automation
# (Secretary Mode). Los perfiles adicionales se autorizan con
# BUSINESS_PROFILE_IDS, separados por comas; las funciones de administración
# continúan limitadas al ADMIN_ID principal.
WELCOME_CHANNEL_URL = "https://t.me/+c6gutVsBfRw4YWUx"
WELCOME_X_URL = "https://x.com/joselito_a26"
WELCOME_INSTAGRAM_URL = "https://www.instagram.com/alemussett26/"
WELCOME_PHOTO_PATH = os.path.join(BASE_DIR, "welcome-photo.jpg")
WELCOME_MESSAGE = (
    "Hola, ¿qué tal? Gracias por escribirme.\n\n"
    "Si te interesa conocer un poco más de mí, te invito a mi canal gratuito "
    "de Telegram, sin ningún compromiso. También puedes encontrarme en mis redes:"
)

# Separate ZIP moderation data from the live payment/subscription database and config.json.
group_db = TinyDB(os.path.join(BASE_DIR, "database.json"))
Config = TinyDB(os.path.join(BASE_DIR, "group_rules.json"))
Blacklist = TinyDB(os.path.join(BASE_DIR, "blacklist.json"))
UltimaPromo = TinyDB(os.path.join(BASE_DIR, "ultima_promo.json"))
Warnings = TinyDB(os.path.join(BASE_DIR, "warnings.json"))
PromosAprobadas = TinyDB(os.path.join(BASE_DIR, "promos_aprobadas.json"))
RegistroActividad = TinyDB(os.path.join(BASE_DIR, "registro_actividad.json"))
Suscripciones = TinyDB(os.path.join(BASE_DIR, "suscripciones.json"))
Estadisticas = TinyDB(os.path.join(BASE_DIR, "stats.json"))
User = Query()

@app.route("/", methods=["GET"])
def home():
    return "Telegram bot alive", 200
@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status":"ok","process_alive":True}), 200
@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(received, WEBHOOK_SECRET):
        return "Unauthorized", 403
    if not request.is_json:
        return "Expected JSON", 415
    update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK", 200

def cargar_config():
    with CONFIG_LOCK:
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

def guardar_config(cfg):
    with CONFIG_LOCK:
        temporal = CONFIG_FILE + ".tmp"
        with open(temporal, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(temporal, CONFIG_FILE)

def actualizar_config(actualizar):
    with CONFIG_LOCK:
        cfg = cargar_config()
        actualizar(cfg)
        guardar_config(cfg)
        return cfg


GRUPO_ID = 0
# --- SEGURIDAD: ANTI-FLOOD ---
_flood_registro = {}
FLOOD_LIMITE = 5
FLOOD_VENTANA = 10

def es_flood(user_id):
    ahora = time.time()
    historial = _flood_registro.get(user_id, [])
    historial = [t for t in historial if ahora - t < FLOOD_VENTANA]
    historial.append(ahora)
    _flood_registro[user_id] = historial
    return len(historial) > FLOOD_LIMITE

COMANDOS_VALIDOS_PRIVADO = [
    "/start", "/menu", "/reglas", "/compartir", "/vchat", "/admin", "/reportar",
    "🏠 /start", "🏹 /menu", "📜 /reglas", "🚀 /compartir", "👤 /admin", "🔥 /vchat"
]

# --- LIBRERÍA ESTÉTICA EXPANDIDA (FUEGO PURO) ---
MSG_INVITACION_LARGO = (
    "🏹 **HAS SIDO INVITADO AL TEMPLO DEL CACIQUE**\n\n"
    "Únete a la tribu más exclusiva de Telegram. Contenido único, las mejores fotos y "
    "videos de los guerreros más calientes de la tribu. 🔥\n\n"
    f"ÚNETE AQUÍ: {LINK_GRUPO}"
)
MSG_ENCODED = urllib.parse.quote(MSG_INVITACION_LARGO)
LINK_SHARE = f"https://t.me/share/url?url={MSG_ENCODED}"
TEXTOS_VC_HOT = [
    "🔥 **¡EL TEMPLO ESTÁ ARDIENDO!** 🔥\n¿Quieres acción real? Pincha el botón y entra al videochat, aquí mandas tú. 🔞",
    "😈 **¡ADRENALINA PURA EN VIVO!** 💦\nEntra ahora al videochat y mira lo que los guerreros tienen para ti. 🔥",
    "🍌 **¡EL CACIQUE ESTÁ ACTIVO Y FOGOSO!** 🔞\nLa temperatura está al máximo. Entra al videochat ahora. 🏹",
    "🍑 **LA TRIBU SE PONE CALIENTE...** 🔥\nDale al botón y únete a la fiesta privada en vivo. 💦",
    "🔱 **CONCILIO DE GUERREROS EN VIVO** 🔞\n¿Te atreves a mirar? Pincha abajo y entra al círculo de fuego. 🔥",
    "💥 **¡EXPLOSIÓN DE PLACER EN DIRECTO!** 🔞\nEl videochat está encendido. ¿Y tú? 🏹",
    "🔥 **¡SÓLO PARA VALIENTES!** 🔞\nEntra al videochat y descubre por qué somos la tribu más dominante. 💦"
]
EMOJIS_ACCION = ["🚀", "🔥", "💦", "🔞", "🏹", "🔱", "🍑", "🍌", "💥", "🥵", "💎", "🛡️", "⚔️", "😈"]

def eliminar_mensaje_seguro(chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
    except:
        pass


def _perfiles_business_autorizados():
    perfiles = {str(ADMIN_ID)}
    perfiles.update(
        item.strip()
        for item in os.environ.get("BUSINESS_PROFILE_IDS", "").split(",")
        if item.strip().isdigit()
    )
    return perfiles


def _markup_bienvenida_business():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton("📢 Canal gratuito", url=WELCOME_CHANNEL_URL),
        types.InlineKeyboardButton("𝕏 X", url=WELCOME_X_URL),
    )
    markup.add(
        types.InlineKeyboardButton("📸 Instagram", url=WELCOME_INSTAGRAM_URL)
    )
    return markup


def _business_saludo_key(profile_id, recipient_id):
    profile_key = hashlib.sha256(str(profile_id).encode("utf-8")).hexdigest()[:16]
    recipient_key = hashlib.sha256(str(recipient_id).encode("utf-8")).hexdigest()[:16]
    return f"{profile_key}:{recipient_key}"


def _marcar_business_saludo_enviado(profile_id, recipient_id):
    with BUSINESS_WELCOME_LOCK:
        try:
            with open(BUSINESS_WELCOME_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        sent = data.setdefault("sent", {})
        if not isinstance(sent, dict):
            sent = {}
            data["sent"] = sent
        sent[_business_saludo_key(profile_id, recipient_id)] = {
            "sent_at": datetime.now(timezone.utc).isoformat()
        }
        temporary = BUSINESS_WELCOME_FILE + ".tmp"
        with open(temporary, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        os.replace(temporary, BUSINESS_WELCOME_FILE)


def _business_saludo_ya_enviado(profile_id, recipient_id):
    with BUSINESS_WELCOME_LOCK:
        try:
            with open(BUSINESS_WELCOME_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            return False
        sent = data.get("sent", {}) if isinstance(data, dict) else {}
        return _business_saludo_key(profile_id, recipient_id) in sent


@bot.business_message_handler(
    content_types=[
        "text", "photo", "video", "document", "audio", "animation", "voice",
        "video_note", "sticker", "contact", "location", "venue", "poll",
        "dice", "game", "invoice", "successful_payment", "web_app_data",
    ]
)
def responder_primer_contacto_business(message):
    connection_id = getattr(message, "business_connection_id", None)
    sender = getattr(message, "from_user", None)
    if (
        not connection_id
        or getattr(getattr(message, "chat", None), "type", None) != "private"
        or sender is None
        or getattr(sender, "is_bot", False)
    ):
        return

    try:
        connection = bot.get_business_connection(connection_id)
    except Exception:
        app.logger.warning("No se pudo validar una conexión de Chat Automation.")
        return

    profile_id = str(getattr(getattr(connection, "user", None), "id", ""))
    rights = getattr(connection, "rights", None)
    if (
        not getattr(connection, "is_enabled", False)
        or not rights
        or not getattr(rights, "can_reply", False)
        or profile_id not in _perfiles_business_autorizados()
        or str(sender.id) == profile_id
    ):
        return

    recipient_id = str(getattr(sender, "id", ""))
    chat_id = str(getattr(message.chat, "id", ""))
    if not recipient_id or recipient_id != chat_id:
        return

    # Serializar primera respuesta para evitar dobles saludos si llegan mensajes
    # simultáneos mientras Telegram reintenta la entrega del webhook.
    with BUSINESS_WELCOME_LOCK:
        if _business_saludo_ya_enviado(profile_id, recipient_id):
            return

        markup = _markup_bienvenida_business()
        enviado = False
        if os.path.isfile(WELCOME_PHOTO_PATH):
            try:
                with open(WELCOME_PHOTO_PATH, "rb") as photo:
                    bot.send_photo(
                        chat_id,
                        photo,
                        caption=WELCOME_MESSAGE,
                        parse_mode=None,
                        reply_markup=markup,
                        business_connection_id=connection_id,
                    )
                enviado = True
            except Exception:
                app.logger.warning(
                    "Falló la foto del saludo Business; se intentará enviar el texto."
                )

        if not enviado:
            try:
                bot.send_message(
                    chat_id,
                    WELCOME_MESSAGE,
                    parse_mode=None,
                    reply_markup=markup,
                    business_connection_id=connection_id,
                )
                enviado = True
            except Exception:
                app.logger.warning("No se pudo enviar el saludo automático Business.")

        if enviado:
            try:
                _marcar_business_saludo_enviado(profile_id, recipient_id)
            except Exception:
                app.logger.exception("No se pudo guardar el registro del saludo Business.")

def registrar_actividad_stats(user_id, username):
    res = Estadisticas.search(User.id == user_id)
    if res:
        nueva_puntuacion = res[0].get('puntos', 0) + 1
        Estadisticas.update({'puntos': nueva_puntuacion, 'last_seen': str(datetime.now())}, User.id == user_id)
    else:
        Estadisticas.insert({'id': user_id, 'username': username, 'puntos': 1, 'last_seen': str(datetime.now())})

def aplicar_castigo(chat_id, user_id, nombre):
    stats = Warnings.search(User.id == user_id)
    count = stats[0]['count'] + 1 if stats else 1
    if count >= 3:
        try:
            bot.kick_chat_member(chat_id, user_id)
            bot.send_message(
                chat_id,
                f"🪓 **SENTENCIA FINAL**\n"
                f"El guerrero @{nombre} ha acumulado 3 penalizaciones y ha sido expulsado permanentemente de la tribu."
            )
            markup = types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("🔓 PERDONAR", callback_data=f"indulto_{user_id}")
            )
            bot.send_message(ADMIN_ID, f"🚩 **EXPULSIÓN EJECUTADA**\nUsuario: @{nombre}\nID: {user_id}", reply_markup=markup)
            Warnings.remove(User.id == user_id)
            return
        except:
            pass
    else:
        until_date = int(time.time()) + (35 * 60)
        try:
            bot.restrict_chat_member(chat_id, user_id, until_date=until_date, can_send_messages=False)
        except:
            pass
        if stats:
            Warnings.update({'count': count, 'last_warn': str(datetime.now())}, User.id == user_id)
        else:
            Warnings.insert({'id': user_id, 'username': nombre, 'count': count, 'last_warn': str(datetime.now())})
        bot.send_message(
            chat_id,
            f"⚠️ **ADVERTENCIA OFICIAL — PENALIZACIÓN {count}/3**\n\n"
            f"Guerrero @{nombre}, has sido reportado por conducta inapropiada. "
            f"Tienes {3 - count} advertencia(s) restante(s). "
            f"A la tercera serás expulsado permanentemente de la tribu. 🏹\n\n"
            f"_Silenciado por 35 minutos._"
        )

def cerrar_sesion_segura(chat_id):
    markup = types.ReplyKeyboardRemove()
    bot.send_message(chat_id, "🔒 **SESIÓN FINALIZADA**", reply_markup=markup)

def guardar_evidencia(message):
    if not es_grupo_autorizado(message.chat.id):
        return
    evidencia = {
        'id': message.from_user.id,
        'uname': (message.from_user.username or "Anonimo").lower(),
        'msg_id': message.message_id,
        'date': str(datetime.now()),
        'type': message.content_type,
        'text': message.text or message.caption or "",
        'file_id': None
    }
    if message.photo:
        evidencia['file_id'] = message.photo[-1].file_id
    if message.video:
        evidencia['file_id'] = message.video.file_id
    RegistroActividad.insert(evidencia)

def obtener_teclado_cuadritos():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
        input_field_placeholder="Selecciona una acción... 🏹",
    )
    markup.row(types.KeyboardButton("🏠 /start"), types.KeyboardButton("🏹 /menu"))
    markup.row(types.KeyboardButton("📜 /reglas"), types.KeyboardButton("🚀 /compartir"))
    markup.row(types.KeyboardButton("👤 /admin"), types.KeyboardButton("🔥 /vchat"))
    return markup

def obtener_emoji_link(url):
    url = url.lower()
    if "t.me" in url: return "🌀"
    if "x.com" in url or "twitter.com" in url: return "𝕏 🔥"
    if "instagram" in url: return "🍉"
    if "onlyfans" in url: return "🔞 💎"
    return "🔗"

def obtener_nombre_red(url):
    url = url.lower()
    if "t.me" in url: return "Telegram"
    if "instagram" in url: return "Instagram"
    if "onlyfans" in url: return "OnlyFans"
    return "Enlace"


def _videochat_guide_url(chat_id):
    try:
        chat=bot.get_chat(chat_id)
        username=getattr(chat,"username",None)
        if username: return f"https://t.me/{username}?videochat"
    except Exception:
        app.logger.info("El grupo no tiene un enlace público de videochat disponible.")
    return LINK_GRUPO

def enviar_invitacion_vchat(chat_id):
    global ID_ULTIMA_INVITACION
    if ID_ULTIMA_INVITACION.get(chat_id):
        eliminar_mensaje_seguro(chat_id, ID_ULTIMA_INVITACION[chat_id])
    msg_random = random.choice(TEXTOS_VC_HOT)
    e1, e2 = random.sample(EMOJIS_ACCION, 2)
    markup = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton(f"{e1} ENTRAR AL VIDEOCHAT {e2}", url=_videochat_guide_url(chat_id))
    )
    try:
        nuevo_msg = bot.send_message(chat_id, msg_random, reply_markup=markup)
        ID_ULTIMA_INVITACION[chat_id] = nuevo_msg.message_id
    except:
        pass

def bucle_notificacion_menu():
    while True:
        time.sleep(45 * 60)
        try:
            bot.send_message(
                _grupos_configurados()[0],
                "🔱 **¡GUERRERO!** ¿Ya tienes tus herramientas activas?\n\n"
                "Presiona el botón 🏹 **/menu** de la barra de mensajes y desbloquea todo el poder de la tribu . 💎🔥"
            )
        except:
            pass

def bucle_repost_automatico():
    while True:
        time.sleep(172800)
        todas = PromosAprobadas.all()
        for p in todas:
            try:
                markup = types.InlineKeyboardMarkup()
                for btn in p['botones']:
                    markup.add(types.InlineKeyboardButton(btn['text'], url=btn['url']))
                if p['is_video']:
                    bot.send_video(_grupos_configurados()[0], p['file_id'], caption=f"🔄 **RE-POST**\n\n{p['desc']}", reply_markup=markup)
                else:
                    bot.send_photo(_grupos_configurados()[0], p['file_id'], caption=f"🔄 **RE-POST**\n\n{p['desc']}", reply_markup=markup)
                time.sleep(10)
            except:
                continue

def editar_o_enviar_panel(
    chat_id, texto, reply_markup=None, message=None, message_id=None, protect_content=False,
    parse_mode="HTML", disable_web_page_preview=True, forzar_texto=False,
):
    message_id = message_id or getattr(message, "message_id", None)
    registro = None
    if int(chat_id) > 0:
        with PANEL_LOCK:
            registro = PANELES_PRIVADOS.get(PANEL_QUERY.chat_id == str(chat_id))
        if not message_id and registro:
            message_id = registro.get("message_id")

    if (
        protect_content
        and message_id
        and not (registro and registro.get("protect_content"))
    ):
        try:
            bot.delete_message(chat_id, message_id)
        except Exception:
            app.logger.info(
                "No se pudo reemplazar el panel privado %s por uno protegido.",
                message_id,
            )
        if int(chat_id) > 0:
            with PANEL_LOCK:
                PANELES_PRIVADOS.remove(PANEL_QUERY.chat_id == str(chat_id))
        message_id = None
        registro = None

    if message_id:
        tipo_panel = (
            registro.get("tipo", "texto")
            if registro and str(registro.get("message_id")) == str(message_id)
            else "foto" if getattr(message, "photo", None) else "texto"
        )
        tipos_panel_media = {"foto", "photo", "video", "document", "audio", "animation"}
        if forzar_texto and tipo_panel in tipos_panel_media:
            try:
                bot.delete_message(chat_id, message_id)
            except Exception:
                app.logger.info(
                    "No se pudo quitar la foto anterior del panel privado %s.",
                    message_id,
                )
            if int(chat_id) > 0:
                with PANEL_LOCK:
                    PANELES_PRIVADOS.remove(PANEL_QUERY.chat_id == str(chat_id))
            message_id = None
            registro = None
        if message_id:
            try:
                if tipo_panel in tipos_panel_media:
                    actualizado = bot.edit_message_caption(
                        caption=texto,
                        chat_id=chat_id,
                        message_id=message_id,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup,
                    )
                else:
                    actualizado = bot.edit_message_text(
                        texto,
                        chat_id=chat_id,
                        message_id=message_id,
                        parse_mode=parse_mode,
                        disable_web_page_preview=disable_web_page_preview,
                        reply_markup=reply_markup,
                    )
                if int(chat_id) > 0:
                    with PANEL_LOCK:
                        PANELES_PRIVADOS.upsert(
                            {
                                "chat_id": str(chat_id),
                                "message_id": message_id,
                                "tipo": tipo_panel,
                                "protect_content": bool(
                                    protect_content
                                    or (registro or {}).get("protect_content")
                                ),
                            },
                            PANEL_QUERY.chat_id == str(chat_id),
                        )
                return actualizado
            except Exception as error:
                if "message is not modified" in str(error).lower():
                    return message or SimpleNamespace(message_id=message_id)
                app.logger.info(
                    "No se pudo editar el panel privado %s; se reemplazará.",
                    message_id,
                )
                try:
                    bot.delete_message(chat_id, message_id)
                except Exception:
                    pass

    nuevo = _SEND_MESSAGE_ORIGINAL(
        chat_id,
        texto,
        parse_mode=parse_mode,
        disable_web_page_preview=disable_web_page_preview,
        protect_content=protect_content,
        reply_markup=reply_markup,
    )
    if int(chat_id) > 0:
        with PANEL_LOCK:
            PANELES_PRIVADOS.upsert(
                {
                    "chat_id": str(chat_id),
                    "message_id": nuevo.message_id,
                    "tipo": "texto",
                    "protect_content": bool(protect_content),
                },
                PANEL_QUERY.chat_id == str(chat_id),
            )
    return nuevo

def enviar_foto_panel(
    chat_id, photo, caption, reply_markup=None, forzar_reemplazo=False
):
    registro = None
    if int(chat_id) > 0:
        with PANEL_LOCK:
            registro = PANELES_PRIVADOS.get(PANEL_QUERY.chat_id == str(chat_id))

    if registro:
        message_id = registro.get("message_id")
        if registro.get("tipo") == "foto" and not forzar_reemplazo:
            try:
                actualizado = bot.edit_message_caption(
                    caption=caption,
                    chat_id=chat_id,
                    message_id=message_id,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
                if int(chat_id) > 0:
                    with PANEL_LOCK:
                        PANELES_PRIVADOS.upsert(
                            {
                                "chat_id": str(chat_id),
                                "message_id": message_id,
                                "tipo": "foto",
                                "protect_content": True,
                            },
                            PANEL_QUERY.chat_id == str(chat_id),
                        )
                return actualizado
            except Exception as error:
                if "message is not modified" in str(error).lower():
                    return None
        try:
            bot.delete_message(chat_id, message_id)
        except Exception:
            pass

    nuevo = bot.send_photo(
        chat_id,
        photo,
        caption=caption,
        reply_markup=reply_markup,
        parse_mode="HTML",
        protect_content=True,
    )
    if int(chat_id) > 0:
        with PANEL_LOCK:
            PANELES_PRIVADOS.upsert(
                {
                    "chat_id": str(chat_id),
                    "message_id": nuevo.message_id,
                    "tipo": "foto",
                    "protect_content": True,
                },
                PANEL_QUERY.chat_id == str(chat_id),
            )
    return nuevo

def eliminar_mensaje_disparador(message):
    try:
        bot.delete_message(message.chat.id, message.message_id)
        return True
    except Exception:
        app.logger.info(
            "No se pudo eliminar el mensaje de acción %s en el chat %s.",
            getattr(message, "message_id", "?"),
            getattr(getattr(message, "chat", None), "id", "?"),
        )
        return False

# ── Datos de pago ─────────────────────────────────────────────────────────────
_AVISO = "\n\n⚠️ Importante: Envía tu comprobante a este mismo chat cuando termines de procesar tu pedido para obtener el GoldPass."

NOMBRE_METODO = {
    "pago_binance":   "🔸 Binance Pay",
    "pago_pm":        "🇻🇪 Pago Móvil",
    "pago_trans":     "🏦 Mercantil (VZLA)",
    "pago_airtm":     "🌐 Airtm",
    "pago_wally":     "💜 Wally",
    "pago_usa_bank":  "🏦🇺🇸 Transferencia Bancaria USA",
    "pago_usa_link":  "🔗🇺🇸 Pago por Link (USA)",
    "pago_visa_mc":   "💳✨ Visa / Mastercard",
    "pago_iban":      "💶🇪🇺 IBAN / Euros",
    "pago_mex":       "🏦🇲🇽 Cuenta MÉX",
    "pago_PayPal":       "🏦 PayPal",
}

METODOS_PAGO_POR_ENLACE = {"pago_usa_link", "pago_visa_mc"}


def cargar_config_pagos():
    with PAYMENT_CONFIG_LOCK:
        try:
            with open(PAYMENT_CONFIG_FILE, "r", encoding="utf-8") as archivo:
                datos = json.load(archivo)
        except FileNotFoundError:
            return {"metodos": {}, "mensajes_link": {}, "portada_file_id": None}
        except json.JSONDecodeError as error:
            app.logger.error(
                "La configuración privada de pagos contiene JSON inválido: %s",
                error,
            )
            raise ValueError("La configuración privada de pagos no es válida.") from error
        if not isinstance(datos, dict):
            raise ValueError("La configuración privada de pagos debe ser un objeto JSON.")
        for campo in ("metodos", "mensajes_link"):
            if campo not in datos:
                datos[campo] = {}
            elif not isinstance(datos[campo], dict):
                raise ValueError(
                    f"El campo privado de pagos {campo} no tiene el formato esperado."
                )
        if datos.get("portada_file_id") is not None and not isinstance(
            datos.get("portada_file_id"), str
        ):
            raise ValueError("La referencia privada de la foto no tiene el formato esperado.")
        return datos


def guardar_config_pagos(datos):
    temporal = PAYMENT_CONFIG_FILE + ".tmp"
    with PAYMENT_CONFIG_LOCK:
        descriptor = os.open(
            temporal, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, ensure_ascii=False, indent=2)
            archivo.write("\n")
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(temporal, PAYMENT_CONFIG_FILE)
        os.chmod(PAYMENT_CONFIG_FILE, 0o600)


def actualizar_config_pagos(actualizar):
    with PAYMENT_CONFIG_LOCK:
        datos = cargar_config_pagos()
        actualizar(datos)
        guardar_config_pagos(datos)
        return datos


def obtener_datos_pago(metodo):
    datos = cargar_config_pagos()
    texto = str(datos.get("metodos", {}).get(metodo) or "").strip()
    if not texto:
        return ""
    if metodo not in METODOS_PAGO_POR_ENLACE and _AVISO.strip() not in texto:
        texto += _AVISO
    return texto


def obtener_mensaje_solicitud_enlace(metodo):
    guardados = cargar_config_pagos().get("mensajes_link", {})
    texto = str(guardados.get(metodo) or "").strip()
    return html.escape(texto) if texto else _MSG_LINK


def guardar_metodo_pago(metodo, texto):
    es_enlace = metodo in METODOS_PAGO_POR_ENLACE
    grupo = "mensajes_link" if es_enlace else "metodos"

    def actualizar(datos):
        datos.setdefault(grupo, {})[metodo] = texto

    actualizar_config_pagos(actualizar)

# Texto que el bot manda al usuario al recibir solicitud de Pago por Link
_MSG_LINK = (
    "✨ <b>¡SOLICITUD RECIBIDA!</b> ✨\n\n"
    "⏳ Tu solicitud está <b>en proceso</b>.\n\n"
    "🔗 <b>PAGO POR LINK</b>\n"
    "Este método te permite pagar con <b>tarjeta de débito o crédito</b> "
    "(Visa / Mastercard). Recibirás un enlace de pago seguro generado "
    "especialmente para ti, el cual <b>se eliminará automáticamente</b> "
    "luego de realizar el pago y nadie más podrá tener acceso a él.\n\n"
    "⚠️ <b>Cargos adicionales:</b>\n"
    "Este método incluye una comisión de <b>5.3% + 0.8%</b> sobre el monto "
    "de la suscripción. Ese porcentaje se suma al costo final antes de "
    "generarte el enlace.\n\n"
    "Nos comunicaremos contigo en breve para enviarte el enlace de pago.\n\n"
    "🙏 <i>Gracias por tu paciencia.</i>"
)

# Aviso de comprobante (se adjunta al texto de datos que el admin copia y envía)
_AVISO_LINK = (
    "\n\n⚠️ Importante: Envía tu comprobante a este mismo chat cuando termines "
    "de procesar tu pedido para obtener el GoldPass."
)

# ── Helpers ───────────────────────────────────────────────────────────────────
PASE_EXPRES_URL = "https://t.me/+xjHnFXb_QTY0NGEx"

def pase_expres_activo():
    """Devuelve True si el pase exprés está configurado y no ha vencido."""
    cfg = cargar_config()
    pe  = cfg.get("pase_expres", {})
    if not pe.get("activo"):
        return False
    vence = pe.get("vence")
    if not vence:
        return False
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S') <= vence

def mostrar_metodos_pago(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=2)

    # Pase Exprés gratuito (solo cuando está activo)
    if pase_expres_activo():
        markup.add(
            types.InlineKeyboardButton(
                "🎟️✨ ¡PASE EXPRÉS GRATUITO — Accede ahora!",
                callback_data="pase_expres_click"
            )
        )

    markup.add(
        types.InlineKeyboardButton("🔸 Binance",             callback_data="pago_binance"),
        types.InlineKeyboardButton("🇻🇪 Pago Móvil",         callback_data="pago_pm"),
        types.InlineKeyboardButton("🏦🇻🇪 Vznl",             callback_data="pago_trans"),
        types.InlineKeyboardButton("🏦🇺🇸 Cuenta USA",       callback_data="pago_usa"),
        types.InlineKeyboardButton("🏦🇲🇽 Cuenta MÉX",       callback_data="pago_mex"),
        types.InlineKeyboardButton("🌐 Airtm",                callback_data="pago_airtm"),
        types.InlineKeyboardButton("💜 Wally",                callback_data="pago_wally"),
        types.InlineKeyboardButton("💳✨ Visa / Mastercard",  callback_data="pago_visa_mc"),
        types.InlineKeyboardButton("💶🇪🇺 IBAN / Euros",     callback_data="pago_iban"),
        types.InlineKeyboardButton(" 🏦 PayPal",     callback_data="pago_PayPal"),
    )

    if pase_expres_activo():
        texto = (
            "🎟️ <b>¡HAY UN PASE EXPRÉS GRATUITO DISPONIBLE!</b> 🎟️\n\n"
            "👑 <b>COSTO DE ACCESO: $1.99 USD</b>\n\n"
            "Selecciona tu método de pago o usa el <b>Pase Exprés gratuito</b> 👆"
        )
    else:
        texto = (
            "👑 <b>COSTO DE ACCESO: $1.99 USD</b>\n\n"
            "Selecciona tu método de pago preferido 👇"
        )
    photo_id = cargar_config_pagos().get("portada_file_id")
    if photo_id:
        try:
            return enviar_foto_panel(
                chat_id,
                photo_id,
                texto,
                markup,
                forzar_reemplazo=True,
            )
        except Exception:
            app.logger.exception("No se pudo cargar la portada configurada de pagos.")
    try:
        portada = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portada.jpg")
        with open(portada, "rb") as photo:
            return enviar_foto_panel(
                chat_id,
                photo,
                texto,
                markup,
                forzar_reemplazo=True,
            )
    except OSError:
        return editar_o_enviar_panel(
            chat_id,
            texto,
            markup,
            protect_content=True,
        )


def markup_admin_config_pagos():
    config_pagos = cargar_config_pagos()
    markup = types.InlineKeyboardMarkup(row_width=1)
    for metodo, nombre in NOMBRE_METODO.items():
        if metodo in METODOS_PAGO_POR_ENLACE:
            configurado = bool(
                config_pagos.get("mensajes_link", {}).get(metodo) or _MSG_LINK
            )
        else:
            configurado = bool(config_pagos.get("metodos", {}).get(metodo))
        estado = "✅" if configurado else "⚠️"
        markup.add(types.InlineKeyboardButton(
            f"{estado} {nombre}",
            callback_data=f"admin_pagos_metodo|{metodo}",
        ))
    markup.add(types.InlineKeyboardButton(
        "🖼️ Cambiar foto del menú",
        callback_data="admin_pagos_cambiar_foto",
    ))
    if config_pagos.get("portada_file_id"):
        markup.add(types.InlineKeyboardButton(
            "♻️ Usar la foto original",
            callback_data="admin_pagos_foto_original",
        ))
    markup.add(types.InlineKeyboardButton(
        "🔙 Volver al panel",
        callback_data="admin_pagos_volver",
    ))
    return markup


def mostrar_admin_config_pagos(
    chat_id, message=None, message_id=None, aviso=None
):
    config_pagos = cargar_config_pagos()
    portada = (
        "personalizada"
        if config_pagos.get("portada_file_id")
        else "foto original"
    )
    texto = (
        "💳 <b>Métodos de pago e imagen</b>\n\n"
        "Selecciona un método para reemplazar su información. "
        "Los datos no se muestran en esta pantalla.\n"
        "En los métodos por enlace se cambia el mensaje que recibe el usuario "
        "al solicitarlo.\n\n"
        f"Foto del menú: <b>{portada}</b>.\n"
        "Las imágenes y los mensajes de pago enviados por el bot usarán "
        "la protección de contenido de Telegram."
    )
    if aviso:
        texto = f"✅ {html.escape(aviso)}\n\n" + texto
    return editar_o_enviar_panel(
        chat_id,
        texto,
        markup_admin_config_pagos(),
        message=message,
        message_id=message_id,
        forzar_texto=True,
    )


def es_admin_privado(call):
    chat = getattr(getattr(call, "message", None), "chat", None)
    return (
        str(call.from_user.id) == str(ADMIN_ID)
        and getattr(chat, "type", None) == "private"
        and str(getattr(chat, "id", "")) == str(ADMIN_ID)
    )


@bot.callback_query_handler(func=lambda call: call.data == "admin_pagos")
def admin_menu_config_pagos(call):
    if not es_admin_privado(call):
        bot.answer_callback_query(call.id, "⛔ Solo el administrador puede abrirlo en privado.")
        return
    bot.answer_callback_query(call.id)
    mostrar_admin_config_pagos(
        call.message.chat.id,
        message=call.message,
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("admin_pagos_metodo|")
)
def admin_editar_metodo_pago(call):
    if not es_admin_privado(call):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    metodo = call.data.split("|", 1)[1]
    if metodo not in NOMBRE_METODO:
        bot.answer_callback_query(call.id, "No encontré ese método.")
        return
    bot.answer_callback_query(call.id)
    admin_estado[call.from_user.id] = {
        "paso": "esperando_datos_metodo_pago",
        "metodo_pago": metodo,
        "panel_message_id": call.message.message_id,
    }
    if metodo in METODOS_PAGO_POR_ENLACE:
        instruccion = (
            "Envía el mensaje que recibirá el usuario al solicitar un enlace de pago."
        )
    else:
        instruccion = (
            "Envía toda la información de pago que el administrador copiará "
            "para compartir con el usuario."
        )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "❌ Cancelar",
        callback_data="admin_pagos_cancelar",
    ))
    editar_o_enviar_panel(
        call.message.chat.id,
        f"✍️ <b>Actualizar {html.escape(NOMBRE_METODO[metodo])}</b>\n\n"
        f"{instruccion}\n\n"
        "Envía el texto completo en un solo mensaje. No se mostrará de vuelta "
        "en el panel y el mensaje que envíes se borrará después de guardarlo.",
        markup,
        message=call.message,
        protect_content=True,
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "admin_pagos_cambiar_foto"
)
def admin_cambiar_foto_pagos(call):
    if not es_admin_privado(call):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    admin_estado[call.from_user.id] = {
        "paso": "esperando_foto_metodos_pago",
        "panel_message_id": call.message.message_id,
    }
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "❌ Cancelar",
        callback_data="admin_pagos_cancelar",
    ))
    editar_o_enviar_panel(
        call.message.chat.id,
        "🖼️ <b>Cambiar la foto del menú de pagos</b>\n\n"
        "Envíame la nueva imagen como foto. Se usará únicamente en el menú "
        "de métodos de pago. El mensaje que envíes se borrará al guardarla.",
        markup,
        message=call.message,
        protect_content=True,
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "admin_pagos_foto_original"
)
def admin_restaurar_foto_pagos(call):
    if not es_admin_privado(call):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id, "Se usará otra vez la foto original.")
    try:
        actualizar_config_pagos(
            lambda datos: datos.update({"portada_file_id": None})
        )
    except Exception:
        app.logger.exception("No se pudo restaurar la foto original de pagos.")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "↩️ Volver a métodos de pago",
            callback_data="admin_pagos",
        ))
        editar_o_enviar_panel(
            call.message.chat.id,
            "No pude guardar el cambio. La foto actual se mantiene.",
            markup,
            message=call.message,
            protect_content=True,
        )
        return
    mostrar_admin_config_pagos(
        call.message.chat.id,
        message=call.message,
        aviso="Foto original restaurada.",
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "admin_pagos_cancelar"
)
def admin_cancelar_edicion_pagos(call):
    if not es_admin_privado(call):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id, "Edición cancelada.")
    admin_estado.pop(call.from_user.id, None)
    mostrar_admin_config_pagos(
        call.message.chat.id,
        message=call.message,
        aviso="No se guardaron cambios.",
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "admin_pagos_volver"
)
def admin_pagos_volver_panel(call):
    if not es_admin_privado(call):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    mostrar_panel_admin(
        call.message.chat.id,
        message=call.message,
    )


def borrar_mensaje_luego(chat_id, message_id, demora):
    time.sleep(demora)
    try:
        bot.delete_message(chat_id, message_id)
    except:
        pass

def construir_markup_botones(botones):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for b in botones:
        markup.add(types.InlineKeyboardButton(b['texto'], url=b['url']))
    return markup

def parsear_intervalo(texto):
    coincidencia = re.fullmatch(r"\s*(\d+)\s*([mhd])\s*", (texto or "").lower())
    if not coincidencia:
        return None
    cantidad = int(coincidencia.group(1))
    unidad = coincidencia.group(2)
    segundos_por_unidad = {"m": 60, "h": 3600, "d": 86400}[unidad]
    segundos = cantidad * segundos_por_unidad
    if cantidad <= 0 or segundos > 365 * 86400:
        return None
    return segundos

def formato_intervalo(segundos):
    if segundos % 86400 == 0:
        return f"{segundos // 86400} día(s)"
    if segundos % 3600 == 0:
        return f"{segundos // 3600} hora(s)"
    return f"{segundos // 60} minuto(s)"

def enviar_publicacion_con_botones(
    chat_id, texto, markup, media_id=None, media_type=None, media_items=None
):
    return _enviar_publicacion_con_adjuntos(
        chat_id, texto, markup, media_id, media_type, media_items
    )


def normalizar_media_items(media_id=None, media_type=None, media_items=None):
    if media_items is not None:
        return [
            {"media_id": item["media_id"], "media_type": item["media_type"]}
            for item in media_items
            if isinstance(item, dict)
            and item.get("media_id")
            and item.get("media_type")
        ]
    if media_id and media_type:
        return [{"media_id": media_id, "media_type": media_type}]
    return []


def media_items_de_publicacion(publicacion):
    return normalizar_media_items(
        publicacion.get("media_id"),
        publicacion.get("media_type"),
        publicacion.get("media_items"),
    )


def markup_tiene_botones(markup):
    return bool(markup and getattr(markup, "keyboard", None))


def validar_media_items(media_items):
    if len(media_items) > 10:
        raise ValueError("Telegram permite hasta 10 archivos en una publicación.")
    if len(media_items) < 2:
        return

    tipos = {item["media_type"] for item in media_items}
    if tipos <= {"photo", "video"}:
        return
    if len(tipos) == 1 and tipos <= {"audio", "document"}:
        return
    raise ValueError(
        "Para enviar varios archivos juntos, mezcla solo fotos/videos "
        "o usa archivos todos del mismo tipo (audio o documento)."
    )


def _enviar_publicacion_con_adjuntos(
    chat_id, texto, markup, media_id=None, media_type=None, media_items=None
):
    adjuntos = normalizar_media_items(media_id, media_type, media_items)
    texto = texto or ""

    if not adjuntos:
        if not texto.strip():
            raise ValueError("Escribe un texto o añade un archivo multimedia.")
        return bot.send_message(
            chat_id,
            texto,
            reply_markup=markup,
            parse_mode="HTML",
        )

    if len(adjuntos) == 1:
        adjunto = adjuntos[0]
        metodo = {
            "photo": bot.send_photo,
            "video": bot.send_video,
            "document": bot.send_document,
            "audio": bot.send_audio,
            "animation": bot.send_animation,
        }.get(adjunto["media_type"])
        if not metodo:
            raise ValueError("Tipo de archivo multimedia no compatible.")
        return metodo(
            chat_id,
            adjunto["media_id"],
            caption=texto or None,
            reply_markup=markup,
            parse_mode="HTML" if texto else None,
        )

    validar_media_items(adjuntos)
    clases_media = {
        "photo": types.InputMediaPhoto,
        "video": types.InputMediaVideo,
        "document": types.InputMediaDocument,
        "audio": types.InputMediaAudio,
    }
    grupo = []
    for indice, adjunto in enumerate(adjuntos):
        clase_media = clases_media.get(adjunto["media_type"])
        if not clase_media:
            raise ValueError(
                "Los GIF/animaciones solo se pueden añadir como archivo único."
            )
        opciones = {"media": adjunto["media_id"]}
        if indice == 0 and texto:
            opciones.update(caption=texto, parse_mode="HTML")
        grupo.append(clase_media(**opciones))

    mensajes = bot.send_media_group(chat_id, grupo)
    if markup_tiene_botones(markup):
        mensajes.append(
            bot.send_message(
                chat_id,
                "Opciones:",
                reply_markup=markup,
            )
        )
    return mensajes

def guardar_ultima_publicacion(canal_key, chat_id, mensaje, texto, media_id, media_type):
    def actualizar(cfg):
        cfg.setdefault("ultima_publicacion", {})[canal_key] = {
            "chat_id": str(chat_id),
            "message_id": getattr(mensaje, "message_id", None),
            "texto": texto or "",
            "media_id": media_id,
            "media_type": media_type,
            "media_items": normalizar_media_items(media_id, media_type),
            "botones_key": canal_key,
        }
    actualizar_config(actualizar)


def buscar_ultima_publicacion_destino(destino_key):
    chat_id = obtener_canal_id(destino_key)
    if not chat_id:
        return None

    publicaciones = cargar_config().get("ultima_publicacion", {})
    coincidencias = []
    for botones_key, publicacion in publicaciones.items():
        if (
            botones_key in CANALES
            and isinstance(publicacion, dict)
            and str(publicacion.get("chat_id")) == str(chat_id)
        ):
            try:
                orden = int(publicacion.get("message_id") or 0)
            except (TypeError, ValueError):
                orden = 0
            coincidencias.append((orden, botones_key, publicacion))
    if not coincidencias:
        return None
    _, botones_key, publicacion = max(coincidencias, key=lambda item: item[0])
    return botones_key, publicacion


def tipo_de_media_compatible(media_items, nuevo_tipo):
    if not media_items:
        return True
    tipos = {item.get("media_type") for item in media_items}
    if nuevo_tipo in ("photo", "video"):
        return tipos <= {"photo", "video"}
    if nuevo_tipo in ("audio", "document"):
        return tipos == {nuevo_tipo}
    return False


def mostrar_controles_media_recurrente(chat_id, cantidad):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if cantidad < 10:
        markup.add(
            types.InlineKeyboardButton(
                "➕ Añadir otro archivo", callback_data="rec_media_agregar"
            )
        )
    markup.add(
        types.InlineKeyboardButton(
            "✅ Continuar", callback_data="rec_media_listo"
        ),
        types.InlineKeyboardButton("❌ Cancelar", callback_data="rec_abortar"),
    )
    bot.send_message(
        chat_id,
        f"✅ Archivo añadido ({cantidad}/10). Envía otro o continúa.",
        reply_markup=markup,
    )


def agregar_media_recurrente(message, media_id, media_type):
    uid = message.from_user.id
    estado = admin_estado.get(uid, {})
    if estado.get("paso") != "esperando_media_recurrente":
        return

    media_items = estado.setdefault("media_items", [])
    if len(media_items) >= 10:
        bot.send_message(message.chat.id, "El máximo es 10 archivos por publicación.")
        return
    if not tipo_de_media_compatible(media_items, media_type):
        bot.send_message(
            message.chat.id,
            "No se puede mezclar ese tipo de archivo con los anteriores. "
            "Usa fotos/videos juntos, o varios documentos o varios audios.",
        )
        return

    media_items.append({"media_id": media_id, "media_type": media_type})
    estado["media_id"] = media_items[0]["media_id"] if len(media_items) == 1 else None
    estado["media_type"] = media_items[0]["media_type"] if len(media_items) == 1 else None
    mostrar_controles_media_recurrente(message.chat.id, len(media_items))

def enviar_con_media(chat_id, texto, markup, boton):
    """Envía mensaje al chat con media del botón si tiene, o solo texto."""
    mid  = boton.get('media_id')
    mtyp = boton.get('media_type')
    metodo = {
        "photo": bot.send_photo,
        "video": bot.send_video,
        "document": bot.send_document,
        "audio": bot.send_audio,
        "animation": bot.send_animation,
    }.get(mtyp)
    if mid and metodo:
        return metodo(
            chat_id,
            mid,
            caption=texto,
            reply_markup=markup,
            parse_mode="HTML",
        )
    return bot.send_message(
        chat_id,
        texto,
        reply_markup=markup,
        parse_mode="HTML",
    )

def expulsar_usuario_vencido(user_id):
    """Expulsa a un usuario del canal VIP, le notifica opciones de renovación
    y lo elimina de la base de datos. Usado tanto por la revisión automática
    de vencimientos como por el comando manual /expulsar (pruebas).
    El db.remove() se ejecuta SIEMPRE aunque el ban o el mensaje fallen."""
    # 1. Expulsar del canal (si ya salió, el ban puede fallar — no importa)
    try:
        bot.ban_chat_member(CANAL_ID, user_id)
        bot.unban_chat_member(CANAL_ID, user_id)
    except Exception as e_ban:
        try:
            bot.send_message(int(ADMIN_ID),
                f"ℹ️ No pude expulsar a <code>{user_id}</code> del canal "
                f"(probablemente ya salió): {e_ban}",
                parse_mode="HTML")
        except:
            pass

    # 2. Notificar al usuario con opciones de renovación
    try:
        markup_renovar = types.InlineKeyboardMarkup(row_width=1)
        markup_renovar.add(
            types.InlineKeyboardButton("⭐ Ingresar con Telegram Stars", url=CANAL_INVITE_LINK),
            types.InlineKeyboardButton("💳 Usar otro método de pago", callback_data="otro_metodo"),
        )
        bot.send_message(
            user_id,
            "⚠️ <b>Tu suscripción VIP ha vencido.</b>\n\n"
            "Elige cómo quieres renovar tu acceso al canal 👇",
            parse_mode="HTML", protect_content=True, reply_markup=markup_renovar
        )
    except:
        pass  # El usuario nunca inició el bot — no se puede notificar

    # 3. Eliminar del registro SIEMPRE, sin importar lo anterior
    db.remove(Query().id == user_id)

def revisar_vencimientos():
    while True:
        ahora = datetime.now()
        vencidos = db.search(Query().vence <= ahora.strftime('%Y-%m-%d %H:%M:%S'))
        for u in vencidos:
            try:
                expulsar_usuario_vencido(u['id'])
            except:
                pass
        time.sleep(3600)

def guardar_foto_menu_pagos(message, foto_id):
    uid = message.from_user.id
    estado = admin_estado.get(uid, {})
    if estado.get("paso") != "esperando_foto_metodos_pago":
        return False
    panel_message_id = estado.get("panel_message_id")
    try:
        actualizar_config_pagos(
            lambda datos: datos.update({"portada_file_id": foto_id})
        )
    except Exception:
        app.logger.exception("No se pudo guardar la nueva portada de pagos.")
        eliminar_mensaje_disparador(message)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "❌ Cancelar",
            callback_data="admin_pagos_cancelar",
        ))
        editar_o_enviar_panel(
            message.chat.id,
            "No pude guardar la nueva foto. La portada anterior se mantiene. "
            "Intenta enviarla de nuevo o pulsa cancelar.",
            markup,
            message_id=panel_message_id,
            protect_content=True,
        )
        return True
    admin_estado.pop(uid, None)
    eliminar_mensaje_disparador(message)
    mostrar_admin_config_pagos(
        message.chat.id,
        message_id=panel_message_id,
        aviso="Foto del menú de pagos actualizada.",
    )
    return True

def rechazar_archivo_foto_pagos(message):
    estado = admin_estado.get(message.from_user.id, {})
    if estado.get("paso") != "esperando_foto_metodos_pago":
        return False
    eliminar_mensaje_disparador(message)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "❌ Cancelar",
        callback_data="admin_pagos_cancelar",
    ))
    editar_o_enviar_panel(
        message.chat.id,
        "Para la portada envíame una imagen como foto de Telegram, no un vídeo "
        "ni un archivo adjunto.",
        markup,
        message_id=estado.get("panel_message_id"),
        protect_content=True,
    )
    return True

def rechazar_media_metodo_pago(message):
    estado = admin_estado.get(message.from_user.id, {})
    if estado.get("paso") != "esperando_datos_metodo_pago":
        return False
    eliminar_mensaje_disparador(message)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "❌ Cancelar",
        callback_data="admin_pagos_cancelar",
    ))
    editar_o_enviar_panel(
        message.chat.id,
        "En este paso necesito el texto de los datos del método de pago. "
        "Envíalo como mensaje de texto o pulsa cancelar.",
        markup,
        message_id=estado.get("panel_message_id"),
        protect_content=True,
    )
    return True

@bot.callback_query_handler(func=lambda call: call.data == "otro_metodo")
def otro_metodo_pago(call):
    bot.answer_callback_query(call.id)
    mostrar_metodos_pago(call.message.chat.id)

# ─── Pase Exprés: usuario lo solicita ───────────────────────────
@bot.callback_query_handler(func=lambda call: call.data == "pase_expres_click")
def pase_expres_solicitud(call):
    bot.answer_callback_query(call.id)

    # Si ya venció mientras el usuario veía el menú, avisarle
    if not pase_expres_activo():
        editar_o_enviar_panel(
            call.message.chat.id,
            "⏰ <b>El Pase Exprés ya no está disponible.</b>\n\n"
            "Puedes acceder usando cualquiera de los métodos de pago. 👇",
            types.InlineKeyboardMarkup(),
            message=call.message,
        )
        return

    user_id  = call.from_user.id
    username = call.from_user.username or "sin_usuario"
    nombre   = call.from_user.first_name or "Usuario"

    # Mensaje de bienvenida al usuario
    msg_usuario = editar_o_enviar_panel(
        call.message.chat.id,
        "🎟️ <b>¡BIENVENIDO AL TEMPLO CACIQUEX VIP!</b> 🎉\n\n"
        "Tu solicitud de <b>Pase Exprés Gratuito</b> fue recibida.\n\n"
        "⏳ <i>Estamos procesando tu acceso, en un momento te llegará el link de ingreso al canal.</i>\n\n"
        "🙏 <i>Gracias por tu paciencia.</i>",
        types.InlineKeyboardMarkup(),
        message=call.message,
        protect_content=True,
    )

    # Notificación al admin
    mencion_html = f'<a href="tg://user?id={user_id}">{nombre}</a>'
    tiene_username = username != "sin_usuario"
    markup_admin = types.InlineKeyboardMarkup(row_width=1)
    if tiene_username:
        markup_admin.add(types.InlineKeyboardButton(
            f"💬 Abrir chat con @{username}",
            url=f"https://t.me/{username}"
        ))
    markup_admin.add(
        types.InlineKeyboardButton("✅ Aprobar Pase Exprés", callback_data=f"peap_{user_id}"),
        types.InlineKeyboardButton("❌ Rechazar",            callback_data=f"perec_{user_id}"),
    )
    uname_txt = f"@{username}" if tiene_username else "sin usuario"
    notif_msg = bot.send_message(
        int(ADMIN_ID),
        f"🎟️ <b>SOLICITUD DE PASE EXPRÉS GRATUITO</b>\n\n"
        f"👤 Nombre: {mencion_html}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"📛 Usuario: {uname_txt}",
        parse_mode="HTML", reply_markup=markup_admin,
        _force_new_message=True,
    )

    # Guardar para poder borrar mensajes al aprobar/rechazar
    solicitudes_info[user_id] = {
        'metodo': 'pase_expres', 'username': username,
        'notif_msg_id': notif_msg.message_id, 'datos_msg_id': None,
        'usuario_chat_id': call.message.chat.id,
        'usuario_msg_id':  msg_usuario.message_id,
    }

def markup_acceso_vip(user_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "🎟️ Confirmar y ver mi acceso",
        callback_data=f"vipconfirm_{int(user_id)}",
    ))
    return markup


def markup_enlace_canal_goldpass():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "🔓 Entrar al canal GoldPass",
        url=CANAL_INVITE_LINK_EXTERNO,
    ))
    return markup


def texto_acceso_vip(titulo):
    return (
        f"🎉 <b>{html.escape(str(titulo))}</b>\n\n"
        "Tu solicitud fue aprobada. Pulsa el botón para recibir tu bienvenida "
        "y el enlace de acceso al canal GoldPass. 🥳\n\n"
        "⏳ <i>El acceso aprobado es válido por 30 días.</i>"
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("vipconfirm_"))
def confirmar_acceso_goldpass(call):
    try:
        user_id = int(call.data.split("_", 1)[1])
    except (IndexError, ValueError):
        bot.answer_callback_query(call.id, "No pude validar este acceso.", show_alert=True)
        return

    if (
        call.message.chat.type != "private"
        or str(call.from_user.id) != str(user_id)
        or str(call.message.chat.id) != str(user_id)
    ):
        bot.answer_callback_query(
            call.id,
            "Este botón de acceso fue emitido para otra cuenta.",
            show_alert=True,
        )
        return

    consulta = Query()
    suscripcion = db.get(consulta.id == user_id)
    if not suscripcion or not suscripcion.get("vence"):
        bot.answer_callback_query(
            call.id,
            "No encuentro una aprobación activa. Escribe /start para ver las opciones.",
            show_alert=True,
        )
        return

    try:
        vencimiento = datetime.strptime(
            str(suscripcion["vence"]), "%Y-%m-%d %H:%M:%S"
        )
    except (TypeError, ValueError):
        vencimiento = None
    if vencimiento and vencimiento <= datetime.now():
        bot.answer_callback_query(
            call.id,
            "Este acceso venció. Escribe /start para renovar.",
            show_alert=True,
        )
        return

    if suscripcion.get("vip_access_sent"):
        bot.answer_callback_query(
            call.id,
            "Ya te envié el enlace de GoldPass en este chat.",
            show_alert=True,
        )
        return

    db.update({"vip_access_sent": True}, consulta.id == user_id)
    try:
        bienvenida = bot.send_message(
            user_id,
            "🎉 <b>¡Gracias por tu compra! Bienvenido/a a GoldPass.</b>\n\n"
            "Espero que disfrutes tu acceso. Pulsa el botón para entrar al canal.\n\n"
            "⏳ <i>Tu acceso es válido por 30 días.</i>",
            parse_mode="HTML",
            reply_markup=markup_enlace_canal_goldpass(),
            protect_content=True,
            _force_new_message=True,
        )
    except Exception:
        db.update({"vip_access_sent": False}, consulta.id == user_id)
        app.logger.exception(
            "No se pudo entregar el enlace GoldPass tras la confirmación del usuario."
        )
        bot.answer_callback_query(
            call.id,
            "No pude enviar el enlace. Inténtalo otra vez en unos segundos.",
            show_alert=True,
        )
        return

    try:
        bot.delete_message(user_id, call.message.message_id)
    except Exception:
        app.logger.info("No se pudo retirar el panel de aprobación VIP.")
    with PANEL_LOCK:
        panel = PANELES_PRIVADOS.get(PANEL_QUERY.chat_id == str(user_id))
        if panel and str(panel.get("message_id")) == str(call.message.message_id):
            PANELES_PRIVADOS.remove(PANEL_QUERY.chat_id == str(user_id))
    db.update(
        {
            "access_message_id": None,
            "access_welcome_message_id": bienvenida.message_id,
        },
        consulta.id == user_id,
    )
    bot.answer_callback_query(call.id, "Listo. Te envié la bienvenida y el acceso.")


# ─── Admin aprueba Pase Exprés ────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("peap_"))
def admin_aprobar_pase_expres(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)

    user_id  = int(call.data.split("_")[1])
    info     = solicitudes_info.pop(user_id, {})
    username = info.get('username', '')
    if username == 'sin_usuario':
        username = ''

    # Registrar en DB (30 días)
    vencimiento = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    db.upsert(
        {
            'id': user_id,
            'vence': vencimiento,
            'username': username,
            'vip_access_sent': False,
        },
        Query().id == user_id,
    )

    # Mantener la solicitud en el mismo panel; el primer botón confirma la
    # acción dentro del bot y luego entrega el enlace real del canal.
    user_chat_id = info.get("usuario_chat_id") or user_id
    try:
        mensaje_acceso = editar_o_enviar_panel(
            user_chat_id,
            texto_acceso_vip("¡Tu Pase Exprés ha sido aprobado!"),
            markup_acceso_vip(user_id),
            message_id=info.get("usuario_msg_id"),
            protect_content=True,
        )
        db.update(
            {"access_message_id": mensaje_acceso.message_id},
            Query().id == user_id,
        )
    except Exception as e:
        bot.send_message(int(ADMIN_ID),
            f"⚠️ No pude notificar al usuario <code>{user_id}</code> ({e}).\n"
            f"Envíale el link manualmente:\n{CANAL_INVITE_LINK_EXTERNO}",
            parse_mode="HTML")

    # Borrar notificación del admin
    try:
        bot.delete_message(int(ADMIN_ID), call.message.message_id)
    except:
        pass
    notif_id = info.get('notif_msg_id')
    if notif_id:
        try:
            bot.delete_message(int(ADMIN_ID), notif_id)
        except:
            pass

    bot.send_message(
        int(ADMIN_ID),
        "✅ <b>Pase Exprés aprobado.</b>\n"
        f"Usuario <code>{user_id}</code> recibió el botón para confirmar y ver su acceso.",
        parse_mode="HTML")

# ─── Admin rechaza Pase Exprés ────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("perec_"))
def admin_rechazar_pase_expres(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)

    user_id = int(call.data.split("_")[1])
    info    = solicitudes_info.pop(user_id, {})

    # Actualizar el panel privado del usuario y notificarle.
    try:
        editar_o_enviar_panel(
            user_id,
            "❌ <b>Tu solicitud de Pase Exprés no pudo ser procesada en este momento.</b>\n\n"
            "Puedes intentarlo con cualquier método de pago usando /start.",
            types.InlineKeyboardMarkup(),
        )
    except:
        pass

    # Borrar notificación del admin
    try:
        bot.delete_message(int(ADMIN_ID), call.message.message_id)
    except:
        pass

    bot.send_message(int(ADMIN_ID),
        "❌ <b>Pase Exprés rechazado.</b>\n"
        f"Usuario <code>{user_id}</code> notificado.",
        parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════
# 2. BOTONES DE PAGO → notificar admin
# ═══════════════════════════════════════════════════════════════════

# ─── Cuenta USA → sub-menú (Transferencia o Link) ─────────────────
@bot.callback_query_handler(func=lambda call: call.data == "pago_usa")
def pago_usa_submenu(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🏦 Transferencia Bancaria USA", callback_data="pago_usa_bank"),
        types.InlineKeyboardButton("🔗 Pago por Link",              callback_data="pago_usa_link"),
    )
    editar_o_enviar_panel(
        call.message.chat.id,
        "🇺🇸 <b>Cuenta USA — Elige tu forma de pago:</b>",
        markup,
        message=call.message,
        protect_content=True,
    )

# ─── Helper: solicitud de Pago por Link (compartido entre usa_link y visa_mc) ──
def _markup_solicitud_usuario():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔙 Volver",             callback_data="volver_metodos_pago"),
        types.InlineKeyboardButton("❌ Cancelar solicitud", callback_data="cancelar_solicitud"),
    )
    return markup

def _procesar_solicitud_link(call, metodo):
    user_id  = call.from_user.id
    username = call.from_user.username or "sin_usuario"
    nombre   = call.from_user.first_name or "Usuario"

    bot.answer_callback_query(call.id)
    solicitudes_pendientes[user_id] = metodo

    msg_usuario = editar_o_enviar_panel(
        call.message.chat.id,
        obtener_mensaje_solicitud_enlace(metodo),
        _markup_solicitud_usuario(),
        message=call.message,
        protect_content=True,
    )

    nombre_metodo  = NOMBRE_METODO.get(metodo, metodo)
    mencion_html   = f'<a href="tg://user?id={user_id}">{nombre}</a>'
    tiene_username = username != "sin_usuario"

    markup_admin = types.InlineKeyboardMarkup(row_width=1)
    if tiene_username:
        markup_admin.add(types.InlineKeyboardButton(
            "💬 Abrir chat del usuario", url=f"https://t.me/{username}"))
    markup_admin.add(
        types.InlineKeyboardButton("🔗 Crear enlace de pago",
                                   callback_data=f"ac_{user_id}_{metodo}"),
        types.InlineKeyboardButton("❌ Rechazar solicitud",
                                   callback_data=f"admin_no_{user_id}"),
    )

    texto_admin = (
        f"🔔 <b>NUEVA SOLICITUD DE PAGO</b>\n\n"
        f"👤 Nombre: {mencion_html}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"📛 Usuario: {'@' + username if tiene_username else '(sin @username)'}\n\n"
        f"💳 Método elegido: <b>{nombre_metodo}</b>"
    )

    try:
        notif_msg    = bot.send_message(
            int(ADMIN_ID), texto_admin,
            parse_mode="HTML", reply_markup=markup_admin,
            _force_new_message=True,
        )
        notif_msg_id = notif_msg.message_id
    except Exception as e:
        try:
            notif_msg    = bot.send_message(int(ADMIN_ID),
                                            texto_admin + f"\n\n⚠️ Error al cargar botones: {e}",
                                            parse_mode="HTML",
                                            _force_new_message=True)
            notif_msg_id = notif_msg.message_id
        except:
            notif_msg_id = None

    solicitudes_info[user_id] = {
        'metodo': metodo, 'username': username,
        'notif_msg_id': notif_msg_id, 'datos_msg_id': None,
        'usuario_chat_id': call.message.chat.id,
        'usuario_msg_id': msg_usuario.message_id,
    }

# ─── Pago por Link (desde sub-menú Cuenta USA) ────────────────────
@bot.callback_query_handler(func=lambda call: call.data == "pago_usa_link")
def solicitud_pago_usa_link(call):
    _procesar_solicitud_link(call, "pago_usa_link")

# ─── Pago por Link (desde botón Visa/Mastercard en menú principal) ─
@bot.callback_query_handler(func=lambda call: call.data == "pago_visa_mc")
def solicitud_pago_visa_mc(call):
    _procesar_solicitud_link(call, "pago_visa_mc")

# ─── Resto de métodos de pago (genérico) ──────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("pago_"))
def solicitud_pago(call):
    metodo   = call.data
    user_id  = call.from_user.id
    username = call.from_user.username or "sin_usuario"
    nombre   = call.from_user.first_name or "Usuario"

    bot.answer_callback_query(call.id)
    solicitudes_pendientes[user_id] = metodo

    # Mensaje al usuario: espera + aviso de comprobante
    msg_usuario = editar_o_enviar_panel(
        call.message.chat.id,
        "✨ <b>¡SOLICITUD RECIBIDA!</b> ✨\n\n"
        "⏳ Tu solicitud está <b>en proceso</b>.\n\n"
        "Nos comunicaremos contigo en breve con los datos de pago.\n\n"
        "🙏 <i>Gracias por tu paciencia.</i>",
        _markup_solicitud_usuario(),
        message=call.message,
        protect_content=True,
    )

    nombre_metodo = NOMBRE_METODO.get(metodo, metodo)

    # Enlace al usuario: en el TEXTO funciona tg:// siempre;
    # en botones URL solo es seguro usar https://, por eso separamos.
    mencion_html = f'<a href="tg://user?id={user_id}">{nombre}</a>'
    tiene_username = username != "sin_usuario"

    markup_admin = types.InlineKeyboardMarkup(row_width=1)
    if tiene_username:
        markup_admin.add(
            types.InlineKeyboardButton("💬 Abrir chat del usuario",
                                       url=f"https://t.me/{username}"),
        )
    markup_admin.add(
        types.InlineKeyboardButton("📋 Ver datos para copiar",
                                   callback_data=f"ac_{user_id}_{metodo}"),
        types.InlineKeyboardButton("❌ Rechazar solicitud",
                                   callback_data=f"admin_no_{user_id}"),
    )

    texto_admin = (
        f"🔔 <b>NUEVA SOLICITUD DE PAGO</b>\n\n"
        f"👤 Nombre: {mencion_html}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"📛 Usuario: {'@' + username if tiene_username else '(sin @username)'}\n\n"
        f"💳 Método elegido: <b>{nombre_metodo}</b>"
    )

    try:
        notif_msg = bot.send_message(
            int(ADMIN_ID), texto_admin,
            parse_mode="HTML", reply_markup=markup_admin,
            _force_new_message=True,
        )
        notif_msg_id = notif_msg.message_id
    except Exception as e:
        # Intento sin markup si hubo error con los botones
        try:
            notif_msg = bot.send_message(
                int(ADMIN_ID),
                texto_admin + f"\n\n⚠️ Error al cargar botones: {e}",
                parse_mode="HTML",
                _force_new_message=True,
            )
            notif_msg_id = notif_msg.message_id
        except:
            notif_msg_id = None

    # Guardar info de la solicitud para poder borrar mensajes después
    solicitudes_info[user_id] = {
        'metodo':         metodo,
        'username':       username,
        'notif_msg_id':   notif_msg_id,
        'datos_msg_id':   None,
        'usuario_chat_id': call.message.chat.id,
        'usuario_msg_id':  msg_usuario.message_id,
    }

# ─── Volver al menú de métodos de pago ───────────────────────────
@bot.callback_query_handler(func=lambda call: call.data == "volver_metodos_pago")
def volver_metodos(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    solicitudes_pendientes.pop(user_id, None)
    info = solicitudes_info.pop(user_id, {})
    # Borrar notificación al admin si existe
    notif_id = info.get('notif_msg_id')
    if notif_id:
        try:
            bot.delete_message(int(ADMIN_ID), notif_id)
        except:
            pass
    mostrar_metodos_pago(call.message.chat.id)

# ─── Cancelar solicitud: pedir motivo ────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data == "cancelar_solicitud")
def cancelar_solicitud_motivo(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💳 Método de pago equivocado",
                                   callback_data="cancel_razon_metodo"),
        types.InlineKeyboardButton("🚫 No quiero la suscripción por ahora",
                                   callback_data="cancel_razon_nosub"),
    )
    try:
        bot.edit_message_text(
            "❓ <b>¿Por qué estás cancelando la solicitud?</b>",
            call.message.chat.id, call.message.message_id,
            parse_mode="HTML", reply_markup=markup
        )
    except:
        bot.send_message(
            call.message.chat.id,
            "❓ <b>¿Por qué estás cancelando la solicitud?</b>",
            parse_mode="HTML", reply_markup=markup
        )

# ─── Cancelar solicitud: procesar motivo ─────────────────────────
@bot.callback_query_handler(func=lambda call: call.data in ("cancel_razon_metodo", "cancel_razon_nosub"))
def cancelar_solicitud_razon(call):
    bot.answer_callback_query(call.id)
    user_id  = call.from_user.id
    username = call.from_user.username or "sin_usuario"
    nombre   = call.from_user.first_name or "Usuario"

    razon_map = {
        "cancel_razon_metodo": "💳 Método de pago equivocado",
        "cancel_razon_nosub":  "🚫 No quiero la suscripción por ahora",
    }
    razon = razon_map[call.data]

    solicitudes_pendientes.pop(user_id, None)
    info = solicitudes_info.pop(user_id, {})

    # Borrar notificación al admin si existe
    notif_id = info.get('notif_msg_id')
    if notif_id:
        try:
            bot.delete_message(int(ADMIN_ID), notif_id)
        except:
            pass

    # Notificar al admin con el motivo
    mencion_html   = f'<a href="tg://user?id={user_id}">{nombre}</a>'
    tiene_username = username != "sin_usuario"
    bot.send_message(
        int(ADMIN_ID),
        f"🚫 <b>SOLICITUD CANCELADA</b>\n\n"
        f"👤 Nombre: {mencion_html}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"📛 Usuario: {'@' + username if tiene_username else '(sin @username)'}\n\n"
        f"📋 Razón: <b>{razon}</b>",
        parse_mode="HTML"
    )

    # Actualizar el panel del usuario con la confirmación.
    editar_o_enviar_panel(
        call.message.chat.id,
        "✅ <b>Solicitud cancelada.</b>\n\n"
        "Si cambias de opinión, usa /start para volver al menú.",
        types.InlineKeyboardMarkup(),
        message=call.message,
    )

# ─── "Crear enlace de pago" para métodos Pago por Link ───────────
# Intercepta ANTES del handler genérico ac_ para pedirle al admin el enlace.
_METODOS_LINK = {"pago_usa_link", "pago_visa_mc"}

@bot.callback_query_handler(func=lambda call: (
    call.data.startswith("ac_") and
    "_".join(call.data.split("_")[2:]) in _METODOS_LINK
))
def admin_crear_enlace_link(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    partes    = call.data.split("_")
    user_id   = int(partes[1])
    metodo    = "_".join(partes[2:])
    admin_estado[call.from_user.id] = {
        "paso":       "esperando_link_pago",
        "user_id_pago": user_id,
        "metodo_link":  metodo,
    }
    bot.send_message(
        call.message.chat.id,
        "🔗 <b>Crea el enlace de cobro</b> en tu plataforma y envíamelo aquí:\n\n"
        "<i>(Debe comenzar con https://)</i>",
        parse_mode="HTML"
    )

# ─── Ver datos para copiar ────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("ac_"))
def admin_ver_datos(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)

    partes        = call.data.split("_")
    user_id       = int(partes[1])
    metodo        = "_".join(partes[2:])
    datos         = obtener_datos_pago(metodo)
    nombre_metodo = NOMBRE_METODO.get(metodo, metodo)
    if not datos:
        bot.send_message(
            int(ADMIN_ID),
            f"⚠️ No hay información configurada para {html.escape(nombre_metodo)}. "
            "Ve a /admin → Métodos de pago e imagen para actualizarla.",
            parse_mode="HTML",
            protect_content=True,
        )
        return

    # CopyTextButton tiene límite de 256 chars; eliminar _AVISO del texto a copiar
    datos_sin_aviso = datos.replace(_AVISO, "").strip()

    markup = types.InlineKeyboardMarkup(row_width=1)
    try:
        # Botón de copia directa (Telegram Bot API 7.1+)
        markup.add(types.InlineKeyboardButton(
            "📋 Copiar datos",
            copy_text=types.CopyTextButton(text=datos_sin_aviso[:256])
        ))
    except Exception:
        pass  # Si la versión no lo soporta, los datos están en <code> para tocar y copiar
    markup.add(
        types.InlineKeyboardButton("✅ Aprobado",  callback_data=f"adap_{user_id}"),
        types.InlineKeyboardButton("❌ Rechazado", callback_data=f"adrec_{user_id}"),
    )

    datos_msg = bot.send_message(
        int(ADMIN_ID),
        f"📋 <b>DATOS — {nombre_metodo}</b>\n\n"
        f"<code>{html.escape(datos)}</code>",
        parse_mode="HTML",
        reply_markup=markup,
        protect_content=True,
    )
    # Guardar ID del mensaje de datos para borrarlo al aprobar/rechazar
    if user_id in solicitudes_info:
        solicitudes_info[user_id]['datos_msg_id'] = datos_msg.message_id
    else:
        solicitudes_info[user_id] = {
            'metodo': metodo, 'username': 'sin_usuario',
            'notif_msg_id': None, 'datos_msg_id': datos_msg.message_id
        }

# ─── Aprobado (desde pantalla de datos) ──────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("adap_"))
def admin_aprobar(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)

    user_id = int(call.data.split("_")[1])
    info    = solicitudes_info.pop(user_id, {})

    # Registrar suscripción VIP (30 días). El usuario confirma el acceso en
    # el bot y después recibe el enlace de invitación del canal.
    vencimiento = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    username = info.get('username', '')
    if username == 'sin_usuario':
        username = ''
    db.upsert(
        {
            'id': user_id,
            'vence': vencimiento,
            'username': username,
            'vip_access_sent': False,
        },
        Query().id == user_id,
    )

    user_chat_id = info.get("usuario_chat_id") or user_id
    try:
        mensaje_acceso = editar_o_enviar_panel(
            user_chat_id,
            texto_acceso_vip("¡Tu solicitud ha sido aprobada!"),
            markup_acceso_vip(user_id),
            message_id=info.get("usuario_msg_id"),
            protect_content=True,
        )
        db.update(
            {"access_message_id": mensaje_acceso.message_id},
            Query().id == user_id,
        )
    except Exception as e:
        bot.send_message(
            int(ADMIN_ID),
            f"⚠️ No pude notificar al usuario <code>{user_id}</code> directamente ({e}).\n"
            f"Es probable que nunca haya iniciado un chat privado con el bot (le dio /start).\n\n"
            f"Ya quedó registrado como VIP igual. Envíale tú este link manualmente:\n"
            f"{CANAL_INVITE_LINK_EXTERNO}",
            parse_mode="HTML"
        )

    # Borrar mensaje de datos (en el chat del admin)
    try:
        bot.delete_message(int(ADMIN_ID), call.message.message_id)
    except:
        pass

    # Borrar notificación original (en el chat del admin)
    notif_id = info.get('notif_msg_id')
    if notif_id:
        try:
            bot.delete_message(int(ADMIN_ID), notif_id)
        except:
            pass

    bot.send_message(int(ADMIN_ID),
        "✅ <b>Transacción completada con éxito.</b>\n"
        f"Usuario <code>{user_id}</code> notificado.",
        parse_mode="HTML"
    )

# ─── Rechazado (desde pantalla de datos) ─────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("adrec_"))
def admin_rechazar_datos(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)

    user_id = int(call.data.split("_")[1])
    info    = solicitudes_info.pop(user_id, {})

    # Mensaje de rechazo al usuario
    try:
        bot.send_message(
            user_id,
            "❌ <b>Tu solicitud ha sido rechazada.</b>\n\n"
            "El pago no pudo ser verificado. Si crees que es un error, "
            "escríbenos directamente.",
            parse_mode="HTML", protect_content=True
        )
    except Exception as e:
        bot.send_message(int(ADMIN_ID), f"⚠️ No pude notificar al usuario: {e}")

    # Borrar mensaje de datos (en el chat del admin)
    try:
        bot.delete_message(int(ADMIN_ID), call.message.message_id)
    except:
        pass

    # Borrar notificación original (en el chat del admin)
    notif_id = info.get('notif_msg_id')
    if notif_id:
        try:
            bot.delete_message(int(ADMIN_ID), notif_id)
        except:
            pass

    # Borrar mensaje "Solicitud recibida" del chat del usuario
    u_chat = info.get('usuario_chat_id')
    u_msg  = info.get('usuario_msg_id')
    if u_chat and u_msg:
        try:
            bot.delete_message(u_chat, u_msg)
        except:
            pass

    bot.send_message(int(ADMIN_ID),
        "❌ <b>Solicitud rechazada.</b>\n"
        f"Usuario <code>{user_id}</code> notificado.",
        parse_mode="HTML"
    )

# ─── Rechazar desde la primera notificación ───────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_no_"))
def admin_rechazar_notif(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    user_id = int(call.data.split("_")[2])
    solicitudes_info.pop(user_id, None)
    try:
        bot.send_message(
            user_id,
            "❌ <b>Tu solicitud no pudo ser procesada en este momento.</b>\n\n"
            "Por favor, intenta de nuevo más tarde.",
            parse_mode="HTML", protect_content=True
        )
        bot.edit_message_text(
            f"❌ <b>Solicitud rechazada</b> — <code>{user_id}</code>",
            call.message.chat.id, call.message.message_id, parse_mode="HTML"
        )
    except Exception as e:
        bot.send_message(int(ADMIN_ID), f"❌ Error: {e}")

# ═══════════════════════════════════════════════════════════════════
# 3. COMPROBANTES DE PAGO (fotos de usuarios)
# ═══════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════
# 4. APROBACIÓN VIP /aprobar ID
# ═══════════════════════════════════════════════════════════════════
@bot.message_handler(commands=['aprobar'])
def aprobar(message):
    if message.chat.type != "private" or str(message.from_user.id) != str(ADMIN_ID):
        return
    try:
        user_id    = int(message.text.split()[1])
    except:
        bot.send_message(int(ADMIN_ID),
            "❌ Error. Usa: <code>/aprobar ID</code>", parse_mode="HTML")
        return

    vencimiento = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    db.upsert(
        {
            'id': user_id,
            'vence': vencimiento,
            'username': '',
            'vip_access_sent': False,
        },
        Query().id == user_id,
    )

    try:
        mensaje_acceso = editar_o_enviar_panel(
            user_id,
            texto_acceso_vip("¡ACCESO VIP APROBADO!"),
            markup_acceso_vip(user_id),
            protect_content=True,
        )
        db.update(
            {"access_message_id": mensaje_acceso.message_id},
            Query().id == user_id,
        )
        bot.send_message(int(ADMIN_ID),
            f"✅ Botón de confirmación de acceso enviado a <code>{user_id}</code>.",
            parse_mode="HTML")
    except Exception as e:
        bot.send_message(
            int(ADMIN_ID),
            f"⚠️ No pude notificar al usuario <code>{user_id}</code> directamente ({e}).\n"
            f"Es probable que nunca haya iniciado un chat privado con el bot (le dio /start).\n\n"
            f"Ya quedó registrado como VIP igual. Envíale tú este link manualmente:\n"
            f"{CANAL_INVITE_LINK_EXTERNO}",
            parse_mode="HTML"
        )

# ═══════════════════════════════════════════════════════════════════
# 5. PRUEBA MANUAL: /expulsar ID_o_@username  (simula el vencimiento)
# ═══════════════════════════════════════════════════════════════════
@bot.message_handler(commands=['expulsar'])
def expulsar_manual(message):
    if message.chat.type != "private" or str(message.from_user.id) != str(ADMIN_ID):
        return
    try:
        objetivo = message.text.split(maxsplit=1)[1].strip()
    except IndexError:
        bot.send_message(int(ADMIN_ID),
            "❌ Error. Usa: <code>/expulsar ID</code> o <code>/expulsar @username</code>",
            parse_mode="HTML")
        return

    User = Query()
    if objetivo.startswith('@'):
        uname = objetivo[1:].lower()
        encontrados = db.search(User.username.test(lambda u: (u or '').lower() == uname))
        if not encontrados:
            bot.send_message(int(ADMIN_ID),
                f"⚠️ No encontré a @{uname} registrado como VIP.\n"
                f"Solo puedo buscar por username si ya se unió al canal después de este cambio.\n"
                f"Prueba con su ID numérico: <code>/expulsar ID</code>",
                parse_mode="HTML")
            return
        user_id = encontrados[0]['id']
    else:
        try:
            user_id = int(objetivo)
        except ValueError:
            bot.send_message(int(ADMIN_ID),
                "❌ ID inválido. Usa: <code>/expulsar ID</code> o <code>/expulsar @username</code>",
                parse_mode="HTML")
            return

    try:
        expulsar_usuario_vencido(user_id)
        bot.send_message(int(ADMIN_ID),
            f"✅ Usuario <code>{user_id}</code> expulsado y notificado (prueba manual).",
            parse_mode="HTML")
    except Exception as e:
        bot.send_message(int(ADMIN_ID),
            f"⚠️ No pude expulsar a <code>{user_id}</code>: {e}", parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════
# 6. REGISTRAR usuario manualmente: /registrar ID [@username]
# ═══════════════════════════════════════════════════════════════════
@bot.message_handler(commands=['registrar'])
def registrar_manual(message):
    if message.chat.type != "private" or str(message.from_user.id) != str(ADMIN_ID):
        return
    partes = message.text.split()
    if len(partes) < 2:
        bot.send_message(int(ADMIN_ID),
            "❌ Uso: <code>/registrar ID</code> o <code>/registrar ID @username</code>\n"
            "Registra al usuario con 30 días desde ahora.",
            parse_mode="HTML")
        return
    try:
        user_id = int(partes[1])
    except ValueError:
        bot.send_message(int(ADMIN_ID), "❌ El ID debe ser numérico.", parse_mode="HTML")
        return
    username = partes[2].lstrip('@') if len(partes) >= 3 else ""
    vencimiento = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    db.upsert({'id': user_id, 'vence': vencimiento, 'username': username}, Query().id == user_id)
    uname_txt = f"@{username}" if username else "—"
    bot.send_message(int(ADMIN_ID),
        f"✅ <b>Usuario registrado manualmente.</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"📛 Usuario: {uname_txt}\n"
        f"📅 Vence: <b>{vencimiento}</b>",
        parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════
# 7. VER LISTA VIP: /listar_vip
# ═══════════════════════════════════════════════════════════════════
@bot.message_handler(commands=['listar_vip'])
def listar_vip(message):
    if message.chat.type != "private" or str(message.from_user.id) != str(ADMIN_ID):
        return
    todos = db.all()
    if not todos:
        bot.send_message(int(ADMIN_ID), "📋 No hay usuarios registrados.", parse_mode="HTML")
        return
    ahora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    lineas = []
    for u in sorted(todos, key=lambda x: x.get('vence', '')):
        uid   = u.get('id', '?')
        vence = u.get('vence', '?')
        uname = f"@{u['username']}" if u.get('username') else "—"
        estado = "🟢" if vence > ahora else "🔴"
        lineas.append(f"{estado} <code>{uid}</code> {uname} → <b>{vence}</b>")
    texto = f"📋 <b>MIEMBROS VIP REGISTRADOS ({len(todos)})</b>\n\n" + "\n".join(lineas)
    bot.send_message(int(ADMIN_ID), texto, parse_mode="HTML")


def mostrar_panel_admin(chat_id, message=None):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💳 Métodos de pago e imagen", callback_data="admin_pagos"),
        types.InlineKeyboardButton("⚙️ Grupos y canales", callback_data="grupos_admin"),
    )
    return editar_o_enviar_panel(chat_id, "🛠 Panel privado de administración", markup, message=message, protect_content=True)

def teclado_admin_privado():
    k=types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, is_persistent=True)
    k.row(types.KeyboardButton("/start"), types.KeyboardButton("/admin"))
    k.row(types.KeyboardButton("💳 Pagos"), types.KeyboardButton("⚙️ Grupos y canales"))
    k.row(
      types.KeyboardButton("👥 Buscar grupo", request_chat=types.KeyboardButtonRequestChat(request_id=4101, chat_is_channel=False, request_title=True, request_username=True)),
      types.KeyboardButton("📢 Buscar canal", request_chat=types.KeyboardButtonRequestChat(request_id=4102, chat_is_channel=True, request_title=True, request_username=True)),
    )
    k.row(types.KeyboardButton("👤 Consultar usuario", request_users=types.KeyboardButtonRequestUsers(request_id=4103, user_is_bot=False, max_quantity=1, request_name=True, request_username=True)), types.KeyboardButton("❌ Cancelar"))
    return k

def _grupos_configurados():
    cfg=cargar_config(); out=[]
    for cid, info in cfg.get("group_settings", {}).items():
        try: n=int(cid)
        except (ValueError,TypeError): continue
        if n not in out: out.append(n)
    for key, info in cfg.get("destinos", {}).items():
        if not isinstance(info,dict) or info.get("archivado"): continue
        try: n=int(info.get("chat_id"))
        except (ValueError,TypeError): continue
        if n != int(CANAL_ID) and n not in out: out.append(n)
    return out

def es_grupo_autorizado(chat_id):
    try: return int(chat_id) in _grupos_configurados()
    except (ValueError,TypeError): return False

def _guardar_chat_seleccionado(chat_id, title, tipo, username=None):
    chat_id=int(chat_id); tipo="canal" if tipo=="canal" else "grupo"
    cfg=cargar_config(); destinos=cfg.setdefault("destinos", {})
    key=next((k for k,v in destinos.items() if isinstance(v,dict) and str(v.get("chat_id"))==str(chat_id)), None)
    if not key: key="dest_"+uuid.uuid4().hex[:10]
    destino=destinos.setdefault(key,{})
    destino.update({"nombre":str(title or chat_id),"chat_id":str(chat_id),"tipo":tipo})
    group=cfg.setdefault("group_settings", {}).setdefault(str(chat_id), {})
    group.update({"title":str(title or chat_id),"type":tipo})
    guardar_config(cfg)
    return key

def _destino_por_key(key):
    cfg=cargar_config(); d=cfg.get("destinos",{}).get(key)
    if d: return d
    if key.startswith("group:"):
        cid=key.split(":",1)[1]; info=cfg.get("group_settings",{}).get(cid)
        if isinstance(info,dict):
            return {"chat_id":cid,"nombre":info.get("title") or info.get("nombre") or cid,"tipo":info.get("type") or "grupo"}
    return None

def _markup_grupos_admin():
    m=types.InlineKeyboardMarkup(row_width=1)
    cfg=cargar_config(); items=[]; seen=set()
    for key,d in cfg.get("destinos",{}).items():
        if not isinstance(d,dict) or d.get("archivado"): continue
        cid=str(d.get("chat_id"))
        if not cid or cid==str(CANAL_ID): continue
        seen.add(cid); items.append((key,d))
    for cid,info in cfg.get("group_settings",{}).items():
        if str(cid) in seen or str(cid)==str(CANAL_ID) or not isinstance(info,dict): continue
        d={"chat_id":str(cid),"nombre":info.get("title") or info.get("nombre") or str(cid),"tipo":info.get("type") or "grupo"}
        items.append((f"group:{cid}",d))
    for key,d in items:
        m.add(types.InlineKeyboardButton(f"📂 {str(d.get('nombre') or d.get('chat_id'))[:36]} · {d.get('tipo','destino')}",callback_data=f"destinfo|{key}"))
    m.add(types.InlineKeyboardButton("➕ Buscar/añadir grupo o canal",callback_data="destpicker"))
    m.add(types.InlineKeyboardButton("🔙 Volver",callback_data="admin_home"))
    return m

@bot.callback_query_handler(func=lambda c: c.data=="admin_home")
def cb_admin_home(c):
    if not es_admin_privado(c): bot.answer_callback_query(c.id,"⛔ Sin permiso."); return
    bot.answer_callback_query(c.id); mostrar_panel_admin(c.message.chat.id,message=c.message)

@bot.callback_query_handler(func=lambda c: c.data=="grupos_admin")
def cb_grupos_admin(c):
    if not es_admin_privado(c): bot.answer_callback_query(c.id,"⛔ Sin permiso."); return
    bot.answer_callback_query(c.id)
    editar_o_enviar_panel(c.message.chat.id,"📂 Grupos y canales guardados",_markup_grupos_admin(),message=c.message,protect_content=True)

@bot.callback_query_handler(func=lambda c: c.data=="destpicker")
def cb_destpicker(c):
    if not es_admin_privado(c): bot.answer_callback_query(c.id,"⛔ Sin permiso."); return
    bot.answer_callback_query(c.id)
    editar_o_enviar_panel(
        c.message.chat.id,
        "Usa Buscar grupo o Buscar canal en la barra inferior para elegir un chat.",
        _markup_grupos_admin(),
        message=c.message,
        protect_content=True,
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("destinfo|"))
def cb_destinfo(c):
    if not es_admin_privado(c): bot.answer_callback_query(c.id,"⛔ Sin permiso."); return
    key=c.data.split("|",1)[1]; d=_destino_por_key(key)
    if not d: bot.answer_callback_query(c.id,"No encontré ese destino."); return
    bot.answer_callback_query(c.id)
    mid=types.InlineKeyboardMarkup(row_width=2)
    try: mid.add(types.InlineKeyboardButton("📋 Copiar ID",copy_text=types.CopyTextButton(text=str(d.get("chat_id")))) )
    except Exception: mid.add(types.InlineKeyboardButton("ID: "+str(d.get("chat_id")),callback_data="noop"))
    mid.add(types.InlineKeyboardButton("⌨️ Botones y publicaciones",callback_data=f"destkeyboard|{key}"),types.InlineKeyboardButton("⚙️ Abrir configuración",callback_data=f"dest_rules|{key}"))
    mid.add(types.InlineKeyboardButton("🗑️ Eliminar",callback_data=f"destdel_confirm|{key}"),types.InlineKeyboardButton("🔙 Volver",callback_data="grupos_admin"))
    text=f"{html.escape(str(d.get('nombre') or 'Destino'))}\nTipo: {html.escape(str(d.get('tipo') or 'grupo/canal'))}\nID: <code>{html.escape(str(d.get('chat_id')))}</code>"
    editar_o_enviar_panel(c.message.chat.id,text,mid,message=c.message,protect_content=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith("destdel_confirm|"))
def cb_destdel_confirm(c):
    if not es_admin_privado(c): bot.answer_callback_query(c.id,"⛔ Sin permiso."); return
    key=c.data.split("|",1)[1]; d=_destino_por_key(key)
    if not d: bot.answer_callback_query(c.id,"No encontré ese destino."); return
    bot.answer_callback_query(c.id)
    m=types.InlineKeyboardMarkup().row(types.InlineKeyboardButton("Sí, eliminar",callback_data=f"destdel|{key}"),types.InlineKeyboardButton("Cancelar",callback_data=f"destinfo|{key}"))
    editar_o_enviar_panel(c.message.chat.id,f"¿Eliminar {html.escape(str(d.get('nombre') or d.get('chat_id')))} de la lista?",m,message=c.message,protect_content=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith("destdel|"))
def cb_destdel(c):
    if not es_admin_privado(c): bot.answer_callback_query(c.id,"⛔ Sin permiso."); return
    key=c.data.split("|",1)[1]; cfg=cargar_config(); d=_destino_por_key(key)
    if not d: bot.answer_callback_query(c.id,"No encontré ese destino."); return
    cid=str(d.get("chat_id")); cfg.get("destinos",{}).pop(key,None); cfg.get("group_settings",{}).pop(cid,None); guardar_config(cfg)
    bot.answer_callback_query(c.id,"Eliminado de la lista.")
    editar_o_enviar_panel(c.message.chat.id,"Destino eliminado de la lista.",_markup_grupos_admin(),message=c.message,protect_content=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith("destkeyboard|"))
def cb_destkeyboard(c):
    if not es_admin_privado(c): bot.answer_callback_query(c.id,"⛔ Sin permiso."); return
    key=c.data.split("|",1)[1]; d=_destino_por_key(key)
    if not d: bot.answer_callback_query(c.id,"Destino no disponible."); return
    if d.get("tipo") == "canal":
        bot.answer_callback_query(
            c.id,
            "Telegram no admite teclados de respuesta en canales; publica botones en línea en una publicación.",
            show_alert=True,
        )
        return
    try:
        bot.send_message(int(d["chat_id"]),"🏹 Accesos rápidos disponibles para el grupo:",reply_markup=obtener_teclado_cuadritos())
        bot.answer_callback_query(c.id,"Botonera publicada.")
    except Exception:
        app.logger.exception("No se pudo publicar la botonera en un destino.")
        bot.answer_callback_query(c.id,"No se pudo publicar; revisa que el bot tenga permiso para enviar mensajes.",show_alert=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith("dest_rules|"))
def cb_dest_rules(c):
    if not es_admin_privado(c): bot.answer_callback_query(c.id,"⛔ Sin permiso."); return
    key=c.data.split("|",1)[1]; d=_destino_por_key(key)
    if not d: bot.answer_callback_query(c.id,"Destino no disponible."); return
    admin_estado[c.from_user.id]={"paso":"esperando_reglas_destino","chat_id":str(d.get("chat_id")),"dest_key":key,"panel_message_id":c.message.message_id}
    bot.answer_callback_query(c.id)
    editar_o_enviar_panel(c.message.chat.id,"Envía el texto de reglas para este grupo. Se guardará por separado para el destino seleccionado.",types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("Cancelar",callback_data="admin_pagos_cancelar")),message=c.message,protect_content=True)

@bot.message_handler(content_types=["chat_shared"])
def recibir_chat_compartido(message):
    if str(message.from_user.id)!=str(ADMIN_ID) or message.chat.type!="private": return
    shared=message.chat_shared
    title=getattr(shared,"title",None) or str(shared.chat_id)
    tipo="canal" if int(getattr(shared,"request_id",0))==4102 else "grupo"
    _guardar_chat_seleccionado(shared.chat_id,title,tipo,getattr(shared,"username",None))
    eliminar_mensaje_seguro(message.chat.id,message.message_id)
    editar_o_enviar_panel(
        message.chat.id,
        f"✅ Guardado: {html.escape(str(title))}\nID: <code>{shared.chat_id}</code>\n\nSelecciona el destino para ver sus acciones.",
        _markup_grupos_admin(),
        protect_content=True,
    )

@bot.message_handler(content_types=["users_shared"])
def recibir_usuario_compartido(message):
    if str(message.from_user.id)!=str(ADMIN_ID) or message.chat.type!="private": return
    shared=message.users_shared; users=getattr(shared,"users",[]) or []
    eliminar_mensaje_seguro(message.chat.id,message.message_id)
    summary=[]
    markup=types.InlineKeyboardMarkup(row_width=1)
    for user in users:
        user_id=getattr(user,"user_id",None)
        name=" ".join(filter(None,(getattr(user,"first_name",None),getattr(user,"last_name",None)))) or "Usuario"
        username=getattr(user,"username",None)
        summary.append(f"{html.escape(name)}" + (f" (@{html.escape(username)})" if username else "") + f" · <code>{user_id}</code>")
        if user_id is not None:
            try: markup.add(types.InlineKeyboardButton("📋 Copiar ID",copy_text=types.CopyTextButton(text=str(user_id))))
            except Exception: pass
    editar_o_enviar_panel(
        message.chat.id,
        "Usuario seleccionado:\n" + "\n".join(summary),
        markup,
        protect_content=True,
    )

@bot.message_handler(commands=["admin"], func=lambda m: m.chat.type=="private" and str(m.from_user.id)==str(ADMIN_ID))
def admin_command_private(message):
    if message.chat.type!="private" or str(message.from_user.id)!=str(ADMIN_ID): return
    mostrar_panel_admin(message.chat.id)
    bot.send_message(message.chat.id,"Atajos privados disponibles abajo.",reply_markup=teclado_admin_privado(),protect_content=True)

@bot.message_handler(func=lambda m: m.chat.type=="private" and str(m.from_user.id)==str(ADMIN_ID) and m.text in ("⚙️ Grupos y canales","💳 Pagos"),content_types=["text"])
def admin_shortcuts(message):
    eliminar_mensaje_seguro(message.chat.id,message.message_id)
    if message.text=="💳 Pagos": mostrar_admin_config_pagos(message.chat.id)
    else: editar_o_enviar_panel(message.chat.id,"Grupos y canales guardados",_markup_grupos_admin(),protect_content=True)

@bot.callback_query_handler(func=lambda c: c.data=="noop")
def cb_noop(c): bot.answer_callback_query(c.id)

@bot.message_handler(commands=["start"])
def start_payment(message):
    uid=message.from_user.id; chat_id=message.chat.id
    if message.chat.type in ("group","supergroup"):
        if not es_grupo_autorizado(chat_id): return
        eliminar_mensaje_seguro(chat_id,message.message_id)
        me=bot.get_me()
        m=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("💳 Abrir menú de acceso",url=f"https://t.me/{me.username}?start=payment"))
        bot.send_message(chat_id,"Para solicitar o gestionar tu acceso, abre el bot en privado:",reply_markup=m,protect_content=True)
        return
    if message.chat.type!="private": return
    mostrar_metodos_pago(chat_id)
    if str(uid)==str(ADMIN_ID): bot.send_message(chat_id,"Atajos privados de administración.",reply_markup=teclado_admin_privado(),protect_content=True)

@bot.message_handler(func=lambda m: m.chat.type=="private" and str(m.from_user.id)==str(ADMIN_ID) and bool(admin_estado.get(m.from_user.id, {}).get("paso")), content_types=["text"])
def flujo_admin_pago(message):
    if message.chat.type!="private" or str(message.from_user.id)!=str(ADMIN_ID): return
    state=admin_estado.get(message.from_user.id,{})
    paso=state.get("paso")
    if not paso: return
    text=(message.text or "").strip()
    if text.lower()=="/cancelar" or text=="❌ Cancelar":
        admin_estado.pop(message.from_user.id,None); eliminar_mensaje_seguro(message.chat.id,message.message_id)
        mostrar_admin_config_pagos(message.chat.id,message_id=state.get("panel_message_id"),aviso="Edición cancelada; no se guardaron cambios."); return
    if paso=="esperando_datos_metodo_pago":
        metodo=state.get("metodo_pago")
        if not text or len(text)>3000:
            eliminar_mensaje_seguro(message.chat.id,message.message_id); mostrar_admin_config_pagos(message.chat.id,message_id=state.get("panel_message_id"),aviso="Texto vacío o demasiado largo; vuelve a intentarlo."); return
        guardar_metodo_pago(metodo,text); eliminar_mensaje_seguro(message.chat.id,message.message_id); admin_estado.pop(message.from_user.id,None)
        mostrar_admin_config_pagos(message.chat.id,message_id=state.get("panel_message_id"),aviso="Método actualizado."); return
    if paso=="esperando_reglas_destino":
        cid=state.get("chat_id"); key=state.get("dest_key")
        eliminar_mensaje_seguro(message.chat.id,message.message_id)
        Config.upsert({"tipo":"reglamento","chat_id":str(cid),"valor.":text}, (User.tipo=="reglamento") & (User.chat_id==str(cid)))
        admin_estado.pop(message.from_user.id,None)
        editar_o_enviar_panel(message.chat.id,"✅ Reglamento guardado para el destino.",_markup_grupos_admin(),protect_content=True)
        return
    if paso=="esperando_link_pago":
        if not text.startswith("https://"):

            eliminar_mensaje_seguro(message.chat.id,message.message_id); bot.send_message(message.chat.id,"El enlace debe comenzar con https://. Inténtalo de nuevo.",protect_content=True); return
        target=state.get("user_id_pago"); method=state.get("metodo_link","pago_usa_link"); admin_estado.pop(message.from_user.id,None); eliminar_mensaje_seguro(message.chat.id,message.message_id)
        markup=types.InlineKeyboardMarkup(row_width=2)
        try: markup.add(types.InlineKeyboardButton("📋 Copiar enlace",copy_text=types.CopyTextButton(text=text)))
        except Exception: pass
        markup.add(types.InlineKeyboardButton("✅ Aprobado",callback_data=f"adap_{target}"),types.InlineKeyboardButton("❌ Rechazado",callback_data=f"adrec_{target}"))
        msg=bot.send_message(int(ADMIN_ID),f"🔗 <b>PAGO POR LINK</b>\n\n{html.escape(text)}{_AVISO_LINK}",parse_mode="HTML",reply_markup=markup,protect_content=True)
        info=solicitudes_info.setdefault(target,{"metodo":method,"username":"sin_usuario","notif_msg_id":None})
        info["datos_msg_id"]=msg.message_id

@bot.message_handler(func=lambda m: m.chat.type=="private", content_types=["photo"])
def recibir_foto_pago(message):
    if message.chat.type!="private": return
    uid=message.from_user.id
    if str(uid)==str(ADMIN_ID) and guardar_foto_menu_pagos(message,message.photo[-1].file_id): return
    if str(uid)==str(ADMIN_ID): return
    try:
        bot.forward_message(int(ADMIN_ID),message.chat.id,message.message_id)
        bot.send_message(int(ADMIN_ID),f"💰 COMPROBANTE\nID: <code>{uid}</code>",parse_mode="HTML",_force_new_message=True)
        eliminar_mensaje_disparador(message)
        bot.send_message(message.chat.id,"✅ Comprobante recibido. En breve verificamos tu pago.",protect_content=True)
    except Exception:
        app.logger.exception("No se pudo reenviar un comprobante de pago.")

@bot.message_handler(func=lambda m: m.chat.type=="private" and str(m.from_user.id)==str(ADMIN_ID) and admin_estado.get(m.from_user.id, {}).get("paso") in ("esperando_foto_metodos_pago","esperando_datos_metodo_pago"), content_types=["document","video","audio","animation"])
def admin_media_payment_fallback(message):
    if str(message.from_user.id)==str(ADMIN_ID) and message.chat.type=="private":
        if rechazar_archivo_foto_pagos(message) or rechazar_media_metodo_pago(message): return

@bot.chat_join_request_handler()
def aprobar_solicitud_goldpass(req):
    if str(req.chat.id)!=str(CANAL_ID): return
    rec=db.get(Query().id==req.from_user.id)
    if not rec or not rec.get("vence"): return
    try:
        expiry=datetime.strptime(str(rec["vence"]),"%Y-%m-%d %H:%M:%S")
        if expiry>datetime.now(): bot.approve_chat_join_request(req.chat.id,req.from_user.id)
    except Exception:
        app.logger.exception("No se pudo procesar solicitud de ingreso al canal VIP.")

@bot.my_chat_member_handler()
def guardian_autorizacion(update):
    chat=update.chat; new=getattr(update.new_chat_member,"status","")
    if new not in ("member","administrator"): return
    actor=getattr(update,"from_user",None)
    if actor and str(actor.id)==str(ADMIN_ID):
        title=getattr(chat,"title",None) or str(chat.id)
        _guardar_chat_seleccionado(chat.id,title,"canal" if chat.type=="channel" else "grupo")
        if chat.type in ("group","supergroup"):
            try: bot.send_message(chat.id,"🔱 Bot conectado. Accesos rápidos:",reply_markup=obtener_teclado_cuadritos())
            except Exception: app.logger.exception("No se pudo publicar la botonera inicial del grupo.")
        else:
            try: bot.send_message(int(ADMIN_ID),f"✅ Canal guardado: {html.escape(str(title))} · ID <code>{chat.id}</code>. Los teclados de respuesta son para grupos; usa botones en línea al publicar en canales.",parse_mode="HTML",protect_content=True)
            except Exception: app.logger.exception("No se pudo confirmar el canal al administrador.")
        return
    if es_grupo_autorizado(chat.id): return
    try: bot.leave_chat(chat.id)
    except Exception: pass
    try: bot.send_message(int(ADMIN_ID),f"🔒 Intento de agregar el bot a un chat no autorizado (ID {chat.id}); se retiró.",parse_mode="HTML")
    except Exception: pass


@bot.message_handler(commands=["menu"], func=lambda m: m.chat.type in ("group","supergroup") and es_grupo_autorizado(m.chat.id))
def group_menu_command(message):
    if message.chat.type in ("group","supergroup") and es_grupo_autorizado(message.chat.id):
        eliminar_mensaje_seguro(message.chat.id,message.message_id)
        bot.send_message(message.chat.id,"🏹 Usa los accesos rápidos de la barra inferior.",reply_markup=obtener_teclado_cuadritos())


def _default_group_id():
    ids=_grupos_configurados()
    return ids[0] if ids else int(os.environ.get("GROUP_ID","0"))
GRUPO_ID = _default_group_id()

# --- MOTOR PRINCIPAL ---
@bot.message_handler(content_types=['text', 'photo', 'video'])
def motor_principal(message):
    global ULTIMOS_MSGS
    chat_id, uid = message.chat.id, message.from_user.id
    print(f"📨 MENSAJE RECIBIDO — chat:{chat_id} uid:{uid} tipo:{message.content_type} texto:{message.text or '[media]'}")
    COMANDOS = ["/menu", "/compartir", "/reglas", "/vchat", "/admin", "/start", "/reportar"]

    # --- SEGURIDAD: BLOQUEAR GRUPOS NO AUTORIZADOS ---
    if message.chat.type in ['group', 'supergroup', 'channel'] and not es_grupo_autorizado(chat_id):
        try:
            bot.leave_chat(chat_id)
        except:
            pass
        return

    # --- SEGURIDAD: BLACKLIST ---
    if Blacklist.search(User.id == uid):
        return

    # --- SEGURIDAD: ANTI-FLOOD ---
    if str(uid) != str(ADMIN_ID) and es_flood(uid):
        try:
            bot.send_message(chat_id, "⚠️ Estás enviando mensajes muy rápido. Espera unos segundos.")
        except:
            pass
        return

    # --- SEGURIDAD: EN PRIVADO SOLO COMANDOS VÁLIDOS ---
    if message.chat.type == 'private' and str(uid) != str(ADMIN_ID):
        texto_check = (message.text or "").strip()
        es_comando = (
            any(texto_check.lower().startswith(c) for c in COMANDOS_VALIDOS_PRIVADO)
            or texto_check.startswith("/")
        )
        if not es_comando and message.content_type == 'text':
            return

    if uid == 1087968824:
        if message.text:
            bot_info = bot.get_me()
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(types.InlineKeyboardButton(
                "🏠 ABRIR MENÚ PRINCIPAL",
                url=f"https://t.me/{bot_info.username}?start=payment"
            ))
            bot.send_message(
                chat_id,
                "🏹 Pulsa el botón para abrir el Menú del Templo en privado. 🔥",
                reply_markup=markup
            )
        return

    uname = (message.from_user.username or "anonimo").lower()
    guardar_evidencia(message)
    if es_grupo_autorizado(chat_id):
        registrar_actividad_stats(uid, uname)
    if not message.text:
        return
    texto = message.text.lower()

    if texto.startswith("/reportar") or (texto.startswith("/start") and "reporte" in texto):
        if not es_grupo_autorizado(chat_id):
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("👤 REPORTAR USUARIO POR NOMBRE", callback_data="menu_reportar_nombre"),
                types.InlineKeyboardButton("🖼️ REPORTAR MULTIMEDIA", callback_data="menu_reportar_multimedia")
            )
            bot.send_message(
                chat_id,
                "🕵️ **CENTRO DE JUSTICIA — GRAN CACIQUE**\n\n"
                "¿Qué tipo de denuncia quieres realizar?\n\n"
                "👤 *Reportar por nombre* — envía una advertencia oficial al infractor en el grupo.\n"
                "🖼️ *Reportar multimedia* — revisa las últimas publicaciones del usuario y denuncia contenido específico.",
                reply_markup=markup
            )
        else:
            eliminar_mensaje_seguro(chat_id, message.message_id)
            if ULTIMOS_MSGS['reportar']:
                eliminar_mensaje_seguro(chat_id, ULTIMOS_MSGS['reportar'])
            markup = types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("🚩 REPORTAR AQUÍ", url=f"https://t.me/{bot.get_me().username}?start=reporte")
            )
            resp = bot.send_message(chat_id, f"👤 @{uname}, clica para denunciar.", reply_markup=markup)
            ULTIMOS_MSGS['reportar'] = resp.message_id
        return

    # --- BLOQUE DE START ---
    if texto in ["/start", "🏠 /start"] or texto.startswith("/start@") or texto.startswith("/start "):
        if not es_grupo_autorizado(chat_id):
            markup = types.InlineKeyboardMarkup(row_width=1)
            btn_grupo = types.InlineKeyboardButton("🔥 ENTRAR AL GRUPO PRINCIPAL", url=LINK_GRUPO)
            btn_invitar = types.InlineKeyboardButton("🚀 INVITAR A GUERREROS", url=LINK_SHARE)
            btn_vip = types.InlineKeyboardButton("💎 SOLICITAR ACCESO VIP", callback_data="solicitar_vip")
            btn_promo = types.InlineKeyboardButton("📢 CREAR MI PUBLICACIÓN", callback_data="crear_promo")
            btn_canal = types.InlineKeyboardButton("📺 ENTRAR AL CANAL GRATUITO", callback_data="canal_gratuito")
            markup.add(btn_grupo, btn_invitar, btn_vip, btn_promo, btn_canal)
            if str(uid) == str(ADMIN_ID):
                markup.add(types.InlineKeyboardButton("⚙️ CONFIGURACIÓN DEL CACIQUE", callback_data="admin_config_panel"))
            bot.send_message(
                chat_id,
                "🏹 *¡BIENVENIDO AL TEMPLO DEL CACIQUE!*\n\nSelecciona una opción de combate:",
                reply_markup=markup
            )
            bot.send_message(chat_id, "⚔️ Tus armas de guerrero están listas.", reply_markup=obtener_teclado_cuadritos())
        else:
            eliminar_mensaje_seguro(chat_id, message.message_id)
            if ULTIMOS_MSGS['start']:
                eliminar_mensaje_seguro(chat_id, ULTIMOS_MSGS['start'])
            bot_info = bot.get_me()
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(types.InlineKeyboardButton(
                "🏠 ABRIR MENÚ DEL CACIQUE",
                url=f"https://t.me/{bot_info.username}?start=payment"
            ))
            aviso = bot.send_message(
                chat_id,
                f"🏹 @{uname}, pulsa el botón para abrir el Menú del Templo en privado. 🔥",
                reply_markup=markup
            )
            ULTIMOS_MSGS['start'] = aviso.message_id
        return

    if "/menu" in texto:
        nombre_display = message.from_user.first_name or f"@{uname}"
        msg_menu = (
            f"🔱 **¡{nombre_display}, tus herramientas están activas!** ⚔️⚔️\n\n"
            f"Usa los botones de la barra de mensajes para dominar la tribu.\n"
            f"💎 Todo el poder de la tribu está en tus manos. 🏹🔥"
        )
        if es_grupo_autorizado(chat_id):
            eliminar_mensaje_seguro(chat_id, message.message_id)
            if ULTIMOS_MSGS['menu']:
                eliminar_mensaje_seguro(chat_id, ULTIMOS_MSGS['menu'])
            resp = bot.send_message(chat_id, msg_menu, reply_markup=obtener_teclado_cuadritos())
            ULTIMOS_MSGS['menu'] = resp.message_id
        elif message.chat.type == "private":
            mostrar_metodos_pago(chat_id)

    elif "/compartir" in texto:
        if es_grupo_autorizado(chat_id):
            eliminar_mensaje_seguro(chat_id, message.message_id)
            if ULTIMOS_MSGS['compartir']:
                eliminar_mensaje_seguro(chat_id, ULTIMOS_MSGS['compartir'])
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("🚀 INVITAR GUERREROS AL TEMPLO", url=LINK_SHARE))
        txt_compartir = (
            f"🏹 @{uname}, ¡recluta más guerreros para la tribu!\n\n"
            f"Pulsa el botón y elige a quién quieres invitar directamente desde tus contactos. 🔥"
        )
        if es_grupo_autorizado(chat_id):
            resp = bot.send_message(chat_id, txt_compartir, reply_markup=markup)
            ULTIMOS_MSGS['compartir'] = resp.message_id
        else:
            bot.send_message(chat_id, txt_compartir, reply_markup=markup)

    elif "/reglas" in texto:
        reglas_cfg = Config.search((User.tipo == 'reglamento') & (User.chat_id == str(chat_id))) or Config.search(User.tipo == 'reglamento')
        saved_group = cargar_config().get("group_settings", {}).get(str(chat_id), {})
        val = reglas_cfg[0]['valor.'] if reglas_cfg else saved_group.get("rules") or "Respeta al Cacique."
        if es_grupo_autorizado(chat_id):
            eliminar_mensaje_seguro(chat_id, message.message_id)
            if ULTIMOS_MSGS['reglas']:
                eliminar_mensaje_seguro(chat_id, ULTIMOS_MSGS['reglas'])
            resp = bot.send_message(chat_id, f"📜 **REGLAMENTO SAGRADO**\n\n{val}", reply_markup=obtener_teclado_cuadritos())
            ULTIMOS_MSGS['reglas'] = resp.message_id
        else:
            bot.send_message(chat_id, f"📜 **REGLAMENTO SAGRADO**\n\n{val}", reply_markup=obtener_teclado_cuadritos())

    elif "/vchat" in texto:
        if es_grupo_autorizado(chat_id):
            eliminar_mensaje_seguro(chat_id, message.message_id)
            enviar_invitacion_vchat(chat_id)

    elif "/admin" in texto:
        bot_info = bot.get_me()
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("👤 Contactar Cacique", url=f"https://t.me/{MY_USER}"),
            types.InlineKeyboardButton("🚩 REPORTAR INFRACTOR", url=f"https://t.me/{bot_info.username}?start=reporte")
        )
        if es_grupo_autorizado(chat_id):
            eliminar_mensaje_seguro(chat_id, message.message_id)
            if ULTIMOS_MSGS['admin']:
                eliminar_mensaje_seguro(chat_id, ULTIMOS_MSGS['admin'])
            resp = bot.send_message(chat_id, "🚩 **CENTRO DE COMANDO**", reply_markup=markup)
            ULTIMOS_MSGS['admin'] = resp.message_id
        else:
            bot.send_message(chat_id, "🚩 **CENTRO DE COMANDO**", reply_markup=markup)


# --- MANEJO DE CALLBACKS ---
@bot.callback_query_handler(func=lambda call: True)
def manejar_clics(call):
    uid, mid = call.from_user.id, call.message.message_id
    u_name = call.from_user.first_name
    u_user = call.from_user.username or "SinUser"

    if Blacklist.search(User.id == uid):
        bot.answer_callback_query(call.id, "❌ Acceso denegado.")
        return

    if str(uid) != str(ADMIN_ID) and es_flood(uid):
        bot.answer_callback_query(call.id, "⚠️ Demasiadas acciones. Espera un momento.")
        return

    # PANEL DE CONFIGURACIÓN ADMIN
    if call.data == "admin_config_panel":
        if str(uid) != str(ADMIN_ID):
            bot.answer_callback_query(call.id, "❌ Acceso denegado: No eres el Cacique Supremo.")
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("📝 EDITAR REGLAMENTO", callback_data="edit_reglas"))
        bot.edit_message_text("🛠 **PANEL DE CONTROL DEL CACIQUE**", uid, mid, reply_markup=markup)

    elif call.data == "edit_reglas":
        if str(uid) != str(ADMIN_ID):
            return
        msg = bot.send_message(uid, "📝 **Escribe el nuevo reglamento para la tribu:**")
        bot.register_next_step_handler(msg, guardar_reglas_db)

    elif call.data == "solicitar_vip":
        bot.answer_callback_query(call.id, "Solicitud enviada.")
        bot.send_message(uid, "✅ **Solicitud enviada al consejo.** Espera a que el Cacique autorice tu entrada.")
        m_vip = types.InlineKeyboardMarkup()
        m_vip.add(
            types.InlineKeyboardButton("✅ APROBAR", callback_data=f"vip_si_{uid}"),
            types.InlineKeyboardButton("❌ NO (Rechazar)", callback_data=f"vip_no_{uid}")
        )
        info_vip = (
            f"💎 **SOLICITUD DE ACCESO VIP**\n\n"
            f"👤 **Guerrero:** {u_name}\n"
            f"🔗 **User:** @{u_user}\n"
            f"🆔 **ID:** {uid}\n\n"
            f"¿Deseas enviar el enlace de pago a este guerrero?"
        )
        bot.send_message(ADMIN_ID, info_vip, reply_markup=m_vip)

    elif call.data == "canal_gratuito":
        bot.answer_callback_query(call.id)
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton(
            "🔥 UNIRME AL TEMPLO DEL CACIQUE X",
            url=LINK_CANAL_GRATUITO
        ))
        bot.send_message(
            uid,
            "🏹 **¿ESTÁS LISTO PARA UNIRTE AL TEMPLO DEL CACIQUE X?**\n\n"
            "Este canal es completamente *gratuito* y está lleno de contenido exclusivo "
            "de la comunidad más ardiente de Telegram. 🔥\n\n"
            "🔱 Si quieres disfrutar del placer y apoyar al Cacique X, "
            "pulsa el botón de abajo y sé parte de nuestra comunidad. ¡La tribu te espera! 💎⚔️",
            reply_markup=markup
        )

    elif call.data.startswith("vip_si_"):
        target_id = int(call.data.split("_")[2])
        bot.answer_callback_query(call.id, "Aprobado")
        bot.edit_message_text(f"✅ **APROBADO:** Se ha enviado el bot de pago al Guerrero {target_id}.", ADMIN_ID, mid)
        txt_pago = (
            f"🔥 **¡ATENCIÓN GUERRERO!** 🔥\n\n"
            f"Tu solicitud ha sido aprobada por el Cacique. Para entrar al Templo VIP, "
            f"debes realizar el pago correspondiente a través de nuestro bot oficial:\n\n"
            f"💰 **SISTEMA DE PAGO:** {BOT_PAGO}\n\n"
            f"Una vez realizado el pago, el bot te dará acceso inmediato. ¡Nos vemos en la cima! 🏹"
        )
        bot.send_message(target_id, txt_pago)

    elif call.data.startswith("vip_no_"):
        target_id = int(call.data.split("_")[2])
        bot.answer_callback_query(call.id, "Rechazado")
        bot.edit_message_text(f"❌ **RECHAZADO:** Solicitud VIP denegada.", ADMIN_ID, mid)
        bot.send_message(target_id, "❌ **Tu solicitud VIP ha sido rechazada por el consejo.**")

    elif call.data == "crear_promo":
        msg = bot.send_message(uid, "📸 Envía Foto o Video:")
        bot.register_next_step_handler(msg, step_multimedia_promo)

    elif call.data == "add_link":
        msg = bot.send_message(uid, "🔗 Envía el siguiente enlace:")
        bot.register_next_step_handler(msg, step_link_promo)

    elif call.data.startswith("finalizar_promo_"):
        bot.answer_callback_query(call.id)
        target_uid = int(call.data.split("_")[2])
        d = user_data.get(target_uid)
        if d:
            m_adm = types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("🚀 APROBAR", callback_data=f"aprobar_{target_uid}"),
                types.InlineKeyboardButton("❌ RECHAZAR", callback_data=f"rechazar_{target_uid}")
            )
            cap = f"🆕 **REVISIÓN**\n👤 @{d['uname']}\nID: {target_uid}\n\n{d['desc']}"
            if d['is_video']:
                bot.send_video(ADMIN_ID, d['file_id'], caption=cap, reply_markup=m_adm)
            else:
                bot.send_photo(ADMIN_ID, d['file_id'], caption=cap, reply_markup=m_adm)
            bot.send_message(target_uid, "🏹 **PUBLICACIÓN ENVIADA.**")

    elif call.data.startswith("aprobar_"):
        target_uid = int(call.data.split("_")[1])
        d = user_data.get(target_uid)
        if d:
            PromosAprobadas.insert(d)
            mk = types.InlineKeyboardMarkup()
            for b in d['botones']:
                mk.add(types.InlineKeyboardButton(b['text'], url=b['url']))
            if d['is_video']:
                bot.send_video(GRUPO_ID, d['file_id'], caption=d['desc'], reply_markup=mk)
            else:
                bot.send_photo(GRUPO_ID, d['file_id'], caption=d['desc'], reply_markup=mk)
            bot.edit_message_caption("🚀 **PUBLICADO**", ADMIN_ID, mid)
            bot.send_message(target_uid, "✅ **¡APROBADO!**")
            bot.answer_callback_query(call.id)

    elif call.data.startswith("rechazar_"):
        target_uid = int(call.data.split("_")[1])
        bot.answer_callback_query(call.id, "Rechazada")
        bot.edit_message_caption("❌ **RECHAZADA**", ADMIN_ID, mid)
        bot.send_message(target_uid, "❌ **Tu publicación no fue aprobada.**")

    elif call.data == "menu_reportar_nombre":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            uid,
            "👤 **REPORTAR USUARIO POR NOMBRE**\n\n"
            "Escribe el @usuario del infractor que quieres denunciar:\n"
            "_(Ejemplo: @NombreDelUsuario o NombreDelUsuario)_"
        )
        bot.register_next_step_handler(msg, step_reporte_por_nombre)

    elif call.data == "menu_reportar_multimedia":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            uid,
            "🖼️ **REPORTAR MULTIMEDIA**\n\n"
            "Escribe el @usuario del infractor cuyas publicaciones quieres revisar:\n"
            "_(Ejemplo: @NombreDelUsuario o NombreDelUsuario)_"
        )
        bot.register_next_step_handler(msg, step_reporte_multimedia_buscar)

    elif call.data.startswith("rpt_media_"):
        parts = call.data.split("_", 3)
        t_id = int(parts[2])
        t_name = parts[3]
        bot.answer_callback_query(call.id, "⚠️ Reporte enviado")
        aplicar_castigo(GRUPO_ID, t_id, t_name)
        advertencias = Warnings.search(User.id == t_id)
        count = advertencias[0]['count'] if advertencias else 1
        bot.send_message(
            uid,
            f"✅ **REPORTE APLICADO**\n\n"
            f"Advertencia {count}/3 enviada a @{t_name} en el grupo.\n"
            f"Ha sido silenciado 35 minutos."
        )


# --- PASOS DE REPORTES ---
def step_reporte_por_nombre(message):
    uid = message.chat.id
    target = message.text.strip().lstrip("@").lower()
    registros = RegistroActividad.search(Query().uname == target)
    if not registros:
        bot.send_message(
            uid,
            f"❌ **No encontré registros de @{target}** en el grupo.\n\n"
            "Verifica que el usuario haya participado recientemente y que el @usuario sea correcto."
        )
        return
    t_id = registros[0]['id']
    aplicar_castigo(GRUPO_ID, t_id, target)
    advertencias = Warnings.search(User.id == t_id)
    count = advertencias[0]['count'] if advertencias else 1
    bot.send_message(
        uid,
        f"✅ **REPORTE ENVIADO**\n\n"
        f"Se ha enviado advertencia oficial *{count}/3* a @{target} en el grupo.\n"
        f"Ha sido silenciado durante 35 minutos.\n\n"
        f"_A la tercera penalización será expulsado permanentemente._"
    )

def step_reporte_multimedia_buscar(message):
    uid = message.chat.id
    target = message.text.strip().lstrip("@").lower()
    todos = RegistroActividad.search(Query().uname == target)
    media = [r for r in todos if r.get('type') in ('photo', 'video', 'text') or r.get('file_id')]
    ultimos = media[-6:] if len(media) > 6 else media
    if not ultimos:
        bot.send_message(
            uid,
            f"❌ **Sin publicaciones registradas de @{target}**.\n\n"
            "Verifica que el usuario haya enviado fotos, videos o mensajes en el grupo."
        )
        return
    bot.send_message(
        uid,
        f"🔍 **Últimas publicaciones de @{target}**\n\n"
        f"Encontré *{len(ultimos)}* registro(s). Pulsa 🚩 REPORTAR en el que quieras denunciar:"
    )
    t_id = ultimos[0]['id']
    for r in ultimos:
        markup = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("🚩 REPORTAR ESTE CONTENIDO", callback_data=f"rpt_media_{t_id}_{target}")
        )
        try:
            if r.get('type') == 'photo' and r.get('file_id'):
                bot.send_photo(uid, r['file_id'], caption=f"📸 Foto de @{target}\n_{r.get('text','') or 'Sin texto'}_", reply_markup=markup)
            elif r.get('type') == 'video' and r.get('file_id'):
                bot.send_video(uid, r['file_id'], caption=f"🎥 Video de @{target}\n_{r.get('text','') or 'Sin texto'}_", reply_markup=markup)
            else:
                txt = r.get('text', '[sin texto]') or '[sin texto]'
                bot.send_message(uid, f"💬 **Mensaje de @{target}:**\n_{txt}_", reply_markup=markup)
        except:
            txt = r.get('text', '[contenido no disponible]') or '[contenido no disponible]'
            bot.send_message(uid, f"⚠️ @{target}: _{txt}_", reply_markup=markup)


# --- PASOS PROMO ---
def step_multimedia_promo(message):
    uid = message.chat.id
    if not (message.photo or message.video):
        bot.send_message(uid, "❌ Material no válido.")
        return
    user_data[uid] = {
        'file_id': message.photo[-1].file_id if message.photo else message.video.file_id,
        'is_video': True if message.video else False,
        'uname': message.from_user.username,
        'botones': []
    }
    bot.send_message(uid, "✍️ Descripción:")
    bot.register_next_step_handler(message, step_descripcion_promo)

def step_descripcion_promo(message):
    uid = message.chat.id
    if uid not in user_data:
        bot.send_message(uid, "⌛ **Sesión expirada.** Usa /start de nuevo.")
        return
    user_data[uid]['desc'] = message.text
    bot.send_message(uid, "🔗 Envía enlace:")
    bot.register_next_step_handler(message, step_link_promo)

def step_link_promo(message):
    uid, link = message.chat.id, message.text
    if uid not in user_data:
        bot.send_message(uid, "⚠️ **ERROR DE MEMORIA:** El bot se reinició. Por favor, inicia de nuevo con /start")
        return
    if "http" not in link:
        bot.send_message(uid, "❌ Link inválido. Intenta de nuevo:")
        bot.register_next_step_handler(message, step_link_promo)
        return
    emoji = obtener_emoji_link(link)
    nombre_red = obtener_nombre_red(link)
    user_data[uid]['botones'].append({'text': f"{emoji} {nombre_red}", 'url': link})
    lista_botones_texto = ""
    for b in user_data[uid]['botones']:
        lista_botones_texto += f"🔹 {b['text']}\n"
    texto_previa = (
        f"✅ **ENLACE REGISTRADO ({len(user_data[uid]['botones'])}/3)**\n\n"
        f"**Así se verán tus botones:**\n"
        f"{lista_botones_texto}\n"
        f"¿Deseas agregar otro o enviar al Cacique?"
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ OTRO ENLACE", callback_data="add_link"),
        types.InlineKeyboardButton("🏹 ENVIAR AL CACIQUE", callback_data=f"finalizar_promo_{uid}")
    )
    bot.send_message(uid, texto_previa, reply_markup=markup)


# --- GUARDAR REGLAS ---
def guardar_reglas_db(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        return
    Config.upsert({'tipo': 'reglamento', 'chat_id': admin_estado.get(message.from_user.id, {}).get('chat_id', 'global'), 'valor.': message.text}, (User.tipo == 'reglamento') & (User.chat_id == admin_estado.get(message.from_user.id, {}).get('chat_id', 'global')))
    bot.send_message(ADMIN_ID, "✅ **REGLAMENTO ACTUALIZADO CON ÉXITO.**")

def proceso_obtener_usuario_reporte(message):
    target = message.text.strip().replace("@", "").lower()
    encontrado = RegistroActividad.search(Query().uname == target)
    if encontrado:
        t_id, t_name = encontrado[0]['id'], encontrado[0]['uname']
        markup = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("🚩 SENTENCIAR", callback_data=f"ejecutar_reporte_{t_id}_{t_name}")
        )
        bot.send_message(message.chat.id, f"👤 **ENCONTRADO:** @{t_name}", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "❌ Sin registros.")



if __name__ == "__main__":
    threading.Thread(target=revisar_vencimientos, name="vip-expiry", daemon=True).start()
    threading.Thread(target=bucle_repost_automatico, name="scheduled-reposts", daemon=True).start()
    threading.Thread(target=bucle_notificacion_menu, name="group-menu-reminder", daemon=True).start()
    # Preserve the deployed Render webhook; never replace it with a Replit dev URL.
    mode=os.environ.get("BOT_MODE","webhook").strip().lower()
    port=int(os.environ.get("PORT","10000"))
    if mode=="polling":
        bot.delete_webhook(drop_pending_updates=False)
        threading.Thread(target=lambda: bot.infinity_polling(skip_pending=False,allowed_updates=WEBHOOK_ALLOWED_UPDATES),daemon=True).start()
    elif mode=="webhook":
        base=(os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("WEBHOOK_URL") or "").rstrip("/")
        if not base: raise RuntimeError("Falta RENDER_EXTERNAL_URL o WEBHOOK_URL para registrar el webhook.")
        if not bot.set_webhook(url=base+WEBHOOK_PATH,secret_token=WEBHOOK_SECRET,allowed_updates=WEBHOOK_ALLOWED_UPDATES):
            raise RuntimeError("Telegram no aceptó el registro del webhook.")
    else: raise RuntimeError("BOT_MODE debe ser webhook o polling.")
    app.run(host="0.0.0.0",port=port,threaded=True,use_reloader=False)
