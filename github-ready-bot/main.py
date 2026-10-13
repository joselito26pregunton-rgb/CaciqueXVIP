import os, threading, time, json, hashlib, hmac, html, random, re, uuid, urllib.parse, unicodedata
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
FREE_GOLDPASS_PROMO_CHAT_ID = "-1003561176552"
GROUP_ADMIN_CONTACT_URL = "https://t.me/Ja2610X"
CANAL_INVITE_LINK = "https://t.me/+U7Kk_sC9pToxZjIx"
CANAL_INVITE_LINK_EXTERNO = "https://t.me/+xjHnFXb_QTY0NGEx"
LINK_GRUPO = "https://t.me/+DT-eLLYZ0g8wNmMx"
LINK_CANAL_GRATUITO = "https://t.me/+c6gutVsBfRw4YWUx"
VIDEOCHAT_INVITE_URLS = {
    "cxhotgochat": "https://t.me/CXHOTGOChat?videochat=a627e2ca16ca8e697d",
}
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
FreeGoldPasses = db.table("free_goldpass")
FREE_GOLDPASS_QUERY = Query()
FREE_GOLDPASS_LOCK = threading.RLock()
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
PANELES_GRUPO_MIEMBRO = {}
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
GroupReports = TinyDB(os.path.join(BASE_DIR, "group_reports.json"))
GroupModerationLog = TinyDB(os.path.join(BASE_DIR, "group_moderation_log.json"))
GroupBannedWords = TinyDB(os.path.join(BASE_DIR, "group_banned_words.json")).table("words")
PromosAprobadas = TinyDB(os.path.join(BASE_DIR, "promos_aprobadas.json"))
RegistroActividad = TinyDB(os.path.join(BASE_DIR, "registro_actividad.json"))
Suscripciones = TinyDB(os.path.join(BASE_DIR, "suscripciones.json"))
Estadisticas = TinyDB(os.path.join(BASE_DIR, "stats.json"))
User = Query()

DEFAULT_PROHIBITED_WORD_GROUPS = (
    ("Abuso sexual infantil", (
        "cp", "pedofilia", "pedofilo", "paidofilia", "pedophile", "pedo",
        "cp link", "cp telegram", "lolita", "loli", "p3do", "p3dofilia",
        "p*do", "niñas", "niños", "menores", "underage", "preteen",
        "toddler", "child", "childporn", "childpornography", "csam", "csae",
        "infantil", "schoolgirl", "kinder",
    )),
    ("Bestialismo y zoofilia", (
        "zoofilia", "zoofilico", "zoophilia", "bestialismo", "bestiality",
        "zoo", "zooporn", "animales", "perros", "caballos", "zoo video",
    )),
    ("Violencia extrema, gore y mutilación", (
        "gore", "snuff", "decapitacion", "decapitado", "mutilacion",
        "tortura", "torture", "asesinato", "murder", "sangre extrema",
        "dismemberment", "execution", "ejecucion", "cartel gore", "suicidio",
        "suicide", "autolesion", "cutters",
    )),
    ("Abuso, no consensual y necrofilia", (
        "necrofilia", "necro", "necrophilia", "cadáver", "cadaver", "corpse",
        "violacion", "rape", "forced", "forzado", "sin consentimiento",
        "non consensual", "drogada", "unconscious", "inconsciente",
    )),
    ("Estafas, spam y material ilegal adicional", (
        "carding", "bins", "cc", "clonadas", "drogas", "drugs",
        "venta de armas", "weapons", "hitman", "sicario",
    )),
)
_PROHIBITED_WORDS_READY = set()
_PROHIBITED_WORDS_CACHE = {}
_PROHIBITED_WORDS_DESTINATION_CACHE = {}

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
        _PROHIBITED_WORDS_DESTINATION_CACHE.clear()
        _PROHIBITED_WORDS_READY.clear()
        _PROHIBITED_WORDS_CACHE.clear()
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
    "🏹 HAS SIDO INVITADO AL TEMPLO DEL CACIQUE\n\n"
    "Únete a la tribu más exclusiva de Telegram. Contenido único, las mejores fotos y "
    "videos de los guerreros más calientes de la tribu. 🔥\n\n"
    f"ÚNETE AQUÍ: {LINK_GRUPO}"
)
MSG_INVITACION_TEXTO = (
    "🏹 HAS SIDO INVITADO AL TEMPLO DEL CACIQUE\n\n"
    "Únete a la tribu más exclusiva de Telegram. Contenido único, las mejores fotos y "
    "videos de los guerreros más calientes de la tribu. 🔥\n\n"
    "ÚNETE AQUÍ:"
)
MSG_ENCODED = urllib.parse.quote(MSG_INVITACION_TEXTO, safe="")
LINK_SHARE = (
    "https://t.me/share/url"
    f"?url={urllib.parse.quote(LINK_GRUPO, safe='')}"
    f"&text={MSG_ENCODED}"
)
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
_indice_texto_vchat = 0
_lock_texto_vchat = threading.Lock()

DEFAULT_GROUP_RULES = (
    "📜 REGLAMENTO DEL JUEGO 😈\n\n"
    "Antes de soltar tus ganas, recuerda estas reglas:\n"
    "1. 💬 Respeta a todos los miembros.\n"
    "No se aceptan insultos, acoso, ni actitudes tóxicas. Aquí se viene a disfrutar, no a molestar.\n\n"
    "2. 🚫 Cero contenido ilegal o prohibido.\n"
    "Nada de pornografía infantil, zoofilia, violencia, incesto, ni nada fuera de la ley.\n"
    "Esto es un espacio adulto, no un delito.\n\n"
    "3. 📵 Sin spam ni publicidad externa.\n"
    "Si quieres compartir algo, consulta primero con la administración.\n"
    "Nadie vino aquí a ver tu link de criptos ni tu grupo copia 😅\n\n"
    "4. 🧠 Consentimiento y buen gusto.\n"
    "Si alguien dice “no”, se respeta.\n"
    "Jugar no significa cruzar límites.\n\n"
    "5. 🤖 Nada de bots, cuentas falsas ni robo de contenido.\n"
    "Si lo haces, serás eliminado más rápido de lo que dura un suspiro.\n\n"
    "6. 😏 Participa con actitud.\n"
    "Sé amable, sé divertido/a, sé tú pero recuerda: lo sexy también puede ser educado.\n\n"
    "✨ Cumple las reglas y disfruta del juego.\n"
    "El placer es más intenso cuando hay límites claros.\n\n"
    "🛡️ Administración del Grupo GRAN JEFE"
)

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

def _usuario_en_lista_negra(user_id, chat_id=None):
    registros = Blacklist.search(User.id == int(user_id))
    for registro in registros:
        if registro.get("status", "active") != "active":
            continue
        alcance = registro.get("chat_id")
        if not alcance and (
            chat_id is None or str(chat_id) == str(GRUPO_ID)
        ):
            return True
        if alcance and chat_id is not None and str(alcance) == str(chat_id):
            return True
    return False


def _advertencias_usuario(chat_id, user_id):
    registros = Warnings.search(User.id == int(user_id))
    salida = []
    for registro in registros:
        alcance = registro.get("chat_id")
        if alcance is None:
            # Los registros del ZIP anterior solo pueden asociarse al grupo
            # principal que usaba aquella versión.
            if str(chat_id) == str(GRUPO_ID):
                salida.append(registro)
        elif str(alcance) == str(chat_id):
            salida.append(registro)
    return salida


def _registrar_accion_moderacion(
    chat_id,
    user_id,
    nombre,
    accion,
    count,
    reporter_id=None,
    evidence_doc_id=None,
    reason=None,
):
    momento = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    motivo = str(reason or (
        "Reporte de miembro" if reporter_id else "Moderación automática"
    ))
    GroupModerationLog.insert({
        "chat_id": str(chat_id),
        "user_id": int(user_id),
        "username": str(nombre or ""),
        "action": accion,
        "count": int(count),
        "reporter_id": int(reporter_id) if reporter_id else None,
        "evidence_doc_id": evidence_doc_id,
        "reason": motivo,
        "date": momento,
    })
    if reporter_id:
        GroupReports.insert({
            "chat_id": str(chat_id),
            "reporter_id": int(reporter_id),
            "reported_user_id": int(user_id),
            "reported_username": str(nombre or ""),
            "action": accion,
            "count": int(count),
            "evidence_doc_id": evidence_doc_id,
            "reason": motivo,
            "date": momento,
        })


def _destino_key_por_chat_id(chat_id):
    cid = str(chat_id)
    cfg = cargar_config()
    for key, destino in cfg.get("destinos", {}).items():
        if isinstance(destino, dict) and str(destino.get("chat_id")) == cid:
            return key
    if cid in cfg.get("group_settings", {}):
        return f"group:{cid}"
    return None


def aplicar_castigo(
    chat_id, user_id, nombre, reporter_id=None, evidence=None, reason=None
):
    chat_id, user_id = int(chat_id), int(user_id)
    stats = _advertencias_usuario(chat_id, user_id)
    anterior = stats[-1] if stats else None
    count = int(anterior.get("count", 0)) + 1 if anterior else 1
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    motivo = str(reason or (
        "Reporte de miembro" if reporter_id else "Moderación automática"
    ))

    if count >= 3:
        try:
            bot.ban_chat_member(chat_id, user_id)
        except Exception:
            app.logger.exception(
                "No se pudo expulsar al usuario %s del grupo %s.",
                user_id,
                chat_id,
            )
            accion = "ban_failed"
        else:
            accion = "ban"
            existentes = [
                registro for registro in Blacklist.search(User.id == user_id)
                if str(registro.get("chat_id", "")) == str(chat_id)
            ]
            datos_lista = {
                "id": user_id,
                "chat_id": str(chat_id),
                "username": str(nombre or ""),
                "reason": f"Tres sanciones: {motivo}",
                "date": ahora,
                "status": "active",
            }
            if existentes:
                Blacklist.update(datos_lista, doc_ids=[existentes[-1].doc_id])
            else:
                Blacklist.insert(datos_lista)
            if anterior:
                try:
                    Warnings.remove(doc_ids=[anterior.doc_id])
                except Exception:
                    app.logger.exception("No se pudo cerrar el contador de advertencias.")

        _registrar_accion_moderacion(
            chat_id,
            user_id,
            nombre,
            accion,
            count,
            reporter_id,
            getattr(evidence, "doc_id", None),
            motivo,
        )
        if accion == "ban":
            dest_key = _destino_key_por_chat_id(chat_id)
            markup = None
            if dest_key:
                markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton(
                    "🔓 Reingresar (2/3)",
                    callback_data=f"mod_perdonar|{dest_key}|{chat_id}|{user_id}",
                ))
            try:
                bot.send_message(
                    int(ADMIN_ID),
                    "🚩 <b>EXPULSIÓN EJECUTADA</b>\n"
                    f"Grupo: <code>{chat_id}</code>\n"
                    f"Usuario: @{html.escape(str(nombre or 'sin_usuario'))}\n"
                    f"ID: <code>{user_id}</code>\n\n"
                    f"Motivo: {html.escape(motivo)}\n\n"
                    "La sanción y la notificación del bot se mantienen privadas.",
                    parse_mode="HTML",
                    reply_markup=markup,
                    protect_content=True,
                )
            except Exception:
                app.logger.exception("No se pudo avisar al administrador de la expulsión.")
        mensaje_reporte = (
            f"✅ Tu reporte sobre @{nombre} fue revisado y el usuario fue expulsado."
            if accion == "ban"
            else (
                f"⚠️ Se registró tu reporte sobre @{nombre}, pero Telegram no permitió "
                "aplicar la expulsión. El administrador podrá revisarlo."
            )
        )
    else:
        silenciado = False
        try:
            bot.restrict_chat_member(
                chat_id,
                user_id,
                until_date=int(time.time()) + (35 * 60),
                can_send_messages=False,
            )
            silenciado = True
        except Exception:
            app.logger.exception(
                "No se pudo silenciar al usuario %s en el grupo %s.",
                user_id,
                chat_id,
            )
        accion = "mute" if silenciado else "warning"
        datos_warning = {
            "id": user_id,
            "chat_id": str(chat_id),
            "username": str(nombre or ""),
            "count": count,
            "last_warn": ahora,
            "reason": motivo,
        }
        if anterior:
            Warnings.update(datos_warning, doc_ids=[anterior.doc_id])
        else:
            Warnings.insert(datos_warning)
        _registrar_accion_moderacion(
            chat_id,
            user_id,
            nombre,
            accion,
            count,
            reporter_id,
            getattr(evidence, "doc_id", None),
            motivo,
        )
        mensaje_reporte = (
            f"✅ Tu reporte sobre @{nombre} fue registrado como sanción "
            f"{count}/3. El grupo no recibió una notificación pública."
            if silenciado
            else f"✅ Tu reporte sobre @{nombre} quedó registrado para revisión."
        )

    if reporter_id:
        try:
            bot.send_message(
                int(reporter_id),
                mensaje_reporte,
                protect_content=True,
            )
        except Exception:
            app.logger.info(
                "No se pudo enviar la confirmación privada del reporte a %s.",
                reporter_id,
            )
    return {"action": accion, "count": count}

def cerrar_sesion_segura(chat_id):
    markup = types.ReplyKeyboardRemove()
    bot.send_message(chat_id, "🔒 **SESIÓN FINALIZADA**", reply_markup=markup)

def guardar_evidencia(message):
    if not es_grupo_autorizado(message.chat.id):
        return
    evidencia = {
        'id': message.from_user.id,
        'chat_id': str(message.chat.id),
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
    evidence_doc_id = RegistroActividad.insert(evidencia)
    return RegistroActividad.get(doc_id=evidence_doc_id)

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
        if username and str(username).lower() in VIDEOCHAT_INVITE_URLS:
            return VIDEOCHAT_INVITE_URLS[str(username).lower()]
        if username: return f"https://t.me/{username}"
        invite_link=getattr(chat,"invite_link",None)
        if invite_link: return invite_link
    except Exception:
        app.logger.info("No se pudo obtener el enlace del grupo para la guía de videochat.")
    try:
        if int(chat_id)==int(GRUPO_ID):
            return LINK_GRUPO
    except (NameError, TypeError, ValueError):
        pass
    return None

def enviar_invitacion_vchat(chat_id, destino_chat_id=None):
    global _indice_texto_vchat
    with _lock_texto_vchat:
        msg_random = TEXTOS_VC_HOT[_indice_texto_vchat % len(TEXTOS_VC_HOT)]
        _indice_texto_vchat += 1
    e1, e2 = random.sample(EMOJIS_ACCION, 2)
    url_grupo = _videochat_guide_url(destino_chat_id or chat_id)
    markup = types.InlineKeyboardMarkup()
    if url_grupo:
        msg_random += (
            "\n\nPulsa el botón para abrir el grupo y usa los controles de Telegram "
            "para iniciar el videochat."
        )
        markup.add(types.InlineKeyboardButton(
            f"{e1} ABRIR GRUPO / VIDEOCHAT {e2}",
            url=url_grupo,
        ))
    else:
        msg_random += (
            "\n\nUsa los controles de llamada de Telegram en el grupo para iniciar "
            "el videochat. El bot no tiene un enlace de acceso disponible para este grupo."
        )
    return editar_panel_miembro(
        chat_id,
        msg_random,
        markup if url_grupo else None,
    )

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
            # Migra en memoria el formato anterior (un texto por método) a una
            # lista de opciones sin mostrar ni modificar los datos existentes.
            for metodo, valores in list(datos[campo].items()):
                if isinstance(valores, str):
                    datos[campo][metodo] = [valores] if valores.strip() else []
                elif isinstance(valores, list):
                    datos[campo][metodo] = [
                        valor.strip()
                        for valor in valores
                        if isinstance(valor, str) and valor.strip()
                    ]
                else:
                    datos[campo][metodo] = []
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
    opciones = cargar_config_pagos().get("metodos", {}).get(metodo, [])
    if isinstance(opciones, str):
        opciones = [opciones] if opciones.strip() else []
    opciones = [str(opcion).strip() for opcion in opciones if str(opcion).strip()]
    if not opciones:
        return ""
    texto = "\n\n────────────\n\n".join(opciones)
    if metodo not in METODOS_PAGO_POR_ENLACE and _AVISO.strip() not in texto:
        texto += _AVISO
    return texto


def obtener_mensaje_solicitud_enlace(metodo):
    guardados = cargar_config_pagos().get("mensajes_link", {})
    textos = guardados.get(metodo, [])
    if isinstance(textos, str):
        textos = [textos] if textos.strip() else []
    textos = [str(texto).strip() for texto in textos if str(texto).strip()]
    return html.escape("\n\n────────────\n\n".join(textos)) if textos else _MSG_LINK


def guardar_metodo_pago(metodo, texto, reemplazar_indice=None):
    es_enlace = metodo in METODOS_PAGO_POR_ENLACE
    grupo = "mensajes_link" if es_enlace else "metodos"

    def actualizar(datos):
        opciones = datos.setdefault(grupo, {}).get(metodo, [])
        if isinstance(opciones, str):
            opciones = [opciones] if opciones.strip() else []
        elif not isinstance(opciones, list):
            opciones = []
        opciones = [opcion for opcion in opciones if isinstance(opcion, str) and opcion.strip()]
        if (
            isinstance(reemplazar_indice, int)
            and 0 <= reemplazar_indice < len(opciones)
        ):
            opciones[reemplazar_indice] = texto
        else:
            opciones.append(texto)
        datos[grupo][metodo] = opciones

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
FREE_GOLDPASS_DURATIONS = {
    60: ("1 minuto", "1m"),
    300: ("5 minutos", "5m"),
    600: ("10 minutos", "10m"),
    86400: ("24 horas", "24h"),
    259200: ("72 horas", "72h"),
}


def free_goldpass_config():
    cfg = cargar_config().get("free_goldpass", {})
    return cfg if isinstance(cfg, dict) else {}


def free_goldpass_activo():
    return bool(free_goldpass_config().get("active"))


def _formato_duracion_freepass(segundos):
    return FREE_GOLDPASS_DURATIONS.get(int(segundos), ("duración no válida", ""))[0]


def _fecha_freepass(registro):
    try:
        return datetime.strptime(str(registro.get("vence")), "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def _registro_freepass(user_id):
    try:
        with FREE_GOLDPASS_LOCK:
            return FreeGoldPasses.get(FREE_GOLDPASS_QUERY.id == int(user_id))
    except (TypeError, ValueError):
        return None


def _suscripcion_vip_activa(user_id):
    registro = db.get(Query().id == int(user_id))
    if not registro:
        return None
    vence = _fecha_freepass(registro)
    return registro if vence and vence > datetime.now() else None


def _editar_anuncio_freepass(config, texto):
    chat_id = config.get("promo_chat_id")
    message_id = config.get("promo_message_id")
    if not chat_id or not message_id:
        return
    try:
        bot.edit_message_text(
            texto,
            chat_id=chat_id,
            message_id=message_id,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=types.InlineKeyboardMarkup(),
        )
    except Exception:
        app.logger.exception("No se pudo cerrar el anuncio de Free Gold Pass.")


def _cancelar_enlaces_pendientes_freepass(campaign_id):
    with FREE_GOLDPASS_LOCK:
        pendientes = [
            dict(registro)
            for registro in FreeGoldPasses.all()
            if registro.get("status") == "pending"
            and registro.get("campaign_id") == campaign_id
        ]
    for registro in pendientes:
        invite_link = registro.get("invite_link")
        if invite_link:
            try:
                bot.revoke_chat_invite_link(CANAL_ID, invite_link)
            except Exception:
                app.logger.exception(
                    "No se pudo revocar un enlace pendiente de Free Gold Pass."
                )
        try:
            with FREE_GOLDPASS_LOCK:
                FreeGoldPasses.update(
                    {
                        "status": "cancelled",
                        "cancelled_at": datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                    },
                    FREE_GOLDPASS_QUERY.id == int(registro.get("id")),
                )
        except (TypeError, ValueError):
            app.logger.exception(
                "No se pudo marcar como cancelado un pase pendiente."
            )


def _desactivar_free_goldpass(motivo, campaign_id=None):
    estado = free_goldpass_config()
    if not estado.get("active"):
        return False
    if campaign_id and estado.get("campaign_id") != campaign_id:
        return False
    actual = dict(estado)
    actual.update({
        "active": False,
        "disabled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "disabled_reason": motivo,
    })
    actualizar_config(lambda cfg: cfg.update({"free_goldpass": actual}))
    _cancelar_enlaces_pendientes_freepass(actual.get("campaign_id"))
    _editar_anuncio_freepass(
        actual,
        "⏰ <b>El pase gratuito GoldPass terminó.</b>\n\n"
        "Los métodos de pago están disponibles nuevamente en el bot.",
    )
    return True


def mostrar_menu_free_goldpass_usuario(chat_id, user_id, registro=None):
    estado = free_goldpass_config()
    duracion = _formato_duracion_freepass(
        registro.get("duration_seconds")
        if registro
        else estado.get("duration_seconds", 0)
    )
    markup = types.InlineKeyboardMarkup()
    if registro and registro.get("status") == "pending":
        markup.add(types.InlineKeyboardButton(
            "🎟️🏆 Entrar al canal GoldPass",
            url=registro.get("invite_link"),
        ))
        texto = (
            "🎟️🏆 <b>Tu pase gratuito GoldPass está listo.</b>\n\n"
            f"Tu pase dura <b>{html.escape(duracion)}</b>. El tiempo empieza "
            "cuando el bot apruebe tu entrada al canal; desde ahí se contará "
            "tu acceso y, al terminar, el bot te retirará.\n\n"
            "¡Disfrútalo! 🔥"
        )
    elif registro and registro.get("status") == "active":
        vence = _fecha_freepass(registro)
        fecha_txt = vence.strftime("%d/%m/%Y %H:%M") if vence else "la hora indicada"
        texto = (
            "🎟️🏆 <b>Tu pase gratuito GoldPass está activo.</b>\n\n"
            f"Tu acceso termina el <b>{fecha_txt}</b>; después el bot te retirará "
            "del canal. ¡Disfrútalo! 🔥"
        )
    else:
        texto = (
            "🎟️🏆 <b>Free Gold Pass disponible</b>\n\n"
            f"Puedes solicitar un acceso gratuito por <b>{html.escape(duracion)}</b>. "
            "El plazo comienza cuando se emite tu enlace; al vencer, el bot te "
            "retirará del canal.\n\n"
            "Pulsa el botón para recibir tu enlace personal. 🔥"
        )
        markup.add(types.InlineKeyboardButton(
            "🎟️🏆 Iniciar Gold Pass",
            callback_data="free_goldpass_claim",
        ))
    return editar_o_enviar_panel(
        chat_id,
        texto,
        markup,
        protect_content=True,
        forzar_texto=True,
    )

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

def mostrar_metodos_pago(chat_id, aviso=None):
    promocion_activa = free_goldpass_activo()
    try:
        user_id = int(chat_id)
    except (TypeError, ValueError):
        user_id = 0
    if user_id > 0:
        pase_personal = _registro_freepass(user_id)
        if pase_personal and pase_personal.get("status") in ("pending", "active"):
            vence = _fecha_freepass(pase_personal)
            if vence and vence <= datetime.now():
                procesar_vencimiento_freepass(pase_personal)
                return
            return mostrar_menu_free_goldpass_usuario(
                chat_id, user_id, registro=pase_personal
            )
        suscripcion = (
            _suscripcion_vip_activa(user_id)
            if promocion_activa
            else None
        )
        if suscripcion:
            vence = _fecha_freepass(suscripcion)
            fecha_txt = vence.strftime("%d/%m/%Y %H:%M") if vence else "la fecha registrada"
            return editar_o_enviar_panel(
                chat_id,
                "✅ <b>Tu acceso GoldPass ya está activo.</b>\n\n"
                f"Tu suscripción está vigente hasta <b>{fecha_txt}</b>.",
                types.InlineKeyboardMarkup(),
                protect_content=True,
                forzar_texto=True,
            )
    if promocion_activa:
        return mostrar_menu_free_goldpass_usuario(chat_id, user_id)

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
    if aviso:
        texto = f"ℹ️ {html.escape(aviso)}\n\n{texto}"
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
    estado_free = "ACTIVADO" if free_goldpass_activo() else "DESACTIVADO"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(
            "💳 Métodos de pago",
            callback_data="admin_pagos_metodos",
        ),
        types.InlineKeyboardButton(
            "🖼️ Cambiar foto del menú",
            callback_data="admin_pagos_cambiar_foto",
        ),
        types.InlineKeyboardButton(
            f"🎟️ Free Gold Pass · {estado_free}",
            callback_data="admin_free_goldpass",
        ),
        types.InlineKeyboardButton(
            "🔙 Volver al panel",
            callback_data="admin_pagos_volver",
        ),
    )
    return markup


def markup_lista_metodos_pago():
    config_pagos = cargar_config_pagos()
    markup = types.InlineKeyboardMarkup(row_width=1)
    for metodo, nombre in NOMBRE_METODO.items():
        campo = "mensajes_link" if metodo in METODOS_PAGO_POR_ENLACE else "metodos"
        opciones = config_pagos.get(campo, {}).get(metodo, [])
        if isinstance(opciones, str):
            opciones = [opciones] if opciones.strip() else []
        cantidad = len(opciones)
        estado = "✅" if cantidad else "⚠️"
        etiqueta = f"{estado} {nombre}"
        if cantidad:
            etiqueta += f" · {cantidad} opción{'es' if cantidad != 1 else ''}"
        elif metodo in METODOS_PAGO_POR_ENLACE:
            etiqueta += " · predeterminado"
        markup.add(types.InlineKeyboardButton(
            etiqueta,
            callback_data=f"admin_pagos_metodo|{metodo}",
        ))
    markup.add(types.InlineKeyboardButton(
        "🔙 Volver",
        callback_data="admin_pagos_metodos_volver",
    ))
    return markup


def _opciones_guardadas_pago(metodo):
    config_pagos = cargar_config_pagos()
    campo = "mensajes_link" if metodo in METODOS_PAGO_POR_ENLACE else "metodos"
    opciones = config_pagos.get(campo, {}).get(metodo, [])
    if isinstance(opciones, str):
        opciones = [opciones] if opciones.strip() else []
    return [opcion for opcion in opciones if isinstance(opcion, str) and opcion.strip()]


def markup_opciones_metodo_pago(metodo):
    markup = types.InlineKeyboardMarkup(row_width=1)
    cantidad = len(_opciones_guardadas_pago(metodo))
    for indice in range(cantidad):
        markup.add(types.InlineKeyboardButton(
            f"✏️ Actualizar opción {indice + 1}",
            callback_data=f"admin_pagos_actualizar|{metodo}|{indice}",
        ))
    markup.add(
        types.InlineKeyboardButton(
            "➕ Agregar otro pago",
            callback_data=f"admin_pagos_agregar|{metodo}",
        ),
        types.InlineKeyboardButton(
            "🔙 Volver",
            callback_data="admin_pagos_metodos",
        ),
    )
    return markup


def mostrar_admin_config_pagos(
    chat_id, message=None, message_id=None, aviso=None
):
    config_pagos = cargar_config_pagos()
    estado_free = free_goldpass_config()
    portada = (
        "personalizada"
        if config_pagos.get("portada_file_id")
        else "foto original"
    )
    texto = (
        "💳 <b>Métodos de pago e imagen</b>\n\n"
        "Administra por separado los métodos de pago y la imagen de este menú. "
        "El texto de pago guardado no se muestra en los paneles.\n\n"
        f"Foto del menú: <b>{portada}</b>.\n"
        "Free Gold Pass: <b>"
        + ("activado" if estado_free.get("active") else "desactivado")
        + "</b>.\n"
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
        protect_content=True,
        forzar_texto=True,
    )


def markup_admin_free_goldpass():
    estado = free_goldpass_config()
    markup = types.InlineKeyboardMarkup(row_width=3)
    if estado.get("active"):
        markup.add(
            types.InlineKeyboardButton(
                "⛔ Cancelar Free Gold Pass",
                callback_data="admin_free_goldpass_disable",
            ),
            types.InlineKeyboardButton(
                "🔙 Volver",
                callback_data="admin_free_goldpass_back",
            ),
        )
    else:
        for segundos, (etiqueta, _) in FREE_GOLDPASS_DURATIONS.items():
            markup.add(types.InlineKeyboardButton(
                etiqueta,
                callback_data=f"admin_free_goldpass_enable|{segundos}",
            ))
        markup.add(types.InlineKeyboardButton(
            "🔙 Volver a métodos de pago",
            callback_data="admin_free_goldpass_back",
        ))
    return markup


def mostrar_admin_free_goldpass(
    chat_id, message=None, message_id=None, aviso=None
):
    estado = free_goldpass_config()
    if estado.get("active"):
        duracion = html.escape(
            _formato_duracion_freepass(estado.get("duration_seconds", 0))
        )
        texto = (
            "🎟️ <b>Free Gold Pass · ACTIVADO</b>\n\n"
            "Los métodos de pago se ocultan para todos mientras esta promoción "
            "esté activa. Cada pase empieza a contar cuando el bot aprueba la "
            "entrada de esa persona al canal.\n"
            f"Duración por persona: <b>{duracion}</b>.\n"
            "Al vencer el primer pase admitido, la promoción se desactivará "
            "automáticamente; los pases activos conservarán su vencimiento. "
            "Si cancelas ahora, se restauran los métodos de pago y se revocan "
            "los enlaces pendientes; quienes ya entraron conservan su tiempo."
        )
    else:
        texto = (
            "🎟️ <b>Free Gold Pass · DESACTIVADO</b>\n\n"
            "Al activarlo, sustituirá los métodos de pago para todos y publicará "
            "un anuncio en el canal gratuito. Cada persona recibirá un enlace "
            "individual; el plazo comenzará cuando el bot apruebe su entrada "
            "al canal privado.\n"
            "Cuando venza el primer pase, se desactivará para todos y volverán "
            "los métodos de pago."
        )
    if aviso:
        texto = f"ℹ️ {html.escape(aviso)}\n\n{texto}"
    return editar_o_enviar_panel(
        chat_id,
        texto,
        markup_admin_free_goldpass(),
        message=message,
        message_id=message_id,
        protect_content=True,
        forzar_texto=True,
    )


def activar_free_goldpass(segundos):
    if segundos not in FREE_GOLDPASS_DURATIONS:
        raise ValueError("La duración seleccionada no está permitida.")
    if free_goldpass_activo():
        return free_goldpass_config()

    bot_info = bot.get_me()
    miembro_goldpass = bot.get_chat_member(CANAL_ID, bot_info.id)
    if getattr(miembro_goldpass, "status", None) != "administrator":
        raise RuntimeError(
            "En el canal privado GoldPass el bot debe ser administrador."
        )
    if not getattr(miembro_goldpass, "can_invite_users", False):
        raise RuntimeError(
            "En el canal privado GoldPass activa para este bot "
            "«Invitar usuarios mediante enlace» o «Añadir suscriptores»."
        )
    if not getattr(miembro_goldpass, "can_restrict_members", False):
        raise RuntimeError(
            "En el canal privado GoldPass activa para este bot "
            "«Expulsar usuarios»; es necesario para retirar a cada persona "
            "cuando venza su pase."
        )
    canal = bot.get_chat(FREE_GOLDPASS_PROMO_CHAT_ID)
    if getattr(canal, "type", None) != "channel":
        raise RuntimeError(
            "El destino configurado para el anuncio no es un canal de Telegram."
        )
    miembro_canal = bot.get_chat_member(canal.id, bot_info.id)
    if (
        getattr(miembro_canal, "status", None) != "administrator"
        or not getattr(miembro_canal, "can_post_messages", False)
    ):
        raise RuntimeError(
            "En el canal gratuito el bot debe ser administrador con permiso "
            "para publicar mensajes."
        )

    etiqueta = _formato_duracion_freepass(segundos)
    url_bot = f"https://t.me/{bot_info.username}?start=free_goldpass"
    markup = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton(
            "🎟️🏆 Reclamar Free Gold Pass",
            url=url_bot,
        )
    )
    texto = (
        "🏹🔥 <b>¡Porque eres uno de los mejores guerreros de mi tribu, "
        "te regalo un pase gratis!</b> 🔥🏹\n\n"
        "Accede por tiempo limitado a GoldPass, con contenido explícito para "
        "adultos. 🎟️💎\n\n"
        f"Tu pase durará <b>{html.escape(etiqueta)}</b> desde que el bot "
        "apruebe tu entrada al canal privado.\n"
        "¿Qué esperas? Reclámalo ahora y disfrútalo. ⏳✨"
    )
    anuncio = bot.send_message(
        canal.id,
        texto,
        parse_mode="HTML",
        reply_markup=markup,
        disable_web_page_preview=True,
        protect_content=True,
    )
    nuevo_estado = {
        "active": True,
        "duration_seconds": int(segundos),
        "campaign_id": uuid.uuid4().hex,
        "promo_chat_id": str(canal.id),
        "promo_message_id": anuncio.message_id,
        "activated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        actualizar_config(
            lambda cfg: cfg.update({"free_goldpass": nuevo_estado})
        )
    except Exception:
        try:
            bot.delete_message(canal.id, anuncio.message_id)
        except Exception:
            app.logger.exception(
                "No se pudo retirar el anuncio tras fallar el guardado."
            )
        raise
    return nuevo_estado


def mostrar_lista_metodos_pago(
    chat_id, message=None, message_id=None, aviso=None
):
    texto = (
        "💳 <b>Métodos de pago</b>\n\n"
        "Selecciona un método para consultar cuántas opciones tiene o agregar "
        "otra. El contenido de pago se mantiene oculto en este panel."
    )
    if aviso:
        texto = f"✅ {html.escape(aviso)}\n\n" + texto
    return editar_o_enviar_panel(
        chat_id,
        texto,
        markup_lista_metodos_pago(),
        message=message,
        message_id=message_id,
        protect_content=True,
        forzar_texto=True,
    )


def mostrar_opciones_metodo_pago(
    chat_id, metodo, message=None, message_id=None, aviso=None
):
    cantidad = len(_opciones_guardadas_pago(metodo))
    nombre = html.escape(NOMBRE_METODO.get(metodo, metodo))
    texto = f"💳 <b>{nombre}</b>\n\n"
    if cantidad:
        texto += (
            f"Hay <b>{cantidad}</b> opción{'es' if cantidad != 1 else ''} "
            "guardada(s). Por privacidad no se muestra su contenido aquí."
        )
    elif metodo in METODOS_PAGO_POR_ENLACE:
        texto += "Se usará el mensaje predeterminado hasta que agregues una opción."
    else:
        texto += "Todavía no hay datos configurados para este método."
    if aviso:
        texto = f"✅ {html.escape(aviso)}\n\n" + texto
    return editar_o_enviar_panel(
        chat_id,
        texto,
        markup_opciones_metodo_pago(metodo),
        message=message,
        message_id=message_id,
        protect_content=True,
        forzar_texto=True,
    )


def mostrar_foto_pago_actual(chat_id, message=None, message_id=None, aviso=None):
    config_pagos = cargar_config_pagos()
    texto = (
        "🖼️ <b>Cambiar la foto del menú de pago</b>\n\n"
        "Esta es la foto que verán los usuarios al elegir cómo pagar. "
        "Pulsa «Agregar foto» para enviar la nueva imagen; se guardará como foto."
    )
    if aviso:
        texto = f"✅ {html.escape(aviso)}\n\n" + texto
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(
            "➕ Agregar foto",
            callback_data="admin_pagos_foto_subir",
        ),
        types.InlineKeyboardButton(
            "🔙 Volver",
            callback_data="admin_pagos",
        ),
    )
    if config_pagos.get("portada_file_id"):
        markup.add(types.InlineKeyboardButton(
            "♻️ Usar foto original",
            callback_data="admin_pagos_foto_original",
        ))

    foto_actual = config_pagos.get("portada_file_id")
    if not foto_actual:
        foto_actual = os.path.join(BASE_DIR, "portada.jpg")
        if not os.path.isfile(foto_actual):
            return editar_o_enviar_panel(
                chat_id, texto, markup, message=message, message_id=message_id,
                protect_content=True, forzar_texto=True,
            )
    if hasattr(foto_actual, "read"):
        return enviar_foto_panel(
            chat_id, foto_actual, texto, markup, forzar_reemplazo=True
        )
    if isinstance(foto_actual, str) and os.path.isfile(foto_actual):
        try:
            with open(foto_actual, "rb") as foto:
                return enviar_foto_panel(
                    chat_id, foto, texto, markup, forzar_reemplazo=True
                )
        except OSError:
            app.logger.exception("No se pudo abrir la foto local del menú de pagos.")
    return enviar_foto_panel(
        chat_id, foto_actual, texto, markup, forzar_reemplazo=True
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


@bot.callback_query_handler(func=lambda call: call.data == "admin_free_goldpass")
def admin_abrir_free_goldpass(call):
    if not es_admin_privado(call):
        bot.answer_callback_query(call.id, "⛔ Solo el administrador puede abrirlo en privado.")
        return
    bot.answer_callback_query(call.id)
    mostrar_admin_free_goldpass(
        call.message.chat.id,
        message=call.message,
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "admin_free_goldpass_back"
)
def admin_volver_free_goldpass(call):
    if not es_admin_privado(call):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    mostrar_admin_config_pagos(
        call.message.chat.id,
        message=call.message,
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("admin_free_goldpass_enable|")
)
def admin_activar_free_goldpass(call):
    if not es_admin_privado(call):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    try:
        segundos = int(call.data.split("|", 1)[1])
        activar_free_goldpass(segundos)
    except Exception as error:
        app.logger.exception("No se pudo activar Free Gold Pass.")
        mensaje = str(error)
        bot.answer_callback_query(
            call.id,
            mensaje[:190] or "No se pudo activar Free Gold Pass.",
            show_alert=True,
        )
        mostrar_admin_free_goldpass(
            call.message.chat.id,
            message=call.message,
            aviso="No se activó; revisa los permisos de administración e inténtalo otra vez.",
        )
        return
    bot.answer_callback_query(call.id, "Free Gold Pass activado.")
    mostrar_admin_free_goldpass(
        call.message.chat.id,
        message=call.message,
        aviso="Activado; el anuncio ya se publicó en el canal gratuito.",
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "admin_free_goldpass_disable"
)
def admin_desactivar_free_goldpass(call):
    if not es_admin_privado(call):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    desactivado = _desactivar_free_goldpass("admin")
    bot.answer_callback_query(
        call.id,
        "Promoción desactivada." if desactivado else "Ya estaba desactivada.",
    )
    mostrar_admin_free_goldpass(
        call.message.chat.id,
        message=call.message,
        aviso="Los métodos de pago vuelven a estar disponibles para nuevas solicitudes.",
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "admin_pagos_metodos"
)
def admin_lista_metodos_pago(call):
    if not es_admin_privado(call):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    mostrar_lista_metodos_pago(call.message.chat.id, message=call.message)


@bot.callback_query_handler(
    func=lambda call: call.data == "admin_pagos_metodos_volver"
)
def admin_pagos_metodos_volver(call):
    if not es_admin_privado(call):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    mostrar_admin_config_pagos(call.message.chat.id, message=call.message)


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
    mostrar_opciones_metodo_pago(
        call.message.chat.id,
        metodo,
        message=call.message,
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("admin_pagos_agregar|")
)
def admin_agregar_opcion_pago(call):
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
        "reemplazar_indice": None,
        "panel_message_id": call.message.message_id,
    }
    if metodo in METODOS_PAGO_POR_ENLACE:
        instruccion = (
            "Envía el mensaje que recibirá el usuario al solicitar un enlace de pago."
        )
    else:
        instruccion = (
            "Envía la información de pago que el administrador copiará "
            "para compartir con el usuario. Envíala completa en un solo mensaje."
        )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "🔙 Volver",
        callback_data="admin_pagos_cancelar",
    ))
    editar_o_enviar_panel(
        call.message.chat.id,
        f"✍️ <b>Agregar otra opción de {html.escape(NOMBRE_METODO[metodo])}</b>\n\n"
        f"{instruccion}\n\n"
        "No se mostrará el contenido en el panel. El mensaje que envíes se "
        "borrará después de guardarlo.",
        markup,
        message=call.message,
        protect_content=True,
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("admin_pagos_actualizar|")
)
def admin_actualizar_opcion_pago(call):
    if not es_admin_privado(call):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    try:
        _, metodo, raw_indice = call.data.split("|", 2)
        indice = int(raw_indice)
    except (ValueError, TypeError):
        bot.answer_callback_query(call.id, "Opción no válida.")
        return
    opciones = _opciones_guardadas_pago(metodo)
    if metodo not in NOMBRE_METODO or not 0 <= indice < len(opciones):
        bot.answer_callback_query(call.id, "Esa opción ya no existe.")
        return
    bot.answer_callback_query(call.id)
    admin_estado[call.from_user.id] = {
        "paso": "esperando_datos_metodo_pago",
        "metodo_pago": metodo,
        "reemplazar_indice": indice,
        "panel_message_id": call.message.message_id,
    }
    markup = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton(
            "🔙 Volver",
            callback_data="admin_pagos_cancelar",
        )
    )
    editar_o_enviar_panel(
        call.message.chat.id,
        f"✍️ <b>Actualizar opción {indice + 1} de "
        f"{html.escape(NOMBRE_METODO[metodo])}</b>\n\n"
        "Envía la información nueva completa en un solo mensaje. "
        "La opción guardada será reemplazada y el mensaje enviado se borrará.",
        markup,
        message=call.message,
        protect_content=True,
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "admin_pagos_cambiar_foto"
)
def admin_ver_foto_pago(call):
    if not es_admin_privado(call):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    mostrar_foto_pago_actual(call.message.chat.id, message=call.message)


@bot.callback_query_handler(
    func=lambda call: call.data == "admin_pagos_foto_subir"
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
        "🔙 Volver",
        callback_data="admin_pagos_cancelar",
    ))
    editar_o_enviar_panel(
        call.message.chat.id,
        "🖼️ <b>Cambiar la foto del menú de pago</b>\n\n"
        "Envía la nueva imagen como foto. Se guardará para el menú de pago. "
        "El mensaje que envíes se borrará al guardarla.",
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
        mostrar_foto_pago_actual(
            call.message.chat.id,
            message=call.message,
            aviso="No pude guardar el cambio; la foto actual se mantiene.",
        )
        return
    mostrar_foto_pago_actual(
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


def procesar_vencimiento_freepass(registro):
    try:
        user_id = int(registro.get("id"))
    except (TypeError, ValueError):
        return False
    vence = _fecha_freepass(registro)
    if not vence or vence > datetime.now():
        return False

    with FREE_GOLDPASS_LOCK:
        actual = FreeGoldPasses.get(FREE_GOLDPASS_QUERY.id == user_id)
        if not actual or actual.get("status") not in (
            "active", "expiring", "kick_pending", "expiry_pending"
        ):
            return False
        ultimo_intento = actual.get("last_kick_attempt")
        if actual.get("status") in ("kick_pending", "expiry_pending") and ultimo_intento:
            try:
                momento = datetime.strptime(
                    ultimo_intento, "%Y-%m-%d %H:%M:%S"
                )
                if datetime.now() - momento < timedelta(seconds=60):
                    return False
            except ValueError:
                pass
        actual["status"] = "expiring"
        FreeGoldPasses.upsert(actual, FREE_GOLDPASS_QUERY.id == user_id)
    registro = actual

    error_desactivacion = None
    try:
        _desactivar_free_goldpass(
            "first_pass_expired",
            campaign_id=registro.get("campaign_id"),
        )
    except Exception as error:
        error_desactivacion = str(error)
        app.logger.exception(
            "No se pudo desactivar la promoción al vencer el primer pase."
        )

    enlace = registro.get("invite_link")
    if enlace:
        try:
            bot.revoke_chat_invite_link(CANAL_ID, enlace)
        except Exception:
            # Puede haberse revocado ya al aprobar el ingreso.
            app.logger.info("El enlace de Free Gold Pass ya no estaba vigente.")

    error_expulsion = None
    try:
        bot.ban_chat_member(CANAL_ID, user_id)
        bot.unban_chat_member(CANAL_ID, user_id)
    except Exception as error:
        error_expulsion = str(error)
        app.logger.exception(
            "No se pudo retirar del canal GoldPass al usuario con pase vencido."
        )
    estado = (
        "kick_pending"
        if error_expulsion
        else "expiry_pending"
        if error_desactivacion
        else "expired"
    )

    with FREE_GOLDPASS_LOCK:
        actual = FreeGoldPasses.get(FREE_GOLDPASS_QUERY.id == user_id) or registro
        actual["status"] = estado
        actual["last_kick_attempt"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        if estado == "expired":
            actual["expired_at"] = actual["last_kick_attempt"]
        if error_expulsion:
            actual["last_kick_error"] = error_expulsion[:500]
        if error_desactivacion:
            actual["last_expiry_error"] = error_desactivacion[:500]
        FreeGoldPasses.upsert(actual, FREE_GOLDPASS_QUERY.id == user_id)

    if not registro.get("notified_at"):
        try:
            mostrar_metodos_pago(
                user_id,
                aviso=(
                    "Tu pase gratuito venció y el acceso al canal terminó."
                    if estado == "expired"
                    else "Tu pase venció; el bot está terminando la expiración y tu salida del canal."
                ),
            )
            with FREE_GOLDPASS_LOCK:
                FreeGoldPasses.update(
                    {"notified_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                    FREE_GOLDPASS_QUERY.id == user_id,
                )
        except Exception:
            app.logger.exception(
                "No se pudo notificar el vencimiento de Free Gold Pass al usuario."
            )

    if (error_expulsion or error_desactivacion) and not registro.get("expiry_error_notified"):
        try:
            bot.send_message(
                int(ADMIN_ID),
                "⚠️ No pude completar automáticamente la expiración Free Gold Pass "
                f"del usuario <code>{user_id}</code>. Revisa permisos y almacenamiento. "
                f"Detalle: {html.escape((error_expulsion or error_desactivacion)[:300])}",
                parse_mode="HTML",
                protect_content=True,
            )
            with FREE_GOLDPASS_LOCK:
                FreeGoldPasses.update(
                    {"expiry_error_notified": True},
                    FREE_GOLDPASS_QUERY.id == user_id,
                )
        except Exception:
            app.logger.exception(
                "No se pudo informar al administrador de un fallo de expulsión."
            )
    return True


def revisar_vencimientos_free_goldpass():
    while True:
        ahora = datetime.now()
        try:
            with FREE_GOLDPASS_LOCK:
                vencidos = [
                    dict(registro)
                    for registro in FreeGoldPasses.all()
                    if registro.get("status") in (
                        "active", "expiring", "kick_pending", "expiry_pending"
                    )
                    and _fecha_freepass(registro)
                    and _fecha_freepass(registro) <= ahora
                ]
            for registro in vencidos:
                try:
                    procesar_vencimiento_freepass(registro)
                except Exception:
                    app.logger.exception(
                        "Error al procesar un vencimiento de Free Gold Pass."
                    )
        except Exception:
            app.logger.exception(
                "Error al revisar vencimientos de Free Gold Pass."
            )
        time.sleep(10)


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
            "🔙 Volver",
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
    mostrar_foto_pago_actual(
        message.chat.id,
        message_id=panel_message_id,
        aviso="Foto del menú actualizada.",
    )
    return True

def rechazar_archivo_foto_pagos(message):
    estado = admin_estado.get(message.from_user.id, {})
    if estado.get("paso") != "esperando_foto_metodos_pago":
        return False
    eliminar_mensaje_disparador(message)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "🔙 Volver",
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

@bot.callback_query_handler(
    func=lambda call: call.data == "free_goldpass_claim"
)
def reclamar_free_goldpass(call):
    if getattr(getattr(call.message, "chat", None), "type", None) != "private":
        bot.answer_callback_query(
            call.id,
            "Abre el bot en privado para reclamar tu pase.",
            show_alert=True,
        )
        return
    user_id = int(call.from_user.id)
    estado = free_goldpass_config()
    if not estado.get("active"):
        bot.answer_callback_query(
            call.id,
            "La promoción terminó; ya puedes consultar los métodos de pago.",
            show_alert=True,
        )
        mostrar_metodos_pago(call.message.chat.id)
        return

    try:
        vencido = None
        enlace_nuevo = False
        with FREE_GOLDPASS_LOCK:
            existente = _registro_freepass(user_id)
            registro = None
            if existente and existente.get("status") == "pending":
                vence_enlace_anterior = _fecha_freepass(existente)
                if (
                    existente.get("campaign_id") == estado.get("campaign_id")
                    and existente.get("invite_link")
                    and (
                        not vence_enlace_anterior
                        or vence_enlace_anterior > datetime.now()
                    )
                ):
                    registro = existente
                elif existente.get("invite_link"):
                    try:
                        bot.revoke_chat_invite_link(
                            CANAL_ID, existente["invite_link"]
                        )
                    except Exception:
                        app.logger.info(
                            "El enlace pendiente anterior de Free Gold Pass "
                            "ya no estaba vigente."
                        )
            elif existente and existente.get("status") == "active":
                vence = _fecha_freepass(existente)
                if vence and vence > datetime.now():
                    registro = existente
                elif vence:
                    vencido = existente
            if vencido:
                pass
            elif registro is None and _suscripcion_vip_activa(user_id):
                raise RuntimeError("Tu acceso GoldPass ya está activo.")
            if registro is None and vencido is None:
                estado = free_goldpass_config()
                if not estado.get("active"):
                    raise RuntimeError("La promoción ya terminó.")
                segundos = int(estado.get("duration_seconds", 0))
                if segundos not in FREE_GOLDPASS_DURATIONS:
                    raise RuntimeError("La duración de la promoción no es válida.")
                emitido = datetime.now().replace(microsecond=0)
                enlace = bot.create_chat_invite_link(
                    CANAL_ID,
                    name="Free GoldPass",
                    creates_join_request=True,
                )
                registro = {
                    "id": user_id,
                    "username": call.from_user.username or "",
                    "campaign_id": estado.get("campaign_id"),
                    "duration_seconds": segundos,
                    "issued_at": emitido.strftime("%Y-%m-%d %H:%M:%S"),
                    "vence": None,
                    "invite_link": enlace.invite_link,
                    "status": "pending",
                    "joined_at": None,
                    "notified_at": None,
                }
                FreeGoldPasses.upsert(
                    registro,
                    FREE_GOLDPASS_QUERY.id == user_id,
                )
                enlace_nuevo = True
        if vencido:
            procesar_vencimiento_freepass(vencido)
            bot.answer_callback_query(
                call.id,
                "Tu pase ya venció; los métodos de pago están disponibles.",
                show_alert=True,
            )
            return
    except Exception:
        app.logger.exception(
            "No se pudo emitir el enlace individual de Free Gold Pass."
        )
        bot.answer_callback_query(
            call.id,
            "No pude generar el enlace. Verifica en el canal GoldPass los permisos "
            "«Invitar usuarios mediante enlace» y «Expulsar usuarios».",
            show_alert=True,
        )
        return

    bot.answer_callback_query(
        call.id,
        "Tu enlace personal está listo."
        if enlace_nuevo
        else (
            "Ya tienes un enlace personal."
            if registro.get("status") == "pending"
            else "Tu acceso está activo."
        ),
    )
    mostrar_menu_free_goldpass_usuario(
        call.message.chat.id,
        user_id,
        registro=registro,
    )


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
    opciones      = _opciones_guardadas_pago(metodo)
    nombre_metodo = NOMBRE_METODO.get(metodo, metodo)
    if not opciones:
        bot.send_message(
            int(ADMIN_ID),
            f"⚠️ No hay información configurada para {html.escape(nombre_metodo)}. "
            "Ve a /admin → Métodos de pago e imagen para actualizarla.",
            parse_mode="HTML",
            protect_content=True,
        )
        return

    # Cada opción va en su propio mensaje para que varias cuentas no excedan
    # el límite de Telegram. Todos los mensajes llevan protección de contenido.
    ids_mensajes = []
    for indice, opcion in enumerate(opciones, start=1):
        datos = opcion
        if metodo not in METODOS_PAGO_POR_ENLACE and _AVISO.strip() not in datos:
            datos += _AVISO
        datos_sin_aviso = datos.replace(_AVISO, "").strip()
        markup = types.InlineKeyboardMarkup(row_width=1)
        try:
            markup.add(types.InlineKeyboardButton(
                f"📋 Copiar opción {indice}",
                copy_text=types.CopyTextButton(text=datos_sin_aviso[:256]),
            ))
        except Exception:
            pass
        markup.add(
            types.InlineKeyboardButton("✅ Aprobado", callback_data=f"adap_{user_id}"),
            types.InlineKeyboardButton("❌ Rechazado", callback_data=f"adrec_{user_id}"),
        )
        datos_msg = bot.send_message(
            int(ADMIN_ID),
            f"📋 <b>DATOS — {html.escape(nombre_metodo)} "
            f"({indice}/{len(opciones)})</b>\n\n"
            f"<code>{html.escape(datos)}</code>",
            parse_mode="HTML",
            reply_markup=markup,
            protect_content=True,
        )
        ids_mensajes.append(datos_msg.message_id)

    # Al aprobar/rechazar se retiran todas las opciones mostradas.
    if user_id in solicitudes_info:
        solicitudes_info[user_id]["datos_msg_ids"] = ids_mensajes
        solicitudes_info[user_id]["datos_msg_id"] = ids_mensajes[-1]
    else:
        solicitudes_info[user_id] = {
            'metodo': metodo, 'username': 'sin_usuario',
            'notif_msg_id': None, 'datos_msg_id': ids_mensajes[-1],
            'datos_msg_ids': ids_mensajes,
        }


def borrar_mensajes_datos_pago(info):
    ids = info.get("datos_msg_ids") or []
    if not ids and info.get("datos_msg_id"):
        ids = [info["datos_msg_id"]]
    for message_id in set(ids):
        try:
            bot.delete_message(int(ADMIN_ID), message_id)
        except Exception:
            pass


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

    # Borrar todos los mensajes con opciones de pago del chat del admin.
    borrar_mensajes_datos_pago(info)

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

    # Borrar todos los mensajes con opciones de pago del chat del admin.
    borrar_mensajes_datos_pago(info)

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


def _registros_grupo(tabla, chat_id, legacy_principal=False, globales=False):
    salida = []
    for registro in tabla.all():
        alcance = registro.get("chat_id")
        if alcance is None:
            if globales or (legacy_principal and str(chat_id) == str(GRUPO_ID)):
                salida.append(registro)
        elif str(alcance) == str(chat_id):
            salida.append(registro)
    return salida


def _eventos_publicacion_grupo(chat_id):
    actividad = _registros_grupo(
        RegistroActividad, chat_id, legacy_principal=True
    )
    promos = _registros_grupo(
        PromosAprobadas, chat_id, legacy_principal=True
    )
    eventos = []
    for registro in actividad:
        eventos.append({"date": registro.get("date", ""), "kind": "actividad", "record": registro})
    for registro in promos:
        eventos.append({"date": registro.get("approved_at", ""), "kind": "promocion", "record": registro})
    return sorted(eventos, key=lambda evento: str(evento.get("date", "")), reverse=True)


def _normalizar_palabra_prohibida(valor):
    normalizada = unicodedata.normalize(
        "NFKD",
        unicodedata.normalize("NFKC", " ".join(str(valor or "").split())).casefold(),
    )
    return "".join(
        caracter for caracter in normalizada
        if not unicodedata.combining(caracter)
    )


def _clasificar_destino_palabras(chat_id):
    cid = str(chat_id)
    cached = _PROHIBITED_WORDS_DESTINATION_CACHE.get(cid)
    if cached is not None:
        return cached
    cfg = cargar_config()
    destinos = [
        (destino, destino.get("chat_id") or destino.get("id"))
        for destino in cfg.get("destinos", {}).values()
        if isinstance(destino, dict)
    ]
    destinos.extend(
        (destino, destino.get("chat_id") or destino.get("id") or group_id)
        for group_id, destino in cfg.get("group_settings", {}).items()
        if isinstance(destino, dict)
    )
    for destino, raw_id in destinos:
        if str(raw_id) != cid:
            continue
        nombre = destino.get("nombre") or destino.get("title") or ""
        clave = re.sub(
            r"[^a-z0-9]",
            "",
            _normalizar_palabra_prohibida(nombre),
        )
        usa_lista_predeterminada = "cxhotgochat" in clave
        mostrar_panel = usa_lista_predeterminada or any(
            marca in clave
            for marca in ("goldpasscxhotgo", "gopasscxhotgo")
        )
        resultado = (mostrar_panel, usa_lista_predeterminada)
        _PROHIBITED_WORDS_DESTINATION_CACHE[cid] = resultado
        return resultado
    resultado = (False, False)
    _PROHIBITED_WORDS_DESTINATION_CACHE[cid] = resultado
    return resultado


def _destino_usa_palabras_predeterminadas(chat_id):
    return _clasificar_destino_palabras(chat_id)[1]


def _destino_muestra_palabras_prohibidas(chat_id):
    return _clasificar_destino_palabras(chat_id)[0]


def _asegurar_palabras_predeterminadas(chat_id):
    cid = str(chat_id)
    if cid in _PROHIBITED_WORDS_READY:
        return
    if not _destino_usa_palabras_predeterminadas(cid):
        _PROHIBITED_WORDS_READY.add(cid)
        _PROHIBITED_WORDS_CACHE.pop(cid, None)
        return
    existentes = {
        _normalizar_palabra_prohibida(row.get("word"))
        for row in GroupBannedWords.search(
            lambda row: str(row.get("chat_id")) == cid
        )
    }
    for categoria, palabras in DEFAULT_PROHIBITED_WORD_GROUPS:
        for palabra in palabras:
            normalizada = _normalizar_palabra_prohibida(palabra)
            if normalizada in existentes:
                continue
            GroupBannedWords.insert({
                "chat_id": cid,
                "word": palabra,
                "normalized": normalizada,
                "category": categoria,
                "source": "default",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            existentes.add(normalizada)
    _PROHIBITED_WORDS_READY.add(cid)
    _PROHIBITED_WORDS_CACHE.pop(cid, None)


def _palabras_prohibidas_destino(chat_id):
    filas = GroupBannedWords.search(
        lambda row: str(row.get("chat_id")) == str(chat_id)
    )
    if not _destino_usa_palabras_predeterminadas(chat_id):
        filas = [fila for fila in filas if fila.get("source") != "default"]
    orden_categoria = {
        categoria: indice
        for indice, (categoria, _) in enumerate(DEFAULT_PROHIBITED_WORD_GROUPS)
    }
    filas_ordenadas = sorted(
        filas,
        key=lambda row: (
            orden_categoria.get(row.get("category"), len(orden_categoria)),
            _normalizar_palabra_prohibida(row.get("word")),
        ),
    )
    salida = []
    vistas = set()
    for fila in filas_ordenadas:
        normalizada = _normalizar_palabra_prohibida(fila.get("word"))
        if not normalizada or normalizada in vistas:
            continue
        vistas.add(normalizada)
        salida.append(fila)
    return salida


def encontrar_palabra_prohibida(chat_id, texto):
    cid = str(chat_id)
    if not _destino_muestra_palabras_prohibidas(cid):
        return None
    _asegurar_palabras_predeterminadas(cid)
    patrones = _PROHIBITED_WORDS_CACHE.get(cid)
    if patrones is None:
        patrones = []
        for fila in _palabras_prohibidas_destino(cid):
            palabra = _normalizar_palabra_prohibida(fila.get("word"))
            if not palabra:
                continue
            literal = re.escape(palabra).replace(r"\ ", r"\s+")
            patrones.append((
                re.compile(r"(?<!\w)" + literal + r"(?!\w)", re.UNICODE),
                fila,
            ))
        _PROHIBITED_WORDS_CACHE[cid] = patrones
    texto_normalizado = _normalizar_palabra_prohibida(texto)
    for patron, fila in patrones:
        if patron.search(texto_normalizado):
            return fila
    return None


def moderar_palabras_prohibidas(message, evidencia=None):
    if message.chat.type not in ("group", "supergroup"):
        return False
    if (
        str(message.from_user.id) == str(ADMIN_ID)
        or getattr(message.from_user, "is_bot", False)
    ):
        return False
    texto = message.text or message.caption or ""
    if not texto.strip():
        return False

    coincidencia = encontrar_palabra_prohibida(message.chat.id, texto)
    if not coincidencia:
        return False
    try:
        rol = bot.get_chat_member(
            message.chat.id,
            message.from_user.id,
        ).status
    except Exception:
        app.logger.exception(
            "No se pudo verificar el rol antes de aplicar el filtro de palabras."
        )
        return False
    if rol in ("creator", "administrator"):
        return False

    mensaje_borrado = True
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except Exception:
        mensaje_borrado = False
        app.logger.exception(
            "Telegram no permitió borrar un mensaje con una palabra prohibida."
        )

    motivo = f"Palabra prohibida: {coincidencia.get('word', '')}"
    if not mensaje_borrado:
        motivo += " · Telegram no permitió borrar el mensaje"
    aplicar_castigo(
        message.chat.id,
        message.from_user.id,
        (message.from_user.username or "anonimo").lower(),
        evidence=evidencia,
        reason=motivo,
    )
    return True


def agregar_palabra_prohibida(chat_id, palabra):
    palabra = " ".join(str(palabra or "").split())
    normalizada = _normalizar_palabra_prohibida(palabra)
    if len(palabra) < 2 or len(palabra) > 100 or "\n" in palabra:
        raise ValueError("La palabra o frase debe tener entre 2 y 100 caracteres.")
    if not _destino_muestra_palabras_prohibidas(chat_id):
        raise ValueError("La lista de palabras no está habilitada para este destino.")
    _asegurar_palabras_predeterminadas(chat_id)
    existente = GroupBannedWords.search(
        lambda row: str(row.get("chat_id")) == str(chat_id)
        and (
            row.get("source") != "default"
            or _destino_usa_palabras_predeterminadas(chat_id)
        )
        and _normalizar_palabra_prohibida(row.get("word")) == normalizada
    )
    if existente:
        return False
    GroupBannedWords.insert({
        "chat_id": str(chat_id),
        "word": palabra,
        "normalized": normalizada,
        "category": "Agregadas por el administrador",
        "source": "admin",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    _PROHIBITED_WORDS_CACHE.pop(str(chat_id), None)
    return True


def mostrar_palabras_prohibidas(
    chat_id, dest_key, message=None, message_id=None, aviso=None
):
    destino = _destino_por_key(dest_key)
    if not destino:
        return None
    cid = str(destino.get("chat_id"))
    if not _destino_muestra_palabras_prohibidas(cid):
        return editar_o_enviar_panel(
            chat_id,
            "Las palabras prohibidas solo están habilitadas para CX HOTGO Chat y GoldPass CX HOTGO.",
            types.InlineKeyboardMarkup().add(types.InlineKeyboardButton(
                "🔙 Volver a configuración",
                callback_data=f"mod_home|{dest_key}",
            )),
            message=message,
            message_id=message_id,
            protect_content=True,
            forzar_texto=True,
        )
    _asegurar_palabras_predeterminadas(cid)
    filas = _palabras_prohibidas_destino(cid)
    por_categoria = {}
    for fila in filas:
        por_categoria.setdefault(
            fila.get("category") or "Agregadas por el administrador", []
        ).append(str(fila.get("word") or ""))

    lineas = [f"🚫 <b>Palabras prohibidas · {html.escape(str(destino.get('nombre') or cid))}</b>"]
    if aviso:
        lineas.append(f"\n✅ {html.escape(str(aviso))}")
    if not filas:
        lineas.append("\nLa lista está vacía. Agrega palabras para activar el filtro en este destino.")
    else:
        for categoria, palabras in por_categoria.items():
            lineas.append(f"\n<b>{html.escape(str(categoria))}</b>")
            lineas.append(", ".join(html.escape(palabra) for palabra in palabras))
        lineas.append(
            "\n\nSe eliminan coincidencias de palabra o frase completa. "
            "La 1.ª y 2.ª sanción silencian 35 minutos; la 3.ª expulsa."
        )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(
            "➕ Agregar palabra",
            callback_data=f"mod_palabras_add|{dest_key}",
        ),
        types.InlineKeyboardButton(
            "🔙 Volver a configuración",
            callback_data=f"mod_home|{dest_key}",
        ),
    )
    return editar_o_enviar_panel(
        chat_id,
        "\n".join(lineas),
        markup,
        message=message,
        message_id=message_id,
        protect_content=True,
        forzar_texto=True,
    )


def enviar_media_panel_control(chat_id, media_type, file_id, caption, markup):
    registro = None
    if int(chat_id) > 0:
        with PANEL_LOCK:
            registro = PANELES_PRIVADOS.get(PANEL_QUERY.chat_id == str(chat_id))
    if registro:
        try:
            bot.delete_message(chat_id, registro.get("message_id"))
        except Exception:
            pass
        with PANEL_LOCK:
            PANELES_PRIVADOS.remove(PANEL_QUERY.chat_id == str(chat_id))
    if media_type == "video":
        nuevo = bot.send_video(
            chat_id,
            file_id,
            caption=caption,
            parse_mode="HTML",
            reply_markup=markup,
            protect_content=True,
        )
        tipo = "video"
    else:
        nuevo = bot.send_photo(
            chat_id,
            file_id,
            caption=caption,
            parse_mode="HTML",
            reply_markup=markup,
            protect_content=True,
        )
        tipo = "foto"
    if int(chat_id) > 0:
        with PANEL_LOCK:
            PANELES_PRIVADOS.upsert(
                {
                    "chat_id": str(chat_id),
                    "message_id": nuevo.message_id,
                    "tipo": tipo,
                    "protect_content": True,
                },
                PANEL_QUERY.chat_id == str(chat_id),
            )
    return nuevo


def enviar_media_panel_publicacion(chat_id, media_type, file_id, caption, markup):
    metodos = {
        "photo": bot.send_photo,
        "video": bot.send_video,
        "document": bot.send_document,
        "audio": bot.send_audio,
        "animation": bot.send_animation,
    }
    metodo = metodos.get(media_type)
    if not metodo:
        raise ValueError("Ese tipo de multimedia no se puede previsualizar.")

    registro = None
    if int(chat_id) > 0:
        with PANEL_LOCK:
            registro = PANELES_PRIVADOS.get(PANEL_QUERY.chat_id == str(chat_id))
    if registro:
        try:
            bot.delete_message(chat_id, registro.get("message_id"))
        except Exception:
            app.logger.info("No se pudo reemplazar el panel previo de publicación.")
        with PANEL_LOCK:
            PANELES_PRIVADOS.remove(PANEL_QUERY.chat_id == str(chat_id))

    nuevo = metodo(
        chat_id,
        file_id,
        caption=caption,
        parse_mode="HTML",
        reply_markup=markup,
        protect_content=True,
    )
    if int(chat_id) > 0:
        with PANEL_LOCK:
            PANELES_PRIVADOS.upsert(
                {
                    "chat_id": str(chat_id),
                    "message_id": nuevo.message_id,
                    "tipo": media_type,
                    "protect_content": True,
                },
                PANEL_QUERY.chat_id == str(chat_id),
            )
    return nuevo


def botones_fijos_publicacion_goldpass():
    ruta = os.path.join(BASE_DIR, "botones_goldpass.json")
    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            guardados = json.load(archivo)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            "No pude leer los enlaces predeterminados de X y OnlyFans."
        ) from error

    if not isinstance(guardados, list):
        raise ValueError("La lista de botones predeterminados no es válida.")

    encontrados = {}
    for boton in guardados:
        if not isinstance(boton, dict):
            continue
        etiqueta = str(boton.get("texto") or "").strip()
        normalizada = etiqueta.casefold()
        url = str(boton.get("url") or "").strip()
        if normalizada in ("x", "𝕏", "𝕏 x"):
            clave, texto = "x", "𝕏 X"
        elif "onlyfans" in normalizada:
            clave, texto = "onlyfans", "🔞 OnlyFans"
        else:
            continue
        if not url.startswith("https://"):
            continue
        encontrados[clave] = {"texto": texto, "url": url}

    if set(encontrados) != {"x", "onlyfans"}:
        raise ValueError(
            "El archivo de botones de GoldPass debe contener los enlaces de X y OnlyFans."
        )
    return [encontrados["x"], encontrados["onlyfans"]]


def markup_publicacion_goldpass():
    markup = types.InlineKeyboardMarkup(row_width=2)
    botones = botones_fijos_publicacion_goldpass()
    markup.row(*[
        types.InlineKeyboardButton(boton["texto"], url=boton["url"])
        for boton in botones
    ])
    return markup


def markup_flujo_publicacion_destino(dest_key):
    return types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton(
            "❌ Cancelar",
            callback_data=f"destpub_cancel|{dest_key}",
        )
    )


def mostrar_paso_publicacion_destino(chat_id, estado, texto, message=None):
    panel = editar_o_enviar_panel(
        chat_id,
        texto,
        markup_flujo_publicacion_destino(estado["dest_key"]),
        message=message,
        message_id=estado.get("panel_message_id"),
        protect_content=True,
        forzar_texto=True,
    )
    estado["panel_message_id"] = panel.message_id
    return panel


def mostrar_previa_publicacion_destino(chat_id, estado):
    destino = _destino_por_key(estado.get("dest_key", ""))
    if not destino:
        raise ValueError("El canal elegido ya no está guardado.")
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(
            "✅ Aceptar y publicar",
            callback_data=f"destpub_accept|{estado['dest_key']}",
        ),
        types.InlineKeyboardButton(
            "✏️ Modificar",
            callback_data=f"destpub_modify|{estado['dest_key']}",
        ),
    )
    caption = (
        f"👁️ <b>Vista previa · "
        f"{html.escape(str(destino.get('nombre') or 'Canal'))}</b>\n\n"
        f"{html.escape(str(estado.get('descripcion') or ''))}"
    )
    panel = enviar_media_panel_publicacion(
        chat_id,
        estado["media_type"],
        estado["media_id"],
        caption,
        markup,
    )
    estado["paso"] = "revision_publicacion_destino"
    estado["panel_message_id"] = panel.message_id
    return panel


def mostrar_panel_control_grupo(
    chat_id, dest_key, destino, message=None, message_id=None, aviso=None
):
    cid = str(destino.get("chat_id"))
    reportes = _registros_grupo(GroupReports, cid)
    advertencias = _registros_grupo(Warnings, cid, legacy_principal=True)
    bloqueados = [
        registro for registro in _registros_grupo(
            Blacklist, cid, legacy_principal=True
        )
        if registro.get("status", "active") == "active"
    ]
    publicaciones = _eventos_publicacion_grupo(cid)

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(
            f"🚩 Reportes ({len(reportes)})",
            callback_data=f"mod_seccion|{dest_key}|reportes|0",
        ),
        types.InlineKeyboardButton(
            f"⚠️ Sanciones ({len(advertencias) + len(bloqueados)})",
            callback_data=f"mod_seccion|{dest_key}|sanciones|0",
        ),
        types.InlineKeyboardButton(
            f"⛔ Lista negra ({len(bloqueados)})",
            callback_data=f"mod_seccion|{dest_key}|blacklist|0",
        ),
        types.InlineKeyboardButton(
            f"📰 Publicaciones ({len(publicaciones)})",
            callback_data=f"mod_seccion|{dest_key}|publicaciones|0",
        ),
    )
    if str(destino.get("tipo") or "").lower() in ("canal", "channel"):
        markup.add(
            types.InlineKeyboardButton(
                "📣 Enviar publicación",
                callback_data=f"destpub_start|{dest_key}",
            )
        )
    if _destino_muestra_palabras_prohibidas(cid):
        markup.add(types.InlineKeyboardButton(
            "🚫 Palabras prohibidas",
            callback_data=f"mod_palabras|{dest_key}",
        ))
    markup.add(
        types.InlineKeyboardButton(
            "🔙 Volver al destino",
            callback_data=f"destinfo|{dest_key}",
        ),
    )
    nombre = html.escape(str(destino.get("nombre") or cid))
    texto = (
        f"🛡️ <b>Control privado · {nombre}</b>\n"
        f"ID: <code>{html.escape(cid)}</code>\n\n"
        "Este panel solo se muestra en el chat privado del administrador. "
        "Aquí se consultan reportes, sanciones y actividad guardada para este destino."
    )
    if aviso:
        texto = f"✅ {html.escape(str(aviso))}\n\n{texto}"
    return editar_o_enviar_panel(
        chat_id, texto, markup, message=message, message_id=message_id,
        protect_content=True, forzar_texto=True,
    )


def mostrar_seccion_control_grupo(
    chat_id, dest_key, section, page=0, message=None
):
    destino = _destino_por_key(dest_key)
    if not destino:
        return None
    cid = str(destino.get("chat_id"))
    page_size = 7
    page = max(0, int(page))
    markup = types.InlineKeyboardMarkup(row_width=2)
    nombre = html.escape(str(destino.get("nombre") or cid))
    titulo = {
        "reportes": "🚩 Reportes recibidos",
        "sanciones": "⚠️ Advertencias y expulsiones",
        "blacklist": "⛔ Lista negra",
        "publicaciones": "📰 Actividad y publicaciones",
    }.get(section)
    if not titulo:
        return mostrar_panel_control_grupo(
            chat_id, dest_key, destino, message=message
        )

    if section == "reportes":
        registros = _registros_grupo(GroupReports, cid)
        registros.sort(key=lambda row: str(row.get("date", "")), reverse=True)
    elif section == "sanciones":
        advertencias = _registros_grupo(Warnings, cid, legacy_principal=True)
        bloqueos = [
            row for row in _registros_grupo(
                Blacklist, cid, legacy_principal=True
            )
            if row.get("status", "active") == "active"
        ]
        acciones = _registros_grupo(GroupModerationLog, cid)
        registros = (
            [{"kind": "advertencia", **row} for row in advertencias]
            + [{"kind": "expulsión", **row} for row in bloqueos]
            + [{"kind": "acción", **row} for row in acciones]
        )
        registros.sort(key=lambda row: str(
            row.get("date") or row.get("last_warn") or ""
        ), reverse=True)
    elif section == "blacklist":
        registros = [
            row for row in _registros_grupo(
                Blacklist, cid, legacy_principal=True
            )
            if row.get("status", "active") == "active"
        ]
        registros.sort(key=lambda row: str(row.get("date", "")), reverse=True)
    else:
        registros = _eventos_publicacion_grupo(cid)

    total = len(registros)
    start = page * page_size
    current = registros[start:start + page_size]
    lines = [f"{titulo} · <b>{nombre}</b>\n"]
    if not current:
        lines.append("Todavía no hay registros guardados para este grupo o canal.")

    for row in current:
        if section == "reportes":
            username = html.escape(str(row.get("reported_username") or "sin_usuario"))
            reporter = html.escape(str(row.get("reporter_id") or "desconocido"))
            action = html.escape(str(row.get("action") or "registrado"))
            when = html.escape(str(row.get("date") or "fecha no registrada"))
            lines.append(
                f"• <b>@{username}</b> · ID "
                f"<code>{row.get('reported_user_id', '?')}</code>\n"
                f"  Reportó: <code>{reporter}</code> · {action} · {when}"
            )
            evidence_id = row.get("evidence_doc_id")
            if evidence_id:
                markup.add(types.InlineKeyboardButton(
                    "👁️ Ver evidencia",
                    callback_data=f"mv|{dest_key}|a|{evidence_id}|r|{page}",
                ))
        elif section == "sanciones":
            username = html.escape(str(row.get("username") or "sin_usuario"))
            user_id = row.get("user_id", row.get("id", "?"))
            kind = row.get("kind", "acción")
            when = html.escape(str(
                row.get("date") or row.get("last_warn") or "fecha no registrada"
            ))
            if kind == "advertencia":
                detalle = f"Advertencias: {row.get('count', 0)}/3"
                if row.get("reason"):
                    detalle += f" · {html.escape(str(row.get('reason')))}"
            elif kind == "expulsión":
                detalle = html.escape(str(row.get("reason") or "Expulsión activa"))
            else:
                detalle = html.escape(str(row.get("action") or "acción registrada"))
                if row.get("count"):
                    detalle += f" · {row.get('count')}/3"
                if row.get("reason"):
                    detalle += f" · {html.escape(str(row.get('reason')))}"
            lines.append(
                f"• <b>@{username}</b> · ID <code>{user_id}</code>\n"
                f"  {detalle} · {when}"
            )
            evidence_id = row.get("evidence_doc_id")
            if evidence_id:
                markup.add(types.InlineKeyboardButton(
                    "👁️ Ver evidencia",
                    callback_data=f"mv|{dest_key}|a|{evidence_id}|s|{page}",
                ))
            if kind == "advertencia":
                markup.add(
                    types.InlineKeyboardButton(
                        f"🔊 Quitar silencio · {str(username)[:12]}",
                        callback_data=f"unmute|{dest_key}|{cid}|{user_id}",
                    ),
                    types.InlineKeyboardButton(
                        "⚠️ Mantener sanción",
                        callback_data=f"keepwarn|{dest_key}|{cid}|{user_id}",
                    ),
                )
        elif section == "blacklist":
            username = html.escape(str(row.get("username") or "sin_usuario"))
            user_id = row.get("id", "?")
            when = html.escape(str(row.get("date") or "fecha no registrada"))
            reason = html.escape(str(row.get("reason") or "Bloqueo activo"))
            lines.append(
                f"• <b>@{username}</b> · ID <code>{user_id}</code>\n"
                f"  {reason} · {when}"
            )
            markup.add(
                types.InlineKeyboardButton(
                    f"🔓 Reingresar {str(username)[:14]} (2/3)",
                    callback_data=f"mod_perdonar|{dest_key}|{cid}|{user_id}",
                ),
                types.InlineKeyboardButton(
                    "⛔ Mantener expulsión",
                    callback_data=f"mod_mantener|{dest_key}|{cid}|{user_id}",
                ),
            )
        else:
            kind = row.get("kind")
            if kind == "promocion":
                promo = row.get("record", {})
                desc = html.escape(str(promo.get("desc") or "Publicación multimedia")[:180])
                label = "🎥" if promo.get("is_video") else "🖼️"
                who = html.escape(str(promo.get("uname") or "miembro"))
                when = html.escape(str(row.get("date") or "fecha no registrada"))
                detail = f"{label} Publicación aprobada por @{who}: {desc}"
            else:
                post = row.get("record", {})
                kind_post = html.escape(str(post.get("type") or "mensaje"))
                who = html.escape(str(post.get("uname") or "miembro"))
                text = html.escape(str(post.get("text") or "").strip()[:180])
                when = html.escape(str(row.get("date") or "fecha no registrada"))
                detail = f"📨 {kind_post} de @{who}"
                if post.get("file_id"):
                    detail += " · multimedia guardada"
                if text:
                    detail += f": {text}"
            lines.append(f"• {detail}\n  {when}")
            record = row.get("record", {})
            record_kind = "p" if kind == "promocion" else "a"
            markup.add(types.InlineKeyboardButton(
                "👁️ Ver publicación",
                callback_data=(
                    f"mv|{dest_key}|{record_kind}|{record.doc_id}|p|{page}"
                ),
            ))

    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton(
            "⬅️ Anterior",
            callback_data=f"mod_seccion|{dest_key}|{section}|{page - 1}",
        ))
    if start + page_size < total:
        nav.append(types.InlineKeyboardButton(
            "Siguiente ➡️",
            callback_data=f"mod_seccion|{dest_key}|{section}|{page + 1}",
        ))
    if nav:
        markup.keyboard.insert(0, nav)
    if total:
        lines.insert(1, f"Página {page + 1} · {total} registros\n")
    markup.add(types.InlineKeyboardButton(
        "🔙 Volver",
        callback_data=f"mod_home|{dest_key}",
    ))
    return editar_o_enviar_panel(
        chat_id,
        "\n".join(lines),
        markup,
        message=message,
        protect_content=True,
        forzar_texto=True,
    )


def _markup_grupos_admin():
    m=types.InlineKeyboardMarkup(row_width=1)
    cfg=cargar_config(); items=[]; seen=set()
    for key,d in cfg.get("destinos",{}).items():
        if not isinstance(d,dict) or d.get("archivado"): continue
        cid=str(d.get("chat_id"))
        if not cid: continue
        seen.add(cid); items.append((key,d))
    for cid,info in cfg.get("group_settings",{}).items():
        if str(cid) in seen or not isinstance(info,dict): continue
        d={"chat_id":str(cid),"nombre":info.get("title") or info.get("nombre") or str(cid),"tipo":info.get("type") or "grupo"}
        items.append((f"group:{cid}",d))
    for key,d in items:
        m.add(types.InlineKeyboardButton(f"📂 {str(d.get('nombre') or d.get('chat_id'))[:36]} · {d.get('tipo','destino')}",callback_data=f"destinfo|{key}"))
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
    if not es_admin_privado(c):
        bot.answer_callback_query(c.id, "⛔ Sin permiso.")
        return
    key = c.data.split("|", 1)[1]
    destino = _destino_por_key(key)
    if not destino:
        bot.answer_callback_query(c.id, "Destino no disponible.")
        return
    bot.answer_callback_query(c.id)
    mostrar_panel_control_grupo(
        c.message.chat.id, key, destino, message=c.message
    )


@bot.callback_query_handler(
    func=lambda c: c.data.startswith("destpub_start|")
)
def cb_destpub_start(c):
    if not es_admin_privado(c):
        bot.answer_callback_query(c.id, "⛔ Sin permiso.")
        return
    dest_key = c.data.split("|", 1)[1]
    destino = _destino_por_key(dest_key)
    if (
        not destino
        or str(destino.get("tipo") or "").lower() not in ("canal", "channel")
    ):
        bot.answer_callback_query(
            c.id, "La publicación directa está disponible para canales."
        )
        return

    uid = c.from_user.id
    estado = {
        "paso": "esperando_media_dest_publicacion",
        "dest_key": dest_key,
        "panel_message_id": c.message.message_id,
    }
    admin_estado[uid] = estado
    bot.answer_callback_query(c.id)
    mostrar_paso_publicacion_destino(
        c.message.chat.id,
        estado,
        "📣 <b>Nueva publicación</b>\n\n"
        f"Canal: <b>{html.escape(str(destino.get('nombre') or ''))}</b>\n"
        "Envía una foto, video, documento, audio o animación. "
        "Después añadirás la descripción y podrás revisar la vista previa.",
        message=c.message,
    )


@bot.callback_query_handler(
    func=lambda c: c.data.startswith("destpub_cancel|")
)
def cb_destpub_cancel(c):
    if not es_admin_privado(c):
        bot.answer_callback_query(c.id, "⛔ Sin permiso.")
        return
    dest_key = c.data.split("|", 1)[1]
    estado = admin_estado.get(c.from_user.id, {})
    if estado.get("dest_key") == dest_key and str(
        estado.get("paso", "")
    ).startswith(("esperando_media_dest_publicacion",
                  "esperando_descripcion_dest_publicacion",
                  "revision_publicacion_destino")):
        admin_estado.pop(c.from_user.id, None)
    destino = _destino_por_key(dest_key)
    bot.answer_callback_query(c.id, "Edición cancelada.")
    if destino:
        mostrar_panel_control_grupo(
            c.message.chat.id,
            dest_key,
            destino,
            message=c.message,
            aviso="Publicación cancelada; no se envió al canal.",
        )
    else:
        editar_o_enviar_panel(
            c.message.chat.id,
            "El canal ya no está guardado.",
            _markup_grupos_admin(),
            message=c.message,
            protect_content=True,
            forzar_texto=True,
        )


@bot.callback_query_handler(
    func=lambda c: c.data.startswith("destpub_modify|")
)
def cb_destpub_modify(c):
    if not es_admin_privado(c):
        bot.answer_callback_query(c.id, "⛔ Sin permiso.")
        return
    dest_key = c.data.split("|", 1)[1]
    estado = admin_estado.get(c.from_user.id, {})
    destino = _destino_por_key(dest_key)
    if (
        not destino
        or estado.get("dest_key") != dest_key
        or estado.get("paso") != "revision_publicacion_destino"
    ):
        bot.answer_callback_query(c.id, "La vista previa ya no está disponible.")
        return

    estado["paso"] = "esperando_media_dest_publicacion"
    estado.pop("media_id", None)
    estado.pop("media_type", None)
    estado.pop("descripcion", None)
    bot.answer_callback_query(c.id)
    mostrar_paso_publicacion_destino(
        c.message.chat.id,
        estado,
        "✏️ <b>Modificar publicación</b>\n\n"
        "Envía de nuevo la foto, video u otro archivo multimedia. "
        "Después podrás escribir la descripción actualizada.",
        message=c.message,
    )


@bot.callback_query_handler(
    func=lambda c: c.data.startswith("destpub_accept|")
)
def cb_destpub_accept(c):
    if not es_admin_privado(c):
        bot.answer_callback_query(c.id, "⛔ Sin permiso.")
        return
    dest_key = c.data.split("|", 1)[1]
    estado = admin_estado.get(c.from_user.id, {})
    destino = _destino_por_key(dest_key)
    if (
        not destino
        or estado.get("dest_key") != dest_key
        or estado.get("paso") != "revision_publicacion_destino"
    ):
        bot.answer_callback_query(c.id, "La vista previa ya no está disponible.")
        return

    try:
        markup = markup_publicacion_goldpass()
        enviar_publicacion_con_botones(
            destino["chat_id"],
            html.escape(str(estado.get("descripcion") or "")),
            markup,
            media_id=estado.get("media_id"),
            media_type=estado.get("media_type"),
        )
    except Exception:
        app.logger.exception(
            "No se pudo publicar la multimedia en el canal %s.", dest_key
        )
        bot.answer_callback_query(
            c.id,
            "No se publicó. Revisa el permiso para publicar mensajes y los enlaces de X/OnlyFans.",
            show_alert=True,
        )
        return

    admin_estado.pop(c.from_user.id, None)
    bot.answer_callback_query(c.id, "Publicación enviada.")
    mostrar_panel_control_grupo(
        c.message.chat.id,
        dest_key,
        destino,
        message=c.message,
        aviso="Publicación enviada al canal con los botones fijos de X y OnlyFans.",
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("mod_home|"))
def cb_mod_home(c):
    if not es_admin_privado(c):
        bot.answer_callback_query(c.id, "⛔ Sin permiso.")
        return
    key = c.data.split("|", 1)[1]
    destino = _destino_por_key(key)
    if not destino:
        bot.answer_callback_query(c.id, "Destino no disponible.")
        return
    bot.answer_callback_query(c.id)
    mostrar_panel_control_grupo(
        c.message.chat.id, key, destino, message=c.message
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("mod_seccion|"))
def cb_mod_seccion(c):
    if not es_admin_privado(c):
        bot.answer_callback_query(c.id, "⛔ Sin permiso.")
        return
    try:
        _, key, section, page = c.data.split("|", 3)
        page = int(page)
    except (ValueError, TypeError):
        bot.answer_callback_query(c.id, "No pude abrir esa sección.")
        return
    if not _destino_por_key(key):
        bot.answer_callback_query(c.id, "Destino no disponible.")
        return
    bot.answer_callback_query(c.id)
    mostrar_seccion_control_grupo(
        c.message.chat.id, key, section, page, message=c.message
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("mod_palabras|"))
def cb_mod_palabras(c):
    if not es_admin_privado(c):
        bot.answer_callback_query(c.id, "⛔ Sin permiso.")
        return
    key = c.data.split("|", 1)[1]
    if not _destino_por_key(key):
        bot.answer_callback_query(c.id, "Destino no disponible.")
        return
    bot.answer_callback_query(c.id)
    mostrar_palabras_prohibidas(
        c.message.chat.id, key, message=c.message
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("mod_palabras_add|"))
def cb_mod_palabras_add(c):
    if not es_admin_privado(c):
        bot.answer_callback_query(c.id, "⛔ Sin permiso.")
        return
    key = c.data.split("|", 1)[1]
    if not _destino_por_key(key):
        bot.answer_callback_query(c.id, "Destino no disponible.")
        return
    admin_estado[c.from_user.id] = {
        "paso": "esperando_palabra_prohibida",
        "dest_key": key,
        "panel_message_id": c.message.message_id,
    }
    markup = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton(
            "Cancelar",
            callback_data=f"mod_palabras_cancel|{key}",
        )
    )
    bot.answer_callback_query(c.id)
    editar_o_enviar_panel(
        c.message.chat.id,
        "Envía una palabra o frase prohibida en un solo mensaje. "
        "La entrada se guardará solo para este grupo o canal; usa /cancelar para salir.",
        markup,
        message=c.message,
        protect_content=True,
        forzar_texto=True,
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("mod_palabras_cancel|"))
def cb_mod_palabras_cancel(c):
    if not es_admin_privado(c):
        bot.answer_callback_query(c.id, "⛔ Sin permiso.")
        return
    key = c.data.split("|", 1)[1]
    estado = admin_estado.get(c.from_user.id, {})
    if estado.get("paso") == "esperando_palabra_prohibida":
        admin_estado.pop(c.from_user.id, None)
    bot.answer_callback_query(c.id, "Edición cancelada.")
    mostrar_palabras_prohibidas(
        c.message.chat.id,
        key,
        message=c.message,
        aviso="No se agregó ninguna palabra.",
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("mod_mantener|"))
def cb_mod_mantener(c):
    if not es_admin_privado(c):
        bot.answer_callback_query(c.id, "⛔ Sin permiso.")
        return
    try:
        _, key, raw_chat_id, raw_user_id = c.data.split("|", 3)
        chat_id, user_id = int(raw_chat_id), int(raw_user_id)
    except (ValueError, TypeError):
        bot.answer_callback_query(c.id, "Datos de usuario inválidos.")
        return
    destino = _destino_por_key(key)
    if not destino or str(destino.get("chat_id")) != str(chat_id):
        bot.answer_callback_query(c.id, "Destino no disponible.")
        return
    active = [
        row for row in Blacklist.search(User.id == user_id)
        if row.get("status", "active") == "active"
        and (
            str(row.get("chat_id")) == str(chat_id)
            or (not row.get("chat_id") and str(chat_id) == str(GRUPO_ID))
        )
    ]
    if not active:
        bot.answer_callback_query(c.id, "Ya no hay una expulsión activa.")
        return
    bot.answer_callback_query(c.id, "Se mantiene la expulsión.")


@bot.callback_query_handler(func=lambda c: c.data.startswith("unmute|"))
def cb_mod_quitar_silencio(c):
    if not es_admin_privado(c):
        bot.answer_callback_query(c.id, "⛔ Sin permiso.")
        return
    try:
        _, key, raw_chat_id, raw_user_id = c.data.split("|", 3)
        chat_id, user_id = int(raw_chat_id), int(raw_user_id)
    except (ValueError, TypeError):
        bot.answer_callback_query(c.id, "Datos de usuario inválidos.")
        return
    destino = _destino_por_key(key)
    if not destino or str(destino.get("chat_id")) != str(chat_id):
        bot.answer_callback_query(c.id, "Destino no disponible.")
        return
    advertencias = _advertencias_usuario(chat_id, user_id)
    if not advertencias:
        bot.answer_callback_query(c.id, "No hay una sanción activa para ese usuario.")
        return
    if _usuario_en_lista_negra(user_id, chat_id):
        bot.answer_callback_query(
            c.id,
            "El usuario sigue expulsado. Usa «Reingresar» en Lista negra.",
            show_alert=True,
        )
        return
    try:
        bot.restrict_chat_member(
            chat_id,
            user_id,
            can_send_messages=True,
            use_independent_chat_permissions=False,
        )
    except Exception:
        app.logger.exception(
            "No se pudo quitar el silencio a %s en el destino %s.",
            user_id,
            chat_id,
        )
        bot.answer_callback_query(
            c.id,
            "Telegram no permitió quitar el silencio; revisa los permisos del bot.",
            show_alert=True,
        )
        return
    GroupModerationLog.insert({
        "chat_id": str(chat_id),
        "user_id": user_id,
        "username": str(advertencias[-1].get("username") or ""),
        "action": "manual_unmute",
        "count": int(advertencias[-1].get("count", 0)),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    bot.answer_callback_query(c.id, "Silencio retirado; se conservó el historial.")
    mostrar_seccion_control_grupo(
        c.message.chat.id,
        key,
        "sanciones",
        0,
        message=c.message,
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("keepwarn|"))
def cb_mod_mantener_sancion(c):
    if not es_admin_privado(c):
        bot.answer_callback_query(c.id, "⛔ Sin permiso.")
        return
    try:
        _, key, raw_chat_id, raw_user_id = c.data.split("|", 3)
        chat_id, user_id = int(raw_chat_id), int(raw_user_id)
    except (ValueError, TypeError):
        bot.answer_callback_query(c.id, "Datos de usuario inválidos.")
        return
    destino = _destino_por_key(key)
    if not destino or str(destino.get("chat_id")) != str(chat_id):
        bot.answer_callback_query(c.id, "Destino no disponible.")
        return
    if not _advertencias_usuario(chat_id, user_id):
        bot.answer_callback_query(c.id, "No hay una sanción activa para ese usuario.")
        return
    bot.answer_callback_query(c.id, "Se mantiene la sanción.")


@bot.callback_query_handler(func=lambda c: c.data.startswith("mv|"))
def cb_mod_ver_publicacion(c):
    if not es_admin_privado(c):
        bot.answer_callback_query(c.id, "⛔ Sin permiso.")
        return
    try:
        _, key, record_kind, raw_doc_id, back_kind, raw_page = c.data.split("|", 5)
        doc_id = int(raw_doc_id)
        page = int(raw_page)
        back_section = {
            "r": "reportes",
            "s": "sanciones",
        }.get(back_kind, "publicaciones")
        destino = _destino_por_key(key)
        if not destino:
            raise ValueError("destino")
        chat_id = str(destino.get("chat_id"))
        tabla = RegistroActividad if record_kind == "a" else PromosAprobadas
        if record_kind not in ("a", "p"):
            raise ValueError("tipo")
        registro = next(
            (
                item for item in _registros_grupo(
                    tabla, chat_id, legacy_principal=True
                )
                if item.doc_id == doc_id
            ),
            None,
        )
        if not registro:
            bot.answer_callback_query(c.id, "La publicación ya no está disponible.")
            return
    except (ValueError, TypeError):
        bot.answer_callback_query(c.id, "No pude abrir esa publicación.")
        return

    back_markup = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton(
            "🔙 Regresar",
            callback_data=f"mod_seccion|{key}|{back_section}|{page}",
        )
    )
    username = html.escape(str(registro.get("uname") or "miembro"))
    if record_kind == "p":
        body = str(registro.get("desc") or "Publicación aprobada")
        media_type = "video" if registro.get("is_video") else "photo"
        date = str(registro.get("approved_at") or "fecha no registrada")
    else:
        body = str(registro.get("text") or "Sin texto")
        media_type = str(registro.get("type") or "")
        date = str(registro.get("date") or "fecha no registrada")
    if registro.get("file_id") and media_type in ("photo", "video"):
        caption = (
            f"📰 <b>Publicación de @{username}</b>\n"
            f"{html.escape(date)}\n\n{html.escape(body[:700])}"
        )
        try:
            enviar_media_panel_control(
                c.message.chat.id,
                media_type,
                registro["file_id"],
                caption,
                back_markup,
            )
            bot.answer_callback_query(c.id)
        except Exception:
            app.logger.exception("No se pudo mostrar una publicación archivada.")
            editar_o_enviar_panel(
                c.message.chat.id,
                "No pude cargar el archivo multimedia guardado. "
                "Puedes regresar al listado.",
                back_markup,
                protect_content=True,
                forzar_texto=True,
            )
            bot.answer_callback_query(c.id, "No pude cargar el contenido.", show_alert=True)
        return

    texto = (
        f"📰 <b>Mensaje de @{username}</b>\n"
        f"{html.escape(date)}\n\n{html.escape(body[:3000])}"
    )
    editar_o_enviar_panel(
        c.message.chat.id,
        texto,
        back_markup,
        message=c.message,
        protect_content=True,
        forzar_texto=True,
    )
    bot.answer_callback_query(c.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("mod_perdonar|"))
def cb_mod_perdonar(c):
    if not es_admin_privado(c):
        bot.answer_callback_query(c.id, "⛔ Sin permiso.")
        return
    try:
        _, key, chat_id, user_id = c.data.split("|", 3)
        chat_id, user_id = int(chat_id), int(user_id)
    except (ValueError, TypeError):
        bot.answer_callback_query(c.id, "Datos de usuario inválidos.")
        return
    destino = _destino_por_key(key)
    if not destino or str(destino.get("chat_id")) != str(chat_id):
        bot.answer_callback_query(c.id, "Destino no disponible.")
        return
    registros = [
        row for row in Blacklist.search(User.id == user_id)
        if row.get("status", "active") == "active"
        and (
            str(row.get("chat_id")) == str(chat_id)
            or (not row.get("chat_id") and str(chat_id) == str(GRUPO_ID))
        )
    ]
    if not registros:
        bot.answer_callback_query(c.id, "Ya no hay una expulsión activa.")
        return
    try:
        bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
    except TypeError:
        try:
            bot.unban_chat_member(chat_id, user_id)
        except Exception:
            app.logger.exception("No se pudo perdonar al usuario %s.", user_id)
            bot.answer_callback_query(c.id, "Telegram no permitió perdonarlo.", show_alert=True)
            return
    except Exception:
        app.logger.exception("No se pudo perdonar al usuario %s.", user_id)
        bot.answer_callback_query(c.id, "Telegram no permitió perdonarlo.", show_alert=True)
        return

    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for row in registros:
        Blacklist.update(
            {"status": "pardoned", "pardoned_at": ahora},
            doc_ids=[row.doc_id],
        )
    advertencias = [
        row for row in Warnings.search(User.id == user_id)
        if (
            str(row.get("chat_id")) == str(chat_id)
            or (not row.get("chat_id") and str(chat_id) == str(GRUPO_ID))
        )
    ]
    datos_advertencia = {
        "id": user_id,
        "chat_id": str(chat_id),
        "username": registros[-1].get("username", ""),
        "count": 2,
        "last_warn": ahora,
        "reentry_probation": True,
    }
    if advertencias:
        Warnings.update(datos_advertencia, doc_ids=[advertencias[-1].doc_id])
    else:
        Warnings.insert(datos_advertencia)
    GroupModerationLog.insert({
        "chat_id": str(chat_id),
        "user_id": user_id,
        "username": registros[-1].get("username", "") if registros else "",
        "action": "reentry_with_warnings",
        "count": 2,
        "date": ahora,
    })
    invite_url = None
    try:
        invitacion = bot.create_chat_invite_link(
            chat_id,
            name="Reingreso con advertencias",
            expire_date=int(time.time()) + 24 * 60 * 60,
            member_limit=1,
        )
        invite_url = getattr(invitacion, "invite_link", None)
    except Exception:
        app.logger.exception(
            "No se pudo crear un enlace de reingreso para el destino %s.",
            chat_id,
        )
    bot.answer_callback_query(c.id, "Acceso desbloqueado; historial de advertencias conservado.")
    markup = types.InlineKeyboardMarkup()
    if invite_url:
        try:
            markup.add(types.InlineKeyboardButton(
                "📋 Copiar invitación (1 uso · 24 h)",
                copy_text=types.CopyTextButton(text=invite_url),
            ))
        except Exception:
            pass
    markup.add(types.InlineKeyboardButton(
        "🔙 Volver a lista negra",
        callback_data=f"mod_seccion|{key}|blacklist|0",
    ))
    texto_reingreso = (
        "✅ <b>Reingreso autorizado</b>\n"
        f"ID: <code>{user_id}</code>\n"
        "Se conservaron 2/3 advertencias. El usuario debe volver a unirse."
    )
    if invite_url:
        texto_reingreso += (
            "\n\nInvitación individual, válida por 24 horas y para un uso:\n"
            f"<code>{html.escape(invite_url)}</code>"
        )
    else:
        texto_reingreso += (
            "\nNo pude generar una invitación. Comparte el enlace habitual del destino "
            "y revisa que el bot tenga permiso para invitar usuarios."
        )
    editar_o_enviar_panel(
        c.message.chat.id,
        texto_reingreso,
        markup,
        message=c.message,
        protect_content=True,
        forzar_texto=True,
    )

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
        f"✅ Añadido: {html.escape(str(title))}\n"
        f"ID: <code>{shared.chat_id}</code>\n\n"
        "Ya aparece como botón en esta lista. Tócalo para abrir sus opciones.",
        _markup_grupos_admin(),
        protect_content=True,
    )


@bot.message_handler(
    func=lambda m: (
        m.chat.type == "private"
        and str(m.from_user.id) == str(ADMIN_ID)
        and admin_estado.get(m.from_user.id, {}).get("paso")
        in (
            "esperando_media_dest_publicacion",
            "esperando_descripcion_dest_publicacion",
            "revision_publicacion_destino",
        )
    ),
    content_types=["photo", "video", "document", "audio", "animation"],
)
def recibir_media_publicacion_destino(message):
    estado = admin_estado.get(message.from_user.id, {})
    if message.photo:
        media_type, media_id = "photo", message.photo[-1].file_id
    elif message.video:
        media_type, media_id = "video", message.video.file_id
    elif message.document:
        media_type, media_id = "document", message.document.file_id
    elif message.audio:
        media_type, media_id = "audio", message.audio.file_id
    elif message.animation:
        media_type, media_id = "animation", message.animation.file_id
    else:
        return

    estado["media_type"] = media_type
    estado["media_id"] = media_id
    estado["paso"] = "esperando_descripcion_dest_publicacion"
    eliminar_mensaje_seguro(message.chat.id, message.message_id)
    mostrar_paso_publicacion_destino(
        message.chat.id,
        estado,
        "✅ Multimedia recibida.\n\n"
        "Ahora envía la descripción de la publicación "
        "(máximo 900 caracteres).",
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

def enviar_aviso_acceso_grupo(chat_id):
    me=bot.get_me()
    markup=types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton(
            "🔥 Abrir menú de acceso 🔥",
            url=f"https://t.me/{me.username}?start=payment",
        )
    )
    return editar_panel_miembro(
        chat_id,
        "Para solicitar o gestionar tu acceso a más diversión, "
        "comunícate con el indio mayor.\n\n"
        "🔥 Presiona el botón aquí 🔥",
        markup,
    )


def _grupo_reporte_seleccionado(valor=None):
    try:
        chat_id = int(valor)
    except (TypeError, ValueError):
        chat_id = int(GRUPO_ID or 0)
    if chat_id and es_grupo_autorizado(chat_id):
        return chat_id
    return int(GRUPO_ID or _default_group_id() or 0)


@bot.message_handler(commands=["start"])
def start_payment(message):
    uid=message.from_user.id; chat_id=message.chat.id
    if message.chat.type in ("group","supergroup"):
        if not es_grupo_autorizado(chat_id): return
        eliminar_mensaje_seguro(chat_id,message.message_id)
        enviar_aviso_acceso_grupo(chat_id)
        return
    if message.chat.type!="private": return
    payload=(message.text or "").split(maxsplit=1)
    if len(payload)>1 and payload[1].strip().lower().startswith("reporte"):
        partes = payload[1].strip().lower().split("_", 1)
        group_id = _grupo_reporte_seleccionado(partes[1] if len(partes) > 1 else None)
        markup=types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(
                "👤 Reportar usuario por nombre",
                callback_data=f"menu_reportar_nombre|{group_id}",
            ),
            types.InlineKeyboardButton(
                "🖼️ Reportar multimedia",
                callback_data=f"menu_reportar_multimedia|{group_id}",
            ),
        )
        editar_o_enviar_panel(
            chat_id,
            "🕵️ CENTRO DE REPORTES\n\nElige qué quieres reportar:",
            markup,
            protect_content=True,
            forzar_texto=True,
        )
        return
    mostrar_metodos_pago(chat_id)
    if str(uid)==str(ADMIN_ID): bot.send_message(chat_id,"Atajos privados de administración.",reply_markup=teclado_admin_privado(),protect_content=True)

@bot.message_handler(func=lambda m: m.chat.type=="private" and str(m.from_user.id)==str(ADMIN_ID) and bool(admin_estado.get(m.from_user.id, {}).get("paso")), content_types=["text"])
def flujo_admin_pago(message):
    if message.chat.type!="private" or str(message.from_user.id)!=str(ADMIN_ID): return
    state=admin_estado.get(message.from_user.id,{})
    paso=state.get("paso")
    if not paso: return
    text=(message.text or "").strip()
    if text.lower()=="/cancelar" or text in ("❌ Cancelar", "🔙 Volver"):
        if paso in (
            "esperando_media_dest_publicacion",
            "esperando_descripcion_dest_publicacion",
            "revision_publicacion_destino",
        ):
            admin_estado.pop(message.from_user.id, None)
            eliminar_mensaje_seguro(message.chat.id, message.message_id)
            destino = _destino_por_key(state.get("dest_key", ""))
            if destino:
                mostrar_panel_control_grupo(
                    message.chat.id,
                    state["dest_key"],
                    destino,
                    message_id=state.get("panel_message_id"),
                    aviso="Publicación cancelada; no se envió al canal.",
                )
            else:
                editar_o_enviar_panel(
                    message.chat.id,
                    "El canal ya no está guardado.",
                    _markup_grupos_admin(),
                    message_id=state.get("panel_message_id"),
                    protect_content=True,
                    forzar_texto=True,
                )
            return
        if paso == "esperando_palabra_prohibida":
            admin_estado.pop(message.from_user.id, None)
            eliminar_mensaje_seguro(message.chat.id, message.message_id)
            mostrar_palabras_prohibidas(
                message.chat.id,
                state.get("dest_key"),
                message_id=state.get("panel_message_id"),
                aviso="Edición cancelada; no se agregó ninguna palabra.",
            )
            return
        admin_estado.pop(message.from_user.id,None); eliminar_mensaje_seguro(message.chat.id,message.message_id)
        mostrar_admin_config_pagos(message.chat.id,message_id=state.get("panel_message_id"),aviso="No se guardaron cambios."); return
    if paso == "esperando_media_dest_publicacion":
        eliminar_mensaje_seguro(message.chat.id, message.message_id)
        mostrar_paso_publicacion_destino(
            message.chat.id,
            state,
            "📣 <b>Nueva publicación</b>\n\n"
            "Envía una foto, video, documento, audio o animación. "
            "Después añadirás la descripción.",
        )
        return
    if paso == "esperando_descripcion_dest_publicacion":
        if not text or len(text) > 900:
            eliminar_mensaje_seguro(message.chat.id, message.message_id)
            mostrar_paso_publicacion_destino(
                message.chat.id,
                state,
                "La descripción debe tener entre 1 y 900 caracteres. "
                "Envíala de nuevo o escribe /cancelar.",
            )
            return
        state["descripcion"] = text
        eliminar_mensaje_seguro(message.chat.id, message.message_id)
        try:
            mostrar_previa_publicacion_destino(message.chat.id, state)
        except Exception:
            app.logger.exception("No se pudo preparar la vista previa del canal.")
            mostrar_paso_publicacion_destino(
                message.chat.id,
                state,
                "No pude preparar la vista previa. Envía de nuevo la descripción "
                "o escribe /cancelar.",
            )
        return
    if paso == "revision_publicacion_destino":
        eliminar_mensaje_seguro(message.chat.id, message.message_id)
        return
    if paso == "esperando_palabra_prohibida":
        dest_key = state.get("dest_key")
        destino = _destino_por_key(dest_key or "")
        panel_message_id = state.get("panel_message_id")
        if not destino:
            admin_estado.pop(message.from_user.id, None)
            eliminar_mensaje_seguro(message.chat.id, message.message_id)
            mostrar_admin_config_pagos(message.chat.id, aviso="El destino ya no está disponible.")
            return
        try:
            agregada = agregar_palabra_prohibida(
                destino.get("chat_id"),
                " ".join(text.split()),
            )
        except ValueError as error:
            eliminar_mensaje_seguro(message.chat.id, message.message_id)
            markup = types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton(
                    "Cancelar",
                    callback_data=f"mod_palabras_cancel|{dest_key}",
                )
            )
            editar_o_enviar_panel(
                message.chat.id,
                f"{html.escape(str(error))} Envía otra entrada o pulsa Cancelar.",
                markup,
                message_id=panel_message_id,
                protect_content=True,
                forzar_texto=True,
            )
            return
        admin_estado.pop(message.from_user.id, None)
        eliminar_mensaje_seguro(message.chat.id, message.message_id)
        mostrar_palabras_prohibidas(
            message.chat.id,
            dest_key,
            message_id=panel_message_id,
            aviso=(
                "Palabra agregada."
                if agregada
                else "Esa palabra o frase ya estaba en la lista."
            ),
        )
        return
    if paso=="esperando_datos_metodo_pago":
        metodo=state.get("metodo_pago")
        if not text or len(text)>3000:
            admin_estado.pop(message.from_user.id,None)
            eliminar_mensaje_seguro(message.chat.id,message.message_id); mostrar_opciones_metodo_pago(message.chat.id,metodo,message_id=state.get("panel_message_id"),aviso="Texto vacío o demasiado largo; pulsa «Agregar otro pago» para reintentarlo."); return
        indice_reemplazo = state.get("reemplazar_indice")
        guardar_metodo_pago(metodo, text, indice_reemplazo)
        eliminar_mensaje_seguro(message.chat.id, message.message_id)
        admin_estado.pop(message.from_user.id, None)
        aviso = (
            f"Opción {indice_reemplazo + 1} actualizada."
            if isinstance(indice_reemplazo, int)
            else "Opción agregada."
        )
        mostrar_opciones_metodo_pago(
            message.chat.id,
            metodo,
            message_id=state.get("panel_message_id"),
            aviso=aviso,
        )
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
    invite = getattr(req, "invite_link", None)
    invite_url = getattr(invite, "invite_link", None)
    if invite_url:
        with FREE_GOLDPASS_LOCK:
            freepass = FreeGoldPasses.get(
                FREE_GOLDPASS_QUERY.invite_link == invite_url
            )
        if freepass:
            user_id = int(req.from_user.id)
            estado_campana = free_goldpass_config()
            duracion = int(freepass.get("duration_seconds", 0) or 0)
            if (
                int(freepass.get("id", 0)) != user_id
                or freepass.get("status") != "pending"
                or not estado_campana.get("active")
                or freepass.get("campaign_id")
                != estado_campana.get("campaign_id")
                or duracion not in FREE_GOLDPASS_DURATIONS
            ):
                try:
                    bot.decline_chat_join_request(req.chat.id, user_id)
                except Exception:
                    app.logger.exception(
                        "No se pudo rechazar una solicitud de Free Gold Pass no válida."
                    )
                return
            try:
                bot.approve_chat_join_request(req.chat.id, user_id)
                entrada = datetime.now().replace(microsecond=0)
                vence = entrada + timedelta(seconds=duracion)
                with FREE_GOLDPASS_LOCK:
                    FreeGoldPasses.update(
                        {
                            "status": "active",
                            "joined_at": entrada.strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                            "vence": vence.strftime("%Y-%m-%d %H:%M:%S"),
                        },
                        FREE_GOLDPASS_QUERY.id == user_id,
                    )
                try:
                    bot.revoke_chat_invite_link(req.chat.id, invite_url)
                except Exception:
                    app.logger.exception(
                        "No se pudo revocar el enlace personal tras el ingreso."
                    )
                try:
                    bot.send_message(
                        user_id,
                        "✅ Tu entrada a GoldPass fue aprobada. Disfruta tu pase; "
                        f"el acceso vence el <b>{vence.strftime('%d/%m/%Y %H:%M:%S')}</b>.",
                        parse_mode="HTML",
                        protect_content=True,
                    )
                except Exception:
                    app.logger.info(
                        "No se pudo enviar el aviso de aprobación del pase."
                    )
            except Exception:
                app.logger.exception(
                    "No se pudo aprobar la solicitud personal de Free Gold Pass."
                )
            return
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


def teclado_menu_miembro(chat_id=None):
    markup = types.InlineKeyboardMarkup(row_width=2)
    destino_id = chat_id if chat_id and int(chat_id) < 0 else _default_group_id()
    markup.add(
        types.InlineKeyboardButton(
            "📢 Crear publicación",
            callback_data="crear_promo",
        ),
        types.InlineKeyboardButton(
            "🚩 Reportar usuario",
            callback_data=f"menu_reportar_nombre|{destino_id}",
        ),
    )
    return markup


def editar_panel_miembro(chat_id, texto, reply_markup=None):
    if int(chat_id) > 0:
        return editar_o_enviar_panel(
            chat_id,
            texto,
            reply_markup,
            protect_content=True,
            parse_mode=None,
            forzar_texto=True,
        )

    key = str(chat_id)
    previous_id = PANELES_GRUPO_MIEMBRO.get(key)
    if previous_id:
        try:
            bot.edit_message_text(
                texto,
                chat_id,
                previous_id,
                parse_mode=None,
                reply_markup=reply_markup,
            )
            return SimpleNamespace(message_id=previous_id)
        except Exception:
            try:
                bot.delete_message(chat_id, previous_id)
            except Exception:
                pass

    panel = bot.send_message(
        chat_id,
        texto,
        parse_mode=None,
        reply_markup=reply_markup,
        protect_content=True,
    )
    PANELES_GRUPO_MIEMBRO[key] = panel.message_id
    return panel


def enviar_menu_miembro(chat_id):
    return editar_panel_miembro(
        chat_id,
        "🏹 MENÚ DE LA COMUNIDAD\n\nElige una acción:",
        teclado_menu_miembro(chat_id),
    )


@bot.message_handler(
    commands=["menu"],
    func=lambda m: m.chat.type == "private"
    or (m.chat.type in ("group", "supergroup") and es_grupo_autorizado(m.chat.id)),
)
def group_menu_command(message):
    if message.chat.type in ("group", "supergroup"):
        eliminar_mensaje_seguro(message.chat.id, message.message_id)
    enviar_menu_miembro(message.chat.id)


def _default_group_id():
    ids=_grupos_configurados()
    return ids[0] if ids else int(os.environ.get("GROUP_ID","0"))
GRUPO_ID = _default_group_id()

# --- MOTOR PRINCIPAL ---
@bot.message_handler(content_types=['text', 'photo', 'video'])
def motor_principal(message):
    global ULTIMOS_MSGS
    chat_id, uid = message.chat.id, message.from_user.id
    print(f"📨 MENSAJE RECIBIDO — tipo:{message.content_type}")
    COMANDOS = ["/menu", "/compartir", "/reglas", "/vchat", "/admin", "/start", "/reportar"]

    # --- SEGURIDAD: BLOQUEAR GRUPOS NO AUTORIZADOS ---
    if message.chat.type in ['group', 'supergroup', 'channel'] and not es_grupo_autorizado(chat_id):
        try:
            bot.leave_chat(chat_id)
        except:
            pass
        return

    # --- SEGURIDAD: BLACKLIST ---
    alcance_lista = (
        chat_id
        if message.chat.type in ("group", "supergroup", "channel")
        else None
    )
    if _usuario_en_lista_negra(uid, alcance_lista):
        return

    # --- SEGURIDAD: ANTI-FLOOD ---
    if str(uid) != str(ADMIN_ID) and uid != 1087968824 and es_flood(uid):
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

    texto_anonimo = (message.text or "").strip().lower()
    atajos_grupo_anonimos = (
        "/start",
        "🏠 /start",
        "/menu",
        "🏹 /menu",
        "/reglas",
        "📜 /reglas",
        "/compartir",
        "🚀 /compartir",
        "/vchat",
        "🔥 /vchat",
        "/admin",
        "👤 /admin",
        "/reportar",
    )
    es_atajo_grupo_anonimo = any(
        texto_anonimo == atajo
        or texto_anonimo.startswith(f"{atajo}@")
        or texto_anonimo.startswith(f"{atajo} ")
        for atajo in atajos_grupo_anonimos
    )
    if uid == 1087968824 and not es_atajo_grupo_anonimo:
        return

    uname = (message.from_user.username or "anonimo").lower()
    evidencia = guardar_evidencia(message)
    if es_grupo_autorizado(chat_id):
        registrar_actividad_stats(uid, uname)
    if moderar_palabras_prohibidas(message, evidencia=evidencia):
        return
    if not message.text:
        return
    texto = message.text.lower()

    if texto.startswith("/reportar"):
        group_id = (
            chat_id
            if message.chat.type in ("group", "supergroup") and es_grupo_autorizado(chat_id)
            else _grupo_reporte_seleccionado()
        )
        if message.chat.type == "private":
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton(
                    "👤 REPORTAR USUARIO POR NOMBRE",
                    callback_data=f"menu_reportar_nombre|{group_id}",
                ),
                types.InlineKeyboardButton(
                    "🖼️ REPORTAR MULTIMEDIA",
                    callback_data=f"menu_reportar_multimedia|{group_id}",
                ),
            )
            editar_o_enviar_panel(
                chat_id,
                "🕵️ CENTRO DE REPORTES\n\nElige qué quieres reportar:",
                markup,
                protect_content=True,
                forzar_texto=True,
            )
        else:
            eliminar_mensaje_seguro(chat_id, message.message_id)
            if ULTIMOS_MSGS['reportar']:
                eliminar_mensaje_seguro(chat_id, ULTIMOS_MSGS['reportar'])
            markup = types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton(
                    "🚩 REPORTAR AQUÍ",
                    url=f"https://t.me/{bot.get_me().username}?start=reporte_{group_id}",
                )
            )
            resp = bot.send_message(chat_id, f"👤 @{uname}, clica para denunciar.", reply_markup=markup)
            ULTIMOS_MSGS['reportar'] = resp.message_id
        return

    # --- BLOQUE DE START ---
    if texto in ["/start", "🏠 /start"] or texto.startswith("/start@") or texto.startswith("/start "):
        if message.chat.type in ("group", "supergroup") and es_grupo_autorizado(chat_id):
            eliminar_mensaje_seguro(chat_id, message.message_id)
            enviar_aviso_acceso_grupo(chat_id)
        elif message.chat.type == "private":
            mostrar_metodos_pago(chat_id)
            if str(uid) == str(ADMIN_ID):
                bot.send_message(
                    chat_id,
                    "Atajos privados de administración.",
                    reply_markup=teclado_admin_privado(),
                    protect_content=True,
                )
        return

    if texto in ("/menu", "🏹 /menu") or texto.startswith("/menu@"):
        if message.chat.type in ("group", "supergroup") and es_grupo_autorizado(chat_id):
            eliminar_mensaje_seguro(chat_id, message.message_id)
        if message.chat.type == "private" or es_grupo_autorizado(chat_id):
            enviar_menu_miembro(chat_id)
        return

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
        reglas_cfg = Config.search((User.tipo == 'reglamento') & (User.chat_id == str(chat_id)))
        saved_group = cargar_config().get("group_settings", {}).get(str(chat_id), {})
        val = (
            reglas_cfg[0].get("valor.")
            if reglas_cfg
            else saved_group.get("rules")
        ) or DEFAULT_GROUP_RULES
        if es_grupo_autorizado(chat_id):
            eliminar_mensaje_seguro(chat_id, message.message_id)
            resp = editar_panel_miembro(chat_id, val)
            ULTIMOS_MSGS['reglas'] = resp.message_id
        else:
            editar_panel_miembro(chat_id, val)

    elif "/vchat" in texto:
        if es_grupo_autorizado(chat_id):
            eliminar_mensaje_seguro(chat_id, message.message_id)
            enviar_invitacion_vchat(chat_id)
        elif message.chat.type == "private":
            eliminar_mensaje_seguro(chat_id, message.message_id)
            destino_id = _default_group_id()
            if destino_id:
                enviar_invitacion_vchat(chat_id, destino_chat_id=destino_id)
            else:
                bot.send_message(
                    chat_id,
                    "No hay un grupo configurado para mostrar la guía de videochat.",
                )

    elif "/admin" in texto:
        markup = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton(
                "👤 Abrir chat privado con el administrador",
                url=GROUP_ADMIN_CONTACT_URL,
            )
        )
        if es_grupo_autorizado(chat_id):
            eliminar_mensaje_seguro(chat_id, message.message_id)
            if ULTIMOS_MSGS['admin']:
                eliminar_mensaje_seguro(chat_id, ULTIMOS_MSGS['admin'])
            resp = editar_panel_miembro(
                chat_id,
                "Para hablar directamente con el administrador, pulsa el botón y Telegram abrirá su chat privado.",
                markup,
            )
            ULTIMOS_MSGS['admin'] = resp.message_id
        else:
            editar_panel_miembro(
                chat_id,
                "Pulsa el botón para abrir el chat privado del administrador.",
                markup,
            )


# --- MANEJO DE CALLBACKS ---
@bot.callback_query_handler(func=lambda call: True)
def manejar_clics(call):
    uid, mid = call.from_user.id, call.message.message_id
    u_name = call.from_user.first_name
    u_user = call.from_user.username or "SinUser"

    alcance_lista = (
        call.message.chat.id
        if call.message and call.message.chat.type in ("group", "supergroup", "channel")
        else None
    )
    if _usuario_en_lista_negra(uid, alcance_lista):
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
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton(
            "🔥 UNIRME AL TEMPLO DEL CACIQUE X",
            url=LINK_CANAL_GRATUITO
        ))
        try:
            editar_o_enviar_panel(
                uid,
                "🏹 **¿ESTÁS LISTO PARA UNIRTE AL TEMPLO DEL CACIQUE X?**\n\n"
                "Este canal es completamente *gratuito* y está lleno de contenido exclusivo "
                "de la comunidad más ardiente de Telegram. 🔥\n\n"
                "🔱 Si quieres disfrutar del placer y apoyar al Cacique X, "
                "pulsa el botón de abajo y sé parte de nuestra comunidad. ¡La tribu te espera! 💎⚔️",
                markup,
                protect_content=True,
                forzar_texto=True,
            )
            bot.answer_callback_query(call.id)
        except Exception:
            bot.answer_callback_query(
                call.id,
                "Abre el bot en privado y pulsa /start antes de usar este botón.",
                show_alert=True,
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
        try:
            msg = bot.send_message(uid, "📸 Envía la foto o el video de tu publicación:")
            bot.register_next_step_handler(msg, step_multimedia_promo)
            bot.answer_callback_query(call.id)
        except Exception:
            bot.answer_callback_query(
                call.id,
                "Abre el bot en privado y pulsa /start antes de crear una publicación.",
                show_alert=True,
            )

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
            mk = types.InlineKeyboardMarkup()
            for b in d['botones']:
                mk.add(types.InlineKeyboardButton(b['text'], url=b['url']))
            if d['is_video']:
                publicado = bot.send_video(
                    GRUPO_ID, d['file_id'], caption=d['desc'], reply_markup=mk
                )
            else:
                publicado = bot.send_photo(
                    GRUPO_ID, d['file_id'], caption=d['desc'], reply_markup=mk
                )
            registro_publicacion = dict(d)
            registro_publicacion.update({
                "chat_id": str(GRUPO_ID),
                "approved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "published_message_id": publicado.message_id,
            })
            PromosAprobadas.insert(registro_publicacion)
            bot.edit_message_caption("🚀 **PUBLICADO**", ADMIN_ID, mid)
            bot.send_message(target_uid, "✅ **¡APROBADO!**")
            bot.answer_callback_query(call.id)

    elif call.data.startswith("rechazar_"):
        target_uid = int(call.data.split("_")[1])
        bot.answer_callback_query(call.id, "Rechazada")
        bot.edit_message_caption("❌ **RECHAZADA**", ADMIN_ID, mid)
        bot.send_message(target_uid, "❌ **Tu publicación no fue aprobada.**")

    elif call.data.startswith("menu_reportar_nombre"):
        group_id = _grupo_reporte_seleccionado(
            call.data.split("|", 1)[1] if "|" in call.data else None
        )
        try:
            msg = bot.send_message(
                uid,
                "👤 **REPORTAR USUARIO POR NOMBRE**\n\n"
                "Escribe el @usuario del infractor que quieres denunciar:\n"
                "_(Ejemplo: @NombreDelUsuario o NombreDelUsuario)_"
            )
            bot.register_next_step_handler(msg, step_reporte_por_nombre, group_id)
            bot.answer_callback_query(call.id)
        except Exception:
            bot.answer_callback_query(
                call.id,
                "Abre el bot en privado y pulsa /start antes de reportar.",
                show_alert=True,
            )

    elif call.data.startswith("menu_reportar_multimedia"):
        group_id = _grupo_reporte_seleccionado(
            call.data.split("|", 1)[1] if "|" in call.data else None
        )
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            uid,
            "🖼️ **REPORTAR MULTIMEDIA**\n\n"
            "Escribe el @usuario del infractor cuyas publicaciones quieres revisar:\n"
            "_(Ejemplo: @NombreDelUsuario o NombreDelUsuario)_"
        )
        bot.register_next_step_handler(msg, step_reporte_multimedia_buscar, group_id)

    elif call.data.startswith("rpt_media|"):
        try:
            _, group_id, target_id, report_message_id = call.data.split("|", 3)
            group_id, target_id = int(group_id), int(target_id)
        except (ValueError, TypeError):
            bot.answer_callback_query(call.id, "El reporte no es válido.", show_alert=True)
            return
        registros = _registros_grupo(
            RegistroActividad, group_id, legacy_principal=True
        )
        evidencia = next(
            (
                row for row in registros
                if int(row.get("id", 0)) == target_id
                and str(row.get("msg_id")) == str(report_message_id)
            ),
            None,
        )
        if not evidencia:
            bot.answer_callback_query(call.id, "Ese contenido ya no está registrado.", show_alert=True)
            return
        aplicar_castigo(
            group_id,
            target_id,
            evidencia.get("uname") or "sin_usuario",
            reporter_id=uid,
            evidence=evidencia,
        )
        bot.answer_callback_query(call.id, "Reporte registrado.")

    elif call.data.startswith("rpt_media_"):
        parts = call.data.split("_", 3)
        t_id = int(parts[2])
        t_name = parts[3]
        aplicar_castigo(GRUPO_ID, t_id, t_name, reporter_id=uid)
        bot.answer_callback_query(call.id, "Reporte registrado.")


# --- PASOS DE REPORTES ---
def step_reporte_por_nombre(message, group_id=None):
    uid = message.chat.id
    target = message.text.strip().lstrip("@").lower()
    group_id = _grupo_reporte_seleccionado(group_id)
    registros = [
        registro
        for registro in _registros_grupo(
            RegistroActividad, group_id, legacy_principal=True
        )
        if str(registro.get("uname", "")).lower() == target
    ]
    if not registros:
        bot.send_message(
            uid,
            f"❌ **No encontré registros de @{target}** en el grupo.\n\n"
            "Verifica que el usuario haya participado recientemente y que el @usuario sea correcto."
        )
        return
    registro = max(registros, key=lambda item: str(item.get("date", "")))
    aplicar_castigo(
        group_id,
        registro["id"],
        target,
        reporter_id=uid,
        evidence=registro,
    )


def step_reporte_multimedia_buscar(message, group_id=None):
    uid = message.chat.id
    target = message.text.strip().lstrip("@").lower()
    group_id = _grupo_reporte_seleccionado(group_id)
    todos = [
        registro
        for registro in _registros_grupo(
            RegistroActividad, group_id, legacy_principal=True
        )
        if str(registro.get("uname", "")).lower() == target
    ]
    ultimos = sorted(todos, key=lambda item: str(item.get("date", "")), reverse=True)[:6]
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
    for r in ultimos:
        markup = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton(
                "🚩 REPORTAR ESTE CONTENIDO",
                callback_data=f"rpt_media|{group_id}|{r['id']}|{r['msg_id']}",
            )
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
    threading.Thread(
        target=revisar_vencimientos_free_goldpass,
        name="free-goldpass-expiry",
        daemon=True,
    ).start()
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
