import os
import threading
import time
import json
import hashlib
import hmac
import html
import re
import random
import uuid
import unicodedata
from types import SimpleNamespace
from urllib.parse import quote
import telebot
from telebot import apihelper
from telebot import types
from tinydb import TinyDB, Query
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from flask import Flask, jsonify, redirect, request

app = Flask(__name__)

@app.route('/')
def home():
    if os.environ.get("BOT_MODE", "webhook").strip().lower() == "polling":
        return "Telegram bot alive (polling).", 200
    return redirect("https://caciquex.netlify.app", code=302)

# --- CONFIGURACIÓN ---

TOKEN = os.environ['TELEGRAM_TOKEN']
WEBHOOK_PATH = "/telegram-webhook"
WEBHOOK_SECRET = hashlib.sha256(
    f"telegram-webhook:{TOKEN}".encode("utf-8")
).hexdigest()
WEBHOOK_ACTIVITY_LOCK = threading.Lock()
WEBHOOK_STATUS_LOCK = threading.Lock()
LAST_WEBHOOK_UPDATE_AT = None
WEBHOOK_STATUS_CACHE_TTL = 10
WEBHOOK_STATUS_CACHE = {"checked_at": 0.0, "payload": None, "http_status": 503}
CANAL_ID = '-1003914257220'      # Canal VIP (suscripciones)
CanaL_ID = '-1003561176552'
ADMIN_ID = '7827130679'
GROUP_ADMIN_CONTACT_URL = "https://t.me/Ja2610X"
# Los perfiles adicionales solo autorizan el saludo automático; no reciben acceso admin.
BUSINESS_PROFILE_OWNER_IDS = {str(ADMIN_ID)}
for _owner_id in os.environ.get("BUSINESS_PROFILE_OWNER_IDS", "").split(","):
    _owner_id = _owner_id.strip()
    if _owner_id:
        if not _owner_id.isdecimal():
            raise ValueError("BUSINESS_PROFILE_OWNER_IDS debe contener IDs numéricos separados por comas.")
        BUSINESS_PROFILE_OWNER_IDS.add(_owner_id)
BUSINESS_PROFILE_OWNER_IDS = frozenset(BUSINESS_PROFILE_OWNER_IDS)

# Link fijo del canal VIP con cobro en Stars al vencer la suscripción mensual
CANAL_INVITE_LINK = "https://t.me/+U7Kk_sC9pToxZjIx"
# Link fijo del canal VIP para pagos externos (admin aprueba manualmente).
# Genera "solicitud de ingreso" que el bot aprueba automáticamente.
CANAL_INVITE_LINK_EXTERNO = "https://t.me/+xjHnFXb_QTY0NGEx"

# Invitación del canal gratuito para respuestas de Telegram Business.
WELCOME_CHANNEL_URL = "https://t.me/+c6gutVsBfRw4YWUx"
WELCOME_X_URL = "https://x.com/joselito_a26"
WELCOME_INSTAGRAM_URL = "https://www.instagram.com/alemussett26/"
WELCOME_PHOTO_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "welcome-photo.jpg"
)
WELCOME_MESSAGE = (
    "Hola, ¿qué tal? Gracias por escribirme.\n\n"
    "Si te interesa conocer un poco más de mí, te invito a mi canal gratuito "
    "de Telegram, sin ningún compromiso. También puedes encontrarme en mis redes:"
)

SEGUNDOS_BORRAR_SOLICITUD = 60   # Borrar mensaje de solicitud al usuario

# ---------------------

bot = telebot.TeleBot(TOKEN, skip_pending=False)

_ADMIN_PRIVATE_CALLBACK_PREFIXES = (
    "admin_", "grupo_", "grp_rules|", "gmod|", "join_review|",
    "btnpreview_", "preview_", "vbotones_", "cboton_", "pubcanal_",
    "scanal_", "ebotones_", "sendto|", "rec_", "approval_verify|",
    "peap_", "perec_", "ac_", "adap_", "adrec_", "admin_no_",
)


@bot.callback_query_handler(
    func=lambda call: (
        str(getattr(getattr(call, "from_user", None), "id", ""))
        == str(ADMIN_ID)
        and getattr(getattr(call, "message", None), "chat", None) is not None
        and getattr(call.message.chat, "type", None) != "private"
        and str(getattr(call, "data", "")).startswith(_ADMIN_PRIVATE_CALLBACK_PREFIXES)
    )
)
def bloquear_callback_admin_fuera_de_privado(call):
    bot.answer_callback_query(
        call.id,
        "🔒 Por privacidad, el panel de administración solo funciona en tu chat privado con el bot.",
        show_alert=True,
    )


def _webhook_status_snapshot():
    global WEBHOOK_STATUS_CACHE
    ahora_monotonic = time.monotonic()
    with WEBHOOK_STATUS_LOCK:
        cache = WEBHOOK_STATUS_CACHE
        if cache["payload"] is not None and ahora_monotonic - cache["checked_at"] < WEBHOOK_STATUS_CACHE_TTL:
            return dict(cache["payload"]), cache["http_status"]

    with WEBHOOK_ACTIVITY_LOCK:
        ultimo_update = LAST_WEBHOOK_UPDATE_AT
    modo = os.environ.get("BOT_MODE", "webhook").strip().lower()
    base = {
        "process_alive": True,
        "telegram_api_reachable": False,
        "mode": modo if modo in {"webhook", "polling"} else "unknown",
        "webhook_configured": None,
        "pending_updates": None,
        "last_webhook_update_at": ultimo_update,
        "last_telegram_error_at": None,
    }
    try:
        info = bot.get_webhook_info()
    except Exception:
        app.logger.warning("No se pudo consultar el estado del webhook de Telegram.")
        payload, http_status = {**base, "status": "telegram_api_unreachable"}, 503
    else:
        webhook_url = str(getattr(info, "url", "") or "")
        try:
            pending = max(0, int(getattr(info, "pending_update_count", 0) or 0))
        except (TypeError, ValueError):
            pending = None
        last_error_at = None
        if getattr(info, "last_error_date", None):
            try:
                last_error_at = datetime.fromtimestamp(
                    int(info.last_error_date), tz=timezone.utc
                ).isoformat()
            except (TypeError, ValueError, OverflowError, OSError):
                pass
        configured = bool(webhook_url)
        status = (
            "polling_mode" if modo == "polling" else
            "webhook_not_configured" if not configured else
            "pending_updates" if pending else
            "telegram_reports_delivery_error" if last_error_at else
            "webhook_ready"
        )
        payload = {
            **base,
            "telegram_api_reachable": True,
            "webhook_configured": configured,
            "pending_updates": pending,
            "last_telegram_error_at": last_error_at,
            "status": status,
        }
        http_status = 200 if modo == "polling" or (
            configured and pending == 0 and last_error_at is None
        ) else 503

    with WEBHOOK_STATUS_LOCK:
        WEBHOOK_STATUS_CACHE = {
            "checked_at": time.monotonic(),
            "payload": dict(payload),
            "http_status": http_status,
        }
    return payload, http_status


@app.route("/healthz", methods=["GET"])
def healthz():
    response = jsonify({"status": "ok", "process_alive": True})
    response.headers["Cache-Control"] = "no-store"
    return response, 200


@app.route("/telegram-health", methods=["GET"])
def telegram_health():
    payload, http_status = _webhook_status_snapshot()
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store"
    return response, http_status


_SEND_MESSAGE_ORIGINAL = bot.send_message
db = TinyDB('usuarios.json')
PANELES_PRIVADOS = db.table("paneles_privados")
TECLADOS_PRIVADOS = db.table("teclados_privados")
PANEL_QUERY = Query()
PANEL_LOCK = threading.RLock()
WELCOME_SENT_DB = TinyDB(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "business_welcome_users.json")
).table("sent")
WELCOME_QUERY = Query()
WELCOME_REPLY_LOCK = threading.Lock()
BUSINESS_CONNECTION_LOCK = threading.RLock()
BUSINESS_CONNECTION_CACHE = {}
BUSINESS_CONNECTION_OWNER_CACHE = {}
BUSINESS_DIAGNOSTIC_LOCK = threading.Lock()
BUSINESS_DIAGNOSTIC_LAST_LOG = {}
RECURRING_LOCK = threading.Lock()


def _log_business_diagnostic(key, message, *args):
    """Loguea diagnósticos Business sin texto ni identificadores personales."""
    ahora = time.monotonic()
    with BUSINESS_DIAGNOSTIC_LOCK:
        ultima_vez = BUSINESS_DIAGNOSTIC_LAST_LOG.get(key)
        if ultima_vez is not None and ahora - ultima_vez < 60:
            return
        BUSINESS_DIAGNOSTIC_LAST_LOG[key] = ahora
    app.logger.info(message, *args)


@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    global LAST_WEBHOOK_UPDATE_AT

    received_secret = request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token", ""
    )
    if not hmac.compare_digest(received_secret, WEBHOOK_SECRET):
        return "Unauthorized", 403
    if not request.is_json:
        return "Expected JSON", 415

    update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
    if getattr(update, "business_connection", None):
        _log_business_diagnostic(
            "webhook_business_connection",
            "Telegram webhook recibió una actualización business_connection.",
        )
    elif getattr(update, "business_message", None):
        _log_business_diagnostic(
            "webhook_business_message",
            "Telegram webhook recibió una actualización business_message.",
        )
    bot.process_new_updates([update])
    with WEBHOOK_ACTIVITY_LOCK:
        LAST_WEBHOOK_UPDATE_AT = datetime.now(timezone.utc).isoformat()
    with WEBHOOK_STATUS_LOCK:
        WEBHOOK_STATUS_CACHE["checked_at"] = 0.0
    return "OK", 200

solicitudes_pendientes = {}
admin_estado = {}

# {user_id: {'metodo': str, 'username': str, 'notif_msg_id': int, 'datos_msg_id': int}}
solicitudes_info = {}


CONFIG_FILE   = 'config.json'
CONFIG_LOCK = threading.RLock()
PAYMENT_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "payment_config.json"
)
PAYMENT_CONFIG_LOCK = threading.RLock()

# ── Canales de publicación de botones (independientes entre sí) ──────────────
# Cada canal tiene su propio ID de destino y su propio archivo de botones,
# así una publicación en uno nunca se envía ni comparte botones con el otro.
CANALES = {
    "goldpass": {"nombre": "🏆 GoldPass CX HOTGO", "archivo": "botones_goldpass.json"},
    "freeclub": {"nombre": "🆓 FREECLUB CX HUB",   "archivo": "botones_freeclub.json"},
}
BOTONES_LOGOS_DEFAULT_RELATIVE = {
    "freeclub": os.path.join("assets", "social-links-freeclub.png"),
    "goldpass": os.path.join("assets", "social-links-goldpass.png"),
}

# ── Config persistente (IDs de canal por clave, etc.) ─────────────────────────
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

def obtener_canal_id(canal_key):
    cfg = cargar_config()
    canal_id = cfg.get('canales', {}).get(canal_key)
    if canal_id:
        return canal_id
    return cfg.get('destinos', {}).get(canal_key, {}).get('chat_id')

def guardar_canal_id(canal_key, chat_id):
    def actualizar(cfg):
        if canal_key in cfg.get('destinos', {}):
            cfg['destinos'][canal_key]['chat_id'] = str(chat_id)
        else:
            cfg.setdefault('canales', {})[canal_key] = str(chat_id)
    actualizar_config(actualizar)

def cargar_destinos_adicionales():
    for key, destino in cargar_config().get("destinos", {}).items():
        if not re.fullmatch(r"dest_[a-f0-9]{10}", str(key)):
            continue
        if (
            not isinstance(destino, dict)
            or not destino.get("nombre")
            or destino.get("archivado")
        ):
            continue
        tipo = str(destino.get("tipo", "")).strip()
        nombre = str(destino["nombre"])
        CANALES[key] = {
            "nombre": f"{nombre} ({tipo})" if tipo in ("grupo", "canal") else nombre,
            "archivo": f"botones_{key}.json",
        }

def guardar_destino_adicional(nombre, chat_id, tipo):
    chat_id = str(chat_id)
    key = None

    def actualizar(cfg):
        nonlocal key
        destinos = cfg.setdefault("destinos", {})
        for existente_key, destino in destinos.items():
            if (
                re.fullmatch(r"dest_[a-f0-9]{10}", str(existente_key))
                and isinstance(destino, dict)
                and destino.get("archivado")
                and str(destino.get("chat_id")) == chat_id
            ):
                key = existente_key
                destino.pop("archivado", None)
                destino.update({
                    "nombre": nombre,
                    "chat_id": chat_id,
                    "tipo": tipo,
                })
                return

        key = f"dest_{uuid.uuid4().hex[:10]}"
        destinos[key] = {
            "nombre": nombre,
            "chat_id": chat_id,
            "tipo": tipo,
        }

    actualizar_config(actualizar)
    CANALES[key] = {
        "nombre": f"{nombre} ({tipo})" if tipo in ("grupo", "canal") else nombre,
        "archivo": f"botones_{key}.json",
    }
    if not os.path.exists(CANALES[key]["archivo"]):
        guardar_botones_custom(key, [])
    return key


def destino_archivado(canal_key):
    cfg = cargar_config()
    destino = cfg.get("destinos", {}).get(canal_key, {})
    archivados = cfg.get("destinos_archivados", [])
    if not isinstance(archivados, list):
        archivados = []
    return bool(
        isinstance(destino, dict) and destino.get("archivado")
    ) or canal_key in archivados


def destino_protegido_por_pagos(canal_key):
    chat_id = obtener_canal_id(canal_key)
    return bool(chat_id and str(chat_id) == str(CANAL_ID))


def archivar_destino_adicional(canal_key):
    if canal_key not in CANALES or destino_protegido_por_pagos(canal_key):
        return False

    resultado = {"archivado": False}

    def archivar(cfg):
        if re.fullmatch(r"dest_[a-f0-9]{10}", str(canal_key)):
            destino = cfg.get("destinos", {}).get(canal_key)
            if not isinstance(destino, dict):
                return
            destino["archivado"] = True
        else:
            archivados = cfg.setdefault("destinos_archivados", [])
            if canal_key not in archivados:
                archivados.append(canal_key)
        recurrente = cfg.get("recurrentes", {}).get(canal_key)
        if isinstance(recurrente, dict):
            recurrente["activo"] = False
            recurrente["pausado_por_archivado"] = True
        resultado["archivado"] = True

    actualizar_config(archivar)
    if (
        resultado["archivado"]
        and re.fullmatch(r"dest_[a-f0-9]{10}", str(canal_key))
    ):
        CANALES.pop(canal_key, None)
    return resultado["archivado"]


def restaurar_destino_fijo(canal_key):
    if canal_key not in CANALES:
        return

    def restaurar(cfg):
        cfg["destinos_archivados"] = [
            key for key in cfg.get("destinos_archivados", [])
            if key != canal_key
        ]

    actualizar_config(restaurar)

def extraer_chat_id_destino(message):
    texto = (getattr(message, "text", None) or "").strip()
    if texto.lstrip("-").isdigit():
        return int(texto)
    origen_clasico = getattr(message, "forward_from_chat", None)
    if origen_clasico:
        return origen_clasico.id
    origen = getattr(message, "forward_origin", None)
    chat_origen = getattr(origen, "chat", None) if origen else None
    return getattr(chat_origen, "id", None)

def completar_destino_adicional(message, uid):
    estado = admin_estado.get(uid, {})
    if estado.get("paso") != "esperando_id_nuevo_destino":
        return False

    chat_id = extraer_chat_id_destino(message)
    if not chat_id:
        bot.send_message(
            message.chat.id,
            "No pude detectar el grupo o canal. Envía su ID numérico o reenvía un mensaje de texto enviado allí.",
        )
        return True

    tipo = "grupo/canal"
    try:
        tipo_telegram = bot.get_chat(chat_id).type
        tipo = "grupo" if tipo_telegram in ("group", "supergroup") else (
            "canal" if tipo_telegram == "channel" else tipo
        )
    except Exception:
        pass

    nombre = estado.get("nombre_destino", "Nuevo destino")
    key = guardar_destino_adicional(nombre, chat_id, tipo)
    admin_estado.pop(uid, None)
    bot.send_message(
        message.chat.id,
        f"✅ <b>{html.escape(nombre)}</b> quedó agregado como destino ({tipo}).\n"
        f"ID: <code>{chat_id}</code>\n\n"
        "El bot debe estar agregado al grupo o tener permisos de administrador en el canal.",
        parse_mode="HTML",
        reply_markup=markup_menu_botones(key),
    )
    return True

def nombre_destino_html(canal_key):
    return html.escape(CANALES[canal_key]["nombre"])

# ── Botones personalizados (uno por canal) ────────────────────────────────────
def cargar_botones_custom(canal_key):
    archivo = CANALES[canal_key]["archivo"]
    try:
        with open(archivo, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def guardar_botones_custom(canal_key, botones):
    archivo = CANALES[canal_key]["archivo"]
    with open(archivo, 'w', encoding='utf-8') as f:
        json.dump(botones, f, ensure_ascii=False, indent=2)


def obtener_media_compartida_botones(canal_key):
    guardada = cargar_config().get("botones_media_compartida", {}).get(canal_key)
    if isinstance(guardada, dict) and guardada.get("media_id") and guardada.get("media_type"):
        return {
            "media_id": guardada["media_id"],
            "media_type": guardada["media_type"],
        }
    if isinstance(guardada, dict) and guardada.get("media_path") and guardada.get("media_type"):
        ruta = os.path.join(os.path.dirname(__file__), guardada["media_path"])
        if os.path.isfile(ruta):
            return {"media_path": ruta, "media_type": guardada["media_type"]}
    ruta_default = os.path.join(
        os.path.dirname(__file__),
        BOTONES_LOGOS_DEFAULT_RELATIVE.get(canal_key, ""),
    )
    if os.path.isfile(ruta_default):
        return {"media_path": ruta_default, "media_type": "photo"}
    return {}


def guardar_media_compartida_botones(canal_key, media):
    if media.get("media_id") and media.get("media_type"):
        valor = {"media_id": media["media_id"], "media_type": media["media_type"]}
    elif media.get("media_path") and media.get("media_type"):
        valor = {
            "media_path": os.path.relpath(
                media["media_path"], os.path.dirname(__file__)
            ),
            "media_type": media["media_type"],
        }
    else:
        valor = {}

    def actualizar(cfg):
        compartidas = cfg.setdefault("botones_media_compartida", {})
        if valor:
            compartidas[canal_key] = valor
        else:
            compartidas.pop(canal_key, None)

    actualizar_config(actualizar)


def markup_seleccionar_canal(callback_prefix):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, info in CANALES.items():
        if destino_archivado(key):
            continue
        markup.add(types.InlineKeyboardButton(
            info["nombre"], callback_data=f"{callback_prefix}_{key}"
        ))
    markup.add(types.InlineKeyboardButton("🔙 Volver al panel", callback_data="admin_volver"))
    return markup


CHAT_REQUEST_GRUPO_ID = 85101
CHAT_REQUEST_CANAL_ID = 85102
CHAT_REQUEST_AGREGAR_BOT_GRUPO_ID = 85103
CHAT_REQUEST_AGREGAR_BOT_CANAL_ID = 85104
USER_REQUEST_ID = 85103
TEXTO_ATAJO_CONFIG = "⚙️ Configurar grupos/canales"
TEXTO_BUSCAR_USERNAME = "🔎 Buscar grupo o canal"
TEXTO_VOLVER_SELECTOR = "↩️ Volver a destinos"


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


def instalar_teclado_persistente(chat_id, texto, reply_markup, forzar=False):
    teclado_key = hashlib.sha256(reply_markup.to_json().encode("utf-8")).hexdigest()
    chat_privado = False
    existente = None
    try:
        chat_privado = int(chat_id) > 0
    except (TypeError, ValueError):
        pass

    if chat_privado:
        with PANEL_LOCK:
            existente = TECLADOS_PRIVADOS.get(PANEL_QUERY.chat_id == str(chat_id))
        if (
            not forzar
            and existente
            and existente.get("teclado_key") == teclado_key
        ):
            return SimpleNamespace(message_id=existente.get("message_id"))

    try:
        mensaje = _SEND_MESSAGE_ORIGINAL(
            chat_id,
            texto,
            reply_markup=reply_markup,
            disable_notification=True,
        )
    except Exception as error:
        detalle_error = " ".join(
            str(valor or "")
            for valor in (
                error,
                getattr(error, "description", None),
                getattr(error, "result_json", None),
            )
        ).upper()
        if "USER_RIGHTS_MISSING" not in detalle_error:
            raise

        app.logger.warning(
            "Telegram rechazó los botones avanzados; se probarán teclados de respaldo."
        )
        mensaje = None
        variantes = (
            (
                teclado_atajos_admin(
                    incluir_agregar_bot=False,
                    incluir_selectores=True,
                ),
                texto,
            ),
            (
                teclado_atajos_admin(
                    incluir_agregar_bot=False,
                    incluir_selectores=False,
                ),
                texto,
            ),
        )
        for teclado_respaldo, texto_respaldo in variantes:
            try:
                mensaje = _SEND_MESSAGE_ORIGINAL(
                    chat_id,
                    texto_respaldo,
                    reply_markup=teclado_respaldo,
                    disable_notification=True,
                )
                reply_markup = teclado_respaldo
                teclado_key = hashlib.sha256(
                    reply_markup.to_json().encode("utf-8")
                ).hexdigest()
                break
            except Exception as error_respaldo:
                detalle_respaldo = " ".join(
                    str(valor or "")
                    for valor in (
                        error_respaldo,
                        getattr(error_respaldo, "description", None),
                        getattr(error_respaldo, "result_json", None),
                    )
                ).upper()
                if "USER_RIGHTS_MISSING" not in detalle_respaldo:
                    raise
        if mensaje is None:
            app.logger.warning(
                "Telegram rechazó también los teclados de respaldo; se continúa sin botonera."
            )
            return None
    if chat_privado:
        with PANEL_LOCK:
            TECLADOS_PRIVADOS.upsert(
                {
                    "chat_id": str(chat_id),
                    "teclado_key": teclado_key,
                    "message_id": mensaje.message_id,
                },
                PANEL_QUERY.chat_id == str(chat_id),
            )
        mensaje_anterior_id = (existente or {}).get("message_id")
        if mensaje_anterior_id and mensaje_anterior_id != mensaje.message_id:
            try:
                bot.delete_message(chat_id, mensaje_anterior_id)
            except Exception:
                app.logger.info(
                    "No se pudo reemplazar el mensaje anterior de accesos rápidos."
                )
    return mensaje


def _mensaje_privado_unico(chat_id, texto, *args, **kwargs):
    forzar_mensaje_nuevo = kwargs.pop("_force_new_message", False)
    markup = kwargs.get("reply_markup")
    try:
        chat_privado = int(chat_id) > 0
    except (TypeError, ValueError):
        chat_privado = False

    if (
        forzar_mensaje_nuevo
        or not chat_privado
        or args
        or isinstance(
            markup,
            (types.ReplyKeyboardMarkup, types.ReplyKeyboardRemove),
        )
        or any(
            nombre in kwargs
            for nombre in ("message_thread_id", "business_connection_id")
        )
    ):
        return _SEND_MESSAGE_ORIGINAL(chat_id, texto, *args, **kwargs)

    parse_mode = kwargs.pop("parse_mode", None)
    reply_markup = kwargs.pop("reply_markup", None)
    disable_web_page_preview = kwargs.pop("disable_web_page_preview", None)
    protect_content = kwargs.pop("protect_content", False)
    kwargs.pop("disable_notification", None)
    kwargs.pop("reply_to_message_id", None)
    kwargs.pop("reply_parameters", None)
    kwargs.pop("allow_sending_without_reply", None)
    if kwargs:
        return _SEND_MESSAGE_ORIGINAL(chat_id, texto, *args, **kwargs)

    return editar_o_enviar_panel(
        chat_id,
        texto,
        reply_markup,
        protect_content=protect_content,
        parse_mode=parse_mode,
        disable_web_page_preview=disable_web_page_preview,
    )


bot.send_message = _mensaje_privado_unico


def derechos_bot_administrador(chat_is_channel):
    """Derechos mínimos para que el bot modere grupos y publique en canales."""
    return types.ChatAdministratorRights(
        is_anonymous=False,
        can_manage_chat=True,
        can_delete_messages=True,
        can_manage_video_chats=False,
        can_restrict_members=not chat_is_channel,
        can_promote_members=False,
        can_change_info=True,
        can_invite_users=True,
        can_post_messages=chat_is_channel,
        can_edit_messages=chat_is_channel,
        can_manage_topics=not chat_is_channel,
    )


def boton_pedir_bot_como_admin(texto, request_id, chat_is_channel):
    return types.KeyboardButton(
        texto,
        request_chat=types.KeyboardButtonRequestChat(
            request_id=request_id,
            chat_is_channel=chat_is_channel,
            bot_administrator_rights=derechos_bot_administrador(chat_is_channel),
            request_title=True,
            request_username=True,
        ),
    )


def teclado_atajos_admin(incluir_agregar_bot=False, incluir_selectores=True):
    teclado = types.ReplyKeyboardMarkup(
        row_width=2,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Elige una acción",
    )
    teclado.row(
        types.KeyboardButton("/start"),
        types.KeyboardButton("/admin"),
    )
    teclado.add(types.KeyboardButton(TEXTO_ATAJO_CONFIG))
    if incluir_selectores:
        teclado.row(
            types.KeyboardButton(
                "👥 Buscar grupo",
                request_chat=types.KeyboardButtonRequestChat(
                    request_id=CHAT_REQUEST_GRUPO_ID,
                    chat_is_channel=False,
                    request_title=True,
                    request_username=True,
                ),
            ),
            types.KeyboardButton(
                "📢 Buscar canal",
                request_chat=types.KeyboardButtonRequestChat(
                    request_id=CHAT_REQUEST_CANAL_ID,
                    chat_is_channel=True,
                    request_title=True,
                    request_username=True,
                ),
            ),
        )
    if incluir_agregar_bot:
        teclado.row(
            boton_pedir_bot_como_admin(
                "➕ Añadir bot · grupo",
                CHAT_REQUEST_AGREGAR_BOT_GRUPO_ID,
                False,
            ),
            boton_pedir_bot_como_admin(
                "➕ Añadir bot · canal",
                CHAT_REQUEST_AGREGAR_BOT_CANAL_ID,
                True,
            ),
        )
    if incluir_selectores:
        teclado.row(
            types.KeyboardButton(
                "👤 Consultar usuario",
                request_users=types.KeyboardButtonRequestUsers(
                    request_id=USER_REQUEST_ID,
                    user_is_bot=False,
                    max_quantity=1,
                    request_name=True,
                    request_username=True,
                ),
            ),
            types.KeyboardButton(TEXTO_VOLVER_SELECTOR),
        )
    else:
        teclado.add(types.KeyboardButton(TEXTO_VOLVER_SELECTOR))
    teclado.add(types.KeyboardButton("❌ Cancelar"))
    return teclado


def teclado_selector_grupos():
    teclado = types.ReplyKeyboardMarkup(
        row_width=2,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Buscar grupo o canal",
    )
    teclado.add(
        types.KeyboardButton(
            "👥 Buscar grupo",
            request_chat=types.KeyboardButtonRequestChat(
                request_id=CHAT_REQUEST_GRUPO_ID,
                chat_is_channel=False,
                request_title=True,
                request_username=True,
            ),
        ),
        types.KeyboardButton(
            "📢 Buscar canal",
            request_chat=types.KeyboardButtonRequestChat(
                request_id=CHAT_REQUEST_CANAL_ID,
                chat_is_channel=True,
                request_title=True,
                request_username=True,
            ),
        ),
    )
    teclado.row(
        boton_pedir_bot_como_admin(
            "➕ Añadir bot · grupo",
            CHAT_REQUEST_AGREGAR_BOT_GRUPO_ID,
            False,
        ),
        boton_pedir_bot_como_admin(
            "➕ Añadir bot · canal",
            CHAT_REQUEST_AGREGAR_BOT_CANAL_ID,
            True,
        ),
    )
    teclado.add(
        types.KeyboardButton(
            "👤 Consultar usuario",
            request_users=types.KeyboardButtonRequestUsers(
                request_id=USER_REQUEST_ID,
                user_is_bot=False,
                max_quantity=1,
                request_name=True,
                request_username=True,
            ),
        ),
    )
    teclado.add(types.KeyboardButton("❌ Cancelar"))
    return teclado


def teclado_picker_tipo_chat():
    teclado = types.ReplyKeyboardMarkup(
        row_width=2,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Elige grupo o canal",
    )
    teclado.row(
        types.KeyboardButton(
            "👥 Buscar grupo",
            request_chat=types.KeyboardButtonRequestChat(
                request_id=CHAT_REQUEST_GRUPO_ID,
                chat_is_channel=False,
                request_title=True,
                request_username=True,
            ),
        ),
        types.KeyboardButton(
            "📢 Buscar canal",
            request_chat=types.KeyboardButtonRequestChat(
                request_id=CHAT_REQUEST_CANAL_ID,
                chat_is_channel=True,
                request_title=True,
                request_username=True,
            ),
        ),
    )
    teclado.row(
        boton_pedir_bot_como_admin(
            "➕ Añadir bot · grupo",
            CHAT_REQUEST_AGREGAR_BOT_GRUPO_ID,
            False,
        ),
        boton_pedir_bot_como_admin(
            "➕ Añadir bot · canal",
            CHAT_REQUEST_AGREGAR_BOT_CANAL_ID,
            True,
        ),
    )
    teclado.add(types.KeyboardButton(TEXTO_VOLVER_SELECTOR))
    return teclado


def teclado_selector_canales():
    teclado = types.ReplyKeyboardMarkup(
        row_width=1,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Selecciona un canal",
    )
    teclado.add(
        types.KeyboardButton(
            "📢 Seleccionar canal",
            request_chat=types.KeyboardButtonRequestChat(
                request_id=CHAT_REQUEST_CANAL_ID,
                chat_is_channel=True,
                request_title=True,
                request_username=True,
            ),
        ),
        types.KeyboardButton("❌ Cancelar"),
    )
    return teclado


def iniciar_selector_grupo(chat_id, user_id):
    estado_anterior = admin_estado.get(user_id, {})
    estado = {
        "paso": "esperando_chat_compartido",
        "toolbar_message_id": estado_anterior.get("toolbar_message_id"),
        "selector_message_id": estado_anterior.get("selector_message_id"),
    }
    admin_estado[user_id] = estado
    selector = mostrar_selector_destinos(
        chat_id,
        message_id=estado.get("selector_message_id"),
    )
    estado = admin_estado.setdefault(user_id, estado)
    if getattr(selector, "message_id", None):
        estado["selector_message_id"] = selector.message_id
    reemplazar_teclado_selector(
        chat_id,
        user_id,
        teclado_selector_grupos(),
        "Usa los botones inferiores para buscar un grupo o canal, o consultar un usuario.",
    )


def reemplazar_teclado_selector(chat_id, user_id, reply_markup, texto):
    estado = admin_estado.setdefault(user_id, {})
    mensaje = instalar_teclado_persistente(
        chat_id,
        texto,
        teclado_atajos_admin(),
        forzar=True,
    )
    estado["toolbar_message_id"] = getattr(mensaje, "message_id", None)
    return mensaje


def markup_destinos_guardados():
    markup = types.InlineKeyboardMarkup(row_width=1)
    guardados = [
        (key, info, obtener_canal_id(key))
        for key, info in CANALES.items()
        if obtener_canal_id(key) and not destino_archivado(key)
    ]
    for key, info, chat_id in guardados:
        ajustes = obtener_ajustes_grupo(key) or {}
        tipo = ajustes.get("type", "grupo/canal")
        titulo = ajustes.get("title") or info.get("nombre", "Destino")
        markup.add(types.InlineKeyboardButton(
            f"📂 {str(titulo)[:48]} · {tipo}",
            callback_data=f"grupo_destino|{key}",
        ))
    if not guardados:
        markup.add(types.InlineKeyboardButton(
            "Todavía no hay grupos o canales guardados",
            callback_data="grupo_selector",
        ))
    return markup


def mostrar_resultado_busqueda_publica(chat_id, user_id, username, message_id):
    try:
        chat = bot.get_chat(username)
    except Exception:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "↩️ Volver a destinos guardados", callback_data="grupo_selector"
        ))
        texto = (
            f"No pude resolver <code>{html.escape(username)}</code>. "
            "Comprueba el @usuario. Telegram permite resolver grupos/canales públicos, "
            "pero no buscar a una persona solo por su @nombre; usa «Consultar usuario»."
        )
        editar_o_enviar_panel(chat_id, texto, markup, message_id=message_id)
        return False

    if chat.type not in ("group", "supergroup", "channel"):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "↩️ Volver a destinos guardados", callback_data="grupo_selector"
        ))
        editar_o_enviar_panel(
            chat_id,
            "Telegram no devolvió un grupo o canal público. Para una persona, usa "
            "«Consultar usuario»; los bots no pueden buscar usuarios por @nombre.",
            markup,
            message_id=message_id,
        )
        return False

    tipo = "canal" if chat.type == "channel" else "grupo"
    titulo = chat.title or getattr(chat, "username", None) or username
    admin_estado[user_id] = {
        "paso": "lookup_result",
        "selector_message_id": message_id,
        "toolbar_message_id": admin_estado.get(user_id, {}).get("toolbar_message_id"),
        "public_lookup": {
            "chat_id": str(chat.id),
            "title": titulo,
            "type": tipo,
            "username": getattr(chat, "username", None),
        },
    }
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(
            "📋 Copiar ID",
            copy_text=types.CopyTextButton(text=str(chat.id)),
        ),
        types.InlineKeyboardButton(
            "📌 Guardar destino",
            callback_data="grupo_lookup_add",
        ),
        types.InlineKeyboardButton(
            "↩️ Volver a destinos guardados",
            callback_data="grupo_selector",
        ),
    )
    nombre_usuario = getattr(chat, "username", None)
    texto = (
        f"🔎 <b>{html.escape(str(titulo))}</b>\n"
        f"Tipo: <b>{html.escape(tipo)}</b>\n"
        f"Usuario: <b>{'@' + html.escape(nombre_usuario) if nombre_usuario else 'Sin @usuario público'}</b>\n"
        f"ID: <code>{html.escape(str(chat.id))}</code>\n\n"
        "Este chat todavía no se guardó en la lista del bot. "
        "Guardar el destino no añade el bot al grupo/canal; usa el botón inferior "
        "«Añadir bot» para solicitar su ingreso como administrador."
    )
    editar_o_enviar_panel(chat_id, texto, markup, message_id=message_id)
    return True


def mostrar_selector_destinos(chat_id_admin, message=None, message_id=None):
    guardados = [
        (key, info, obtener_canal_id(key))
        for key, info in CANALES.items()
        if obtener_canal_id(key) and not destino_archivado(key)
    ]
    lineas = "\n".join(
        f"• {html.escape((obtener_ajustes_grupo(key) or {}).get('title') or info['nombre'])} "
        f"— <code>{html.escape(str(chat_id))}</code>"
        for key, info, chat_id in guardados
    ) or "No hay destinos guardados todavía."
    texto = (
        "⚙️ <b>Configuración de grupos y canales</b>\n\n"
        "<b>Guardados:</b>\n" + lineas + "\n\n"
        "Pulsa uno para configurarlo o usa «Buscar grupo» o «Buscar canal» "
        "en la barra inferior para agregar otro. También puedes consultar un usuario."
    )
    markup = markup_destinos_guardados()
    if message is None:
        if message_id:
            return editar_o_enviar_panel(
                chat_id_admin,
                texto,
                markup,
                message_id=message_id,
                forzar_texto=True,
            )
        return editar_o_enviar_panel(
            chat_id_admin,
            texto,
            parse_mode="HTML",
            reply_markup=markup,
            disable_web_page_preview=True,
            forzar_texto=True,
        )
    return editar_o_enviar_panel(
        chat_id_admin,
        texto,
        markup,
        message=message,
        forzar_texto=True,
    )


def buscar_destino_por_chat_id(chat_id):
    for canal_key in CANALES:
        if str(obtener_canal_id(canal_key)) == str(chat_id):
            return canal_key
    return None


def obtener_o_crear_destino_compartido(chat_id, title, tipo):
    canal_key = buscar_destino_por_chat_id(chat_id)
    if canal_key:
        if not re.fullmatch(r"dest_[a-f0-9]{10}", str(canal_key)):
            restaurar_destino_fijo(canal_key)
        return canal_key
    return guardar_destino_adicional(
        title or "Grupo o canal", chat_id, tipo
    )


GROUP_CONFIG_CATEGORIES = [
    ("reglamento", "📜 Reglamento"),
    ("atajos", "⌨️ Botones rápidos del grupo"),
]
GROUP_CONFIG_PAGE_SIZE = 2
GROUP_FEATURE_TITLES = dict(GROUP_CONFIG_CATEGORIES)
GROUP_FEATURE_TITLES_EN = {
    "reglamento": "📜 Rules",
    "atajos": "⌨️ Group shortcuts",
}
GROUP_FEATURE_DESCRIPTIONS_EN = {
    "reglamento": "Save the rules and show them in the group with /rules.",
    "atajos": "Choose and publish the member toolbar: /start, /menu, /reglas, /compartir, /admin, and /vchat.",
}
GROUP_FEATURE_TEXT_PROMPTS = {
    "reglamento": ("Reglamento", "Escribe el reglamento que quieres mostrar con /rules."),
}
GROUP_FEATURE_TEXT_PROMPTS_EN = {
    "reglamento": ("Rules", "Write the rules that /rules will show."),
}
GROUP_MEMBER_SHORTCUTS = (
    ("start", "🏠 /start", "__group_start__"),
    ("menu", "🏹 /menu", "__group_menu__"),
    ("rules", "📜 /reglas", "/rules"),
    ("share", "🚀 /compartir", "__group_share__"),
    ("admin", "👤 /admin", "__group_admin__"),
    ("vchat", "🔥 /vchat", "__videochat_guide__"),
)
GROUP_MODERATION_ACTIONS = (
    ("❌ Off", "off"),
    ("⚠️ Warn", "warn"),
    ("❗ Kick", "kick"),
    ("🔇 Silenciar", "mute"),
    ("🚫 Ban", "ban"),
)
GROUP_MODERATION_SOURCES = (
    ("channel", "📢 Canales"),
    ("group", "👥 Grupos"),
    ("user", "👤 Usuarios"),
    ("bot", "🤖 Bots"),
)
GROUP_MODERATION_SOURCE_LABELS = dict(GROUP_MODERATION_SOURCES)
GROUP_MODERATION_POLICY_LABELS = {
    "telegram_links": "🔗 Enlaces de Telegram",
    "internet_links": "🌐 Enlaces de internet",
    "forward_channel": "📢 Reenvíos de canales",
    "forward_group": "👥 Reenvíos de grupos",
    "forward_user": "👤 Reenvíos de usuarios",
    "forward_bot": "🤖 Reenvíos de bots",
    "quote_channel": "📢 Citas de canales",
    "quote_group": "👥 Citas de grupos",
    "quote_user": "👤 Citas de usuarios",
    "quote_bot": "🤖 Citas de bots",
}
GROUP_MEDIA_PAGES = (
    (("story", "📱 Historias"), ("photo", "🖼️ Fotos"), ("video", "🎥 Vídeos")),
    (("album", "🗂️ Álbumes"), ("live_photo", "📸 Live Photo"), ("animation", "🎞️ GIF")),
    (("sticker", "🎟️ Stickers"), ("animated_sticker", "✨ Stickers animados"), ("document", "📎 Archivos")),
)


def _nuevos_ajustes_grupo(chat_id, title, tipo):
    return {
        "chat_id": str(chat_id),
        "title": title or "Grupo o canal",
        "type": tipo or "grupo/canal",
        "enabled": {},
        "moderation_policies": {},
        "media_policies": {},
        "flood_limit": 5,
        "flood_window_seconds": 3,
        "flood_action": "off",
        "flood_delete_messages": False,
        "welcome_mode": "always",
        "welcome_send_private": False,
        "welcome_delete_previous": False,
        "welcome_seen_users": [],
        "goodbye_send_private": False,
        "goodbye_delete_previous": False,
        "captcha_mode": "button",
        "captcha_timeout_seconds": 90,
        "captcha_action": "ban",
        "captcha_delete_service_message": False,
        "captcha_theme": "classic",
        "night_mode_action": "delete",
        "night_mode_mute": False,
        "warning_limit": 3,
        "warning_action": "mute",
        "warning_duration_seconds": 3600,
        "rules": "",
        "rules_media_before": None,
        "rules_media_after": None,
        "rules_keyboard": [],
        "rules_access": "all",
        "captcha_text": "",
        "welcome_text": "¡Bienvenido/a, {name}!",
        "goodbye_text": "👋 {name} salió del grupo.",
        "blocked_words": [],
        "blocked_user_ids": [],
        "masked_exceptions": [],
        "filters": {},
        "custom_commands": {},
        "quick_buttons": [],
        "quick_commands_enabled": {},
        "videochat_button_label": "🔥 /vchat",
        "max_length": 0,
        "warnings": {},
    }


def obtener_ajustes_grupo(canal_key):
    chat_id = obtener_canal_id(canal_key)
    if not chat_id:
        return None
    cfg = cargar_config()
    destino = cfg.get("destinos", {}).get(canal_key, {})
    defaults = _nuevos_ajustes_grupo(
        chat_id,
        destino.get("nombre", CANALES.get(canal_key, {}).get("nombre", "Grupo")),
        destino.get("tipo", "grupo/canal"),
    )
    existente = cfg.get("group_settings", {}).get(str(chat_id))
    if not isinstance(existente, dict):
        existente = defaults
        cambio = True
    else:
        cambio = False
        for key, value in defaults.items():
            if key not in existente:
                existente[key] = value
                cambio = True
        existente["chat_id"] = str(chat_id)
        if destino.get("nombre") and existente.get("title") != destino["nombre"]:
            existente["title"] = destino["nombre"]
            cambio = True
        if destino.get("tipo") and existente.get("type") != destino["tipo"]:
            existente["type"] = destino["tipo"]
            cambio = True
    if cambio:
        def guardar(config):
            config.setdefault("group_settings", {})[str(chat_id)] = existente
        actualizar_config(guardar)
    return existente


def actualizar_ajustes_grupo(canal_key, actualizar):
    chat_id = obtener_canal_id(canal_key)
    if not chat_id:
        return None

    def modificar(config):
        destino = config.get("destinos", {}).get(canal_key, {})
        ajustes = config.setdefault("group_settings", {}).setdefault(
            str(chat_id),
            _nuevos_ajustes_grupo(
                chat_id,
                destino.get("nombre", CANALES.get(canal_key, {}).get("nombre", "Grupo")),
                destino.get("tipo", "grupo/canal"),
            ),
        )
        actualizar(ajustes)
    actualizar_config(modificar)
    return obtener_ajustes_grupo(canal_key)


def etiqueta_boton_videochat(ajustes):
    etiqueta = str((ajustes or {}).get("videochat_button_label") or "").strip()
    return (etiqueta or "🔥 /vchat")[:32]


def atajos_fijos_grupo(ajustes):
    ajustes = ajustes or {}
    if str(ajustes.get("type", "")).lower() == "canal":
        return []
    enabled = ajustes.get("quick_commands_enabled", {})
    result = []
    for key, label, action in GROUP_MEMBER_SHORTCUTS:
        if enabled.get(key, True):
            if key == "vchat":
                label = etiqueta_boton_videochat(ajustes)
            result.append({"key": key, "label": label, "action": action})
    return result


def es_atajo_admin(item):
    label = str((item or {}).get("label", "")).strip().casefold()
    action = str((item or {}).get("action", "")).strip()
    comando = action.split(maxsplit=1)[0].split("@", 1)[0].casefold() if action else ""
    return label in ("/admin", "admin") or comando == "/admin"


def enlace_bot_privado():
    try:
        username = getattr(bot.get_me(), "username", None)
    except Exception:
        username = None
    return f"https://t.me/{username}?start=from_group" if username else None


def enlace_invitacion_grupo(chat_id, ajustes):
    invite = str((ajustes or {}).get("group_link") or "").strip()
    if (ajustes or {}).get("group_link_enabled") and re.fullmatch(
        r"https?://[^\s<>\"']+", invite, re.IGNORECASE
    ):
        return invite
    try:
        chat = bot.get_chat(chat_id)
        username = getattr(chat, "username", None)
        if username:
            return f"https://t.me/{username}"
        invite = str(getattr(chat, "invite_link", "") or "").strip()
        if re.fullmatch(r"https?://[^\s<>\"']+", invite, re.IGNORECASE):
            return invite
    except Exception:
        app.logger.info("No se pudo obtener un enlace para compartir el grupo.")
    return None


def enlace_videochat_grupo(chat_id):
    try:
        chat = bot.get_chat(chat_id)
    except Exception:
        app.logger.info("No se pudo consultar el grupo para abrir su videochat.")
        return None
    username = getattr(chat, "username", None)
    return f"https://t.me/{username}?videochat" if username else None


def funcion_grupo_activada(canal_key, ajustes, feature):
    if feature == "reglamento":
        return bool(str((ajustes or {}).get("rules", "")).strip())
    if feature == "atajos":
        return bool(atajos_fijos_grupo(ajustes) or (ajustes or {}).get("quick_buttons"))
    return False


def _politica_ajuste(ajustes, policy_id):
    if policy_id == "flood":
        legacy = bool((ajustes or {}).get("enabled", {}).get("antiflood"))
        return {
            "action": (ajustes or {}).get("flood_action", "delete" if legacy else "off"),
            "delete_messages": bool((ajustes or {}).get("flood_delete_messages", legacy)),
            "exceptions": [],
            "username_spam": False,
            "bot_spam": False,
        }
    policies = (ajustes or {}).get("moderation_policies", {})
    policy = policies.get(policy_id, {}) if isinstance(policies, dict) else {}
    return {
        "action": str(policy.get("action", "off")),
        "delete_messages": bool(policy.get("delete_messages", False)),
        "exceptions": list(policy.get("exceptions", [])),
        "username_spam": bool(policy.get("username_spam", False)),
        "bot_spam": bool(policy.get("bot_spam", False)),
    }


def _texto_accion_moderacion(action):
    return {
        "off": "Off", "warn": "Warn", "kick": "Kick", "mute": "Silenciar",
        "ban": "Ban", "delete": "Eliminar",
    }.get(str(action), "Off")


def _estado_politica(ajustes, policy_id):
    policy = _politica_ajuste(ajustes, policy_id)
    return (
        f"Castigo: {_texto_accion_moderacion(policy['action'])}\n"
        f"Eliminación: {'Sí ✅' if policy['delete_messages'] else 'No ❌'}"
    )


def mostrar_configuracion_grupo(
    chat_id_admin, canal_key, pagina=0, message=None, message_id=None, aviso=None
):
    if canal_key not in CANALES:
        return editar_o_enviar_panel(
            chat_id_admin, "No encontré ese grupo o canal.",
            message=message, message_id=message_id,
        )
    ajustes = obtener_ajustes_grupo(canal_key)
    if not ajustes:
        return editar_o_enviar_panel(
            chat_id_admin, "Este destino todavía no tiene un ID guardado.",
            message=message, message_id=message_id,
        )
    pagina = max(0, int(pagina or 0))
    markup = types.InlineKeyboardMarkup(row_width=2)
    botones = []
    for feature, label in GROUP_CONFIG_CATEGORIES:
        estado = "🟢" if funcion_grupo_activada(canal_key, ajustes, feature) else "⚪"
        botones.append(types.InlineKeyboardButton(
            f"{estado} {label}",
            callback_data=f"grupo_feature|{canal_key}|{feature}|{pagina}",
        ))
    markup.row(*botones)
    markup.add(types.InlineKeyboardButton(
        "↩️ Volver",
        callback_data=f"grupo_ficha|{canal_key}",
    ))
    texto = (
        f"⚙️ <b>Configuración de {html.escape(str(ajustes.get('type', 'grupo/canal')))}</b>\n"
        f"<b>{html.escape(str(ajustes.get('title', CANALES[canal_key]['nombre'])))}</b>\n"
        f"ID: <code>{html.escape(str(ajustes['chat_id']))}</code>\n\n"
        "Elige qué quieres configurar. Los cambios se guardan solo para este destino."
    )
    if aviso:
        texto = f"✅ {html.escape(aviso)}\n\n{texto}"
    return editar_o_enviar_panel(
        chat_id_admin, texto, markup, message=message, message_id=message_id,
        forzar_texto=True,
    )


RULES_HELP_HTML = (
    "📚 <b>Todo lo que puedes hacer con las reglas</b>\n\n"
    "────────────\n"
    "🔘 <b>BOTONES</b>\n"
    "Las reglas pueden mostrarse mediante botones personalizados para facilitar su acceso a los miembros del grupo, "
    "utilizando la siguiente sintaxis al crear el botón:\n\n"
    "<code>Nombre del botón - rules</code>\n\n"
    "Al pulsarlo, el usuario verá automáticamente el reglamento configurado para el grupo.\n"
    "────────────\n"
    "🧠 <b>CAPTCHA</b>\n"
    "Puedes utilizar el tag:\n\n"
    "<code>{RULES}</code>\n\n"
    "Al hacerlo, el bot reemplazará automáticamente el tag por el texto completo de las reglas configuradas.\n\n"
    "Esta función resulta especialmente útil para mostrar las normas durante el proceso de verificación de nuevos usuarios.\n"
    "────────────\n"
    "🔎 <b>ARGUMENTOS</b>\n"
    "Los argumentos permiten mostrar únicamente una parte específica del reglamento.\n\n"
    "Puedes utilizar números, palabras o emojis para acceder directamente a una regla determinada.\n\n"
    "Ejemplo: <code>/rules 1</code>\n"
    "                <code>/rules spam</code>\n"
    "                <code>/rules 🚫</code>\n\n"
    "El bot mostrará únicamente la línea o párrafo relacionado con el argumento indicado.\n"
    "────────────\n"
    "📝 <b>CONTENIDO DEL MENSAJE</b>\n"
    "Desde el botón ✍🏼 Personalizar mensaje puedes configurar cómo se mostrará el reglamento a los usuarios.\n\n"
    "Elementos disponibles:\n\n"
    "📄 <b>Texto</b>\n"
    "Contenido del reglamento.\n\n"
    "🖼️ <b>Multimedia</b>\n"
    "Imágenes o banners que pueden mostrarse encima o debajo del reglamento.\n\n"
    "🔠 <b>Teclado</b>\n"
    "Botones personalizados para enlaces, comandos o secciones relacionadas."
)


def mostrar_menu_reglamento(
    chat_id_admin, canal_key, pagina=0, message=None, message_id=None,
    mostrar_ayuda=False, aviso=None,
):
    ajustes = obtener_ajustes_grupo(canal_key) or {}
    acceso = ajustes.get("rules_access", "all")
    texto = (
        f"📜 <b>Reglamento — {html.escape(str(ajustes.get('title') or 'Grupo'))}</b>\n\n"
        "En esta sección puedes crear y gestionar las normas del grupo.\n\n"
        "Los miembros podrán consultar el reglamento con <code>/rules</code>, "
        "un botón personalizado o durante el CAPTCHA.\n\n"
        f"Acceso al comando: <b>{'Solo administradores' if acceso == 'admins' else 'Todos los miembros'}</b>."
    )
    if mostrar_ayuda:
        texto += "\n\n" + RULES_HELP_HTML
    if aviso:
        texto = f"✅ {html.escape(aviso)}\n\n{texto}"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(
        "📚 Todo lo que puedes hacer con las reglas" if not mostrar_ayuda else "🔽 Ocultar detalles",
        callback_data=f"grp_rules|help|{canal_key}|{pagina}|{0 if mostrar_ayuda else 1}",
    ))
    markup.add(types.InlineKeyboardButton(
        "✍🏼 Personalizar mensaje",
        callback_data=f"grp_rules|editor|{canal_key}|{pagina}",
    ))
    markup.add(types.InlineKeyboardButton(
        "📍 Permisos de comandos",
        callback_data=f"grp_rules|permisos|{canal_key}|{pagina}|{int(mostrar_ayuda)}",
    ))
    markup.add(types.InlineKeyboardButton(
        "↩️ Volver",
        callback_data=f"grupo_config|{canal_key}|{pagina}",
    ))
    return editar_o_enviar_panel(
        chat_id_admin, texto, markup, message=message, message_id=message_id,
        forzar_texto=True,
    )


def mostrar_editor_reglamento(
    chat_id_admin, canal_key, pagina=0, message=None, message_id=None, aviso=None
):
    ajustes = obtener_ajustes_grupo(canal_key) or {}
    reglas = str(ajustes.get("rules", "")).strip()
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton(
        "✏️ Editar texto",
        callback_data=f"grp_rules|edit|{canal_key}|{pagina}",
    ))
    markup.row(
        types.InlineKeyboardButton(
            "🖼️ Multimedia encima",
            callback_data=f"grp_rules|media|{canal_key}|{pagina}|before",
        ),
        types.InlineKeyboardButton(
            "🖼️ Multimedia debajo",
            callback_data=f"grp_rules|media|{canal_key}|{pagina}|after",
        ),
    )
    for posicion in ("before", "after"):
        if ajustes.get(f"rules_media_{posicion}"):
            markup.add(types.InlineKeyboardButton(
                f"🗑️ Quitar multimedia {'encima' if posicion == 'before' else 'debajo'}",
                callback_data=f"grp_rules|media_clear|{canal_key}|{pagina}|{posicion}",
            ))
    markup.add(types.InlineKeyboardButton(
        "🔠 Configurar teclado",
        callback_data=f"grp_rules|keyboard|{canal_key}|{pagina}",
    ))
    if ajustes.get("rules_keyboard"):
        markup.add(types.InlineKeyboardButton(
            "🗑️ Quitar todos los botones",
            callback_data=f"grp_rules|keyboard_clear|{canal_key}|{pagina}",
        ))
    markup.add(types.InlineKeyboardButton(
        "↩️ Volver a Reglamento",
        callback_data=f"grp_rules|home|{canal_key}|{pagina}|0",
    ))
    texto = (
        f"✍🏼 <b>Personalizar mensaje — {html.escape(str(ajustes.get('title') or 'Grupo'))}</b>\n\n"
        f"<b>Texto actual:</b>\n{html.escape(reglas[:1000]) if reglas else '<i>Sin texto configurado.</i>'}\n\n"
        f"Multimedia encima: {'configurada' if ajustes.get('rules_media_before') else 'no configurada'}\n"
        f"Multimedia debajo: {'configurada' if ajustes.get('rules_media_after') else 'no configurada'}\n"
        f"Botones configurados: {len(ajustes.get('rules_keyboard', []))}"
    )
    if aviso:
        texto = f"✅ {html.escape(aviso)}\n\n{texto}"
    return editar_o_enviar_panel(
        chat_id_admin, texto, markup, message=message, message_id=message_id,
        forzar_texto=True,
    )


def mostrar_teclado_reglamento(
    chat_id_admin, canal_key, pagina=0, message=None, message_id=None, aviso=None
):
    ajustes = obtener_ajustes_grupo(canal_key) or {}
    botones = ajustes.get("rules_keyboard", [])
    lineas = "\n".join(
        f"• <b>{html.escape(str(item.get('label', 'Botón')))}</b> → "
        f"<code>{html.escape(str(item.get('action', '')))}</code>"
        for item in botones[:20]
    ) or "Todavía no hay botones personalizados."
    texto = (
        f"🔠 <b>Teclado del Reglamento — {html.escape(str(ajustes.get('title') or 'Grupo'))}</b>\n\n"
        f"{lineas}\n\nAgrega una línea con <code>etiqueta=acción</code> o "
        "<code>Nombre del botón - rules</code>."
    )
    if aviso:
        texto = f"✅ {html.escape(aviso)}\n\n{texto}"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(
        "➕ Agregar botón",
        callback_data=f"grp_rules|keyboard_add|{canal_key}|{pagina}",
    ))
    for index, item in enumerate(botones[:20]):
        markup.add(types.InlineKeyboardButton(
            f"🗑️ Quitar: {str(item.get('label', 'Botón'))[:48]}",
            callback_data=f"grp_rules|keyboard_del|{canal_key}|{pagina}|{index}",
        ))
    markup.add(types.InlineKeyboardButton(
        "↩️ Volver a personalizar mensaje",
        callback_data=f"grp_rules|editor|{canal_key}|{pagina}",
    ))
    return editar_o_enviar_panel(
        chat_id_admin, texto, markup, message=message, message_id=message_id,
        forzar_texto=True,
    )


def mostrar_permisos_reglamento(
    chat_id_admin, canal_key, pagina=0, message=None, message_id=None,
    mostrar_ayuda=False, aviso=None,
):
    ajustes = obtener_ajustes_grupo(canal_key) or {}
    acceso = ajustes.get("rules_access", "all")
    texto = (
        f"📍 <b>Permisos de comandos — {html.escape(str(ajustes.get('title') or 'Grupo'))}</b>\n\n"
        "Elige quién puede consultar las reglas con <code>/rules</code>.\n\n"
        f"Acceso actual: <b>{'Solo administradores' if acceso == 'admins' else 'Todos los miembros'}</b>."
    )
    if aviso:
        texto = f"✅ {html.escape(aviso)}\n\n{texto}"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(
        ("✅ " if acceso == "all" else "") + "👥 Todos los miembros",
        callback_data=f"grp_rules|access|{canal_key}|{pagina}|all",
    ))
    markup.add(types.InlineKeyboardButton(
        ("✅ " if acceso == "admins" else "") + "🛡️ Solo administradores",
        callback_data=f"grp_rules|access|{canal_key}|{pagina}|admins",
    ))
    markup.add(types.InlineKeyboardButton(
        "↩️ Volver a Reglamento",
        callback_data=f"grp_rules|home|{canal_key}|{pagina}|{int(mostrar_ayuda)}",
    ))
    return editar_o_enviar_panel(
        chat_id_admin, texto, markup, message=message, message_id=message_id,
        forzar_texto=True,
    )


def construir_teclado_reglamento(canal_key, ajustes):
    botones = (ajustes or {}).get("rules_keyboard", [])
    if not botones or canal_key not in CANALES:
        return None
    markup = types.InlineKeyboardMarkup(row_width=2)
    fila = []
    for index, item in enumerate(botones[:20]):
        etiqueta = str(item.get("label", "Botón"))[:64]
        accion = str(item.get("action", "")).strip()
        boton = (
            types.InlineKeyboardButton(etiqueta, url=accion)
            if accion.startswith(("https://", "http://"))
            else types.InlineKeyboardButton(
                etiqueta, callback_data=f"rules_inline|{canal_key}|{index}"
            )
        )
        fila.append(boton)
        if len(fila) == 2:
            markup.row(*fila)
            fila = []
    if fila:
        markup.row(*fila)
    return markup


def separar_sintaxis_boton(texto):
    if "=" in texto:
        etiqueta, accion = texto.split("=", 1)
    else:
        coincidencia = re.fullmatch(r"\s*(.{1,32}?)\s+-\s+(.+?)\s*", texto)
        if not coincidencia:
            raise ValueError("Usa etiqueta=acción o «Nombre del botón - rules».")
        etiqueta, accion = coincidencia.groups()
    etiqueta, accion = etiqueta.strip(), accion.strip()
    if accion.casefold() == "rules":
        accion = "/rules"
    if not etiqueta or not accion or len(etiqueta) > 64:
        raise ValueError("La etiqueta debe tener de 1 a 64 caracteres y la acción no puede estar vacía.")
    if accion.startswith(("https://", "http://")) and not re.fullmatch(
        r"https?://[^\s<>\"']+", accion, re.IGNORECASE
    ):
        raise ValueError("El enlace no parece válido.")
    return etiqueta, accion


def mostrar_menu_atajos_grupo(
    chat_id_admin, canal_key, pagina=0, message=None, message_id=None, aviso=None
):
    ajustes = obtener_ajustes_grupo(canal_key) or {}
    botones = ajustes.get("quick_buttons", [])
    es_grupo = str(ajustes.get("type") or "grupo").lower() != "canal"
    etiqueta_videochat = etiqueta_boton_videochat(ajustes)
    markup = types.InlineKeyboardMarkup(row_width=1)
    if es_grupo:
        enabled = ajustes.get("quick_commands_enabled", {})
        for start in range(0, len(GROUP_MEMBER_SHORTCUTS), 2):
            fila = []
            for key, label, _action in GROUP_MEMBER_SHORTCUTS[start:start + 2]:
                if key == "vchat":
                    label = etiqueta_videochat
                mark = "✅" if enabled.get(key, True) else "⚪"
                fila.append(types.InlineKeyboardButton(
                    f"{mark} {label}",
                    callback_data=f"grupo_atajo_toggle|{canal_key}|{key}|{pagina}",
                ))
            markup.row(*fila)
        markup.add(types.InlineKeyboardButton(
            f"✏️ Nombre del botón de videochat: {etiqueta_videochat}",
            callback_data=f"grupo_atajos_video_label|{canal_key}|{pagina}",
        ))
    markup.add(
        types.InlineKeyboardButton(
            "➕ Agregar botón",
            callback_data=f"grupo_atajos_add|{canal_key}|{pagina}",
        ),
        types.InlineKeyboardButton(
            "📲 Publicar botones en el chat",
            callback_data=f"grupo_atajos_apply|{canal_key}|{pagina}",
        ),
        types.InlineKeyboardButton(
            "🧹 Quitar botones del chat",
            callback_data=f"grupo_atajos_remove|{canal_key}|{pagina}",
        ),
    )
    for index, item in enumerate(botones[:20]):
        markup.add(types.InlineKeyboardButton(
            f"🗑️ Quitar: {str(item.get('label', 'Botón'))[:48]}",
            callback_data=f"grupo_atajos_del|{canal_key}|{index}|{pagina}",
        ))
    markup.add(types.InlineKeyboardButton(
        "↩️ Volver a ajustes",
        callback_data=f"grupo_config|{canal_key}|{pagina}",
    ))
    resumen_custom = "\n".join(
        f"• <b>{html.escape(str(item.get('label', 'Botón')))}</b> → "
        f"<code>{html.escape(str(item.get('action', '')))}</code>"
        for item in botones[:20]
    ) or "Todavía no hay botones personalizados."
    if es_grupo:
        enabled = ajustes.get("quick_commands_enabled", {})
        acciones = {
            "start": "abre el menú privado del bot",
            "menu": "muestra el menú del grupo",
            "rules": "muestra el reglamento de este grupo",
            "share": "comparte el enlace del grupo",
            "admin": "abre el contacto del administrador",
            "vchat": "muestra el acceso o guía de videochat",
        }
        labels = {
            key: etiqueta_videochat if key == "vchat" else label
            for key, label, _action in GROUP_MEMBER_SHORTCUTS
        }
        fixed = "\n".join(
            f"{'✅' if enabled.get(key, True) else '⚪'} "
            f"<b>{html.escape(labels[key])}</b> → {acciones[key]}"
            for key, _label, _action in GROUP_MEMBER_SHORTCUTS
        )
        resumen_custom = f"{fixed}\n\n<b>Botones personalizados</b>\n{resumen_custom}"
    tipo = str(ajustes.get("type") or "grupo").lower()
    detalle = (
        "En grupos, publica el teclado para dejar los accesos visibles bajo la barra de escritura. "
        "Telegram requiere un toque adicional en enlaces; una tecla de respuesta no puede abrirlos directamente."
        if tipo != "canal" else
        "En canales Telegram no ofrece una barra de respuesta para suscriptores; los botones se publican bajo un mensaje."
    )
    texto = (
        f"⌨️ <b>Botones rápidos — {html.escape(str(ajustes.get('title', 'este chat')))}</b>\n\n"
        f"{resumen_custom}\n\n"
        "Los seis accesos fijos se pueden activar o desactivar y el nombre del botón de videochat es editable. "
        "Para añadir botones usa <code>etiqueta=acción</code>, por ejemplo "
        "<code>🌐 Sitio=https://ejemplo.com</code> o <code>📜 Reglamento - rules</code>.\n\n"
        f"{html.escape(detalle)}"
    )
    if aviso:
        texto = f"✅ {html.escape(aviso)}\n\n{texto}"
    return editar_o_enviar_panel(
        chat_id_admin, texto, markup, message=message, message_id=message_id,
        forzar_texto=True,
    )


def enviar_ficha_destino(
    chat_id_admin, canal_key, chat_id, title, tipo, message=None, message_id=None,
    aviso=None,
):
    nombre = title or CANALES[canal_key]["nombre"]
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "📋 Copiar ID",
            copy_text=types.CopyTextButton(text=str(chat_id)),
        ),
    )
    markup.add(
        types.InlineKeyboardButton(
            "⚙️ Abrir configuración",
            callback_data=f"grupo_config|{canal_key}",
        ),
        types.InlineKeyboardButton(
            "📋 Botones y publicaciones",
            callback_data=f"grupo_botones|{canal_key}",
        ),
    )
    markup.add(types.InlineKeyboardButton(
        "🗑️ Eliminar grupo/canal",
        callback_data=f"grupo_eliminar_confirmar|{canal_key}",
    ))
    detalle = aviso or (
        "Elige una acción. Los ajustes se guardan por separado para este grupo o canal."
    )
    texto = (
        f"✅ <b>{html.escape(nombre)}</b>\n"
        f"Tipo: <b>{html.escape(tipo)}</b>\n"
        f"ID: <code>{html.escape(str(chat_id))}</code>\n\n{detalle}"
    )
    return editar_o_enviar_panel(
        chat_id_admin, texto, markup, message=message, message_id=message_id
    )

    # --- CONFIGURACIÓN DE IDENTIDAD ---
    TOKEN = os.environ['TELEGRAM_TOKEN']
    ADMIN_ID = 7827130679
    GRUPO_ID = -1003209796081
    LINK_GRUPO = "https://t.me/+DT-eLLYZ0g8wNmMx"
    LINK_CANAL_GRATUITO = "https://t.me/+dv7otcdqzmk0NWU5"
    MY_USER = 'Ja2610X'
    BOT_USER = "CACIQUEXVIPbot"
    BOT_PAGO = "@CaciqueXmembot"

    bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

    # --- BASES DE DATOS (MANTENIDAS ÍNTEGRAS) ---
    db = TinyDB('database.json')
    Config = TinyDB('config.json')
    Blacklist = TinyDB('blacklist.json')
    UltimaPromo = TinyDB('ultima_promo.json')
    Warnings = TinyDB('warnings.json')
    PromosAprobadas = TinyDB('promos_aprobadas.json')
    RegistroActividad = TinyDB('registro_actividad.json')
    Suscripciones = TinyDB('suscripciones.json')
    Estadisticas = TinyDB('stats.json')
    User = Query()
    user_data = {}
    ID_ULTIMA_INVITACION = None
    ULTIMOS_MSGS = {'reglas': None, 'admin': None, 'menu': None, 'compartir': None, 'start': None, 'reportar': None, 'anon': None}
    reporte_msgs = {}

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
    # --- para solo grupos a los que el bot es agregado por mi usurio principal ) ---
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

    # --- FUNCIONES DE SISTEMA ---
    app = Flask('')

    @app.route('/')
    def home():
        return "SISTEMA CACIQUE SUPREMO ACTIVO - VERSIÓN ESTÉTICA V17.5 (ID LOCKED)"

    @app.route(f'/{TOKEN}', methods=['POST'])
    def webhook():
        if request.headers.get('content-type') == 'application/json':
            try:
                json_string = request.get_data().decode('utf-8')
                update = telebot.types.Update.de_json(json_string)
                bot.process_new_updates([update])
            except Exception as e:
                print(f"❌ ERROR EN WEBHOOK: {e}")
            return '', 200
        else:
            abort(403)

    def eliminar_mensaje_seguro(chat_id, message_id):
        try:
            bot.delete_message(chat_id, message_id)
        except:
            pass

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
        if message.chat.id != GRUPO_ID:
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
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, input_field_placeholder="Selecciona tu arma de guerra... 🏹")
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

    def enviar_invitacion_vchat():
        global ID_ULTIMA_INVITACION
        if ID_ULTIMA_INVITACION:
            eliminar_mensaje_seguro(GRUPO_ID, ID_ULTIMA_INVITACION)
        msg_random = random.choice(TEXTOS_VC_HOT)
        e1, e2 = random.sample(EMOJIS_ACCION, 2)
        markup = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton(f"{e1} ENTRAR AL VIDEOCHAT {e2}", url="https://t.me/indiosavoy?videochat")
        )
        try:
            nuevo_msg = bot.send_message(GRUPO_ID, msg_random, reply_markup=markup)
            ID_ULTIMA_INVITACION = nuevo_msg.message_id
        except:
            pass

    def bucle_notificacion_menu():
        while True:
            time.sleep(45 * 60)
            try:
                bot.send_message(
                    GRUPO_ID,
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
                        bot.send_video(GRUPO_ID, p['file_id'], caption=f"🔄 **RE-POST**\n\n{p['desc']}", reply_markup=markup)
                    else:
                        bot.send_photo(GRUPO_ID, p['file_id'], caption=f"🔄 **RE-POST**\n\n{p['desc']}", reply_markup=markup)
                    time.sleep(10)
                except:
                    continue

    # --- SEGURIDAD: BLOQUEO DE GRUPOS/CANALES NO AUTORIZADOS ---
    @bot.my_chat_member_handler()
    def guardian_grupos(update):
        chat = update.chat
        nuevo_estado = update.new_chat_member.status
        if chat.id == GRUPO_ID:
            return
        if nuevo_estado in ['member', 'administrator']:
            try:
                bot.send_message(
                    chat.id,
                    "🔒 Este bot es privado y no puede ser agregado a grupos o canales no autorizados."
                )
            except:
                pass
            try:
                bot.leave_chat(chat.id)
            except:
                pass
            tipo = "canal" if chat.type == "channel" else "grupo"
            nombre = chat.title or str(chat.id)
            bot.send_message(
                ADMIN_ID,
                f"🚨 *ALERTA DE SEGURIDAD*\n\n"
                f"Intentaron agregar el bot a un {tipo} no autorizado:\n"
                f"📛 *Nombre:* {nombre}\n"
                f"🆔 *ID:* {chat.id}\n\n"
                f"✅ El bot salió automáticamente."
            )

    # --- MOTOR PRINCIPAL ---
    @bot.message_handler(content_types=['text', 'photo', 'video'])
    def motor_principal(message):
        global ULTIMOS_MSGS
        chat_id, uid = message.chat.id, message.from_user.id
        print(f"📨 MENSAJE RECIBIDO — chat:{chat_id} uid:{uid} tipo:{message.content_type} texto:{message.text or '[media]'}")
        COMANDOS = ["/menu", "/compartir", "/reglas", "/vchat", "/admin", "/start", "/reportar"]

        # --- SEGURIDAD: BLOQUEAR GRUPOS NO AUTORIZADOS ---
        if message.chat.type in ['group', 'supergroup', 'channel'] and chat_id != GRUPO_ID:
            try:
                bot.leave_chat(chat_id)
            except:
                pass
            return

        # --- SEGURIDAD: BLACKLIST ---
        if Blacklist.search(User.id == uid):
            return

        # --- SEGURIDAD: ANTI-FLOOD ---
        if uid != ADMIN_ID and es_flood(uid):
            try:
                bot.send_message(chat_id, "⚠️ Estás enviando mensajes muy rápido. Espera unos segundos.")
            except:
                pass
            return

        # --- SEGURIDAD: EN PRIVADO SOLO COMANDOS VÁLIDOS ---
        if message.chat.type == 'private' and uid != ADMIN_ID:
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
                    url=f"https://t.me/{bot_info.username}?start=menu"
                ))
                bot.send_message(
                    chat_id,
                    "🏹 Pulsa el botón para abrir el Menú del Templo en privado. 🔥",
                    reply_markup=markup
                )
            return

        uname = (message.from_user.username or "chat_id == GRUPO_ID:o").lower()
        guardar_evidencia(message)
        if chat_id == GRUPO_ID:
            registrar_actividad_stats(uid, uname)
        if not message.text:
            return
        texto = message.text.lower()

        if texto.startswith("/reportar") or (texto.startswith("/start") and "reporte" in texto):
            if chat_id != GRUPO_ID:
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
            if chat_id != GRUPO_ID:
                markup = types.InlineKeyboardMarkup(row_width=1)
                btn_grupo = types.InlineKeyboardButton("🔥 ENTRAR AL GRUPO PRINCIPAL", url=LINK_GRUPO)
                btn_invitar = types.InlineKeyboardButton("🚀 INVITAR A GUERREROS", url=LINK_SHARE)
                btn_vip = types.InlineKeyboardButton("💎 SOLICITAR ACCESO VIP", callback_data="solicitar_vip")
                btn_promo = types.InlineKeyboardButton("📢 CREAR MI PUBLICACIÓN", callback_data="crear_promo")
                btn_canal = types.InlineKeyboardButton("📺 ENTRAR AL CANAL GRATUITO", callback_data="canal_gratuito")
                markup.add(btn_grupo, btn_invitar, btn_vip, btn_promo, btn_canal)
                if uid == ADMIN_ID:
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
                    url=f"https://t.me/{bot_info.username}?start=menu"
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
            if chat_id == GRUPO_ID:
                eliminar_mensaje_seguro(chat_id, message.message_id)
                if ULTIMOS_MSGS['menu']:
                    eliminar_mensaje_seguro(chat_id, ULTIMOS_MSGS['menu'])
                resp = bot.send_message(chat_id, msg_menu, reply_markup=obtener_teclado_cuadritos())
                ULTIMOS_MSGS['menu'] = resp.message_id
            else:
                bot.send_message(chat_id, msg_menu, reply_markup=obtener_teclado_cuadritos())

        elif "/compartir" in texto:
            if chat_id == GRUPO_ID:
                eliminar_mensaje_seguro(chat_id, message.message_id)
                if ULTIMOS_MSGS['compartir']:
                    eliminar_mensaje_seguro(chat_id, ULTIMOS_MSGS['compartir'])
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(types.InlineKeyboardButton("🚀 INVITAR GUERREROS AL TEMPLO", url=LINK_SHARE))
            txt_compartir = (
                f"🏹 @{uname}, ¡recluta más guerreros para la tribu!\n\n"
                f"Pulsa el botón y elige a quién quieres invitar directamente desde tus contactos. 🔥"
            )
            if chat_id == GRUPO_ID:
                resp = bot.send_message(chat_id, txt_compartir, reply_markup=markup)
                ULTIMOS_MSGS['compartir'] = resp.message_id
            else:
                bot.send_message(chat_id, txt_compartir, reply_markup=markup)

        elif "/reglas" in texto:
            reglas_cfg = Config.search(User.tipo == 'reglamento')
            val = reglas_cfg[0]['valor.'] if reglas_cfg else "Respeta al Cacique."
            if chat_id == GRUPO_ID:
                eliminar_mensaje_seguro(chat_id, message.message_id)
                if ULTIMOS_MSGS['reglas']:
                    eliminar_mensaje_seguro(chat_id, ULTIMOS_MSGS['reglas'])
                resp = bot.send_message(chat_id, f"📜 **REGLAMENTO SAGRADO**\n\n{val}", reply_markup=obtener_teclado_cuadritos())
                ULTIMOS_MSGS['reglas'] = resp.message_id
            else:
                bot.send_message(chat_id, f"📜 **REGLAMENTO SAGRADO**\n\n{val}", reply_markup=obtener_teclado_cuadritos())

        elif "/vchat" in texto:
            if chat_id == GRUPO_ID:
                eliminar_mensaje_seguro(chat_id, message.message_id)
                enviar_invitacion_vchat()

        elif "/admin" in texto:
            bot_info = bot.get_me()
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("👤 Contactar Cacique", url=f"https://t.me/{MY_USER}"),
                types.InlineKeyboardButton("🚩 REPORTAR INFRACTOR", url=f"https://t.me/{bot_info.username}?start=reporte")
            )
            if chat_id == GRUPO_ID:
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

        if uid != ADMIN_ID and es_flood(uid):
            bot.answer_callback_query(call.id, "⚠️ Demasiadas acciones. Espera un momento.")
            return
    markup.add(
        types.InlineKeyboardButton(
            "➕ Agregar botón",
            callback_data=f"grupo_atajos_add|{canal_key}|{pagina}",
        ),
        types.InlineKeyboardButton(
            "📲 Publicar botones en el chat",
            callback_data=f"grupo_atajos_apply|{canal_key}|{pagina}",
        ),
        types.InlineKeyboardButton(
            "🧹 Quitar botones del chat",
            callback_data=f"grupo_atajos_remove|{canal_key}|{pagina}",
        ),
    )
    for index, item in enumerate(botones[:20]):
        etiqueta = str(item.get("label", "Botón"))[:50]
        markup.add(types.InlineKeyboardButton(
            f"🗑️ Quitar: {etiqueta}",
            callback_data=f"grupo_atajos_del|{canal_key}|{index}|{pagina}",
        ))
def guardar_edicion_funcion_grupo(canal_key, feature, texto):
    if feature != "reglamento":
        raise ValueError("Esta opción no admite edición de texto.")
    texto = (texto or "").strip()
    if texto.lower() == "/vaciar":
        texto = ""
    if len(texto) > 4000:
        raise ValueError("El texto no puede superar 4000 caracteres.")
    actualizar_ajustes_grupo(
        canal_key, lambda ajustes: ajustes.update({"rules": texto})
    )
    return "Reglamento guardado."


def mostrar_menu_funcion_grupo(
    chat_id_admin, canal_key, feature, pagina=0, message=None,
    message_id=None, aviso=None,
):
    if feature == "reglamento":
        return mostrar_menu_reglamento(
            chat_id_admin, canal_key, pagina, message=message,
            message_id=message_id, aviso=aviso,
        )
    if feature == "atajos":
        return mostrar_menu_atajos_grupo(
            chat_id_admin, canal_key, pagina, message=message,
            message_id=message_id, aviso=aviso,
        )
    return mostrar_configuracion_grupo(
        chat_id_admin, canal_key, pagina, message=message,
        message_id=message_id,
        aviso="Esta opción ya no forma parte del panel de configuración.",
    )


def _mostrar_configuracion_grupo_reemplazada(
    chat_id_admin, canal_key, *args, **kwargs
):
    return mostrar_configuracion_grupo(
        chat_id_admin,
        canal_key,
        message=kwargs.get("message"),
        message_id=kwargs.get("message_id"),
        aviso="Esta sección se administra ahora desde Reglamento y Botones rápidos.",
    )


for _nombre_menu_reemplazado in (
    "mostrar_menu_antispam",
    "mostrar_menu_antiflood",
    "mostrar_menu_multimedia_grupo",
    "mostrar_menu_bienvenida_despedida",
    "mostrar_menu_captcha_grupo",
    "mostrar_menu_modo_nocturno",
    "mostrar_menu_advertencias_grupo",
    "mostrar_menu_excepciones_moderacion",
    "mostrar_menu_enlace_grupo",
    "mostrar_menu_aprobacion_grupo",
    "mostrar_menu_palabras_grupo",
    "mostrar_menu_bloqueos_grupo",
    "mostrar_menu_miembros_grupo",
    "mostrar_menu_enmascarados_grupo",
):
    globals()[_nombre_menu_reemplazado] = _mostrar_configuracion_grupo_reemplazada


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

def revisar_publicaciones_recurrentes():
    while True:
        ahora = time.time()
        try:
            recurrentes = cargar_config().get("recurrentes", {})
            for destino_key, recurrente in recurrentes.items():
                botones_key = recurrente.get("botones_key", destino_key)
                if (
                    destino_key not in CANALES
                    or botones_key not in CANALES
                    or not recurrente.get("activo")
                ):
                    continue
                if float(recurrente.get("proximo_envio", 0)) > ahora:
                    continue

                with RECURRING_LOCK:
                    cfg_actual = cargar_config()
                    recurrente = cfg_actual.get("recurrentes", {}).get(destino_key, {})
                    if not recurrente.get("activo") or float(recurrente.get("proximo_envio", 0)) > time.time():
                        continue
                    botones_key = recurrente.get("botones_key", destino_key)
                    if botones_key not in CANALES:
                        continue

                    chat_id = obtener_canal_id(destino_key)
                    botones = cargar_botones_custom(botones_key)
                    if not chat_id:
                        def pausar_por_configuracion(cfg):
                            actual = cfg.get("recurrentes", {}).get(destino_key)
                            if actual:
                                actual["activo"] = False
                                actual["error"] = "Falta configurar el destino."
                        actualizar_config(pausar_por_configuracion)
                        bot.send_message(
                            int(ADMIN_ID),
                            f"⏸️ Se pausó la publicación recurrente de "
                            f"{html.escape(CANALES[destino_key]['nombre'])}: configura el destino.",
                            parse_mode="HTML",
                        )
                        continue

                    markup = construir_markup_botones(botones) if botones else None
                    try:
                        nuevo = enviar_publicacion_con_botones(
                            int(chat_id),
                            recurrente.get("texto", ""),
                            markup,
                            recurrente.get("media_id"),
                            recurrente.get("media_type"),
                            media_items=recurrente.get("media_items"),
                        )
                        mensajes_nuevos = nuevo if isinstance(nuevo, list) else [nuevo]
                        ids_nuevos = [
                            mensaje.message_id
                            for mensaje in mensajes_nuevos
                            if getattr(mensaje, "message_id", None) is not None
                        ]
                        if not ids_nuevos:
                            raise RuntimeError("Telegram no devolvió los mensajes publicados.")
                    except Exception as error:
                        app.logger.exception("Falló una publicación recurrente.")
                        def reintentar_mas_tarde(cfg):
                            actual = cfg.get("recurrentes", {}).get(destino_key)
                            if actual and actual.get("activo"):
                                actual["proximo_envio"] = time.time() + 300
                                actual["error"] = str(error)[:300]
                        actualizar_config(reintentar_mas_tarde)
                        bot.send_message(
                            int(ADMIN_ID),
                            f"⚠️ No pude publicar el mensaje recurrente en "
                            f"{html.escape(CANALES[destino_key]['nombre'])}. "
                            "Volveré a intentarlo en 5 minutos.",
                            parse_mode="HTML",
                        )
                        continue

                    chat_anterior = recurrente.get("ultimo_chat_id")
                    siguiente = time.time() + int(recurrente["intervalo_segundos"])

                    def guardar_nuevo_envio(cfg):
                        actual = cfg.get("recurrentes", {}).get(destino_key)
                        if not actual:
                            return
                        actual.update({
                            "ultimo_message_id": ids_nuevos[-1],
                            "ultimo_message_ids": ids_nuevos,
                            "ultimo_chat_id": str(chat_id),
                            "ultimo_envio": time.time(),
                            "proximo_envio": siguiente,
                        })
                        actual.pop("error", None)
                        cfg.setdefault("ultima_publicacion", {})[botones_key] = {
                            "chat_id": str(chat_id),
                            "message_id": ids_nuevos[0],
                            "texto": recurrente.get("texto", ""),
                            "media_id": recurrente.get("media_id"),
                            "media_type": recurrente.get("media_type"),
                            "media_items": normalizar_media_items(
                                recurrente.get("media_id"),
                                recurrente.get("media_type"),
                                recurrente.get("media_items"),
                            ),
                            "botones_key": botones_key,
                        }
                    actualizar_config(guardar_nuevo_envio)

                    mensajes_anteriores = recurrente.get("ultimo_message_ids") or [
                        recurrente.get("ultimo_message_id")
                    ]
                    if chat_anterior:
                        errores_borrado = 0
                        for message_id in dict.fromkeys(filter(None, mensajes_anteriores)):
                            try:
                                bot.delete_message(int(chat_anterior), int(message_id))
                            except Exception:
                                errores_borrado += 1
                                app.logger.exception(
                                    "No se pudo borrar un mensaje recurrente anterior."
                                )
                        if errores_borrado:
                            bot.send_message(
                                int(ADMIN_ID),
                                f"⚠️ El nuevo mensaje se publicó en "
                                f"{html.escape(CANALES[destino_key]['nombre'])}, pero no pude borrar "
                                f"{errores_borrado} mensaje(s) anterior(es). Revisa los permisos del bot.",
                                parse_mode="HTML",
                            )
        except Exception:
            app.logger.exception("Error al revisar las publicaciones recurrentes.")
        time.sleep(15)

# ── Migración: configuración antigua (canal único) → canales independientes ──
# Antes existía un solo "canal_botones_id" compartido por todas las publicaciones.
# Ahora cada canal (GoldPass CX HOTGO / FREECLUB CX HUB) tiene su propio ID y su
# propio set de botones, así publicar en uno nunca llega ni comparte botones con el otro.
cargar_destinos_adicionales()
_cfg_init = cargar_config()
if 'canales' not in _cfg_init:
    canal_viejo = _cfg_init.get('canal_botones_id') or CanaL_ID
    _cfg_init['canales'] = {"goldpass": str(canal_viejo), "freeclub": None}
    _cfg_init.pop('canal_botones_id', None)
    guardar_config(_cfg_init)

if not os.path.exists(CANALES['goldpass']['archivo']) and os.path.exists('botones_custom.json'):
    with open('botones_custom.json', 'r', encoding='utf-8') as _f:
        guardar_botones_custom('goldpass', json.load(_f))

threading.Thread(target=revisar_vencimientos, daemon=True).start()
threading.Thread(target=revisar_publicaciones_recurrentes, daemon=True).start()

# ═══════════════════════════════════════════════════════════════════
# 👥 NUEVO MIEMBRO EN EL CANAL (entró directo, sin pasar por el bot)
# ═══════════════════════════════════════════════════════════════════
@bot.my_chat_member_handler()
def rechazar_agregados_no_autorizados(update):
    """Sale de grupos/canales si quien añadió o promovió al bot no es el dueño."""
    if getattr(update.chat, "type", None) == "private":
        return
    estado_nuevo = getattr(update.new_chat_member, "status", None)
    if estado_nuevo not in ("member", "administrator", "creator"):
        return
    actor = getattr(update, "from_user", None)
    if actor and str(actor.id) == str(ADMIN_ID):
        if getattr(update.chat, "type", None) not in ("group", "supergroup"):
            return
        try:
            canal_key = obtener_o_crear_destino_compartido(
                update.chat.id,
                getattr(update.chat, "title", None) or "Grupo de Telegram",
                "grupo",
            )
            actualizar_ajustes_grupo(
                canal_key,
                lambda ajustes: ajustes.update({
                    "chat_id": str(update.chat.id),
                    "title": getattr(update.chat, "title", None) or "Grupo de Telegram",
                    "type": "grupo",
                }),
            )
            ajustes = obtener_ajustes_grupo(canal_key) or {}
            if not ajustes.get("quick_buttons_message_id"):
                publicar_teclado_atajos_grupo(
                    canal_key,
                    "📹 Atajo de videochat y botones del grupo disponibles abajo.",
                )
        except Exception:
            app.logger.exception(
                "No se pudo registrar el grupo ni publicar sus atajos iniciales."
            )
        return
    try:
        bot.leave_chat(update.chat.id)
        app.logger.warning(
            "El bot salió de un chat porque la incorporación no fue autorizada."
        )
    except Exception:
        app.logger.warning(
            "No se pudo completar la salida de un chat con incorporación no autorizada."
        )


# Cuando alguien entra al canal directamente (link de invitación sin
# aprobación, añadido por un admin, etc.) se registra con 30 días.
# Requiere que el bot sea admin del canal con permiso de "ver miembros".
@bot.chat_member_handler()
def nuevo_miembro_directo(update):
    if str(update.chat.id) != str(CANAL_ID):
        procesar_evento_miembro_grupo(update)
        return
    miembro = update.new_chat_member
    # Solo cuando el estado pasa a member/administrator (entrada)
    if miembro.status not in ("member", "administrator", "creator"):
        return
    miembro_anterior = getattr(update, "old_chat_member", None)
    if getattr(miembro_anterior, "status", None) in (
        "member", "administrator", "creator"
    ):
        return
    # Ignorar al propio bot
    if miembro.user.is_bot:
        return

    user_id  = miembro.user.id
    username = miembro.user.username or ""
    nombre   = miembro.user.first_name or "Usuario"

    User = Query()
    ya_registrado = db.get(User.id == user_id)
    if ya_registrado:
        access_message_id = ya_registrado.get("access_message_id")
        if access_message_id:
            try:
                bot.delete_message(user_id, access_message_id)
            except Exception:
                app.logger.info(
                    "No se pudo retirar la tarjeta de acceso tras confirmar la entrada al canal."
                )
            with PANEL_LOCK:
                panel = PANELES_PRIVADOS.get(PANEL_QUERY.chat_id == str(user_id))
                if panel and str(panel.get("message_id")) == str(access_message_id):
                    PANELES_PRIVADOS.remove(PANEL_QUERY.chat_id == str(user_id))
            try:
                bot.send_message(
                    user_id,
                    "🎉 ¡Bienvenido! Espero que disfrutes tu acceso al canal GoldPass.",
                    protect_content=True,
                    _force_new_message=True,
                )
                db.update(
                    {"access_message_id": None},
                    User.id == user_id,
                )
            except Exception:
                app.logger.exception(
                    "No se pudo enviar el mensaje de bienvenida tras la entrada VIP."
                )
        return  # ya tiene registro activo, no sobreescribir

    vencimiento = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    db.upsert({'id': user_id, 'vence': vencimiento, 'username': username}, User.id == user_id)

    uname_txt = f"@{username}" if username else f"<code>{user_id}</code>"
    bot.send_message(
        int(ADMIN_ID),
        f"👤 <b>Nuevo miembro registrado automáticamente</b>\n\n"
        f"👤 Nombre: <b>{nombre}</b>\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"📛 Usuario: {uname_txt}\n"
        f"📅 Vence: <b>{vencimiento}</b>\n\n"
        f"<i>Entró al canal directamente (no pasó por el flujo de pago).</i>",
        parse_mode="HTML"
    )

# ═══════════════════════════════════════════════════════════════════
# 🔓 SOLICITUD DE INGRESO AL CANAL (link fijo con cobro en Stars)
# ═══════════════════════════════════════════════════════════════════
# Los links de pago del canal VIP siguen aprobándose automáticamente.
# Las solicitudes de otros grupos/canales pasan por el flujo de aprobación
# configurado para ese destino y nunca se aprueban por esta ruta.
@bot.chat_join_request_handler()
def aprobar_solicitud_canal(chat_join_request):
    if str(chat_join_request.chat.id) != str(CANAL_ID):
        ajustes = obtener_ajustes_chat(chat_join_request.chat.id)
        if ajustes and ajustes.get("enabled", {}).get("aprobacion"):
            usuario = chat_join_request.from_user
            canal_key = buscar_destino_por_chat_id(chat_join_request.chat.id)
            if ajustes.get("approval_auto_enabled") and canal_key:
                izquierda, derecha = random.randint(1, 6), random.randint(1, 6)
                respuesta = izquierda + derecha
                opciones = {respuesta}
                while len(opciones) < 3:
                    opciones.add(
                        max(2, min(12, respuesta + random.choice((-3, -2, -1, 1, 2, 3))))
                    )
                opciones = list(opciones)
                random.shuffle(opciones)
                respuesta_correcta = opciones.index(respuesta)
                if canal_key:
                    def registrar_pendiente(ajustes_actuales):
                        pendientes = ajustes_actuales.setdefault("approval_captcha_answers", {})
                        pendientes[str(usuario.id)] = {
                            "choice": respuesta_correcta,
                            "expires_at": time.time() + 600,
                        }
                        if len(pendientes) > 500:
                            pendientes.pop(next(iter(pendientes)))
                    actualizar_ajustes_grupo(canal_key, registrar_pendiente)
                try:
                    markup = types.InlineKeyboardMarkup(row_width=3)
                    markup.row(*[
                        types.InlineKeyboardButton(
                            str(number),
                            callback_data=(
                                f"approval_verify|{chat_join_request.chat.id}|"
                                f"{usuario.id}|{index}"
                            ),
                        )
                        for index, number in enumerate(opciones)
                    ])
                    bot.send_message(
                        usuario.id,
                        f"Verificación para solicitar ingreso a "
                        f"«{html.escape(str(ajustes.get('title', 'este grupo')))}»:\n\n"
                        f"¿Cuánto es {izquierda} + {derecha}?",
                        reply_markup=markup,
                    )
                    return
                except Exception:
                    app.logger.info(
                        "No se pudo enviar la verificación privada de la solicitud %s.",
                        usuario.id,
                    )
                    if canal_key:
                        actualizar_ajustes_grupo(
                            canal_key,
                            lambda actual: actual.update({
                                "approval_captcha_answers": {
                                    key: value for key, value in
                                    actual.get("approval_captcha_answers", {}).items()
                                    if str(key) != str(usuario.id)
                                },
                            }),
                        )
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.row(
                types.InlineKeyboardButton(
                    "✅ Aprobar",
                    callback_data=f"join_review|approve|{chat_join_request.chat.id}|{usuario.id}",
                ),
                types.InlineKeyboardButton(
                    "⛔ Rechazar",
                    callback_data=f"join_review|decline|{chat_join_request.chat.id}|{usuario.id}",
                ),
            )
            destino = ajustes.get("log_chat_id") or int(ADMIN_ID)
            try:
                bot.send_message(
                    destino,
                    f"📩 Solicitud de ingreso a <b>{html.escape(str(ajustes.get('title', chat_join_request.chat.id)))}</b>\n"
                    f"Usuario: {html.escape(usuario.first_name or 'Sin nombre')} "
                    f"(<code>{usuario.id}</code>)",
                    parse_mode="HTML",
                    reply_markup=markup,
                )
            except Exception:
                app.logger.exception("No se pudo notificar una solicitud de ingreso.")
        return

    user_id  = chat_join_request.from_user.id
    username = chat_join_request.from_user.username or ""
    try:
        bot.approve_chat_join_request(chat_join_request.chat.id, user_id)
        vencimiento = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
        db.upsert({'id': user_id, 'vence': vencimiento, 'username': username}, Query().id == user_id)
    except Exception as e:
        try:
            bot.send_message(int(ADMIN_ID), f"⚠️ No pude aprobar el ingreso de <code>{user_id}</code>: {e}", parse_mode="HTML")
        except:
            pass


@bot.callback_query_handler(func=lambda call: call.data.startswith("approval_verify|"))
def confirmar_aprobacion_privada(call):
    try:
        _, chat_id_text, user_id_text, choice_text = call.data.split("|", 3)
        chat_id, user_id, choice = int(chat_id_text), int(user_id_text), int(choice_text)
    except (ValueError, TypeError):
        bot.answer_callback_query(call.id, "La solicitud ya no está disponible.")
        return
    if int(call.from_user.id) != user_id:
        bot.answer_callback_query(call.id, "Este botón es para la persona que solicitó entrar.")
        return
    ajustes = obtener_ajustes_chat(chat_id) or {}
    pendientes = ajustes.get("approval_captcha_answers", {})
    solicitud = pendientes.get(str(user_id))
    if not solicitud:
        bot.answer_callback_query(call.id, "La solicitud expiró o ya fue procesada.")
        return
    if float(solicitud.get("expires_at", 0)) < time.time():
        canal_key = buscar_destino_por_chat_id(chat_id)
        if canal_key:
            actualizar_ajustes_grupo(
                canal_key,
                lambda actual: actual.setdefault("approval_captcha_answers", {}).pop(str(user_id), None),
            )
        bot.answer_callback_query(call.id, "La verificación expiró.", show_alert=True)
        return
    if int(solicitud.get("choice", -1)) != choice:
        bot.answer_callback_query(call.id, "Respuesta incorrecta. Prueba otra opción.", show_alert=True)
        return
    try:
        bot.approve_chat_join_request(chat_id, user_id)
        canal_key = buscar_destino_por_chat_id(chat_id)
        if canal_key:
            actualizar_ajustes_grupo(
                canal_key,
                lambda actual: actual.update({
                    "approval_captcha_answers": {
                        key: value for key, value in
                        actual.get("approval_captcha_answers", {}).items()
                        if str(key) != str(user_id)
                    },
                }),
            )
        bot.answer_callback_query(call.id, "Solicitud aprobada.")
        try:
            bot.edit_message_text(
                "✅ Solicitud aprobada. Ya puedes entrar al grupo.",
                call.message.chat.id,
                call.message.message_id,
            )
        except Exception:
            pass
    except Exception:
        app.logger.exception("No se pudo aprobar la solicitud privada.")
        bot.answer_callback_query(call.id, "No pude aprobarla; contacta a un administrador.")


@bot.callback_query_handler(func=lambda call: call.data.startswith("join_review|"))
def revisar_solicitud_grupo(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Solo el administrador principal puede decidir.")
        return
    try:
        _, decision, chat_id, user_id = call.data.split("|", 3)
        chat_id = int(chat_id)
        user_id = int(user_id)
        if decision == "approve":
            bot.approve_chat_join_request(chat_id, user_id)
            texto = "✅ Solicitud aprobada."
        elif decision == "decline":
            bot.decline_chat_join_request(chat_id, user_id)
            texto = "⛔ Solicitud rechazada."
        else:
            raise ValueError("Acción desconocida.")
        bot.answer_callback_query(call.id, texto)
        try:
            bot.edit_message_reply_markup(
                call.message.chat.id,
                call.message.message_id,
                reply_markup=None,
            )
        except Exception:
            pass
    except Exception as error:
        bot.answer_callback_query(call.id, "No pude procesar la solicitud.")
        app.logger.exception("Falló la revisión de una solicitud de ingreso: %s", error)

# ═══════════════════════════════════════════════════════════════════
# 🧰 ADMINISTRACIÓN DE DESTINOS Y BOTONES
# ═══════════════════════════════════════════════════════════════════
BOTONES_RETURN_CALLBACK = {}


def markup_menu_botones(canal_key, return_callback="admin_volver"):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("👁️ Vista previa real", callback_data=f"preview_{canal_key}"),
        types.InlineKeyboardButton(
            "🖼️ Editar enlaces y multimedia",
            callback_data=f"botones_media_lista|{canal_key}",
        ),
        types.InlineKeyboardButton(
            "⏰ Mensajes recurrentes",
            callback_data=f"botones_recurrente|{canal_key}",
        ),
        types.InlineKeyboardButton("➕ Crear botón", callback_data=f"cboton_{canal_key}"),
        types.InlineKeyboardButton("🗑️ Eliminar botón", callback_data=f"ebotones_{canal_key}"),
        types.InlineKeyboardButton("📤 Enviar a grupo o canal", callback_data=f"pubcanal_{canal_key}"),
        types.InlineKeyboardButton("🔙 Volver", callback_data=return_callback),
    )
    return markup

def mostrar_gestion_botones(
    chat_id,
    canal_key,
    message=None,
    return_callback=None,
    message_id=None,
    aviso=None,
):
    if return_callback is None:
        return_callback = BOTONES_RETURN_CALLBACK.get(str(chat_id), "admin_volver")
    else:
        BOTONES_RETURN_CALLBACK[str(chat_id)] = return_callback
    botones = cargar_botones_custom(canal_key)
    ultima = buscar_ultima_publicacion_destino(canal_key)
    lineas_botones = []
    for boton in botones[:20]:
        nombre = html.escape(str(boton.get("texto") or "Botón"))
        tipo = "enlace" if boton.get("url") else "acción"
        lineas_botones.append(f"• {nombre} ({tipo})")
    if len(botones) > 20:
        lineas_botones.append(f"• … y {len(botones) - 20} más")
    resumen_botones = "\n".join(lineas_botones) or "• Todavía no hay botones configurados."

    if ultima:
        _, publicacion = ultima
        cantidad_media = len(media_items_de_publicacion(publicacion))
        resumen_publicacion = (
            "Última publicación registrada: "
            f"{cantidad_media} archivo(s) multimedia."
        )
    else:
        resumen_publicacion = "No hay una publicación anterior registrada para mostrar."

    multimedia_compartida = obtener_media_compartida_botones(canal_key)
    resumen_media = (
        "Multimedia compartida: configurada."
        if multimedia_compartida
        else "Multimedia compartida: pendiente."
    )
    resumen = (
        f"📋 <b>{html.escape(CANALES[canal_key]['nombre'])}</b>\n"
        f"Botones configurados: <b>{len(botones)}</b>\n"
        f"{resumen_media}\n"
        f"{resumen_publicacion}\n\n"
        f"{resumen_botones}\n\n"
        "El contenido multimedia o el mensaje se mostrarán solamente al pulsar "
        "«Vista previa real».\n\nElige una acción:"
    )
    if aviso:
        resumen = f"✅ {html.escape(aviso)}\n\n" + resumen
    return editar_o_enviar_panel(
        chat_id,
        resumen,
        markup_menu_botones(canal_key, return_callback),
        message=message,
        message_id=message_id,
        forzar_texto=True,
    )


def mostrar_lista_media_botones(
    chat_id, canal_key, message=None, message_id=None, aviso=None
):
    if canal_key not in CANALES:
        return None
    estado = admin_estado.get(chat_id, {})
    if (
        estado.get("tipo_editor") != "botones_lote"
        or estado.get("canal_key") != canal_key
    ):
        estado = {
            "tipo_editor": "botones_lote",
            "paso": "editar_botones_lote",
            "canal_key": canal_key,
            "botones_borrador": [
                dict(boton) for boton in cargar_botones_custom(canal_key)
            ],
            "media_borrador": obtener_media_compartida_botones(canal_key),
            "panel_message_id": message_id or getattr(message, "message_id", None),
        }
        admin_estado[chat_id] = estado
    elif message_id or message:
        estado["panel_message_id"] = message_id or getattr(message, "message_id", None)

    botones = estado.get("botones_borrador", [])
    media = estado.get("media_borrador", {})
    markup = types.InlineKeyboardMarkup(row_width=2)
    fila = []
    for indice, boton in enumerate(botones):
        nombre = str(boton.get("texto") or f"Botón {indice + 1}")
        fila.append(types.InlineKeyboardButton(
            f"{indice + 1}. {nombre[:24]}",
            callback_data=f"botones_lote_item|{canal_key}|{indice}",
        ))
        if len(fila) == 2:
            markup.row(*fila)
            fila = []
    if fila:
        markup.row(*fila)
    markup.row(
        types.InlineKeyboardButton(
            "➕ Agregar otro enlace",
            callback_data=f"botones_lote_nuevo|{canal_key}",
        ),
        types.InlineKeyboardButton(
            "🖼️ Cambiar multimedia",
            callback_data=f"botones_lote_media|{canal_key}",
        ),
    )
    markup.add(types.InlineKeyboardButton(
        "✅ Confirmar cambios y ver vista previa",
        callback_data=f"botones_lote_confirmar|{canal_key}",
    ))
    markup.row(
        types.InlineKeyboardButton(
            "🔙 Volver a botones", callback_data=f"botones_menu|{canal_key}"
        ),
        types.InlineKeyboardButton(
            "❌ Descartar borrador",
            callback_data=f"botones_lote_descartar|{canal_key}",
        ),
    )
    estado_media = (
        "Los logos PNG están preparados en la imagen compartida."
        if media.get("media_path")
        else "La imagen compartida está lista para la vista previa."
        if media.get("media_id")
        else "Aún no hay multimedia compartida."
    )
    texto = (
        f"🖼️ <b>Editar enlaces y multimedia — "
        f"{html.escape(CANALES[canal_key]['nombre'])}</b>\n\n"
        f"Botones en este borrador: <b>{len(botones)}</b>\n"
        f"{estado_media}\n\n"
        "Selecciona un botón para editar su nombre o enlace. "
        "Puedes añadir enlaces y cambiar una sola imagen para toda la publicación. "
        "Nada se guarda hasta confirmar."
    )
    if not botones:
        texto += "\n\nTodavía no hay botones; agrega el primero."
    if aviso:
        texto = f"ℹ️ {html.escape(aviso)}\n\n" + texto
    panel = editar_o_enviar_panel(
        chat_id,
        texto,
        markup,
        message=message,
        message_id=estado.get("panel_message_id"),
        forzar_texto=True,
    )
    if panel:
        estado["panel_message_id"] = getattr(panel, "message_id", None)
    return panel


def mostrar_editor_boton_lote(
    chat_id, canal_key, indice, message=None, message_id=None, aviso=None
):
    estado = admin_estado.get(chat_id, {})
    botones = estado.get("botones_borrador", [])
    if (
        estado.get("tipo_editor") != "botones_lote"
        or estado.get("canal_key") != canal_key
        or indice < 0
        or indice >= len(botones)
    ):
        return mostrar_lista_media_botones(
            chat_id, canal_key, message=message, message_id=message_id,
            aviso="Ese botón ya no está en el borrador.",
        )
    estado["paso"] = "editar_botones_lote"
    estado["indice_boton_borrador"] = indice
    estado["panel_message_id"] = (
        message_id
        or getattr(message, "message_id", None)
        or estado.get("panel_message_id")
    )
    boton = botones[indice]
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "✏️ Cambiar nombre",
            callback_data=f"botones_lote_nombre|{canal_key}|{indice}",
        ),
        types.InlineKeyboardButton(
            "🔗 Cambiar enlace",
            callback_data=f"botones_lote_url|{canal_key}|{indice}",
        ),
    )
    markup.add(types.InlineKeyboardButton(
        "↩️ Volver a todos los botones",
        callback_data=f"botones_lote_lista|{canal_key}",
    ))
    texto = (
        f"🔗 <b>Editar botón {indice + 1}</b>\n\n"
        f"Nombre: <b>{html.escape(str(boton.get('texto') or 'Sin nombre'))}</b>\n"
        f"Enlace: <code>{html.escape(str(boton.get('url') or 'Sin enlace'))}</code>"
    )
    if aviso:
        texto = f"ℹ️ {html.escape(aviso)}\n\n" + texto
    panel = editar_o_enviar_panel(
        chat_id, texto, markup, message=message,
        message_id=estado["panel_message_id"], forzar_texto=True,
    )
    if panel:
        estado["panel_message_id"] = getattr(panel, "message_id", None)
    return panel


def markup_preview_botones_lote(canal_key, botones):
    markup = types.InlineKeyboardMarkup(row_width=2)
    for boton in botones:
        url = str(boton.get("url") or "").strip()
        if not url.startswith(("https://", "http://")):
            continue
        markup.add(types.InlineKeyboardButton(
            str(boton.get("texto") or "Abrir")[:64],
            url=url,
        ))
    markup.row(
        types.InlineKeyboardButton(
            "↩️ Regresar",
            callback_data=f"botones_lote_lista|{canal_key}",
        ),
        types.InlineKeyboardButton(
            "📤 Publicar",
            callback_data=f"botones_lote_publicar|{canal_key}",
        ),
    )
    return markup


def enviar_media_compartida_botones(chat_id, media, caption, markup):
    media_type = media.get("media_type")
    metodo = {
        "photo": bot.send_photo,
        "video": bot.send_video,
        "document": bot.send_document,
        "audio": bot.send_audio,
        "animation": bot.send_animation,
    }.get(media_type)
    if not metodo:
        raise ValueError("La multimedia compartida no tiene un tipo válido.")
    opciones = {
        "caption": caption or None,
        "parse_mode": "HTML" if caption else None,
        "reply_markup": markup,
    }
    if media.get("media_path"):
        with open(media["media_path"], "rb") as archivo:
            return metodo(chat_id, archivo, **opciones)
    if media.get("media_id"):
        return metodo(chat_id, media["media_id"], **opciones)
    raise ValueError("No hay una imagen o multimedia preparada.")


def mostrar_vista_previa_botones_lote(chat_id, canal_key, aviso=None):
    estado = admin_estado.get(chat_id, {})
    if (
        estado.get("tipo_editor") != "botones_lote"
        or estado.get("canal_key") != canal_key
    ):
        return mostrar_lista_media_botones(chat_id, canal_key)
    botones = estado.get("botones_borrador", [])
    media = estado.get("media_borrador", {})
    caption = (
        f"👁️ <b>Vista previa — {html.escape(CANALES[canal_key]['nombre'])}</b>"
    )
    if aviso:
        caption = f"ℹ️ {html.escape(aviso)}\n\n" + caption
    markup = markup_preview_botones_lote(canal_key, botones)
    panel_message_id = estado.get("panel_message_id")
    if panel_message_id:
        try:
            bot.delete_message(chat_id, panel_message_id)
        except Exception:
            app.logger.info("No se pudo reemplazar el panel de edición por su vista previa.")
        with PANEL_LOCK:
            registro = PANELES_PRIVADOS.get(PANEL_QUERY.chat_id == str(chat_id))
            if registro and str(registro.get("message_id")) == str(panel_message_id):
                PANELES_PRIVADOS.remove(PANEL_QUERY.chat_id == str(chat_id))
    if media.get("media_type"):
        mensaje = enviar_media_compartida_botones(chat_id, media, caption, markup)
        tipo_panel = media["media_type"]
    else:
        mensaje = bot.send_message(
            chat_id,
            caption + "\n\n(No hay multimedia; solo se mostrarán los botones.)",
            parse_mode="HTML",
            reply_markup=markup,
        )
        tipo_panel = "texto"
    estado["paso"] = "botones_lote_preview"
    estado["panel_message_id"] = mensaje.message_id
    registrar_panel_privado(chat_id, mensaje.message_id, tipo_panel)
    return mensaje


def mostrar_editor_media_boton(
    chat_id, canal_key, indice, message=None, message_id=None, aviso=None
):
    botones = cargar_botones_custom(canal_key) if canal_key in CANALES else []
    if indice < 0 or indice >= len(botones):
        return mostrar_lista_media_botones(
            chat_id,
            canal_key,
            message=message,
            message_id=message_id,
            aviso="Ese botón ya no existe.",
        )
    boton = botones[indice]
    nombre = html.escape(str(boton.get("texto") or f"Botón {indice + 1}"))
    estado_media = (
        f"Actualmente tiene multimedia ({html.escape(str(boton.get('media_type')))})."
        if boton.get("media_id") and boton.get("media_type")
        else "Actualmente no tiene multimedia."
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(
        "📤 Enviar multimedia nueva",
        callback_data=f"botones_media_subir|{canal_key}|{indice}",
    ))
    markup.add(
        types.InlineKeyboardButton(
            "🔙 Volver a botones", callback_data=f"botones_menu|{canal_key}"
        ),
        types.InlineKeyboardButton(
            "↩️ Elegir otro botón",
            callback_data=f"botones_media_lista|{canal_key}",
        ),
    )
    texto = (
        f"🖼️ <b>{nombre}</b>\n"
        f"{html.escape(CANALES[canal_key]['nombre'])}\n\n"
        f"{estado_media}\n"
        "Al cambiarlo se mantienen el nombre y el enlace del botón."
    )
    if aviso:
        texto = f"✅ {html.escape(aviso)}\n\n" + texto
    return editar_o_enviar_panel(
        chat_id,
        texto,
        markup,
        message=message,
        message_id=message_id,
        forzar_texto=True,
    )


def cargar_contenido_vista_previa(destino_key):
    recurrente = cargar_config().get("recurrentes", {}).get(destino_key, {})
    contenido_programado = (
        str(recurrente.get("texto") or "").strip()
        or recurrente.get("media_items")
        or recurrente.get("media_id")
    )
    if contenido_programado:
        return {
            "texto": recurrente.get("texto", ""),
            "botones_key": recurrente.get("botones_key", destino_key),
            "media_items": normalizar_media_items(
                recurrente.get("media_id"),
                recurrente.get("media_type"),
                recurrente.get("media_items"),
            ),
        }

    ultima = buscar_ultima_publicacion_destino(destino_key)
    if not ultima:
        return None
    botones_key, publicacion = ultima
    return {
        "texto": publicacion.get("texto", ""),
        "botones_key": botones_key,
        "media_items": media_items_de_publicacion(publicacion),
    }


def markup_vista_previa(botones, contexto, destino_key, cantidad_media, indice_media):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for boton in botones:
        url = boton.get("url")
        if url:
            markup.add(types.InlineKeyboardButton(
                str(boton.get("texto") or "Abrir"),
                url=url,
            ))
    if cantidad_media > 1:
        navegacion = []
        if indice_media > 0:
            navegacion.append(types.InlineKeyboardButton(
                "◀️ Anterior",
                callback_data=(
                    f"btnpreview_nav|{contexto}|{destino_key}|{indice_media - 1}"
                ),
            ))
        navegacion.append(types.InlineKeyboardButton(
            f"📎 {indice_media + 1}/{cantidad_media}",
            callback_data=(
                f"btnpreview_info|{contexto}|{destino_key}|{indice_media}"
            ),
        ))
        if indice_media + 1 < cantidad_media:
            navegacion.append(types.InlineKeyboardButton(
                "Siguiente ▶️",
                callback_data=(
                    f"btnpreview_nav|{contexto}|{destino_key}|{indice_media + 1}"
                ),
            ))
        if navegacion:
            markup.row(*navegacion)
    markup.add(types.InlineKeyboardButton(
        "🔙 Regresar",
        callback_data=f"btnpreview_back|{contexto}|{destino_key}",
    ))
    return markup


def registrar_panel_privado(chat_id, message_id, tipo):
    if int(chat_id) <= 0 or not message_id:
        return
    with PANEL_LOCK:
        PANELES_PRIVADOS.upsert(
            {
                "chat_id": str(chat_id),
                "message_id": message_id,
                "tipo": "foto" if tipo == "photo" else tipo,
                "protect_content": False,
            },
            PANEL_QUERY.chat_id == str(chat_id),
        )


def guardar_contexto_recurrente_panel(
    chat_id, message_id, botones_key, destino_key
):
    if int(chat_id) <= 0 or not message_id:
        return
    with PANEL_LOCK:
        registro = PANELES_PRIVADOS.get(
            PANEL_QUERY.chat_id == str(chat_id)
        )
        if not registro or str(registro.get("message_id")) != str(message_id):
            return
        PANELES_PRIVADOS.update(
            {
                "recurrente_botones_key": botones_key,
                "recurrente_destino_key": destino_key,
            },
            PANEL_QUERY.chat_id == str(chat_id),
        )


def obtener_botones_key_panel_recurrente(chat_id, message, destino_key):
    message_id = getattr(message, "message_id", None)
    if int(chat_id) > 0:
        with PANEL_LOCK:
            registro = PANELES_PRIVADOS.get(
                PANEL_QUERY.chat_id == str(chat_id)
            )
        if (
            registro
            and str(registro.get("message_id")) == str(message_id)
            and registro.get("recurrente_destino_key") == destino_key
        ):
            return registro.get("recurrente_botones_key", destino_key)
    return (
        cargar_config()
        .get("recurrentes", {})
        .get(destino_key, {})
        .get("botones_key", destino_key)
    )


def input_media_vista_previa(item, caption):
    clases = {
        "photo": types.InputMediaPhoto,
        "video": types.InputMediaVideo,
        "document": types.InputMediaDocument,
        "audio": types.InputMediaAudio,
        "animation": types.InputMediaAnimation,
    }
    clase = clases.get(item.get("media_type"))
    if not clase:
        raise ValueError("Tipo de archivo multimedia no compatible.")
    opciones = {"media": item["media_id"]}
    if caption:
        opciones.update(caption=caption, parse_mode="HTML")
    return clase(**opciones)


def enviar_media_vista_previa(chat_id, item, caption, markup):
    metodos = {
        "photo": bot.send_photo,
        "video": bot.send_video,
        "document": bot.send_document,
        "audio": bot.send_audio,
        "animation": bot.send_animation,
    }
    metodo = metodos.get(item.get("media_type"))
    if not metodo:
        raise ValueError("Tipo de archivo multimedia no compatible.")
    return metodo(
        chat_id,
        item["media_id"],
        caption=caption or None,
        parse_mode="HTML" if caption else None,
        reply_markup=markup,
    )


def mostrar_vista_previa_real(
    chat_id_admin,
    destino_key,
    message=None,
    contexto="buttons",
    indice_media=0,
):
    botones_key_retorno = (
        obtener_botones_key_panel_recurrente(
            chat_id_admin, message, destino_key
        )
        if contexto == "rec"
        else None
    )

    def guardar_contexto(message_panel):
        if contexto == "rec" and message_panel:
            guardar_contexto_recurrente_panel(
                chat_id_admin,
                getattr(message_panel, "message_id", None),
                botones_key_retorno or destino_key,
                destino_key,
            )

    contenido = cargar_contenido_vista_previa(destino_key)
    nombre_destino = html.escape(CANALES[destino_key]["nombre"])
    if not contenido:
        texto = (
            f"No hay una publicación real guardada para "
            f"<b>{nombre_destino}</b>."
        )
        markup = markup_vista_previa([], contexto, destino_key, 0, 0)
        panel = editar_o_enviar_panel(
            chat_id_admin,
            texto,
            markup,
            message=message,
            forzar_texto=True,
        )
        guardar_contexto(panel)
        return False

    botones = cargar_botones_custom(contenido["botones_key"])
    media_items = contenido["media_items"]
    texto = str(contenido.get("texto") or "")
    markup = markup_vista_previa(
        botones,
        contexto,
        destino_key,
        len(media_items),
        indice_media,
    )
    if not media_items:
        if not texto.strip():
            texto = f"La publicación de <b>{nombre_destino}</b> no tiene texto ni multimedia."
        panel = editar_o_enviar_panel(
            chat_id_admin,
            texto,
            markup,
            message=message,
            forzar_texto=True,
        )
        guardar_contexto(panel)
        return True

    if indice_media < 0 or indice_media >= len(media_items):
        indice_media = 0
        markup = markup_vista_previa(
            botones, contexto, destino_key, len(media_items), indice_media
        )
    item = media_items[indice_media]
    caption = texto
    if len(caption) > 1024:
        caption = caption[:1021] + "…"

    registro = None
    if int(chat_id_admin) > 0:
        with PANEL_LOCK:
            registro = PANELES_PRIVADOS.get(
                PANEL_QUERY.chat_id == str(chat_id_admin)
            )
    mensaje_actual = getattr(message, "message_id", None)
    if not mensaje_actual and registro:
        mensaje_actual = registro.get("message_id")
    tipos_media = {"foto", "photo", "video", "document", "audio", "animation"}
    if (
        mensaje_actual
        and registro
        and str(registro.get("message_id")) == str(mensaje_actual)
        and registro.get("tipo") in tipos_media
    ):
        try:
            actualizado = bot.edit_message_media(
                media=input_media_vista_previa(item, caption),
                chat_id=chat_id_admin,
                message_id=mensaje_actual,
                reply_markup=markup,
            )
            registrar_panel_privado(
                chat_id_admin, mensaje_actual, item["media_type"]
            )
            guardar_contexto(actualizado or message)
            return actualizado
        except Exception as error:
            if "message is not modified" in str(error).lower():
                return message
            app.logger.info(
                "No se pudo editar el archivo del panel de vista previa %s.",
                mensaje_actual,
            )

    if mensaje_actual:
        try:
            bot.delete_message(chat_id_admin, mensaje_actual)
        except Exception as error:
            app.logger.exception(
                "No se pudo reemplazar el mensaje anterior por la vista previa."
            )
            raise RuntimeError(
                "No pude reemplazar el panel anterior por la vista previa."
            ) from error
    nuevo = enviar_media_vista_previa(chat_id_admin, item, caption, markup)
    registrar_panel_privado(
        chat_id_admin,
        getattr(nuevo, "message_id", None),
        item["media_type"],
    )
    guardar_contexto(nuevo)
    return True

# ═══════════════════════════════════════════════════════════════════
# 🛡️ PROTECCIÓN CONTRA GRUPOS
# ═══════════════════════════════════════════════════════════════════
GROUP_MESSAGE_TIMES = {}
GROUP_ADMIN_CACHE = {}
GROUP_MODERATION_LOCK = threading.Lock()
GROUP_TIMEZONE = ZoneInfo("America/Port_of_Spain")
CAPTCHA_PENDIENTES = {}
GROUP_JOIN_TIMES = {}
GROUP_MEMBER_JOINED_AT = {}


def fragmentar_mensaje_telegram(texto, maximo=3600):
    partes = []
    restante = str(texto or "")
    while len(restante) > maximo:
        corte = restante.rfind("\n", 0, maximo)
        if corte < maximo // 2:
            corte = maximo
        partes.append(restante[:corte])
        restante = restante[corte:].lstrip("\n")
    if restante:
        partes.append(restante)
    return partes or [""]


def _expirar_captcha(chat_id, user_id):
    llave = (str(chat_id), int(user_id))
    pendiente = CAPTCHA_PENDIENTES.pop(llave, None)
    if not pendiente:
        return
    ajustes = obtener_ajustes_chat(chat_id) or {}
    action = str(ajustes.get("captcha_action", "ban"))
    try:
        if action == "warn":
            canal_key = buscar_destino_por_chat_id(chat_id)
            total = 0
            if canal_key:
                def registrar(ajustes_actuales):
                    nonlocal total
                    warnings = ajustes_actuales.setdefault("warnings", {})
                    clave = str(user_id)
                    total = int(warnings.get(clave, 0) or 0) + 1
                    warnings[clave] = total
                actualizar_ajustes_grupo(canal_key, registrar)
                latest = obtener_ajustes_grupo(canal_key) or ajustes
                limit = max(1, int(latest.get("warning_limit", 3) or 3))
                if total >= limit:
                    action_at_limit = str(latest.get("warning_action", "mute"))
                    if action_at_limit not in ("warn", "off", "delete"):
                        _aplicar_sancion_grupo(
                            chat_id,
                            user_id,
                            action_at_limit,
                            latest.get("warning_duration_seconds", 3600),
                        )
            bot.send_message(chat_id, "⚠️ Un miembro no completó el CAPTCHA y recibió una advertencia.")
        elif action in ("kick", "mute", "ban"):
            duration = ajustes.get("warning_duration_seconds", 3600)
            _aplicar_sancion_grupo(chat_id, user_id, action, duration)
            bot.send_message(
                chat_id,
                "⛔ Se aplicó el castigo configurado a un miembro que no completó el CAPTCHA.",
            )
        if ajustes.get("captcha_delete_service_message") and pendiente.get("message_id"):
            bot.delete_message(chat_id, pendiente["message_id"])
        elif pendiente.get("message_id"):
            bot.edit_message_text(
                "⌛ El tiempo para completar la verificación terminó.",
                chat_id,
                pendiente["message_id"],
            )
    except Exception:
        app.logger.exception("No se pudo aplicar la acción al CAPTCHA vencido.")


def procesar_evento_miembro_grupo(update):
    if update.chat.type not in ("group", "supergroup"):
        return
    ajustes = obtener_ajustes_chat(update.chat.id)
    if not ajustes:
        return

    miembro_nuevo = update.new_chat_member
    miembro_anterior = update.old_chat_member
    usuario = getattr(miembro_nuevo, "user", None)
    if not usuario:
        return

    estados_activos = ("member", "administrator", "creator")
    estaba = miembro_anterior.status in estados_activos
    esta = miembro_nuevo.status in estados_activos or (
        miembro_nuevo.status == "restricted" and getattr(miembro_nuevo, "is_member", False)
    )
    nombre = usuario.first_name or "Usuario"
    enabled = ajustes.get("enabled", {})

    member_key = (str(update.chat.id), int(usuario.id))
    if esta and not estaba:
        if usuario.is_bot:
            if ajustes.get("block_bots_enabled"):
                try:
                    bot.ban_chat_member(update.chat.id, usuario.id)
                except Exception:
                    app.logger.exception("No se pudo bloquear el bot que entró al grupo.")
            return
        now = time.monotonic()
        GROUP_MEMBER_JOINED_AT[member_key] = now
        blocked_ids = {str(value) for value in ajustes.get("blocked_user_ids", [])}
        if (
            str(usuario.id) in blocked_ids
            and (
                ajustes.get("block_join_enabled")
                or ajustes.get("block_leave_enabled")
                or ajustes.get("block_join_leave_enabled")
            )
        ):
            try:
                bot.ban_chat_member(update.chat.id, usuario.id)
            except Exception:
                app.logger.exception("No se pudo bloquear el reingreso de un usuario.")
            return
        if ajustes.get("block_multiple_join_enabled"):
            recent = [
                stamp for stamp in GROUP_JOIN_TIMES.get(str(update.chat.id), [])
                if now - stamp <= 10
            ]
            recent.append(now)
            GROUP_JOIN_TIMES[str(update.chat.id)] = recent[-100:]
            if len(recent) >= 5:
                try:
                    bot.ban_chat_member(update.chat.id, usuario.id)
                except Exception:
                    app.logger.exception("No se pudo frenar un ingreso múltiple.")
                return

    if estaba and not esta:
        joined_at = GROUP_MEMBER_JOINED_AT.pop(member_key, None)
        ingreso_rapido = (
            joined_at is not None and time.monotonic() - joined_at <= 60
        )
        bloquear_reingreso = bool(
            ajustes.get("block_leave_enabled")
            or (ajustes.get("block_join_leave_enabled") and ingreso_rapido)
        )
        if bloquear_reingreso:
            canal_key = buscar_destino_por_chat_id(update.chat.id)
            if canal_key:
                def guardar_bloqueo_salida(ajustes_actuales):
                    ids = [str(value) for value in ajustes_actuales.setdefault("blocked_user_ids", [])]
                    if str(usuario.id) not in ids:
                        ids.append(str(usuario.id))
                    ajustes_actuales["blocked_user_ids"] = ids[-1000:]
                actualizar_ajustes_grupo(canal_key, guardar_bloqueo_salida)
            try:
                bot.ban_chat_member(update.chat.id, usuario.id)
            except Exception:
                app.logger.exception("No se pudo bloquear el reingreso tras la salida.")

    if esta and not estaba:
        vistos = {str(value) for value in ajustes.get("welcome_seen_users", [])}
        primera_vez = str(usuario.id) not in vistos
        if primera_vez:
            def registrar_primera_entrada(ajustes_actuales):
                seen = ajustes_actuales.setdefault("welcome_seen_users", [])
                if str(usuario.id) not in {str(value) for value in seen}:
                    seen.append(str(usuario.id))
                    if len(seen) > 5000:
                        del seen[:-5000]
            canal_key = buscar_destino_por_chat_id(update.chat.id)
            if canal_key:
                actualizar_ajustes_grupo(canal_key, registrar_primera_entrada)
        if enabled.get("bienvenida"):
            welcome_mode = str(ajustes.get("welcome_mode", "always"))
            mostrar_bienvenida = welcome_mode != "first" or primera_vez
            if mostrar_bienvenida:
                texto = str(ajustes.get("welcome_text", "¡Bienvenido/a, {name}!"))
                target_chat = (
                    usuario.id
                    if ajustes.get("welcome_send_private")
                    else update.chat.id
                )
                try:
                    if (
                        ajustes.get("welcome_delete_previous")
                        and target_chat == update.chat.id
                        and ajustes.get("welcome_last_message_id")
                    ):
                        try:
                            bot.delete_message(
                                update.chat.id, ajustes["welcome_last_message_id"]
                            )
                        except Exception:
                            app.logger.info("No se pudo retirar la bienvenida anterior.")
                    welcome_message = bot.send_message(
                        target_chat, texto.replace("{name}", nombre)
                    )
                    if target_chat == update.chat.id:
                        canal_key = buscar_destino_por_chat_id(update.chat.id)
                        if canal_key:
                            actualizar_ajustes_grupo(
                                canal_key,
                                lambda actual: actual.update(
                                    {"welcome_last_message_id": welcome_message.message_id}
                                ),
                            )
                except Exception:
                    app.logger.exception("No se pudo enviar el mensaje de bienvenida.")
        if enabled.get("captcha") and miembro_nuevo.status == "member":
            llave = (str(update.chat.id), int(usuario.id))
            timeout = max(
                15, min(600, int(ajustes.get("captcha_timeout_seconds", 90) or 90))
            )
            mode = str(ajustes.get("captcha_mode", "button"))
            theme = str(ajustes.get("captcha_theme", "classic"))
            captcha_text = str(ajustes.get("captcha_text") or "")
            answer = None
            if mode == "math":
                left, right = random.randint(1, 9), random.randint(1, 9)
                answer = str(left + right)
                question = f"¿Cuánto es {left} + {right}?"
                if not captcha_text:
                    captcha_text = "{name}, resuelve esta pregunta para verificarte: {question}"
                if "{question}" in captcha_text:
                    captcha_text = captcha_text.replace("{question}", question)
                else:
                    captcha_text += f"\n\n{question}"
            elif not captcha_text:
                captcha_text = (
                    "{name}, pulsa el botón de verificación antes de {timeout} segundos."
                    if theme == "simple" else
                    "👋 {name}, pulsa el botón en {timeout} segundos para confirmar tu ingreso. "
                    "Mientras tanto, el bot eliminará tus mensajes."
                )
            if theme == "rules" and "{RULES}" not in captcha_text:
                captcha_text += "\n\n{RULES}"
            captcha_text = (
                captcha_text
                .replace("{name}", nombre)
                .replace("{timeout}", str(timeout))
                .replace("{RULES}", str(ajustes.get("rules", "")).strip() or "Todavía no se ha publicado un reglamento.")
            )
            CAPTCHA_PENDIENTES[llave] = {
                "joined_at": time.monotonic(),
                "mode": mode,
                "answer": answer,
            }
            markup = None
            if mode != "math":
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(
                    "✅ Verificar que soy una persona",
                    callback_data=f"captcha_ok|{update.chat.id}|{usuario.id}",
                ))
            try:
                segmentos = fragmentar_mensaje_telegram(captcha_text)
                for segmento in segmentos[:-1]:
                    bot.send_message(update.chat.id, segmento)
                challenge = bot.send_message(
                    update.chat.id, segmentos[-1], reply_markup=markup
                )
                CAPTCHA_PENDIENTES[llave]["message_id"] = challenge.message_id
                timer = threading.Timer(
                    timeout, _expirar_captcha, args=(update.chat.id, usuario.id)
                )
                timer.daemon = True
                timer.start()
            except Exception:
                CAPTCHA_PENDIENTES.pop(llave, None)
                app.logger.exception("No se pudo iniciar la verificación CAPTCHA.")
    elif estaba and not esta and enabled.get("despedida"):
        texto = str(ajustes.get("goodbye_text", "👋 {name} salió del grupo."))
        target_chat = (
            usuario.id if ajustes.get("goodbye_send_private") else update.chat.id
        )
        try:
            if (
                ajustes.get("goodbye_delete_previous")
                and target_chat == update.chat.id
                and ajustes.get("goodbye_last_message_id")
            ):
                try:
                    bot.delete_message(
                        update.chat.id, ajustes["goodbye_last_message_id"]
                    )
                except Exception:
                    app.logger.info("No se pudo retirar la despedida anterior.")
            goodbye_message = bot.send_message(
                target_chat, texto.replace("{name}", nombre)
            )
            if target_chat == update.chat.id:
                canal_key = buscar_destino_por_chat_id(update.chat.id)
                if canal_key:
                    actualizar_ajustes_grupo(
                        canal_key,
                        lambda actual: actual.update(
                            {"goodbye_last_message_id": goodbye_message.message_id}
                        ),
                    )
        except Exception:
            app.logger.exception("No se pudo enviar el mensaje de despedida.")


@bot.callback_query_handler(func=lambda call: call.data.startswith("captcha_ok|"))
def verificar_captcha_grupo(call):
    partes = call.data.split("|")
    if len(partes) != 3:
        bot.answer_callback_query(call.id, "No pude verificar esta solicitud.")
        return
    _, chat_id, user_id_text = partes
    try:
        user_id = int(user_id_text)
    except ValueError:
        bot.answer_callback_query(call.id, "La verificación ya no está disponible.")
        return
    if call.from_user.id != user_id:
        bot.answer_callback_query(call.id, "Este botón es para la persona que acaba de entrar.")
        return
    llave = (str(chat_id), user_id)
    pendiente = CAPTCHA_PENDIENTES.pop(llave, None)
    if not pendiente:
        bot.answer_callback_query(call.id, "La verificación expiró o ya se completó.")
        return
    bot.answer_callback_query(call.id, "Verificación completada.")
    ajustes = obtener_ajustes_chat(chat_id) or {}
    try:
        if ajustes.get("captcha_delete_service_message"):
            bot.delete_message(int(chat_id), pendiente["message_id"])
        else:
            bot.edit_message_text(
                f"✅ {html.escape(call.from_user.first_name or 'Miembro')} ya está verificado.",
                int(chat_id),
                pendiente["message_id"],
                parse_mode="HTML",
            )
    except Exception:
        app.logger.exception("No se pudo actualizar el mensaje CAPTCHA.")


def obtener_ajustes_chat(chat_id):
    ajustes = cargar_config().get("group_settings", {}).get(str(chat_id))
    if not ajustes:
        return None
    return ajustes


def es_administrador_grupo(chat_id, user_id):
    ahora = time.monotonic()
    cache_key = (str(chat_id), int(user_id))
    with GROUP_MODERATION_LOCK:
        cached = GROUP_ADMIN_CACHE.get(cache_key)
        if cached and cached[0] > ahora:
            return cached[1]
    try:
        miembro = bot.get_chat_member(chat_id, user_id)
        resultado = miembro.status in ("creator", "administrator")
    except Exception:
        app.logger.exception("No se pudo verificar el rol de un miembro del grupo.")
        return None
    with GROUP_MODERATION_LOCK:
        GROUP_ADMIN_CACHE[cache_key] = (ahora + 30, resultado)
    return resultado


def _borrar_mensaje_grupo(message):
    try:
        bot.delete_message(message.chat.id, message.message_id)
        return True
    except Exception:
        app.logger.exception("No se pudo borrar un mensaje moderado.")
        return False


def _enviar_registro_moderacion(ajustes, chat_id, texto):
    destino = ajustes.get("log_chat_id") or int(ADMIN_ID)
    try:
        bot.send_message(
            destino,
            f"🛡️ <b>Moderación</b>\n{html.escape(str(ajustes.get('title', chat_id)))}\n"
            f"{html.escape(texto)}",
            parse_mode="HTML",
        )
    except Exception:
        app.logger.exception("No se pudo enviar un registro de moderación.")


def _obtener_objetivo_comando(message):
    partes = (message.text or "").split()
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id, partes[1:]
    if len(partes) > 1 and partes[1].lstrip("-").isdigit():
        return int(partes[1]), partes[2:]
    return None, partes[1:]


def _permisos_silencio():
    return types.ChatPermissions(
        can_send_messages=False,
        can_send_audios=False,
        can_send_documents=False,
        can_send_photos=False,
        can_send_videos=False,
        can_send_video_notes=False,
        can_send_voice_notes=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
    )


def _seleccionar_fragmento_reglas(reglas, argumento):
    argumento = (argumento or "").strip()
    if not argumento:
        return reglas
    parrafos = [
        parte.strip()
        for parte in re.split(r"\n\s*\n", reglas)
        if parte.strip()
    ]
    if not parrafos:
        parrafos = [linea.strip() for linea in reglas.splitlines() if linea.strip()]
    elif len(parrafos) == 1:
        lineas = [linea.strip() for linea in reglas.splitlines() if linea.strip()]
        if len(lineas) > 1:
            parrafos = lineas
    if argumento.isdecimal():
        indice = int(argumento) - 1
        if 0 <= indice < len(parrafos):
            return parrafos[indice]
    objetivo = argumento.casefold()
    coincidencias_linea = [
        linea.strip()
        for linea in reglas.splitlines()
        if objetivo in linea.casefold()
    ]
    if coincidencias_linea:
        return "\n".join(coincidencias_linea)
    coincidencias_parrafo = [
        parrafo for parrafo in parrafos if objetivo in parrafo.casefold()
    ]
    return "\n\n".join(coincidencias_parrafo)


def _enviar_media_reglamento(chat_id, multimedia):
    if not isinstance(multimedia, dict):
        return
    metodos = {
        "photo": bot.send_photo,
        "video": bot.send_video,
        "document": bot.send_document,
        "audio": bot.send_audio,
        "animation": bot.send_animation,
    }
    metodo = metodos.get(multimedia.get("media_type"))
    if not metodo or not multimedia.get("media_id"):
        raise ValueError("El archivo multimedia del Reglamento no es válido.")
    return metodo(chat_id, multimedia["media_id"])


def publicar_reglamento(
    chat_id,
    ajustes,
    argumento="",
    reply_to_message=None,
    es_admin=None,
    canal_key=None,
):
    if ajustes.get("rules_access", "all") == "admins" and es_admin is not True:
        texto_denegado = "Solo los administradores del grupo pueden consultar el reglamento."
        if reply_to_message:
            bot.reply_to(reply_to_message, texto_denegado)
        else:
            bot.send_message(chat_id, texto_denegado)
        return False

    reglas = str(ajustes.get("rules", "")).strip()
    if not reglas:
        respuesta = "Todavía no se ha publicado un reglamento."
    elif argumento:
        respuesta = _seleccionar_fragmento_reglas(reglas, argumento)
        if not respuesta:
            respuesta = f"No encontré una regla relacionada con «{argumento}»."
    else:
        respuesta = reglas

    mostrar_multimedia = bool(reglas and not argumento and respuesta == reglas)
    if mostrar_multimedia:
        try:
            _enviar_media_reglamento(
                chat_id, ajustes.get("rules_media_before")
            )
        except Exception:
            app.logger.exception("No se pudo mostrar el multimedia superior del Reglamento.")
            respuesta = "⚠️ No pude mostrar el multimedia superior.\n\n" + respuesta

    if canal_key not in CANALES:
        canal_key = buscar_destino_por_chat_id(chat_id)
    markup = construir_teclado_reglamento(canal_key, ajustes)
    opciones = {"reply_markup": markup} if markup else {}
    if reply_to_message:
        opciones["reply_to_message_id"] = reply_to_message.message_id
    publicado = bot.send_message(chat_id, respuesta, **opciones)

    if mostrar_multimedia:
        try:
            _enviar_media_reglamento(
                chat_id, ajustes.get("rules_media_after")
            )
        except Exception:
            app.logger.exception("No se pudo mostrar el multimedia inferior del Reglamento.")
    return publicado


def _gestionar_comando_moderacion(message, ajustes, es_admin, texto_override=None):
    texto = texto_override if texto_override is not None else (message.text or "")
    if not texto.strip():
        return False
    comando_completo = texto.split(maxsplit=1)[0].split("@", 1)[0].lower()
    chat_id = message.chat.id
    user_id = getattr(message.from_user, "id", None)
    if comando_completo in ("/rules", "rules"):
        partes_comando = texto.split(maxsplit=1)
        argumento = partes_comando[1].strip() if len(partes_comando) > 1 else ""
        publicar_reglamento(
            chat_id,
            ajustes,
            argumento=argumento,
            reply_to_message=message,
            es_admin=es_admin,
            canal_key=buscar_destino_por_chat_id(chat_id),
        )
        return True
    if comando_completo == "/tag":
        etiqueta = str(ajustes.get("tag", "")).strip()
        if etiqueta:
            bot.reply_to(message, etiqueta)
        return True
    if comando_completo in ("/grouplink", "/link"):
        enabled = bool(ajustes.get("group_link_enabled"))
        invite = str(ajustes.get("group_link") or "").strip()
        if not enabled or not invite:
            bot.reply_to(message, "El enlace del grupo está desactivado o aún no se ha configurado.")
        elif comando_completo == "/link" and es_admin is True:
            bot.reply_to(message, "Este comando es para miembros. Usa /grouplink para ver el enlace.")
        else:
            bot.reply_to(
                message,
                f'🔗 <a href="{html.escape(invite, quote=True)}">Abrir enlace del grupo</a>',
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        return True
    if comando_completo == "/report":
        if not ajustes.get("enabled", {}).get("reportes"):
            bot.reply_to(message, "Los reportes están desactivados en este grupo.")
            return True
        reportado = message.reply_to_message
        nombre = (
            getattr(getattr(reportado, "from_user", None), "first_name", None)
            or "miembro"
        )
        nota = texto.split(maxsplit=1)[1] if len(texto.split(maxsplit=1)) > 1 else ""
        detalle = (
            f"Reporte de {getattr(message.from_user, 'first_name', 'miembro')} "
            f"(ID {user_id})"
            + (f" sobre {nombre}." if reportado else ".")
            + (f" Nota: {nota}" if nota else "")
        )
        _enviar_registro_moderacion(ajustes, chat_id, detalle)
        bot.reply_to(message, "✅ Reporte enviado a la administración.")
        return True
    if comando_completo.startswith("/") and comando_completo[1:] in ajustes.get("custom_commands", {}):
        bot.reply_to(message, str(ajustes["custom_commands"][comando_completo[1:]]))
        return True

    if comando_completo not in ("/warn", "/ban", "/unban", "/mute"):
        return False
    if es_admin is not True:
        bot.reply_to(message, "Solo un administrador del grupo puede usar este comando.")
        return True

    objetivo, argumentos = _obtener_objetivo_comando(message)
    if objetivo is None:
        bot.reply_to(
            message,
            "Responde al mensaje de la persona o escribe su ID después del comando.",
        )
        return True

    try:
        if comando_completo == "/ban":
            bot.ban_chat_member(chat_id, objetivo)
            _registrar_sancion_grupo(chat_id, objetivo, "ban")
            bot.reply_to(message, f"🚫 Usuario {objetivo} expulsado y bloqueado.")
        elif comando_completo == "/unban":
            bot.unban_chat_member(chat_id, objetivo, only_if_banned=True)
            _registrar_sancion_grupo(chat_id, objetivo, None)
            bot.reply_to(message, f"✅ Bloqueo retirado para {objetivo}.")
        elif comando_completo == "/mute":
            duracion = argumentos[0] if argumentos and re.fullmatch(r"\d+[mhd]", argumentos[0].lower()) else "10m"
            cantidad = int(duracion[:-1])
            unidad = duracion[-1].lower()
            segundos = cantidad * {"m": 60, "h": 3600, "d": 86400}[unidad]
            if cantidad < 1 or segundos > 366 * 86400:
                raise ValueError("La duración debe estar entre 1 minuto y 366 días.")
            bot.restrict_chat_member(
                chat_id,
                objetivo,
                until_date=int(time.time() + segundos),
                permissions=_permisos_silencio(),
            )
            _registrar_sancion_grupo(chat_id, objetivo, "mute")
            bot.reply_to(message, f"🔇 Usuario {objetivo} silenciado por {duracion}.")
        else:
            if not ajustes.get("enabled", {}).get("advertencias"):
                bot.reply_to(message, "Activa Advertencias antes de usar /warn.")
                return True
            total = None
            def modificar(ajustes_actuales):
                nonlocal total
                advertencias = ajustes_actuales.setdefault("warnings", {})
                clave = str(objetivo)
                total = int(advertencias.get(clave, 0)) + 1
                advertencias[clave] = total
            actualizar_ajustes_grupo(
                buscar_destino_por_chat_id(chat_id), modificar
            )
            motivo = " ".join(argumentos).strip()
            current_settings = obtener_ajustes_chat(chat_id) or ajustes
            warning_limit = max(
                1, int(current_settings.get("warning_limit", 3) or 3)
            )
            bot.reply_to(
                message,
                f"⚠️ Advertencia {min(total, warning_limit)}/{warning_limit} para {objetivo}."
                + (f" Motivo: {motivo}" if motivo else ""),
            )
            if total >= warning_limit:
                sanction = str(current_settings.get("warning_action", "mute"))
                if sanction in ("off", "warn", "delete"):
                    sanction = "mute"
                try:
                    _aplicar_sancion_grupo(
                        chat_id,
                        objetivo,
                        sanction,
                        current_settings.get("warning_duration_seconds", 3600),
                    )
                except Exception:
                    app.logger.exception(
                        "No se pudo aplicar el castigo del límite de advertencias."
                    )
                    bot.reply_to(
                        message,
                        "No pude aplicar el castigo; revisa los permisos de administración del bot.",
                    )
                else:
                    bot.send_message(
                        chat_id,
                        f"🔇 Usuario {objetivo} sancionado por acumular "
                        f"{warning_limit} advertencias.",
                    )
        _enviar_registro_moderacion(
            ajustes,
            chat_id,
            f"Comando {comando_completo} ejecutado por {user_id} sobre {objetivo}.",
        )
    except ValueError as error:
        bot.reply_to(message, str(error))
    except Exception as error:
        app.logger.exception("Falló una acción de moderación.")
        bot.reply_to(
            message,
            "No pude completar la acción. Revisa que el bot sea administrador con permisos de "
            "restringir o expulsar miembros.\n"
            f"{str(error)[:300]}",
        )
    return True


def _en_horario_nocturno(ajustes):
    horas = ajustes.get("night_hours") or ["22:00", "07:00"]
    ahora = datetime.now(GROUP_TIMEZONE).strftime("%H:%M")
    inicio, fin = horas
    return inicio <= ahora < fin if inicio < fin else (ahora >= inicio or ahora < fin)


def _segundos_hasta_fin_horario(ajustes):
    hours = ajustes.get("night_hours") or ["22:00", "07:00"]
    start, end = hours
    now = datetime.now(GROUP_TIMEZONE)
    end_time = datetime.strptime(end, "%H:%M").time()
    end_at = datetime.combine(now.date(), end_time, tzinfo=GROUP_TIMEZONE)
    if start >= end and now.strftime("%H:%M") >= start:
        end_at += timedelta(days=1)
    return max(60, int((end_at - now).total_seconds()))


def _texto_tiene_alfabeto_no_latino(texto):
    letras = [caracter for caracter in texto if caracter.isalpha()]
    if not letras:
        return False
    no_latinas = 0
    for caracter in letras:
        nombre = unicodedata.name(caracter, "")
        if any(script in nombre for script in ("CYRILLIC", "GREEK", "ARABIC", "HEBREW")):
            no_latinas += 1
    return no_latinas / len(letras) >= 0.6


def _texto_y_urls_mensaje(message):
    partes = [
        getattr(message, "text", None) or "",
        getattr(message, "caption", None) or "",
    ]
    urls = []
    for atributo in ("entities", "caption_entities"):
        for entity in getattr(message, atributo, None) or []:
            entity_type = getattr(entity, "type", "")
            if entity_type == "text_link" and getattr(entity, "url", None):
                urls.append(str(entity.url))
            elif entity_type == "url":
                origen = getattr(message, "text", None) or getattr(message, "caption", None) or ""
                offset = int(getattr(entity, "offset", 0) or 0)
                length = int(getattr(entity, "length", 0) or 0)
                urls.append(origen[offset:offset + length])
    return " ".join(partes + urls).strip()


def _contiene_enlace_telegram(message, ajustes):
    texto = _texto_y_urls_mensaje(message)
    if re.search(r"(?i)(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/", texto):
        return True
    policy = _politica_ajuste(ajustes, "telegram_links")
    return bool(
        policy["username_spam"]
        and re.search(r"(?<![\w/])@[A-Za-z0-9_]{5,32}\b", texto)
    )


def _contiene_enlace_de_bot(message):
    texto = _texto_y_urls_mensaje(message)
    return bool(
        re.search(
            r"(?i)(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/"
            r"[A-Za-z0-9_]*bot(?:\b|[/?])|(?:\?|&)start(?:group)?=",
            texto,
        )
    )


def _contiene_enlace_externo(message):
    texto = _texto_y_urls_mensaje(message)
    for url in re.findall(
        r"(?i)(?:https?://|www\.)[^\s<>()]+|"
        r"(?<![@\w])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
        r"[a-z]{2,}"
        r"(?:/[^\s<>()]*)?",
        texto,
    ):
        if not re.search(r"(?i)(?:t\.me|telegram\.me)", url):
            return True
    return False


def _tipo_origen_reenvio(message):
    origin = getattr(message, "forward_origin", None)
    origin_type = str(getattr(origin, "type", "") or "").lower()
    if origin_type == "channel":
        return "channel", getattr(origin, "chat", None)
    if origin_type == "chat":
        chat = getattr(origin, "chat", None)
        chat_type = str(getattr(chat, "type", "") or "")
        return ("channel" if chat_type == "channel" else "group"), chat
    if origin_type in ("user", "hidden_user"):
        user = getattr(origin, "sender_user", None)
        if user is not None and getattr(user, "is_bot", False):
            return "bot", user
        return "user", user

    forwarded_chat = getattr(message, "forward_from_chat", None)
    if forwarded_chat is not None:
        chat_type = str(getattr(forwarded_chat, "type", "") or "")
        return ("channel" if chat_type == "channel" else "group"), forwarded_chat
    forwarded_user = getattr(message, "forward_from", None)
    if forwarded_user is not None:
        return ("bot" if getattr(forwarded_user, "is_bot", False) else "user"), forwarded_user
    if (
        getattr(message, "forward_date", None)
        or getattr(message, "forward_sender_name", None)
        or origin is not None
    ):
        return "user", None
    return None, None


def _tipo_origen_cita(message):
    quote = getattr(message, "quote", None)
    external = getattr(message, "external_reply", None)
    origin = getattr(external, "origin", None) if external else None
    if quote is None and external is None:
        for entity in getattr(message, "entities", None) or []:
            if str(getattr(entity, "type", "")).lower() in (
                "blockquote", "expandable_blockquote"
            ):
                return "user", None
        return None, None
    if origin is not None:
        origin_type = str(getattr(origin, "type", "") or "").lower()
        if origin_type == "channel":
            return "channel", getattr(origin, "chat", None)
        if origin_type == "chat":
            chat = getattr(origin, "chat", None)
            return (
                "channel" if getattr(chat, "type", "") == "channel" else "group",
                chat,
            )
        user = getattr(origin, "sender_user", None)
        return ("bot" if getattr(user, "is_bot", False) else "user"), user
    return "user", None


def _tipo_multimedia_moderacion(message):
    content_type = str(getattr(message, "content_type", "") or "")
    if content_type == "story":
        return "story"
    if getattr(message, "media_group_id", None):
        return "album"
    if content_type == "photo":
        return "photo"
    if content_type == "video":
        return "live_photo" if getattr(message, "live_photo", None) else "video"
    if content_type == "animation":
        return "animation"
    if content_type == "sticker":
        sticker = getattr(message, "sticker", None)
        return (
            "animated_sticker"
            if getattr(sticker, "is_animated", False) or getattr(sticker, "is_video", False)
            else "sticker"
        )
    if content_type in ("document", "audio", "voice", "video_note"):
        return "document" if content_type != "video_note" else "video"
    if content_type == "live_photo":
        return "live_photo"
    return None


def _politica_exime_mensaje(message, policy):
    exceptions = {str(value).strip().casefold() for value in policy.get("exceptions", [])}
    if not exceptions:
        return False
    user = getattr(message, "from_user", None)
    if user is not None:
        if str(getattr(user, "id", "")) in exceptions:
            return True
        username = str(getattr(user, "username", "") or "").casefold()
        if username and ("@" + username) in exceptions:
            return True
    return False


def _registrar_sancion_grupo(chat_id, user_id, action):
    canal_key = buscar_destino_por_chat_id(chat_id)
    if not canal_key:
        return
    user_key = str(int(user_id))
    def guardar(ajustes):
        sanciones = ajustes.setdefault("known_sanctions", {})
        if action in ("mute", "ban"):
            sanciones[user_key] = action
        else:
            sanciones.pop(user_key, None)
    actualizar_ajustes_grupo(canal_key, guardar)


def _aplicar_sancion_grupo(chat_id, user_id, action, duration_seconds=3600):
    if action in ("off", "", None):
        return
    if action == "kick":
        bot.ban_chat_member(chat_id, user_id)
        bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
    elif action == "mute":
        seconds = max(60, min(int(duration_seconds or 3600), 366 * 86400))
        bot.restrict_chat_member(
            chat_id,
            user_id,
            until_date=int(time.time() + seconds),
            permissions=_permisos_silencio(),
        )
        _registrar_sancion_grupo(chat_id, user_id, "mute")
    elif action == "ban":
        bot.ban_chat_member(chat_id, user_id)
        _registrar_sancion_grupo(chat_id, user_id, "ban")


def _incrementar_advertencia_automatica(message, ajustes, motivo):
    canal_key = buscar_destino_por_chat_id(message.chat.id)
    user = getattr(message, "from_user", None)
    if not canal_key or not user:
        return
    total = 0
    def guardar(ajustes_actuales):
        nonlocal total
        warnings = ajustes_actuales.setdefault("warnings", {})
        user_key = str(user.id)
        total = int(warnings.get(user_key, 0) or 0) + 1
        warnings[user_key] = total
    actualizar_ajustes_grupo(canal_key, guardar)
    latest = obtener_ajustes_grupo(canal_key) or ajustes
    limit = max(1, int(latest.get("warning_limit", 3) or 3))
    nombre = html.escape(
        str(getattr(user, "first_name", None) or getattr(user, "username", None) or user.id)
    )
    bot.send_message(
        message.chat.id,
        f"⚠️ <a href=\"tg://user?id={int(user.id)}\">{nombre}</a>: "
        f"advertencia {min(total, limit)}/{limit}."
        + (f" Motivo: {html.escape(motivo)}" if motivo else ""),
        parse_mode="HTML",
    )
    if total >= limit:
        sanction = str(latest.get("warning_action", "mute"))
        if sanction not in ("warn", "off", "delete"):
            try:
                _aplicar_sancion_grupo(
                    message.chat.id,
                    user.id,
                    sanction,
                    latest.get("warning_duration_seconds", 3600),
                )
            except Exception:
                app.logger.exception("No se pudo aplicar el castigo por advertencias.")


def _aplicar_politica_moderacion(message, ajustes, policy_id, motivo):
    policy = _politica_ajuste(ajustes, policy_id)
    action = policy["action"]
    delete_message = policy["delete_messages"]
    if action == "off" and not delete_message:
        return False
    if _politica_exime_mensaje(message, policy):
        return False
    user = getattr(message, "from_user", None)
    if delete_message:
        _borrar_mensaje_grupo(message)
    if action == "warn" and user:
        _incrementar_advertencia_automatica(message, ajustes, motivo)
    elif action in ("kick", "mute", "ban") and user:
        try:
            _aplicar_sancion_grupo(
                message.chat.id,
                user.id,
                action,
                ajustes.get("warning_duration_seconds", 3600),
            )
        except Exception:
            app.logger.exception("No se pudo aplicar una sanción automática.")
    _enviar_registro_moderacion(
        ajustes,
        message.chat.id,
        f"{motivo} (usuario {getattr(user, 'id', 'desconocido')}; acción {_texto_accion_moderacion(action)}).",
    )
    return True


def _aplicar_politica_por_fuente(message, ajustes, prefix, source, source_object, motivo):
    if not source:
        return False
    policy_id = f"{prefix}_{source}"
    policy = _politica_ajuste(ajustes, policy_id)
    exceptions = {str(value).strip().casefold() for value in policy.get("exceptions", [])}
    source_id = getattr(source_object, "id", None)
    source_username = str(getattr(source_object, "username", "") or "").casefold()
    if (
        source_id is not None and str(source_id) in exceptions
    ) or (source_username and "@" + source_username in exceptions):
        return False
    return _aplicar_politica_moderacion(message, ajustes, policy_id, motivo)


def _remitente_enmascarado_exento(message, ajustes):
    sender_chat = getattr(message, "sender_chat", None)
    if not sender_chat:
        return False
    exceptions = {str(value).strip().casefold() for value in ajustes.get("masked_exceptions", [])}
    sender_id = str(getattr(sender_chat, "id", ""))
    username = str(getattr(sender_chat, "username", "") or "").casefold()
    return sender_id in exceptions or (username and "@" + username in exceptions)


def responder_atajo_publico_grupo(chat_id, action, ajustes, usuario_id, message=None):
    if action == "rules":
        return publicar_reglamento(
            chat_id,
            ajustes,
            reply_to_message=message,
            es_admin=es_administrador_grupo(chat_id, usuario_id),
            canal_key=buscar_destino_por_chat_id(chat_id),
        )

    markup = types.InlineKeyboardMarkup(row_width=2)
    if action == "start":
        link = enlace_bot_privado()
        texto = (
            "🏠 Para abrir el menú privado del bot, pulsa el botón. "
            "Los métodos de pago solo se muestran en privado."
        )
        if link:
            markup.add(types.InlineKeyboardButton("💬 Abrir el bot", url=link))
        else:
            texto += " Busca el bot y envíale /start."
        return bot.send_message(
            chat_id, texto, reply_markup=markup if markup.keyboard else None
        )

    if action == "menu":
        markup.row(
            types.InlineKeyboardButton("📜 Reglas", callback_data="gpub|rules"),
            types.InlineKeyboardButton("🔗 Compartir", callback_data="gpub|share"),
        )
        markup.add(types.InlineKeyboardButton(
            "📹 Videochat", callback_data="gpub|videochat"
        ))
        link = enlace_bot_privado()
        if link:
            markup.add(types.InlineKeyboardButton("💬 Abrir el bot", url=link))
        return bot.send_message(
            chat_id,
            "📋 <b>Menú rápido del grupo</b>\nSelecciona una opción:",
            parse_mode="HTML",
            reply_markup=markup,
        )

    if action == "share":
        link = enlace_invitacion_grupo(chat_id, ajustes)
        if not link:
            return bot.send_message(
                chat_id,
                "No hay un enlace público o de invitación disponible para compartir. "
                "Pide a un administrador que configure el enlace del grupo.",
            )
        share_url = (
            "https://t.me/share/url?url="
            + quote(link, safe="")
            + "&text="
            + quote("Te invito a unirte a este grupo.", safe="")
        )
        markup.add(types.InlineKeyboardButton("📤 Compartir invitación", url=share_url))
        return bot.send_message(
            chat_id, "🔗 Pulsa para compartir la invitación:", reply_markup=markup
        )

    if action == "videochat":
        link = enlace_videochat_grupo(chat_id)
        if not link:
            return bot.send_message(
                chat_id,
                "📹 Este grupo no tiene un @usuario público para crear un enlace directo. "
                "Abre el icono de llamada/cámara desde la información del grupo. "
                "El bot no puede iniciar la llamada por sí mismo.",
            )
        markup.add(types.InlineKeyboardButton("📹 Abrir videochat del grupo", url=link))
        return bot.send_message(
            chat_id,
            "📹 Pulsa el enlace para abrir el videochat del grupo. "
            "Telegram solo lo abrirá si hay una llamada disponible; el bot no puede iniciarla.",
            reply_markup=markup,
        )
    if action == "admin":
        markup.add(types.InlineKeyboardButton(
            "👤 Contactar a @Ja2610X",
            url=GROUP_ADMIN_CONTACT_URL,
        ))
        return bot.send_message(
            chat_id,
            "👤 Para contactar al administrador, pulsa el botón:",
            reply_markup=markup,
        )
    return None


@bot.callback_query_handler(func=lambda call: call.data.startswith("gpub|"))
def callback_atajo_publico_grupo(call):
    if not call.message or call.message.chat.type not in ("group", "supergroup"):
        bot.answer_callback_query(call.id, "Esta acción solo funciona en el grupo.")
        return
    canal_key = buscar_destino_por_chat_id(call.message.chat.id)
    if not canal_key or destino_archivado(canal_key):
        bot.answer_callback_query(call.id, "Este grupo no está disponible.")
        return
    action = call.data.split("|", 1)[1]
    if action not in ("rules", "share", "videochat"):
        bot.answer_callback_query(call.id, "Acción no válida.")
        return
    bot.answer_callback_query(call.id)
    responder_atajo_publico_grupo(
        call.message.chat.id,
        action,
        obtener_ajustes_grupo(canal_key) or {},
        call.from_user.id,
        message=call.message,
    )


def moderar_mensaje_grupo(message, ajustes):
    usuario = getattr(message, "from_user", None)
    enabled = ajustes.get("enabled", {})
    if not usuario:
        if (
            enabled.get("enmascarados")
            and not _remitente_enmascarado_exento(message, ajustes)
            and ajustes.get("masked_delete_messages", True)
        ):
            _borrar_mensaje_grupo(message)
        return
    if getattr(usuario, "is_bot", False):
        return
    es_admin = es_administrador_grupo(message.chat.id, usuario.id)
    pending_key = (str(message.chat.id), int(usuario.id))
    pending_captcha = CAPTCHA_PENDIENTES.get(pending_key)
    if pending_captcha and es_admin is not True:
        if pending_captcha.get("mode") == "math":
            answer = str(pending_captcha.get("answer", ""))
            received = (getattr(message, "text", "") or "").strip()
            if answer and received == answer:
                CAPTCHA_PENDIENTES.pop(pending_key, None)
                _borrar_mensaje_grupo(message)
                try:
                    if ajustes.get("captcha_delete_service_message"):
                        bot.delete_message(
                            message.chat.id, pending_captcha["message_id"]
                        )
                    else:
                        bot.edit_message_text(
                            f"✅ {html.escape(usuario.first_name or 'Miembro')} ya está verificado.",
                            message.chat.id,
                            pending_captcha["message_id"],
                            parse_mode="HTML",
                        )
                except Exception:
                    app.logger.exception("No se pudo actualizar el mensaje CAPTCHA.")
                return
        _borrar_mensaje_grupo(message)
        return
    texto = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()
    atajos_base = atajos_fijos_grupo(ajustes)
    accion_atajo = next(
        (
            item["action"]
            for item in atajos_base
            if str(item.get("label", "")).casefold() == texto.casefold()
        ),
        None,
    )
    if not accion_atajo:
        comando = texto.split(maxsplit=1)[0].split("@", 1)[0].casefold() if texto else ""
        accion_atajo = {
            "/start": "__group_start__",
            "/menu": "__group_menu__",
            "/compartir": "__group_share__",
            "/reglas": "/rules",
            "/vchat": "__videochat_guide__",
            "/admin": "__group_admin__",
        }.get(comando)
    acciones_grupo = {
        "__group_start__": "start",
        "__group_menu__": "menu",
        "__group_share__": "share",
        "__group_admin__": "admin",
        "__videochat_guide__": "videochat",
    }
    if accion_atajo in acciones_grupo:
        responder_atajo_publico_grupo(
            message.chat.id,
            acciones_grupo[accion_atajo],
            ajustes,
            usuario.id,
            message=message,
        )
        eliminar_mensaje_disparador(message)
        return
    if accion_atajo == "/rules":
        _gestionar_comando_moderacion(
            message, ajustes, es_admin, texto_override="/rules"
        )
        eliminar_mensaje_disparador(message)
        return
    atajo = next(
        (
            item for item in ajustes.get("quick_buttons", [])
            if str(item.get("label", "")).casefold() == texto.casefold()
        ),
        None,
    )
    if atajo:
        action = str(atajo.get("action", "")).strip()
        if action.startswith(("http://", "https://")):
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔗 Abrir enlace", url=action))
            bot.reply_to(
                message,
                "Pulsa el botón para abrir el enlace:",
                reply_markup=markup,
            )
        elif action.startswith("/"):
            if not _gestionar_comando_moderacion(
                message, ajustes, es_admin, texto_override=action
            ):
                bot.reply_to(
                    message,
                    f"El comando {html.escape(action)} todavía no está implementado en este bot.",
                    parse_mode="HTML",
                )
        eliminar_mensaje_disparador(message)
        return
    if _gestionar_comando_moderacion(message, ajustes, es_admin):
        eliminar_mensaje_disparador(message)
        return
    if es_admin is not False:
        return

    if enabled.get("permisos"):
        _borrar_mensaje_grupo(message)
        return

    texto_busqueda = texto.casefold()

    if enabled.get("modo_nocturno") and _en_horario_nocturno(ajustes):
        action = str(ajustes.get("night_mode_action", "delete"))
        if action == "mute":
            try:
                _aplicar_sancion_grupo(
                    message.chat.id,
                    usuario.id,
                    "mute",
                    _segundos_hasta_fin_horario(ajustes),
                )
            except Exception:
                app.logger.exception("No se pudo silenciar durante el horario nocturno.")
        if _borrar_mensaje_grupo(message):
            _enviar_registro_moderacion(ajustes, message.chat.id, f"Mensaje eliminado por modo nocturno (usuario {usuario.id}).")
        return
    if (
        enabled.get("enmascarados")
        and getattr(message, "sender_chat", None)
        and not _remitente_enmascarado_exento(message, ajustes)
        and ajustes.get("masked_delete_messages", True)
    ):
        _borrar_mensaje_grupo(message)
        return

    telegram_policy = _politica_ajuste(ajustes, "telegram_links")
    telegram_text = _texto_y_urls_mensaje(message)
    is_bot_link = _contiene_enlace_de_bot(message)
    has_telegram_link = bool(
        re.search(r"(?i)(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/", telegram_text)
    )
    has_username = bool(
        telegram_policy["username_spam"]
        and re.search(r"(?<![\w/])@[A-Za-z0-9_]{5,32}\b", telegram_text)
    )
    if (
        (is_bot_link and telegram_policy["bot_spam"])
        or (has_telegram_link and not is_bot_link)
        or has_username
    ):
        if _aplicar_politica_moderacion(
            message, ajustes, "telegram_links", "Enlace o usuario de Telegram"
        ):
            return

    if _contiene_enlace_externo(message) and _aplicar_politica_moderacion(
        message, ajustes, "internet_links", "Enlace de internet"
    ):
        return

    forward_source, forward_object = _tipo_origen_reenvio(message)
    if _aplicar_politica_por_fuente(
        message, ajustes, "forward", forward_source, forward_object, "Reenvío"
    ):
        return

    quote_source, quote_object = _tipo_origen_cita(message)
    if _aplicar_politica_por_fuente(
        message, ajustes, "quote", quote_source, quote_object, "Cita externa"
    ):
        return

    if enabled.get("antispam") or enabled.get("antiflood") or enabled.get("guardian"):
        ahora = time.monotonic()
        llave = (str(message.chat.id), int(usuario.id))
        with GROUP_MODERATION_LOCK:
            flood_window = max(
                1,
                min(
                    300,
                    int(
                        ajustes.get(
                            "flood_window_seconds",
                            5 if enabled.get("antiflood") else 15,
                        )
                        or 5
                    ),
                ),
            )
            tiempos = [
                t for t in GROUP_MESSAGE_TIMES.get(llave, [])
                if ahora - t <= max(15, flood_window)
            ]
            tiempos.append(ahora)
            GROUP_MESSAGE_TIMES[llave] = tiempos
        exceso_flood = (enabled.get("antiflood") or enabled.get("guardian")) and sum(
            1 for t in tiempos if ahora - t <= flood_window
        ) > max(1, int(ajustes.get("flood_limit", 5) or 5))
        exceso_spam = (enabled.get("antispam") or enabled.get("guardian")) and len(tiempos) > 12
        if exceso_flood or exceso_spam:
            action = str(
                ajustes.get(
                    "flood_action",
                    "delete" if enabled.get("antiflood") or enabled.get("guardian") else "off",
                )
            )
            if exceso_flood and enabled.get("guardian") and action == "off":
                _borrar_mensaje_grupo(message)
                _enviar_registro_moderacion(
                    ajustes, message.chat.id,
                    f"Mensaje eliminado por la protección Bot Guardián (usuario {usuario.id}).",
                )
                return
            if action == "delete":
                _borrar_mensaje_grupo(message)
                _enviar_registro_moderacion(
                    ajustes, message.chat.id,
                    f"Mensaje eliminado por spam/flood (usuario {usuario.id}).",
                )
                return
            if exceso_flood and _aplicar_politica_moderacion(
                message,
                ajustes,
                "flood",
                f"Anti-flood: más de {ajustes.get('flood_limit', 5)} mensajes en {flood_window} s",
            ):
                return
            if exceso_spam:
                _borrar_mensaje_grupo(message)
                _enviar_registro_moderacion(
                    ajustes, message.chat.id,
                    f"Mensaje eliminado por límite antispam (usuario {usuario.id}).",
                )
            return

    if texto:
        max_length = int(ajustes.get("max_length", 0) or 0)
        if max_length and len(texto) > max_length:
            _borrar_mensaje_grupo(message)
            return
        palabras = ajustes.get("blocked_words", [])
        if (enabled.get("palabras") or enabled.get("guardian") or enabled.get("bloqueos")) and any(
            str(palabra).casefold() in texto_busqueda for palabra in palabras if palabra
        ):
            if "blocked_words" not in ajustes.get("moderation_policies", {}):
                _borrar_mensaje_grupo(message)
                return
            if _aplicar_politica_moderacion(
                message, ajustes, "blocked_words", "Palabra prohibida"
            ):
                return
        if enabled.get("alfabetos") and _texto_tiene_alfabeto_no_latino(texto):
            _borrar_mensaje_grupo(message)
            return
        if enabled.get("antiporno") and re.search(
            r"(?<!\w)(porn|porno|xxx|nudes?|sexchat|onlyfans)(?!\w)",
            texto_busqueda,
        ):
            _borrar_mensaje_grupo(message)
            return
        if enabled.get("filtros"):
            for palabra, respuesta in ajustes.get("filters", {}).items():
                if str(palabra).casefold() in texto_busqueda:
                    bot.reply_to(message, str(respuesta))
                    break

    media_type = _tipo_multimedia_moderacion(message)
    if media_type:
        media_action = str(ajustes.get("media_policies", {}).get(media_type, "off"))
        if media_action != "off":
            if media_action == "delete":
                _borrar_mensaje_grupo(message)
                _enviar_registro_moderacion(
                    ajustes,
                    message.chat.id,
                    f"Contenido multimedia eliminado ({media_type}; usuario {usuario.id}).",
                )
            else:
                _aplicar_politica_moderacion(
                    message,
                    {
                        **ajustes,
                        "moderation_policies": {
                            **ajustes.get("moderation_policies", {}),
                            f"media_{media_type}": {
                                "action": media_action,
                                "delete_messages": False,
                                "exceptions": [],
                            },
                        },
                    },
                    f"media_{media_type}",
                    f"Tipo multimedia bloqueado: {media_type}",
                )
            return

    tipos_multimedia = {
        "photo", "video", "document", "audio", "voice", "video_note", "animation",
        "sticker", "story", "live_photo",
    }
    global_media_block = bool(
        ajustes.get("media_global_block", enabled.get("multimedia", False))
    )
    if (
        (global_media_block and message.content_type in tipos_multimedia)
        or (enabled.get("stickers_gif") and message.content_type in ("sticker", "animation"))
    ):
        _borrar_mensaje_grupo(message)


@bot.message_handler(func=lambda m: m.chat.type != "private")
def bloquear_grupos(message):
    if buscar_destino_por_chat_id(message.chat.id):
        if message.chat.type in ("group", "supergroup"):
            ajustes = obtener_ajustes_chat(message.chat.id)
            if ajustes:
                moderar_mensaje_grupo(message, ajustes)
        return
    try:
        bot.send_message(message.chat.id,
            "🚫 <b>ACCESO DENEGADO</b>\nEste bot solo responde en chats privados.",
            parse_mode="HTML")
        bot.leave_chat(message.chat.id)
    except:
        pass

# ═══════════════════════════════════════════════════════════════════
# 🔐 PANEL ADMIN  /admin
# ═══════════════════════════════════════════════════════════════════
def mostrar_panel_admin(chat_id, message=None):
    if str(chat_id) != str(ADMIN_ID):
        return None
    lineas_estado = []
    for key, info in CANALES.items():
        if destino_archivado(key):
            continue
        canal_id = obtener_canal_id(key)
        if canal_id:
            lineas_estado.append(
                f"✅ {html.escape(info['nombre'])}: <code>{html.escape(str(canal_id))}</code>"
            )
        else:
            lineas_estado.append(f"⚠️ {html.escape(info['nombre'])}: no configurado")
    estado_canal = "\n".join(lineas_estado)

    # Estado del Pase Exprés
    cfg = cargar_config()
    pe  = cfg.get("pase_expres", {})
    if pe.get("activo") and pase_expres_activo():
        estado_pe = f"🎟️ Pase Exprés: 🟢 Activo hasta <b>{pe.get('vence','?')}</b>"
        lbl_pe    = "🎟️ Pase Exprés  [🟢 ACTIVO]"
    else:
        estado_pe = "🎟️ Pase Exprés: 🔴 Inactivo"
        lbl_pe    = "🎟️ Pase Exprés  [🔴 inactivo]"

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(lbl_pe,                          callback_data="admin_pase_expres"),
        types.InlineKeyboardButton(
            "💳 Métodos de pago e imagen",
            callback_data="admin_pagos",
        ),
        types.InlineKeyboardButton("📋 Ver y administrar botones", callback_data="admin_ver_botones"),
        types.InlineKeyboardButton("⏰ Mensajes recurrentes", callback_data="admin_rec_menu"),
    )
    return editar_o_enviar_panel(
        chat_id,
        f"🔐 <b>PANEL DE ADMINISTRACIÓN</b>\n\n"
        f"{estado_canal}\n"
        f"{estado_pe}\n\n"
        f"¿Qué deseas hacer?",
        markup,
        message=message,
        forzar_texto=True,
    )

@bot.message_handler(commands=['admin'])
def panel_admin(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        return
    eliminar_mensaje_disparador(message)
    if message.chat.type != "private":
        bot.send_message(
            int(ADMIN_ID),
            "🔒 Por privacidad, abre /admin en el chat privado con el bot.",
        )
        return
    instalar_teclado_persistente(
        message.chat.id,
        "⌨️ Atajos disponibles en la barra inferior.",
        teclado_atajos_admin(),
        forzar=True,
    )
    mostrar_panel_admin(message.chat.id)


def markup_destinos_recurrentes():
    markup = types.InlineKeyboardMarkup(row_width=1)
    for destino_key, info in CANALES.items():
        if not obtener_canal_id(destino_key) or destino_archivado(destino_key):
            continue
        markup.add(types.InlineKeyboardButton(
            info["nombre"],
            callback_data=f"rec_destino|{destino_key}|{destino_key}",
        ))
    if not markup.keyboard:
        markup.add(types.InlineKeyboardButton(
            "No hay grupos o canales guardados",
            callback_data="rec_choose",
        ))
    markup.add(types.InlineKeyboardButton(
        "🔙 Volver al panel", callback_data="admin_volver"
    ))
    return markup


@bot.callback_query_handler(func=lambda call: call.data == "admin_rec_menu")
def panel_mensajes_recurrentes(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    BOTONES_RETURN_CALLBACK[str(call.message.chat.id)] = "admin_volver"
    editar_o_enviar_panel(
        call.message.chat.id,
        "⏰ <b>Mensajes recurrentes</b>\nSelecciona un destino guardado:",
        markup_destinos_recurrentes(),
        message=call.message,
    )


@bot.message_handler(
    func=lambda message: (
        message.chat.type == "private"
        and str(message.from_user.id) == str(ADMIN_ID)
        and message.text in (
            TEXTO_ATAJO_CONFIG,
            "Configuration",
            "⚙️ Configuration",
            "❌ Cancelar",
        )
    ),
    content_types=["text"],
)
def administrar_atajos(message):
    uid = message.from_user.id
    eliminar_mensaje_disparador(message)
    if message.text == "❌ Cancelar":
        estado = admin_estado.pop(uid, {})
        selector_message_id = estado.get("selector_message_id")
        if selector_message_id:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "↩️ Abrir configuración de grupos y canales",
                callback_data="admin_volver",
            ))
            editar_o_enviar_panel(
                message.chat.id,
                "Acción cancelada. El selector quedó cerrado.",
                markup,
                message_id=selector_message_id,
            )
        admin_estado[uid] = {
            "toolbar_message_id": estado.get("toolbar_message_id"),
        }
        reemplazar_teclado_selector(
            message.chat.id,
            uid,
            teclado_atajos_admin(),
            "⌨️ Atajos de administración disponibles en la barra inferior.",
        )
        admin_estado.pop(uid, None)
        return
    iniciar_selector_grupo(message.chat.id, uid)


@bot.message_handler(
    func=lambda message: (
        message.chat.type == "private"
        and str(message.from_user.id) == str(ADMIN_ID)
        and message.text == TEXTO_BUSCAR_USERNAME
    ),
    content_types=["text"],
)
def iniciar_busqueda_publica(message):
    eliminar_mensaje_disparador(message)
    estado = admin_estado.setdefault(message.from_user.id, {})
    estado["paso"] = "esperando_chat_compartido"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "↩️ Volver a destinos guardados", callback_data="grupo_selector"
    ))
    texto = (
        "🔎 <b>Buscar grupo o canal</b>\n\n"
        "Elige el tipo en la barra inferior. Telegram abrirá su selector con una búsqueda "
        "por nombre y los chats que la cuenta puede seleccionar."
    )
    panel = editar_o_enviar_panel(
        message.chat.id,
        texto,
        markup,
        message_id=estado.get("selector_message_id"),
    )
    if getattr(panel, "message_id", None):
        estado["selector_message_id"] = panel.message_id
    reemplazar_teclado_selector(
        message.chat.id,
        message.from_user.id,
        teclado_picker_tipo_chat(),
        "Elige «Buscar grupo» o «Buscar canal» para abrir la búsqueda de Telegram.",
    )


@bot.message_handler(
    func=lambda message: (
        message.chat.type == "private"
        and str(message.from_user.id) == str(ADMIN_ID)
        and message.text == TEXTO_VOLVER_SELECTOR
    ),
    content_types=["text"],
)
def volver_a_destinos_guardados(message):
    eliminar_mensaje_disparador(message)
    estado = admin_estado.get(message.from_user.id, {})
    if estado.get("paso") not in ("esperando_chat_compartido", "esperando_lookup_publico"):
        return
    estado["paso"] = "esperando_chat_compartido"
    mostrar_selector_destinos(
        message.chat.id,
        message_id=estado.get("selector_message_id"),
    )
    reemplazar_teclado_selector(
        message.chat.id,
        message.from_user.id,
        teclado_selector_grupos(),
        "Usa los botones inferiores para buscar otro grupo o canal, o consultar un usuario.",
    )


@bot.message_handler(
    func=lambda message: (
        message.chat.type == "private"
        and str(message.from_user.id) == str(ADMIN_ID)
        and message.content_type == "chat_shared"
    ),
    content_types=["chat_shared"],
)
def recibir_chat_seleccionado(message):
    estado = admin_estado.get(message.from_user.id, {})
    paso = estado.get("paso")
    compartido = getattr(message, "chat_shared", None)
    request_id = getattr(compartido, "request_id", None)
    if paso not in ("esperando_chat_compartido", "esperando_canal_registro"):
        if paso is not None or request_id not in (
            CHAT_REQUEST_GRUPO_ID,
            CHAT_REQUEST_CANAL_ID,
            CHAT_REQUEST_AGREGAR_BOT_GRUPO_ID,
            CHAT_REQUEST_AGREGAR_BOT_CANAL_ID,
        ):
            return
        estado = {"paso": "esperando_chat_compartido"}
        admin_estado[message.from_user.id] = estado
        paso = estado["paso"]
    eliminar_mensaje_disparador(message)

    if not compartido:
        editar_o_enviar_panel(
            message.chat.id,
            "No recibí los datos del chat. Intenta seleccionarlo otra vez.",
            types.InlineKeyboardMarkup(),
            message_id=estado.get("selector_message_id"),
        )
        return
    if paso == "esperando_canal_registro":
        canal_key = estado.get("canal_key")
        pagina = estado.get("pagina", 0)
        if request_id != CHAT_REQUEST_CANAL_ID:
            editar_o_enviar_panel(
                message.chat.id,
                "Elige un canal con el botón de selección.",
                types.InlineKeyboardMarkup(),
                message_id=estado.get("panel_message_id"),
            )
            return
        registro_id = str(compartido.chat_id)
        registro_titulo = (
            getattr(compartido, "title", None)
            or getattr(compartido, "username", None)
            or "Canal de registro"
        )
        actualizar_ajustes_grupo(
            canal_key,
            lambda ajustes: ajustes.update({
                "log_chat_id": registro_id,
                "log_chat_title": registro_titulo,
            }),
        )
        admin_estado.pop(message.from_user.id, None)
        instalar_teclado_persistente(
            message.chat.id,
            "⌨️ Atajos de administración disponibles en la barra inferior.",
            teclado_atajos_admin(),
            forzar=True,
        )
        mostrar_menu_funcion_grupo(
            message.chat.id,
            canal_key,
            "registro",
            pagina,
            aviso=(
                f"✅ Canal de registro guardado: <b>{html.escape(registro_titulo)}</b> "
                f"(<code>{html.escape(registro_id)}</code>)."
            ),
        )
        return

    if request_id in (
        CHAT_REQUEST_CANAL_ID,
        CHAT_REQUEST_AGREGAR_BOT_CANAL_ID,
    ):
        tipo = "canal"
    elif request_id in (
        CHAT_REQUEST_GRUPO_ID,
        CHAT_REQUEST_AGREGAR_BOT_GRUPO_ID,
    ):
        tipo = "grupo"
    else:
        editar_o_enviar_panel(
            message.chat.id,
            "La selección no coincide con el selector activo.",
            types.InlineKeyboardMarkup(),
            message_id=estado.get("selector_message_id"),
        )
        return

    chat_id = str(compartido.chat_id)
    title = getattr(compartido, "title", None) or getattr(compartido, "username", None) or "Grupo o canal"
    canal_key = obtener_o_crear_destino_compartido(chat_id, title, tipo)

    def guardar_ficha(ajustes):
        ajustes["chat_id"] = chat_id
        ajustes["title"] = title
        ajustes["type"] = tipo
    actualizar_ajustes_grupo(canal_key, guardar_ficha)
    selector_message_id = estado.get("selector_message_id")
    admin_estado[message.from_user.id] = {
        "paso": "esperando_chat_compartido",
        "selector_message_id": selector_message_id,
        "toolbar_message_id": estado.get("toolbar_message_id"),
    }
    reemplazar_teclado_selector(
        message.chat.id,
        message.from_user.id,
        teclado_selector_grupos(),
        "Destino seleccionado. Usa «Buscar grupo» o «Buscar canal» para consultar otro.",
    )
    aviso = None
    if request_id in (
        CHAT_REQUEST_AGREGAR_BOT_GRUPO_ID,
        CHAT_REQUEST_AGREGAR_BOT_CANAL_ID,
    ):
        try:
            bot_actual = bot.get_me()
            estado_bot = bot.get_chat_member(chat_id, bot_actual.id).status
            if estado_bot in ("administrator", "creator"):
                aviso = (
                    "✅ Telegram añadió el bot como administrador con los permisos "
                    "solicitados. Ya puedes abrir su configuración."
                )
            elif estado_bot == "member":
                aviso = (
                    "⚠️ El bot está en el chat, pero Telegram no lo confirmó como "
                    "administrador. Promuévelo desde Administradores y verifica los permisos."
                )
            else:
                aviso = (
                    "⚠️ El destino se guardó, pero el bot no figura como administrador. "
                    "Comprueba la lista de administradores del chat."
                )
        except Exception:
            app.logger.warning("No se pudo verificar el estado administrativo del bot.")
            aviso = (
                "✅ El destino se guardó. No pude verificar desde aquí si Telegram "
                "aplicó los permisos; revisa Administradores en el chat."
            )
    enviar_ficha_destino(
        message.chat.id, canal_key, chat_id, title, tipo,
        message_id=selector_message_id,
        aviso=aviso,
    )


@bot.message_handler(
    func=lambda message: (
        message.chat.type == "private"
        and str(message.from_user.id) == str(ADMIN_ID)
        and message.content_type == "users_shared"
    ),
    content_types=["users_shared"],
)
def recibir_usuario_compartido(message):
    estado = admin_estado.get(message.from_user.id, {})
    compartido = getattr(message, "users_shared", None)
    if getattr(compartido, "request_id", None) != USER_REQUEST_ID:
        return
    if estado.get("paso") not in ("esperando_chat_compartido", "esperando_lookup_publico"):
        if estado.get("paso") is not None:
            return
        estado = {"paso": "esperando_chat_compartido"}
        admin_estado[message.from_user.id] = estado
    eliminar_mensaje_disparador(message)
    usuarios = getattr(compartido, "users", []) if compartido else []
    if not usuarios:
        editar_o_enviar_panel(
            message.chat.id,
            "Telegram no compartió los datos del usuario.",
            types.InlineKeyboardMarkup(),
            message_id=estado.get("selector_message_id"),
        )
        return
    usuario = usuarios[0]
    nombre = " ".join(
        parte for parte in (
            getattr(usuario, "first_name", None),
            getattr(usuario, "last_name", None),
        ) if parte
    ) or "Usuario seleccionado"
    username = getattr(usuario, "username", None)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "📋 Copiar ID",
        copy_text=types.CopyTextButton(text=str(usuario.user_id)),
    ))
    admin_estado[message.from_user.id] = {
        **estado,
        "paso": "esperando_chat_compartido",
    }
    texto = (
        f"👤 <b>{html.escape(nombre)}</b>\n"
        f"Usuario: <b>{'@' + html.escape(username) if username else 'No compartido por Telegram'}</b>\n"
        f"ID: <code>{html.escape(str(usuario.user_id))}</code>\n\n"
        "Telegram solo comparte los campos autorizados por la persona."
    )
    editar_o_enviar_panel(
        message.chat.id,
        texto,
        markup,
        message_id=estado.get("selector_message_id"),
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("grupo_destino|"))
def callback_abrir_destino_guardado(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    canal_key = call.data.split("|", 1)[1]
    if canal_key not in CANALES or destino_archivado(canal_key):
        bot.answer_callback_query(call.id, "No encontré ese destino.")
        return
    chat_id = obtener_canal_id(canal_key)
    ajustes = obtener_ajustes_grupo(canal_key) or {}
    bot.answer_callback_query(call.id)
    enviar_ficha_destino(
        call.message.chat.id,
        canal_key,
        chat_id,
        ajustes.get("title") or CANALES[canal_key]["nombre"],
        ajustes.get("type", "grupo/canal"),
        message=call.message,
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("grupo_eliminar_confirmar|")
)
def confirmar_eliminar_destino(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    canal_key = call.data.split("|", 1)[1]
    if canal_key not in CANALES or destino_archivado(canal_key):
        bot.answer_callback_query(call.id, "No encontré ese destino.")
        return

    chat_id = obtener_canal_id(canal_key)
    ajustes = obtener_ajustes_grupo(canal_key) or {}
    titulo = ajustes.get("title") or CANALES[canal_key]["nombre"]
    tipo = ajustes.get("type", "grupo/canal")
    if destino_protegido_por_pagos(canal_key):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "↩️ Volver a la ficha",
            callback_data=f"grupo_ficha|{canal_key}",
        ))
        bot.answer_callback_query(call.id, "Este destino está protegido.")
        editar_o_enviar_panel(
            call.message.chat.id,
            f"🔒 <b>{html.escape(str(titulo))}</b> está vinculado al canal de acceso VIP. "
            "No se puede retirar desde esta lista para evitar interrumpir las aprobaciones "
            "y renovaciones de pago.",
            markup,
            message=call.message,
        )
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(
            "🗑️ Sí, eliminar de la lista",
            callback_data=f"grupo_eliminar|{canal_key}",
        ),
        types.InlineKeyboardButton(
            "↩️ Cancelar",
            callback_data=f"grupo_ficha|{canal_key}",
        ),
    )
    bot.answer_callback_query(call.id)
    editar_o_enviar_panel(
        call.message.chat.id,
        f"¿Quitar <b>{html.escape(str(titulo))}</b> de tu lista?\n"
        f"Tipo: <b>{html.escape(str(tipo))}</b>\n"
        f"ID: <code>{html.escape(str(chat_id))}</code>\n\n"
        "Se conservarán sus ajustes y botones. Cualquier mensaje recurrente se pausará. "
        "Si vuelves a agregar el mismo grupo o canal, se recuperarán sus datos.",
        markup,
        message=call.message,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("grupo_eliminar|"))
def eliminar_destino_de_lista(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    canal_key = call.data.split("|", 1)[1]
    if not archivar_destino_adicional(canal_key):
        mensaje = (
            "Este destino está protegido por el flujo VIP."
            if destino_protegido_por_pagos(canal_key)
            else "No encontré ese destino."
        )
        bot.answer_callback_query(call.id, mensaje, show_alert=True)
        return

    estado_anterior = admin_estado.get(call.from_user.id, {})
    selector = mostrar_selector_destinos(
        call.message.chat.id,
        message=call.message,
    )
    admin_estado[call.from_user.id] = {
        "paso": "esperando_chat_compartido",
        "selector_message_id": getattr(selector, "message_id", call.message.message_id),
        "toolbar_message_id": estado_anterior.get("toolbar_message_id"),
    }
    bot.answer_callback_query(call.id, "Se quitó de tu lista; sus datos se conservaron.")


@bot.callback_query_handler(func=lambda call: call.data.startswith("grupo_ficha|"))
def callback_volver_a_ficha_destino(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    canal_key = call.data.split("|", 1)[1]
    chat_id = (
        obtener_canal_id(canal_key)
        if canal_key in CANALES and not destino_archivado(canal_key)
        else None
    )
    ajustes = obtener_ajustes_grupo(canal_key) if chat_id else None
    if not chat_id:
        bot.answer_callback_query(call.id, "No encontré ese destino.")
        return
    bot.answer_callback_query(call.id)
    enviar_ficha_destino(
        call.message.chat.id,
        canal_key,
        chat_id,
        (ajustes or {}).get("title") or CANALES[canal_key]["nombre"],
        (ajustes or {}).get("type", "grupo/canal"),
        message=call.message,
    )


@bot.callback_query_handler(func=lambda call: call.data == "grupo_selector")
def callback_volver_selector_destinos(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    toolbar_message_id = admin_estado.get(call.from_user.id, {}).get("toolbar_message_id")
    admin_estado[call.from_user.id] = {
        "paso": "esperando_chat_compartido",
        "selector_message_id": call.message.message_id,
        "toolbar_message_id": toolbar_message_id,
    }
    selector = mostrar_selector_destinos(call.message.chat.id, message=call.message)
    admin_estado[call.from_user.id]["selector_message_id"] = getattr(
        selector, "message_id", call.message.message_id
    )
    reemplazar_teclado_selector(
        call.message.chat.id,
        call.from_user.id,
        teclado_selector_grupos(),
        "Usa los botones inferiores para buscar otro grupo o canal, o consultar un usuario.",
    )


@bot.callback_query_handler(func=lambda call: call.data == "grupo_lookup_add")
def callback_agregar_busqueda_publica(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    estado = admin_estado.get(call.from_user.id, {})
    resultado = estado.get("public_lookup")
    if not resultado:
        bot.answer_callback_query(call.id, "La búsqueda venció; inténtalo otra vez.")
        return
    canal_key = obtener_o_crear_destino_compartido(
        resultado["chat_id"], resultado["title"], resultado["type"]
    )
    actualizar_ajustes_grupo(
        canal_key,
        lambda ajustes: ajustes.update({
            "chat_id": str(resultado["chat_id"]),
            "title": resultado["title"],
            "type": resultado["type"],
        }),
    )
    admin_estado[call.from_user.id] = {
        "paso": "esperando_chat_compartido",
        "selector_message_id": call.message.message_id,
        "toolbar_message_id": estado.get("toolbar_message_id"),
    }
    bot.answer_callback_query(call.id, "Destino guardado.")
    reemplazar_teclado_selector(
        call.message.chat.id,
        call.from_user.id,
        teclado_selector_grupos(),
        "Destino guardado. Usa «Buscar grupo» o «Buscar canal» para consultar otro.",
    )
    enviar_ficha_destino(
        call.message.chat.id,
        canal_key,
        resultado["chat_id"],
        resultado["title"],
        resultado["type"],
        message=call.message,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("grupo_config|"))
def callback_configurar_grupo(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    partes = call.data.split("|")
    canal_key = partes[1] if len(partes) > 1 else ""
    pagina = 0
    if len(partes) > 2:
        try:
            pagina = max(0, int(partes[2]))
        except ValueError:
            pagina = 0
    mostrar_configuracion_grupo(
        call.message.chat.id, canal_key, pagina, message=call.message
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("grupo_botones|"))
def callback_gestionar_botones_grupo(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    partes = call.data.split("|")
    canal_key = partes[1] if len(partes) > 1 else ""
    pagina = 0
    if len(partes) > 2:
        try:
            pagina = max(0, int(partes[2]))
        except ValueError:
            pagina = 0
    if canal_key not in CANALES or not obtener_canal_id(canal_key):
        bot.send_message(call.message.chat.id, "Ese grupo o canal no tiene un ID configurado.")
        return
    mostrar_gestion_botones(
        call.message.chat.id,
        canal_key,
        message=call.message,
        return_callback=f"grupo_config|{canal_key}|{pagina}",
    )


def markup_atajos_para_canal(botones):
    markup = types.InlineKeyboardMarkup(row_width=2)
    fila = []
    for index, item in enumerate(botones[:20]):
        etiqueta = str(item.get("label", "Atajo"))[:64]
        action = str(item.get("action", "")).strip()
        if action.startswith(("https://", "http://")):
            boton = types.InlineKeyboardButton(etiqueta, url=action)
        else:
            boton = types.InlineKeyboardButton(
                etiqueta, callback_data=f"gquick|{index}"
            )
        fila.append(boton)
        if len(fila) == 2:
            markup.row(*fila)
            fila = []
    if fila:
        markup.row(*fila)
    return markup


def botones_atajos_publicables_grupo(ajustes):
    personalizados = [
        item for item in (ajustes or {}).get("quick_buttons", [])
        if not es_atajo_admin(item)
    ][:20]
    return [*atajos_fijos_grupo(ajustes), *personalizados]


def publicar_teclado_atajos_grupo(canal_key, texto="⌨️ Atajos disponibles para los miembros:"):
    ajustes = obtener_ajustes_grupo(canal_key) or {}
    chat_id = obtener_canal_id(canal_key)
    if not chat_id or str(ajustes.get("type", "")).lower() == "canal":
        raise ValueError("El destino no es un grupo disponible.")

    previous_message_id = ajustes.get("quick_buttons_message_id")
    botones = botones_atajos_publicables_grupo(ajustes)
    teclado = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
        row_width=2,
    )
    for inicio in range(0, len(botones), 2):
        fila = [
            types.KeyboardButton(str(item.get("label", "Atajo"))[:64])
            for item in botones[inicio:inicio + 2]
        ]
        teclado.row(*fila)

    mensaje = bot.send_message(int(chat_id), texto, reply_markup=teclado)
    actualizar_ajustes_grupo(
        canal_key,
        lambda config: config.update({
            "quick_buttons_message_id": mensaje.message_id,
            "quick_buttons_chat_id": str(chat_id),
        }),
    )
    if (
        previous_message_id
        and str(ajustes.get("quick_buttons_chat_id")) == str(chat_id)
        and str(previous_message_id) != str(mensaje.message_id)
    ):
        try:
            bot.delete_message(int(chat_id), previous_message_id)
        except Exception:
            app.logger.info(
                "El nuevo teclado se publicó, pero no se pudo borrar el mensaje anterior."
            )
    return mensaje


def actualizar_teclado_atajos_si_publicado(canal_key, texto):
    ajustes = obtener_ajustes_grupo(canal_key) or {}
    if not ajustes.get("quick_buttons_message_id"):
        return None
    if str(ajustes.get("quick_buttons_chat_id")) != str(obtener_canal_id(canal_key)):
        return None
    try:
        publicar_teclado_atajos_grupo(canal_key, texto)
        return True
    except Exception:
        app.logger.exception("No se pudo actualizar el teclado de atajos del grupo.")
        return False


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("grupo_atajo_toggle|")
)
def callback_toggle_atajo_grupo(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    partes = call.data.split("|")
    claves_validas = {item[0] for item in GROUP_MEMBER_SHORTCUTS}
    if len(partes) != 4 or partes[1] not in CANALES or partes[2] not in claves_validas:
        bot.answer_callback_query(call.id, "No encontré ese atajo.")
        return
    _, canal_key, shortcut_key, pagina_txt = partes
    ajustes = obtener_ajustes_grupo(canal_key) or {}
    if str(ajustes.get("type", "")).lower() == "canal":
        bot.answer_callback_query(call.id, "Los atajos de la barra solo funcionan en grupos.")
        return
    try:
        pagina = max(0, int(pagina_txt))
    except ValueError:
        pagina = 0

    estado_nuevo = {}
    def alternar(ajustes_actuales):
        configurados = ajustes_actuales.setdefault("quick_commands_enabled", {})
        nuevo_valor = not bool(configurados.get(shortcut_key, True))
        configurados[shortcut_key] = nuevo_valor
        estado_nuevo["activo"] = nuevo_valor

    actualizar_ajustes_grupo(canal_key, alternar)
    if ajustes.get("quick_buttons_message_id"):
        publicado = actualizar_teclado_atajos_si_publicado(
            canal_key, "⌨️ Se actualizaron los atajos disponibles para los miembros."
        )
        aviso = (
            "Atajo actualizado y teclado publicado."
            if publicado else
            "Ajuste guardado. No se pudo actualizar el teclado; pulsa «Publicar botones en el chat»."
        )
    else:
        aviso = (
            "Atajo activado. Pulsa «Publicar botones en el chat» para mostrarlo."
            if estado_nuevo.get("activo") else
            "Atajo desactivado. Pulsa «Publicar botones en el chat» para aplicar la selección."
        )
    bot.answer_callback_query(call.id, "Activado." if estado_nuevo.get("activo") else "Desactivado.")
    mostrar_menu_atajos_grupo(
        call.message.chat.id, canal_key, pagina, message=call.message, aviso=aviso
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("grupo_atajos_video_label|")
)
def callback_editar_etiqueta_videochat(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    partes = call.data.split("|")
    if len(partes) != 3 or partes[1] not in CANALES:
        bot.answer_callback_query(call.id, "No encontré ese grupo.")
        return
    _, canal_key, pagina_txt = partes
    try:
        pagina = max(0, int(pagina_txt))
    except ValueError:
        pagina = 0
    ajustes = obtener_ajustes_grupo(canal_key) or {}
    if str(ajustes.get("type", "")).lower() == "canal":
        bot.answer_callback_query(call.id, "Esta opción solo está disponible en grupos.")
        return
    admin_estado[call.from_user.id] = {
        "paso": "esperando_videochat_button_label",
        "feature": "atajos",
        "canal_key": canal_key,
        "pagina": pagina,
        "panel_message_id": call.message.message_id,
    }
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "↩️ Volver a atajos",
        callback_data=f"grupo_feature|{canal_key}|atajos|{pagina}",
    ))
    bot.answer_callback_query(call.id)
    editar_o_enviar_panel(
        call.message.chat.id,
        f"✏️ <b>Nombre del botón de videochat</b>\n\n"
        f"Nombre actual: <b>{html.escape(etiqueta_boton_videochat(ajustes))}</b>\n\n"
        "Envía el nuevo nombre (máximo 32 caracteres; puedes incluir emojis) "
        "o escribe /cancelar.",
        markup,
        message=call.message,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("grupo_atajos_add|"))
def callback_agregar_atajo_grupo(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    partes = call.data.split("|")
    if len(partes) != 3 or partes[1] not in CANALES:
        bot.answer_callback_query(call.id, "No encontré ese grupo.")
        return
    canal_key, pagina = partes[1], int(partes[2])
    admin_estado[call.from_user.id] = {
        "paso": "esperando_atajo_grupo",
        "canal_key": canal_key,
        "pagina": pagina,
        "panel_message_id": call.message.message_id,
    }
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "↩️ Volver a atajos",
        callback_data=f"grupo_feature|{canal_key}|atajos|{pagina}",
    ))
    bot.answer_callback_query(call.id)
    editar_o_enviar_panel(
        call.message.chat.id,
        "Envía <code>etiqueta=acción</code> o <code>Nombre del botón - rules</code>.\n"
        "Acciones admitidas: un comando del bot (por ejemplo <code>/rules</code>) "
        "o un enlace <code>https://...</code>.\n"
        "Ejemplos: <code>📜 Reglamento=/rules</code> · "
        "<code>🌐 Sitio=https://ejemplo.com</code>",
        markup,
        message=call.message,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("grupo_atajos_del|"))
def callback_eliminar_atajo_grupo(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    partes = call.data.split("|")
    if len(partes) != 4 or partes[1] not in CANALES:
        bot.answer_callback_query(call.id, "No encontré ese botón.")
        return
    _, canal_key, indice_txt, pagina_txt = partes
    try:
        indice, pagina = int(indice_txt), int(pagina_txt)
    except ValueError:
        bot.answer_callback_query(call.id, "Selección inválida.")
        return
    def eliminar(ajustes):
        botones = ajustes.setdefault("quick_buttons", [])
        if 0 <= indice < len(botones):
            botones.pop(indice)
    tenia_teclado = bool(
        (obtener_ajustes_grupo(canal_key) or {}).get("quick_buttons_message_id")
    )
    actualizar_ajustes_grupo(canal_key, eliminar)
    sincronizado = (
        actualizar_teclado_atajos_si_publicado(
            canal_key, "⌨️ Se actualizó la botonera del grupo."
        )
        if tenia_teclado else None
    )
    bot.answer_callback_query(call.id, "Atajo eliminado.")
    mostrar_menu_atajos_grupo(
        call.message.chat.id,
        canal_key,
        pagina,
        message=call.message,
        aviso=(
            "Botón eliminado y teclado actualizado."
            if sincronizado is True else
            "Botón eliminado; publica los atajos manualmente en el grupo."
            if sincronizado is False else
            "Botón eliminado."
        ),
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("grupo_atajos_apply|"))
def callback_publicar_atajos_grupo(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    partes = call.data.split("|")
    if len(partes) != 3 or partes[1] not in CANALES:
        bot.answer_callback_query(call.id, "No encontré ese destino.")
        return
    canal_key, pagina = partes[1], int(partes[2])
    ajustes = obtener_ajustes_grupo(canal_key) or {}
    chat_id = obtener_canal_id(canal_key)
    es_canal = str(ajustes.get("type", "")).lower() == "canal"
    botones = (
        ajustes.get("quick_buttons", [])
        if es_canal else botones_atajos_publicables_grupo(ajustes)
    )
    if not chat_id or not botones:
        bot.answer_callback_query(call.id, "Agrega al menos un atajo y comprueba el ID.")
        return
    try:
        if es_canal:
            mensaje = bot.send_message(
                int(chat_id),
                "⌨️ Atajos rápidos",
                reply_markup=markup_atajos_para_canal(botones),
            )
        else:
            mensaje = publicar_teclado_atajos_grupo(
                canal_key,
                "⌨️ Atajos y guía de videochat disponibles para los miembros:",
            )
        if es_canal:
            actualizar_ajustes_grupo(
                canal_key,
                lambda config: config.update({
                    "quick_buttons_message_id": mensaje.message_id,
                    "quick_buttons_chat_id": str(chat_id),
                }),
            )
        bot.answer_callback_query(call.id, "Atajos publicados.")
        mostrar_menu_atajos_grupo(
            call.message.chat.id,
            canal_key,
            pagina,
            message=call.message,
            aviso="Atajos publicados en el destino.",
        )
    except Exception:
        app.logger.exception("No se pudieron publicar los atajos del grupo.")
        bot.answer_callback_query(call.id, "No pude publicarlos; revisa los permisos del bot.")


@bot.callback_query_handler(func=lambda call: call.data.startswith("grupo_atajos_remove|"))
def callback_quitar_atajos_grupo(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    partes = call.data.split("|")
    if len(partes) != 3 or partes[1] not in CANALES:
        bot.answer_callback_query(call.id, "No encontré ese destino.")
        return
    canal_key, pagina = partes[1], int(partes[2])
    ajustes = obtener_ajustes_grupo(canal_key) or {}
    chat_id = obtener_canal_id(canal_key)
    try:
        if str(ajustes.get("type", "")).lower() == "canal":
            message_id = ajustes.get("quick_buttons_message_id")
            if message_id:
                bot.edit_message_reply_markup(
                    int(chat_id), int(message_id), reply_markup=None
                )
        else:
            bot.send_message(
                int(chat_id),
                "⌨️ Se quitaron los atajos rápidos.",
                reply_markup=types.ReplyKeyboardRemove(),
            )
        actualizar_ajustes_grupo(
            canal_key,
            lambda config: config.update({
                "quick_buttons_message_id": None,
                "quick_buttons_chat_id": None,
            }),
        )
        bot.answer_callback_query(call.id, "Teclado retirado.")
        mostrar_menu_atajos_grupo(
            call.message.chat.id,
            canal_key,
            pagina,
            message=call.message,
            aviso="Se retiró el teclado publicado.",
        )
    except Exception:
        app.logger.exception("No se pudo retirar el teclado del destino.")
        bot.answer_callback_query(call.id, "No pude quitarlo; revisa los permisos del bot.")


@bot.callback_query_handler(func=lambda call: call.data.startswith("gquick|"))
def callback_atajo_canal(call):
    if not getattr(call, "message", None):
        bot.answer_callback_query(call.id, "No encontré el canal.")
        return
    canal_key = buscar_destino_por_chat_id(call.message.chat.id)
    if not canal_key:
        bot.answer_callback_query(call.id, "Este destino no está guardado.")
        return
    try:
        indice = int(call.data.split("|", 1)[1])
    except ValueError:
        bot.answer_callback_query(call.id, "Acción inválida.")
        return
    ajustes = obtener_ajustes_grupo(canal_key) or {}
    botones = ajustes.get("quick_buttons", [])
    if not 0 <= indice < len(botones):
        bot.answer_callback_query(call.id, "Este atajo ya no existe.")
        return
    action = str(botones[indice].get("action", "")).strip()
    partes_accion = action.split(maxsplit=1)
    comando_accion = partes_accion[0].split("@", 1)[0].lower() if partes_accion else ""
    if comando_accion == "/rules":
        es_admin = es_administrador_grupo(
            call.message.chat.id, call.from_user.id
        )
        if ajustes.get("rules_access", "all") == "admins" and es_admin is not True:
            bot.answer_callback_query(
                call.id,
                "Solo los administradores pueden consultar el reglamento.",
                show_alert=True,
            )
            return
        argumento = partes_accion[1] if len(partes_accion) > 1 else ""
        bot.answer_callback_query(call.id)
        publicar_reglamento(
            call.message.chat.id,
            ajustes,
            argumento=argumento,
            es_admin=es_admin,
            canal_key=buscar_destino_por_chat_id(call.message.chat.id),
        )
        return
    if action == "/tag":
        respuesta = str(ajustes.get("tag", "")).strip()
        respuesta = respuesta or "Todavía no hay contenido configurado para este atajo."
    elif action.startswith("/") and action[1:] in ajustes.get("custom_commands", {}):
        respuesta = str(ajustes["custom_commands"][action[1:]])
    else:
        bot.answer_callback_query(
            call.id, "Este comando solo está disponible en un grupo.", show_alert=True
        )
        return
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, respuesta)


@bot.callback_query_handler(func=lambda call: call.data.startswith("rules_inline|"))
def callback_boton_teclado_reglamento(call):
    partes = call.data.split("|")
    if len(partes) != 3 or partes[1] not in CANALES:
        bot.answer_callback_query(call.id, "Este botón ya no está disponible.")
        return
    canal_key = partes[1]
    if str(obtener_canal_id(canal_key)) != str(call.message.chat.id):
        bot.answer_callback_query(call.id, "Este botón pertenece a otro grupo.")
        return
    try:
        indice = int(partes[2])
    except ValueError:
        bot.answer_callback_query(call.id, "Acción inválida.")
        return
    ajustes = obtener_ajustes_grupo(canal_key) or {}
    botones = ajustes.get("rules_keyboard", [])
    if not 0 <= indice < len(botones):
        bot.answer_callback_query(call.id, "Este botón ya no existe.")
        return
    accion = str(botones[indice].get("action", "")).strip()
    partes_accion = accion.split(maxsplit=1)
    comando_accion = partes_accion[0].split("@", 1)[0].lower() if partes_accion else ""
    if comando_accion == "/rules":
        es_admin = es_administrador_grupo(
            call.message.chat.id, call.from_user.id
        )
        if ajustes.get("rules_access", "all") == "admins" and es_admin is not True:
            bot.answer_callback_query(
                call.id,
                "Solo los administradores pueden consultar el reglamento.",
                show_alert=True,
            )
            return
        argumento = partes_accion[1] if len(partes_accion) > 1 else ""
        bot.answer_callback_query(call.id)
        publicar_reglamento(
            call.message.chat.id,
            ajustes,
            argumento=argumento,
            es_admin=es_admin,
            canal_key=canal_key,
        )
        return
    comando = accion.split(maxsplit=1)[0].split("@", 1)[0].lstrip("/").casefold()
    respuesta = str(ajustes.get("custom_commands", {}).get(comando, "")).strip()
    if not respuesta:
        bot.answer_callback_query(
            call.id,
            "Este botón no apunta a una regla ni a un comando personalizado disponible.",
            show_alert=True,
        )
        return
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, respuesta)


@bot.callback_query_handler(func=lambda call: call.data.startswith("grupo_feature|"))
def callback_abrir_funcion_grupo(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    partes = call.data.split("|")
    if len(partes) != 4:
        return
    _, canal_key, feature, pagina_txt = partes
    estado = admin_estado.get(call.from_user.id, {})
    if (
        feature == "captcha"
        and estado.get("canal_key") == canal_key
        and estado.get("paso") == "esperando_texto_captcha"
    ):
        admin_estado.pop(call.from_user.id, None)
    try:
        pagina = max(0, int(pagina_txt))
    except ValueError:
        pagina = 0
    mostrar_menu_funcion_grupo(
        call.message.chat.id, canal_key, feature, pagina, message=call.message
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("grp_rules|"))
def callback_configuracion_reglamento(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    partes = call.data.split("|")
    if len(partes) < 4 or len(partes) > 5:
        bot.answer_callback_query(call.id, "No pude leer esta opción.")
        return
    _, accion, canal_key, pagina_txt, *valor_partes = partes
    if canal_key not in CANALES:
        bot.answer_callback_query(call.id, "No encontré ese grupo o canal.")
        return
    try:
        pagina = max(0, int(pagina_txt))
    except ValueError:
        pagina = 0
    valor = valor_partes[0] if valor_partes else ""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    estado_actual = admin_estado.get(call.from_user.id, {})
    if (
        estado_actual.get("canal_key") == canal_key
        and accion in ("home", "help", "editor", "keyboard", "permisos")
        and estado_actual.get("paso") in (
            "esperando_media_reglas",
            "esperando_teclado_reglas",
            "esperando_ajuste_grupo",
        )
    ):
        admin_estado.pop(call.from_user.id, None)

    if accion == "home":
        mostrar_menu_reglamento(
            chat_id, canal_key, pagina, message=call.message,
            mostrar_ayuda=valor == "1",
        )
    elif accion == "help":
        mostrar_menu_reglamento(
            chat_id, canal_key, pagina, message=call.message,
            mostrar_ayuda=valor == "1",
        )
    elif accion == "editor":
        mostrar_editor_reglamento(
            chat_id, canal_key, pagina, message=call.message
        )
    elif accion == "edit":
        admin_estado[call.from_user.id] = {
            "paso": "esperando_ajuste_grupo",
            "canal_key": canal_key,
            "feature": "reglamento",
            "pagina": pagina,
            "panel_message_id": message_id,
            "volver_a_editor_reglas": True,
        }
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "↩️ Volver a personalizar mensaje",
            callback_data=f"grp_rules|editor|{canal_key}|{pagina}",
        ))
        actual = str((obtener_ajustes_grupo(canal_key) or {}).get("rules", "")).strip()
        editar_o_enviar_panel(
            chat_id,
            "✍🏼 <b>Editar texto del Reglamento</b>\n\n"
            f"Texto actual:\n{html.escape(actual[:1200]) if actual else '<i>Sin texto guardado.</i>'}\n\n"
            "Envía el nuevo texto. Usa <code>/vaciar</code> para borrarlo o "
            "<code>/cancelar</code> para regresar.",
            markup,
            message=call.message,
            forzar_texto=True,
        )
    elif accion == "media" and valor in ("before", "after"):
        admin_estado[call.from_user.id] = {
            "paso": "esperando_media_reglas",
            "canal_key": canal_key,
            "pagina": pagina,
            "posicion": valor,
            "panel_message_id": message_id,
        }
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "↩️ Cancelar",
            callback_data=f"grp_rules|editor|{canal_key}|{pagina}",
        ))
        lugar = "encima" if valor == "before" else "debajo"
        editar_o_enviar_panel(
            chat_id,
            f"🖼️ <b>Multimedia {lugar} del Reglamento</b>\n\n"
            "Envíame una foto, video, GIF o archivo multimedia. "
            "Este archivo reemplazará el que ya esté en esta posición.\n\n"
            "Usa /cancelar para volver.",
            markup,
            message=call.message,
            forzar_texto=True,
        )
    elif accion == "media_clear" and valor in ("before", "after"):
        actualizar_ajustes_grupo(
            canal_key,
            lambda ajustes: ajustes.update({f"rules_media_{valor}": None}),
        )
        mostrar_editor_reglamento(
            chat_id, canal_key, pagina, message=call.message,
            aviso="Se quitó el multimedia.",
        )
    elif accion == "keyboard":
        mostrar_teclado_reglamento(
            chat_id, canal_key, pagina, message=call.message
        )
    elif accion == "keyboard_add":
        admin_estado[call.from_user.id] = {
            "paso": "esperando_teclado_reglas",
            "canal_key": canal_key,
            "pagina": pagina,
            "panel_message_id": message_id,
        }
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "↩️ Volver al teclado",
            callback_data=f"grp_rules|keyboard|{canal_key}|{pagina}",
        ))
        editar_o_enviar_panel(
            chat_id,
            "🔠 <b>Agregar botón al Reglamento</b>\n\n"
            "Envía <code>etiqueta=acción</code> o <code>Nombre del botón - rules</code>. "
            "La acción puede ser un enlace, "
            "<code>/rules</code>, <code>/rules argumento</code> o un comando "
            "personalizado ya configurado.\n\nUsa /cancelar para salir.",
            markup,
            message=call.message,
            forzar_texto=True,
        )
    elif accion == "keyboard_del":
        try:
            index = int(valor)
        except ValueError:
            bot.send_message(chat_id, "La selección del botón no es válida.")
            return
        def quitar_boton(ajustes):
            botones = ajustes.setdefault("rules_keyboard", [])
            if 0 <= index < len(botones):
                botones.pop(index)
        actualizar_ajustes_grupo(canal_key, quitar_boton)
        mostrar_teclado_reglamento(
            chat_id, canal_key, pagina, message=call.message,
            aviso="Se quitó el botón.",
        )
    elif accion == "keyboard_clear":
        actualizar_ajustes_grupo(
            canal_key, lambda ajustes: ajustes.update({"rules_keyboard": []})
        )
        mostrar_editor_reglamento(
            chat_id, canal_key, pagina, message=call.message,
            aviso="Se quitaron los botones.",
        )
    elif accion == "permisos":
        mostrar_permisos_reglamento(
            chat_id, canal_key, pagina, message=call.message,
            mostrar_ayuda=valor == "1",
        )
    elif accion == "access" and valor in ("all", "admins"):
        actualizar_ajustes_grupo(
            canal_key, lambda ajustes: ajustes.update({"rules_access": valor})
        )
        mostrar_permisos_reglamento(
            chat_id, canal_key, pagina, message=call.message,
            aviso=(
                "El comando ya está disponible para todos."
                if valor == "all"
                else "El comando quedó limitado a los administradores."
            ),
        )
    else:
        mostrar_menu_reglamento(
            chat_id, canal_key, pagina, message=call.message,
            aviso="Esa acción no está disponible.",
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith("grupo_captcha_text|"))
def callback_editar_texto_captcha(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    partes = call.data.split("|")
    if len(partes) != 3 or partes[1] not in CANALES:
        bot.answer_callback_query(call.id, "No encontré ese grupo.")
        return
    _, canal_key, pagina_txt = partes
    try:
        pagina = max(0, int(pagina_txt))
    except ValueError:
        pagina = 0
    bot.answer_callback_query(call.id)
    ajustes = obtener_ajustes_grupo(canal_key) or {}
    admin_estado[call.from_user.id] = {
        "paso": "esperando_texto_captcha",
        "canal_key": canal_key,
        "pagina": pagina,
        "panel_message_id": call.message.message_id,
    }
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "↩️ Volver a CAPTCHA",
        callback_data=f"grupo_feature|{canal_key}|captcha|{pagina}",
    ))
    texto_actual = str(ajustes.get("captcha_text") or "").strip()
    editar_o_enviar_panel(
        call.message.chat.id,
        "✍🏼 <b>Personalizar mensaje CAPTCHA</b>\n\n"
        f"Actual:\n{html.escape(texto_actual[:1000]) if texto_actual else '<i>Mensaje predeterminado.</i>'}\n\n"
        "Puedes usar <code>{name}</code> para el nombre y <code>{RULES}</code> "
        "para insertar el reglamento completo. Usa /vaciar para restaurar el mensaje "
        "predeterminado o /cancelar para salir.",
        markup,
        message=call.message,
        forzar_texto=True,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("grupo_toggle|"))
def callback_toggle_funcion_grupo(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    partes = call.data.split("|")
    if len(partes) != 4:
        bot.answer_callback_query(call.id, "No pude leer el ajuste.")
        return
    _, canal_key, feature, pagina_txt = partes
    try:
        pagina = max(0, int(pagina_txt))
    except ValueError:
        pagina = 0

    def cambiar(ajustes):
        enabled = ajustes.setdefault("enabled", {})
        enabled[feature] = not bool(enabled.get(feature, False))
        if feature == "guardian" and enabled[feature]:
            enabled["antispam"] = True
            enabled["antiflood"] = True
            enabled["palabras"] = True
    actualizar_ajustes_grupo(canal_key, cambiar)
    bot.answer_callback_query(call.id, "Ajuste actualizado.")
    mostrar_menu_funcion_grupo(
        call.message.chat.id, canal_key, feature, pagina, message=call.message
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("gmod|"))
def callback_configurar_moderacion_grupo(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    partes = call.data.split("|")
    if len(partes) < 4 or len(partes) > 7:
        bot.answer_callback_query(call.id, "No pude leer ese ajuste.")
        return
    _, accion, canal_key, pagina_txt, *valores = partes
    if canal_key not in CANALES:
        bot.answer_callback_query(call.id, "No encontré ese grupo.")
        return
    try:
        pagina = max(0, int(pagina_txt))
    except ValueError:
        pagina = 0
    chat_id = call.message.chat.id

    def volver_antispam(seccion="root", policy_id=None):
        mostrar_menu_antispam(
            chat_id, canal_key, pagina, message=call.message,
            seccion=seccion, policy_id=policy_id,
        )

    if accion == "link_set" and not valores:
        try:
            link = bot.export_chat_invite_link(obtener_canal_id(canal_key))
            actualizar_ajustes_grupo(canal_key, lambda ajustes: ajustes.update({
                "group_link": link,
                "group_link_enabled": True,
            }))
            bot.answer_callback_query(call.id, "Enlace guardado y activado.")
            mostrar_menu_enlace_grupo(
                chat_id, canal_key, pagina, message=call.message,
                aviso="Enlace actualizado.",
            )
        except Exception as error:
            bot.answer_callback_query(call.id, "No pude generar el enlace.")
            mostrar_menu_enlace_grupo(
                chat_id, canal_key, pagina, message=call.message,
                aviso=f"Telegram rechazó la acción: {error}",
            )
        return

    if accion == "link_toggle" and not valores:
        ajustes = obtener_ajustes_grupo(canal_key) or {}
        if not ajustes.get("group_link") and not ajustes.get("group_link_enabled"):
            bot.answer_callback_query(call.id, "Primero establece un enlace.")
            mostrar_menu_enlace_grupo(
                chat_id, canal_key, pagina, message=call.message,
                aviso="Genera un enlace antes de activarlo.",
            )
            return
        actualizar_ajustes_grupo(
            canal_key,
            lambda ajustes: ajustes.update({
                "group_link_enabled": not bool(ajustes.get("group_link_enabled"))
            }),
        )
        bot.answer_callback_query(call.id, "Estado actualizado.")
        mostrar_menu_enlace_grupo(chat_id, canal_key, pagina, message=call.message)
        return

    if accion == "approval_toggle" and not valores:
        actualizar_ajustes_grupo(
            canal_key,
            lambda ajustes: ajustes.update({
                "approval_auto_enabled": not bool(ajustes.get("approval_auto_enabled"))
            }),
        )
        bot.answer_callback_query(call.id, "Auto-aprobación actualizada.")
        mostrar_menu_aprobacion_grupo(chat_id, canal_key, pagina, message=call.message)
        return

    if accion == "approval_link" and not valores:
        try:
            invite = bot.create_chat_invite_link(
                obtener_canal_id(canal_key), creates_join_request=True
            )
            actualizar_ajustes_grupo(
                canal_key,
                lambda ajustes: ajustes.update({"approval_link": invite.invite_link}),
            )
            bot.answer_callback_query(call.id, "Enlace de solicitud creado.")
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(types.InlineKeyboardButton(
                "🔗 Abrir enlace de solicitud", url=invite.invite_link
            ))
            markup.add(types.InlineKeyboardButton(
                "↩️ Volver",
                callback_data=f"grupo_feature|{canal_key}|aprobacion|{pagina}",
            ))
            editar_o_enviar_panel(
                chat_id,
                f"📩 <b>Enlace con aprobación</b>\n\n{html.escape(invite.invite_link)}",
                markup,
                message=call.message,
                forzar_texto=True,
            )
        except Exception as error:
            bot.answer_callback_query(call.id, "No pude crear el enlace.")
            mostrar_menu_aprobacion_grupo(
                chat_id, canal_key, pagina, message=call.message,
                aviso=f"Telegram rechazó la acción: {error}",
            )
        return

    if accion == "words_action" and len(valores) == 1:
        value = valores[0]
        if value not in {"off", "warn", "kick", "mute", "ban"}:
            bot.answer_callback_query(call.id, "Castigo no disponible.")
            return
        def set_words_action(ajustes):
            policy = ajustes.setdefault("moderation_policies", {}).setdefault("blocked_words", {})
            policy["action"] = value
            policy.setdefault("delete_messages", True)
            ajustes.setdefault("enabled", {})["palabras"] = (
                value != "off" or bool(policy.get("delete_messages"))
            )
        actualizar_ajustes_grupo(canal_key, set_words_action)
        bot.answer_callback_query(call.id, "Castigo actualizado.")
        mostrar_menu_palabras_grupo(chat_id, canal_key, pagina, message=call.message)
        return

    if accion == "words_delete" and not valores:
        ajustes_actuales = obtener_ajustes_grupo(canal_key) or {}
        policy_actual = _politica_ajuste(ajustes_actuales, "blocked_words")
        def toggle_words_delete(ajustes):
            policy = ajustes.setdefault("moderation_policies", {}).setdefault("blocked_words", {})
            policy.setdefault("action", policy_actual["action"])
            policy["delete_messages"] = not bool(policy_actual["delete_messages"])
            ajustes.setdefault("enabled", {})["palabras"] = (
                policy.get("action", "off") != "off" or policy["delete_messages"]
            )
        actualizar_ajustes_grupo(canal_key, toggle_words_delete)
        bot.answer_callback_query(call.id, "Borrado de mensajes actualizado.")
        mostrar_menu_palabras_grupo(chat_id, canal_key, pagina, message=call.message)
        return

    if accion == "words_list" and not valores:
        words = list((obtener_ajustes_grupo(canal_key) or {}).get("blocked_words", []))
        texto = "🔠 <b>Palabras prohibidas</b>\n\n" + (
            "\n".join(f"• {html.escape(str(word))}" for word in words[:150])
            if words else "La lista está vacía."
        )
        if len(words) > 150:
            texto += f"\n… y {len(words) - 150} más."
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "↩️ Volver",
            callback_data=f"grupo_feature|{canal_key}|palabras|{pagina}",
        ))
        bot.answer_callback_query(call.id)
        editar_o_enviar_panel(chat_id, texto, markup, message=call.message, forzar_texto=True)
        return

    if accion == "block_list" and not valores:
        ids = list((obtener_ajustes_grupo(canal_key) or {}).get("blocked_user_ids", []))
        texto = "📋 <b>Blocklist / Blacklist</b>\n\n" + (
            "\n".join(f"• <code>{html.escape(str(user_id))}</code>" for user_id in ids[:100])
            if ids else "No hay IDs bloqueados."
        )
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.row(
            types.InlineKeyboardButton(
                "➕ Añadir ID",
                callback_data=f"grupo_editar|{canal_key}|bloqueos|{pagina}|add",
            ),
            types.InlineKeyboardButton(
                "➖ Retirar ID",
                callback_data=f"grupo_editar|{canal_key}|bloqueos|{pagina}|remove",
            ),
        )
        markup.add(types.InlineKeyboardButton(
            "↩️ Volver",
            callback_data=f"grupo_feature|{canal_key}|bloqueos|{pagina}",
        ))
        bot.answer_callback_query(call.id)
        editar_o_enviar_panel(chat_id, texto, markup, message=call.message, forzar_texto=True)
        return

    if accion == "block_toggle" and len(valores) == 1:
        field = valores[0]
        valid = {
            "block_join_enabled", "block_leave_enabled",
            "block_join_leave_enabled", "block_multiple_join_enabled",
            "block_bots_enabled",
        }
        if field not in valid:
            bot.answer_callback_query(call.id, "Ajuste no disponible.")
            return
        actualizar_ajustes_grupo(
            canal_key,
            lambda ajustes: ajustes.update({field: not bool(ajustes.get(field))}),
        )
        bot.answer_callback_query(call.id, "Regla de bloqueo actualizada.")
        mostrar_menu_bloqueos_grupo(chat_id, canal_key, pagina, message=call.message)
        return

    if accion == "masked_exceptions" and not valores:
        exceptions = list((obtener_ajustes_grupo(canal_key) or {}).get("masked_exceptions", []))
        texto = "☀️ <b>Excepciones de usuarios enmascarados</b>\n\n" + (
            "\n".join(f"• {html.escape(str(value))}" for value in exceptions[:100])
            if exceptions else "No hay excepciones configuradas."
        )
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.row(
            types.InlineKeyboardButton(
                "➕ Añadir",
                callback_data=f"grupo_editar|{canal_key}|enmascarados|{pagina}|add",
            ),
            types.InlineKeyboardButton(
                "➖ Eliminar",
                callback_data=f"grupo_editar|{canal_key}|enmascarados|{pagina}|remove",
            ),
        )
        markup.add(types.InlineKeyboardButton(
            "↩️ Volver",
            callback_data=f"grupo_feature|{canal_key}|enmascarados|{pagina}",
        ))
        bot.answer_callback_query(call.id)
        editar_o_enviar_panel(chat_id, texto, markup, message=call.message, forzar_texto=True)
        return

    if accion == "masked_delete" and not valores:
        actualizar_ajustes_grupo(
            canal_key,
            lambda ajustes: ajustes.update({
                "masked_delete_messages": not bool(ajustes.get("masked_delete_messages", True))
            }),
        )
        bot.answer_callback_query(call.id, "Ajuste actualizado.")
        mostrar_menu_enmascarados_grupo(chat_id, canal_key, pagina, message=call.message)
        return

    if accion == "members_confirm" and len(valores) == 1:
        action = valores[0]
        if action not in {"unmute_all", "unban_all", "kick_muted", "kick_deleted"}:
            bot.answer_callback_query(call.id, "Acción no disponible.")
            return
        labels = {
            "unmute_all": "quitar el silencio a los miembros sancionados que el bot tiene registrados",
            "unban_all": "desbloquear a los miembros que el bot tiene registrados",
            "kick_muted": "expulsar a los miembros actualmente silenciados por este bot",
            "kick_deleted": "revisar los usuarios registrados e intentar retirar las cuentas eliminadas",
        }
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.row(
            types.InlineKeyboardButton(
                "✅ Confirmar",
                callback_data=f"gmod|members_run|{canal_key}|{pagina}|{action}",
            ),
            types.InlineKeyboardButton(
                "↩️ Cancelar",
                callback_data=f"grupo_feature|{canal_key}|miembros|{pagina}",
            ),
        )
        bot.answer_callback_query(call.id)
        editar_o_enviar_panel(
            chat_id,
            f"⚠️ <b>Confirma la acción</b>\n\nVas a {labels[action]}. "
            "No se pueden incluir miembros que Telegram no haya mostrado antes al bot.",
            markup,
            message=call.message,
            forzar_texto=True,
        )
        return

    if accion == "members_run" and len(valores) == 1:
        action = valores[0]
        ajustes = obtener_ajustes_grupo(canal_key) or {}
        records = dict(ajustes.get("known_sanctions", {}))
        target_ids = [
            int(user_id) for user_id, sanction in records.items()
            if (action in {"unmute_all", "kick_muted"} and sanction == "mute")
            or (action == "unban_all" and sanction == "ban")
            or (action == "kick_deleted" and sanction in {"mute", "ban"})
        ]
        chat_target = obtener_canal_id(canal_key)
        completed = 0
        for user_id in target_ids:
            try:
                if action == "unmute_all":
                    bot.restrict_chat_member(
                        chat_target,
                        user_id,
                        permissions=types.ChatPermissions(
                            can_send_messages=True, can_send_audios=True,
                            can_send_documents=True, can_send_photos=True,
                            can_send_videos=True, can_send_video_notes=True,
                            can_send_voice_notes=True, can_send_polls=True,
                            can_send_other_messages=True, can_add_web_page_previews=True,
                        ),
                    )
                elif action == "unban_all":
                    bot.unban_chat_member(chat_target, user_id, only_if_banned=True)
                elif action == "kick_muted":
                    bot.ban_chat_member(chat_target, user_id)
                    bot.unban_chat_member(chat_target, user_id, only_if_banned=True)
                else:
                    member = bot.get_chat_member(chat_target, user_id)
                    if getattr(getattr(member, "user", None), "is_deleted", False):
                        bot.ban_chat_member(chat_target, user_id)
                    else:
                        continue
                completed += 1
            except Exception:
                app.logger.info("No se pudo aplicar gestión masiva a %s en %s.", user_id, chat_target)
        def clear_handled(ajustes_actuales):
            current = ajustes_actuales.setdefault("known_sanctions", {})
            for user_id in target_ids:
                if action in {"unmute_all", "unban_all", "kick_muted"}:
                    current.pop(str(user_id), None)
        actualizar_ajustes_grupo(canal_key, clear_handled)
        bot.answer_callback_query(call.id, "Acción terminada.")
        mostrar_menu_miembros_grupo(
            chat_id, canal_key, pagina, message=call.message,
            aviso=f"Se procesaron {completed} miembro(s).",
        )
        return

    if accion == "open" and len(valores) == 1:
        seccion = valores[0]
        if seccion not in ("telegram", "forward", "quotes", "internet"):
            bot.answer_callback_query(call.id, "Sección no disponible.")
            return
        bot.answer_callback_query(call.id)
        volver_antispam(seccion=seccion)
        return

    if accion == "policy" and len(valores) == 2:
        policy_id, seccion = valores
        if policy_id not in GROUP_MODERATION_POLICY_LABELS:
            bot.answer_callback_query(call.id, "Ajuste no disponible.")
            return
        bot.answer_callback_query(call.id)
        volver_antispam(seccion=seccion, policy_id=policy_id)
        return

    if accion == "set" and len(valores) == 2:
        policy_id, policy_action = valores
        if (
            policy_id not in GROUP_MODERATION_POLICY_LABELS
            or policy_action not in {value for _, value in GROUP_MODERATION_ACTIONS}
        ):
            bot.answer_callback_query(call.id, "Acción no disponible.")
            return
        def guardar(ajustes):
            policy = ajustes.setdefault("moderation_policies", {}).setdefault(
                policy_id, {}
            )
            policy["action"] = policy_action
        actualizar_ajustes_grupo(canal_key, guardar)
        seccion = (
            "forward" if policy_id.startswith("forward_") else
            "quotes" if policy_id.startswith("quote_") else
            "internet" if policy_id == "internet_links" else
            "telegram"
        )
        bot.answer_callback_query(call.id, "Castigo actualizado.")
        volver_antispam(seccion=seccion, policy_id=policy_id)
        return

    if accion == "del" and len(valores) == 1:
        policy_id = valores[0]
        if policy_id not in GROUP_MODERATION_POLICY_LABELS:
            bot.answer_callback_query(call.id, "Ajuste no disponible.")
            return
        def alternar_borrado(ajustes):
            policy = ajustes.setdefault("moderation_policies", {}).setdefault(
                policy_id, {}
            )
            policy["delete_messages"] = not bool(policy.get("delete_messages", False))
        actualizar_ajustes_grupo(canal_key, alternar_borrado)
        seccion = (
            "forward" if policy_id.startswith("forward_") else
            "quotes" if policy_id.startswith("quote_") else
            "internet" if policy_id == "internet_links" else
            "telegram"
        )
        bot.answer_callback_query(call.id, "Eliminación actualizada.")
        volver_antispam(seccion=seccion, policy_id=policy_id)
        return

    if accion == "tg" and len(valores) == 1 and valores[0] in ("usernames", "bots"):
        field = "username_spam" if valores[0] == "usernames" else "bot_spam"
        def alternar_filtro_telegram(ajustes):
            policy = ajustes.setdefault("moderation_policies", {}).setdefault(
                "telegram_links", {}
            )
            policy[field] = not bool(policy.get(field, False))
        actualizar_ajustes_grupo(canal_key, alternar_filtro_telegram)
        bot.answer_callback_query(call.id, "Filtro actualizado.")
        volver_antispam(seccion="telegram", policy_id="telegram_links")
        return

    if accion == "welcome_mode" and len(valores) == 1:
        mode = valores[0]
        if mode not in ("always", "first"):
            bot.answer_callback_query(call.id, "Modo no disponible.")
            return
        actualizar_ajustes_grupo(
            canal_key, lambda ajustes: ajustes.update({"welcome_mode": mode})
        )
        bot.answer_callback_query(call.id, "Modo de bienvenida actualizado.")
        mostrar_menu_bienvenida_despedida(
            chat_id, canal_key, "bienvenida", pagina, message=call.message
        )
        return

    if accion == "member_toggle" and len(valores) == 1:
        field = valores[0]
        allowed_fields = {
            "welcome_send_private", "welcome_delete_previous",
            "goodbye_send_private", "goodbye_delete_previous",
        }
        if field not in allowed_fields:
            bot.answer_callback_query(call.id, "Ajuste no disponible.")
            return
        actualizar_ajustes_grupo(
            canal_key,
            lambda ajustes: ajustes.update({field: not bool(ajustes.get(field, False))}),
        )
        feature = "bienvenida" if field.startswith("welcome_") else "despedida"
        bot.answer_callback_query(call.id, "Ajuste actualizado.")
        mostrar_menu_bienvenida_despedida(
            chat_id, canal_key, feature, pagina, message=call.message
        )
        return

    if accion == "captcha_mode" and len(valores) == 1:
        mode = valores[0]
        if mode not in ("button", "math"):
            bot.answer_callback_query(call.id, "Modo no disponible.")
            return
        actualizar_ajustes_grupo(
            canal_key, lambda ajustes: ajustes.update({"captcha_mode": mode})
        )
        bot.answer_callback_query(call.id, "Modo CAPTCHA actualizado.")
        mostrar_menu_captcha_grupo(
            chat_id, canal_key, pagina, message=call.message
        )
        return

    if accion == "captcha_time" and len(valores) == 1:
        try:
            seconds = int(valores[0])
        except ValueError:
            seconds = 0
        if seconds not in (30, 60, 90, 120, 300):
            bot.answer_callback_query(call.id, "Tiempo no disponible.")
            return
        actualizar_ajustes_grupo(
            canal_key,
            lambda ajustes: ajustes.update({"captcha_timeout_seconds": seconds}),
        )
        bot.answer_callback_query(call.id, "Tiempo CAPTCHA actualizado.")
        mostrar_menu_captcha_grupo(
            chat_id, canal_key, pagina, message=call.message
        )
        return

    if accion == "captcha_action" and len(valores) == 1:
        value = valores[0]
        if value not in {action for _, action in GROUP_MODERATION_ACTIONS}:
            bot.answer_callback_query(call.id, "Castigo no disponible.")
            return
        actualizar_ajustes_grupo(
            canal_key, lambda ajustes: ajustes.update({"captcha_action": value})
        )
        bot.answer_callback_query(call.id, "Castigo CAPTCHA actualizado.")
        mostrar_menu_captcha_grupo(
            chat_id, canal_key, pagina, message=call.message
        )
        return

    if accion == "captcha_theme" and len(valores) == 1:
        theme = valores[0]
        if theme not in ("classic", "rules", "simple"):
            bot.answer_callback_query(call.id, "Tema no disponible.")
            return
        actualizar_ajustes_grupo(
            canal_key, lambda ajustes: ajustes.update({"captcha_theme": theme})
        )
        bot.answer_callback_query(call.id, "Tema CAPTCHA actualizado.")
        mostrar_menu_captcha_grupo(
            chat_id, canal_key, pagina, message=call.message
        )
        return

    if accion == "captcha_delete" and not valores:
        actualizar_ajustes_grupo(
            canal_key,
            lambda ajustes: ajustes.update({
                "captcha_delete_service_message": not bool(
                    ajustes.get("captcha_delete_service_message", False)
                )
            }),
        )
        bot.answer_callback_query(call.id, "Ajuste actualizado.")
        mostrar_menu_captcha_grupo(
            chat_id, canal_key, pagina, message=call.message
        )
        return

    if accion == "night_action" and len(valores) == 1:
        value = valores[0]
        if value not in ("delete", "mute"):
            bot.answer_callback_query(call.id, "Acción no disponible.")
            return
        actualizar_ajustes_grupo(
            canal_key, lambda ajustes: ajustes.update({"night_mode_action": value})
        )
        bot.answer_callback_query(call.id, "Acción nocturna actualizada.")
        mostrar_menu_modo_nocturno(
            chat_id, canal_key, pagina, message=call.message
        )
        return

    if accion == "night_duration" and len(valores) == 1:
        try:
            seconds = int(valores[0])
        except ValueError:
            seconds = 0
        if seconds not in (3600, 28800, 86400):
            bot.answer_callback_query(call.id, "Duración no disponible.")
            return
        actualizar_ajustes_grupo(
            canal_key,
            lambda ajustes: ajustes.update({"night_mode_duration_seconds": seconds}),
        )
        bot.answer_callback_query(call.id, "Duración actualizada.")
        mostrar_menu_modo_nocturno(
            chat_id, canal_key, pagina, message=call.message
        )
        return

    if accion == "warning_limit" and len(valores) == 1:
        try:
            warning_limit = int(valores[0])
        except ValueError:
            warning_limit = 0
        if warning_limit not in (2, 3, 5, 10):
            bot.answer_callback_query(call.id, "Límite no disponible.")
            return
        actualizar_ajustes_grupo(
            canal_key,
            lambda ajustes: ajustes.update({"warning_limit": warning_limit}),
        )
        bot.answer_callback_query(call.id, "Límite actualizado.")
        mostrar_menu_advertencias_grupo(
            chat_id, canal_key, pagina, message=call.message
        )
        return

    if accion == "warning_action" and len(valores) == 1:
        value = valores[0]
        if value not in {action for _, action in GROUP_MODERATION_ACTIONS}:
            bot.answer_callback_query(call.id, "Acción no disponible.")
            return
        actualizar_ajustes_grupo(
            canal_key, lambda ajustes: ajustes.update({"warning_action": value})
        )
        bot.answer_callback_query(call.id, "Acción actualizada.")
        mostrar_menu_advertencias_grupo(
            chat_id, canal_key, pagina, message=call.message
        )
        return

    if accion == "warning_duration" and len(valores) == 1:
        try:
            seconds = int(valores[0])
        except ValueError:
            seconds = 0
        if seconds not in (3600, 86400, 604800):
            bot.answer_callback_query(call.id, "Duración no disponible.")
            return
        actualizar_ajustes_grupo(
            canal_key,
            lambda ajustes: ajustes.update({"warning_duration_seconds": seconds}),
        )
        bot.answer_callback_query(call.id, "Duración actualizada.")
        mostrar_menu_advertencias_grupo(
            chat_id, canal_key, pagina, message=call.message
        )
        return

    if accion == "back" and len(valores) == 1:
        seccion = valores[0]
        if seccion == "root":
            bot.answer_callback_query(call.id)
            volver_antispam()
        elif seccion in ("telegram", "internet", "forward", "quotes"):
            bot.answer_callback_query(call.id)
            volver_antispam(seccion=seccion)
        else:
            bot.answer_callback_query(call.id, "Sección no disponible.")
        return

    if accion == "exceptions" and len(valores) == 1:
        policy_id = valores[0]
        if policy_id not in GROUP_MODERATION_POLICY_LABELS:
            bot.answer_callback_query(call.id, "Ajuste no disponible.")
            return
        bot.answer_callback_query(call.id)
        mostrar_menu_excepciones_moderacion(
            chat_id, canal_key, pagina, policy_id, message=call.message
        )
        return

    if accion == "exc_rm" and len(valores) == 2:
        policy_id, index_txt = valores
        try:
            index = int(index_txt)
        except ValueError:
            bot.answer_callback_query(call.id, "Excepción inválida.")
            return
        def quitar_excepcion(ajustes):
            policy = ajustes.setdefault("moderation_policies", {}).setdefault(
                policy_id, {}
            )
            exceptions = policy.setdefault("exceptions", [])
            if 0 <= index < len(exceptions):
                exceptions.pop(index)
        actualizar_ajustes_grupo(canal_key, quitar_excepcion)
        bot.answer_callback_query(call.id, "Excepción eliminada.")
        mostrar_menu_excepciones_moderacion(
            chat_id, canal_key, pagina, policy_id, message=call.message,
            aviso="Excepción eliminada.",
        )
        return

    if accion == "flood_edit" and len(valores) == 1 and valores[0] in ("limit", "window"):
        field = valores[0]
        admin_estado[call.from_user.id] = {
            "paso": "esperando_valor_antiflood",
            "canal_key": canal_key,
            "pagina": pagina,
            "field": field,
            "panel_message_id": call.message.message_id,
        }
        label = "cantidad de mensajes (1–100)" if field == "limit" else "ventana en segundos (1–300)"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "↩️ Volver a Anti-flood",
            callback_data=f"grupo_feature|{canal_key}|antiflood|{pagina}",
        ))
        bot.answer_callback_query(call.id)
        editar_o_enviar_panel(
            chat_id,
            f"🌊 <b>Configurar Anti-flood</b>\n\nEnvía la {label}.",
            markup, message=call.message, forzar_texto=True,
        )
        return

    if accion == "flood_action" and len(valores) == 1:
        value = valores[0]
        if value not in {action for _, action in GROUP_MODERATION_ACTIONS}:
            bot.answer_callback_query(call.id, "Acción no disponible.")
            return
        def guardar_accion_flood(ajustes):
            ajustes["flood_action"] = value
            ajustes.setdefault("enabled", {})["antiflood"] = (
                value != "off" or bool(ajustes.get("flood_delete_messages", False))
            )
        actualizar_ajustes_grupo(canal_key, guardar_accion_flood)
        bot.answer_callback_query(call.id, "Castigo actualizado.")
        mostrar_menu_antiflood(chat_id, canal_key, pagina, message=call.message)
        return

    if accion == "flood_delete" and not valores:
        def alternar_flood_delete(ajustes):
            ajustes["flood_delete_messages"] = not bool(
                ajustes.get("flood_delete_messages", True)
            )
            ajustes.setdefault("enabled", {})["antiflood"] = (
                ajustes.get("flood_action", "off") != "off"
                or ajustes["flood_delete_messages"]
            )
        actualizar_ajustes_grupo(canal_key, alternar_flood_delete)
        bot.answer_callback_query(call.id, "Eliminación actualizada.")
        mostrar_menu_antiflood(chat_id, canal_key, pagina, message=call.message)
        return

    if accion == "media_page" and len(valores) == 1:
        try:
            media_page = int(valores[0])
        except ValueError:
            media_page = 0
        bot.answer_callback_query(call.id)
        mostrar_menu_multimedia_grupo(
            chat_id, canal_key, pagina, message=call.message,
            media_page=media_page,
        )
        return

    if accion == "media_global" and len(valores) == 1:
        try:
            media_page = int(valores[0])
        except ValueError:
            media_page = 0
        def alternar_toda_multimedia(ajustes):
            current = bool(
                ajustes.get(
                    "media_global_block",
                    ajustes.get("enabled", {}).get("multimedia", False),
                )
            )
            ajustes["media_global_block"] = not current
        actualizar_ajustes_grupo(canal_key, alternar_toda_multimedia)
        bot.answer_callback_query(call.id, "Filtro general actualizado.")
        mostrar_menu_multimedia_grupo(
            chat_id, canal_key, pagina, message=call.message,
            media_page=media_page,
        )
        return

    if accion == "media_open" and len(valores) == 2:
        try:
            media_page = int(valores[0])
        except ValueError:
            media_page = 0
        media_type = valores[1]
        allowed = {key for page_items in GROUP_MEDIA_PAGES for key, _ in page_items}
        if media_type not in allowed:
            bot.answer_callback_query(call.id, "Tipo de contenido no disponible.")
            return
        bot.answer_callback_query(call.id)
        mostrar_menu_multimedia_grupo(
            chat_id, canal_key, pagina, message=call.message,
            media_type=media_type, media_page=media_page,
        )
        return

    if accion == "media_set" and len(valores) == 3:
        try:
            media_page = int(valores[0])
        except ValueError:
            media_page = 0
        media_type, value = valores[1:]
        allowed = {key for page_items in GROUP_MEDIA_PAGES for key, _ in page_items}
        if media_type not in allowed or value not in (
            "off", "warn", "kick", "mute", "ban", "delete"
        ):
            bot.answer_callback_query(call.id, "Acción no disponible.")
            return
        def guardar_accion_media(ajustes):
            policies = ajustes.setdefault("media_policies", {})
            policies[media_type] = value
            if "media_global_block" not in ajustes:
                ajustes["media_global_block"] = False
        actualizar_ajustes_grupo(canal_key, guardar_accion_media)
        bot.answer_callback_query(call.id, "Acción actualizada.")
        mostrar_menu_multimedia_grupo(
            chat_id, canal_key, pagina, message=call.message,
            media_type=media_type, media_page=media_page,
        )
        return

    bot.answer_callback_query(call.id, "Ese ajuste aún no está disponible.")


@bot.callback_query_handler(func=lambda call: call.data.startswith("grupo_editar|"))
def callback_editar_ajuste_grupo(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    partes = call.data.split("|")
    if len(partes) not in (4, 5):
        bot.answer_callback_query(call.id, "No pude leer el ajuste.")
        return
    _, canal_key, feature, pagina_txt, *modo_edicion = partes
    modo_edicion = modo_edicion[0] if modo_edicion else "add"
    if canal_key not in CANALES or feature not in GROUP_FEATURE_TEXT_PROMPTS:
        bot.answer_callback_query(call.id, "Opción no disponible.")
        return
    try:
        pagina = max(0, int(pagina_txt))
    except ValueError:
        pagina = 0
    ajustes = obtener_ajustes_grupo(canal_key) or {}
    ingles = ajustes.get("language", "es") == "en"
    label, prompt = (
        GROUP_FEATURE_TEXT_PROMPTS_EN.get(feature, GROUP_FEATURE_TEXT_PROMPTS[feature])
        if ingles else
        GROUP_FEATURE_TEXT_PROMPTS[feature]
    )
    if feature in ("palabras", "bloqueos", "enmascarados"):
        if modo_edicion == "remove":
            prompt = "Escribe la palabra o el ID/@username que quieres retirar de la lista."
        elif feature == "palabras":
            prompt = "Escribe una palabra o frase que quieras bloquear."
        elif feature == "bloqueos":
            prompt = "Escribe el ID numérico de usuario que quieres añadir a la blocklist."
        else:
            prompt = "Escribe el ID del chat o @username que será una excepción."
    admin_estado[call.from_user.id] = {
        "paso": "esperando_ajuste_grupo",
        "canal_key": canal_key,
        "feature": feature,
        "pagina": pagina,
        "panel_message_id": call.message.message_id,
        "edit_mode": modo_edicion,
    }
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "↩️ Volver a opciones",
        callback_data=f"grupo_feature|{canal_key}|{feature}|{pagina}",
    ))
    editar_o_enviar_panel(
        call.message.chat.id,
        f"✏️ <b>{html.escape(label)}</b>\n\n{html.escape(prompt)}\n\n"
        + ("Send /cancel to exit." if ingles else "Escribe /cancelar para salir."),
        markup,
        message=call.message,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("grupo_accion|"))
def callback_accion_funcion_grupo(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    partes = call.data.split("|")
    if len(partes) != 5:
        bot.answer_callback_query(call.id, "No pude leer la acción.")
        return
    _, canal_key, feature, accion, pagina_txt = partes
    try:
        pagina = max(0, int(pagina_txt))
    except ValueError:
        pagina = 0
    chat_id = obtener_canal_id(canal_key)
    if not chat_id:
        bot.answer_callback_query(call.id, "Falta configurar el ID del chat.")
        return

    bot.answer_callback_query(call.id)
    if feature == "enlace" and accion == "generar":
        try:
            invite = bot.export_chat_invite_link(chat_id)
            bot.send_message(call.message.chat.id, f"🔗 Enlace del grupo:\n{invite}")
        except Exception as error:
            bot.send_message(
                call.message.chat.id,
                f"No pude generar el enlace. Revisa que el bot sea administrador y pueda invitar miembros.\n"
                f"<code>{html.escape(str(error))}</code>",
                parse_mode="HTML",
            )
    elif feature == "aprobacion" and accion == "crear":
        try:
            invite = bot.create_chat_invite_link(chat_id, creates_join_request=True)
            bot.send_message(
                call.message.chat.id,
                f"📩 Enlace que requiere aprobación:\n{invite.invite_link}",
            )
        except Exception as error:
            bot.send_message(
                call.message.chat.id,
                "No pude crear el enlace con aprobación. El bot necesita permiso para invitar miembros.\n"
                f"<code>{html.escape(str(error))}</code>",
                parse_mode="HTML",
            )
    elif feature == "eliminacion":
        segundos = int(accion)
        try:
            apihelper._make_request(
                TOKEN,
                "setChatMessageAutoDeleteTime",
                method="post",
                params={
                    "chat_id": chat_id,
                    "message_auto_delete_time": segundos,
                },
            )
            actualizar_ajustes_grupo(
                canal_key,
                lambda ajustes: ajustes.update({"auto_delete_seconds": segundos}),
            )
            texto = "Desactivé el borrado automático." if segundos == 0 else (
                f"Los mensajes se borrarán automáticamente después de {segundos // 86400} día(s)."
            )
            bot.send_message(call.message.chat.id, f"✅ {texto}")
        except Exception as error:
            bot.send_message(
                call.message.chat.id,
                "Telegram no aceptó el ajuste. El bot necesita permisos de administrador.\n"
                f"<code>{html.escape(str(error))}</code>",
                parse_mode="HTML",
            )
    elif feature == "topics" and accion == "crear":
        admin_estado[call.from_user.id] = {
            "paso": "esperando_nombre_topic",
            "canal_key": canal_key,
            "pagina": pagina,
        }
        bot.send_message(
            call.message.chat.id,
            "Escribe el nombre del nuevo tema. Esta opción requiere un supergrupo con Topics habilitados.",
        )
    elif feature in ("miembros", "bloqueos") and accion == "ayuda":
        bot.send_message(
            call.message.chat.id,
            "En el grupo, responde al mensaje de una persona con:\n"
            "<code>/warn motivo</code> — advertir (3 advertencias bloquean 1 hora)\n"
            "<code>/mute 10m motivo</code> — silenciar por tiempo\n"
            "<code>/ban motivo</code> — expulsar y bloquear\n"
            "<code>/unban ID</code> — retirar el bloqueo\n"
            "También puedes indicar el ID después del comando.",
            parse_mode="HTML",
        )
    elif feature == "discusion":
        bot.send_message(
            call.message.chat.id,
            "Telegram no permite vincular o cambiar el grupo de discusión mediante Bot API. "
            "Abre el canal → Editar → Discusión y selecciona el grupo allí.",
        )
    elif feature == "registro":
        admin_estado[call.from_user.id] = {
            "paso": "esperando_canal_registro",
            "canal_key": canal_key,
            "pagina": pagina,
        }
        instalar_teclado_persistente(
            call.message.chat.id,
            "Usa el botón 📢 Buscar canal de la barra inferior para elegir dónde recibir los avisos.",
            teclado_atajos_admin(),
        )
        editar_o_enviar_panel(
            call.message.chat.id,
            "Selecciona el canal donde quieres recibir avisos de moderación con el botón 📢 Buscar canal de la barra inferior.",
            message=call.message,
        )
    elif feature == "lang":
        def cambiar_idioma(ajustes):
            ajustes["language"] = "en" if ajustes.get("language", "es") == "es" else "es"
        ajustes = actualizar_ajustes_grupo(canal_key, cambiar_idioma)
        idioma = ajustes.get("language", "es")
        bot.send_message(
            call.message.chat.id,
            (
                "Language saved: English. The group-settings menus now use English."
                if idioma == "en" else
                "Idioma guardado: Español. Los menús de configuración del grupo usarán español."
            ),
        )
    mostrar_menu_funcion_grupo(call.message.chat.id, canal_key, feature, pagina)


# ─── Pase Exprés ─────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data == "admin_pase_expres")
def admin_pase_expres_menu(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    cfg = cargar_config()
    pe  = cfg.get("pase_expres", {})
    activo = pe.get("activo") and pase_expres_activo()

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("⏱️ Activar por tiempo personalizado", callback_data="admin_pe_activar"))
    if activo:
        markup.add(types.InlineKeyboardButton("🔴 Desactivar ahora", callback_data="admin_pe_desactivar"))
    markup.add(types.InlineKeyboardButton("🔙 Volver al panel", callback_data="admin_volver"))

    if activo:
        estado_txt = f"🟢 <b>ACTIVO</b> — vence el <b>{pe.get('vence','?')}</b>"
    else:
        estado_txt = "🔴 <b>INACTIVO</b>"

    bot.send_message(
        call.message.chat.id,
        f"🎟️ <b>PASE EXPRÉS GRATUITO</b>\n\n"
        f"Estado actual: {estado_txt}\n\n"
        f"Cuando está activo, cualquier usuario que abra /start verá un botón destacado "
        f"de acceso gratuito al canal GoldPass.\n\n"
        f"¿Qué deseas hacer?",
        parse_mode="HTML", reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin_pe_activar")
def admin_pe_activar(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    admin_estado[call.from_user.id] = {"paso": "esperando_duracion_pase"}
    bot.send_message(
        call.message.chat.id,
        "⏱️ <b>¿Cuánto tiempo quieres que esté activo el Pase Exprés?</b>\n\n"
        "Escribe la duración, por ejemplo:\n"
        "• <code>30m</code> → 30 minutos\n"
        "• <code>2h</code> → 2 horas\n"
        "• <code>1d</code> → 1 día\n"
        "• <code>90m</code> → 90 minutos",
        parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin_pe_desactivar")
def admin_pe_desactivar(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    actualizar_config(
        lambda cfg: cfg.update({"pase_expres": {"activo": False, "vence": None}})
    )
    bot.send_message(
        call.message.chat.id,
        "🔴 <b>Pase Exprés desactivado.</b>\n\n"
        "El botón ya no aparecerá en /start.",
        parse_mode="HTML"
    )

# ─── Configurar canal destino ─────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data == "admin_setcanal")
def admin_setcanal(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    iniciar_selector_grupo(call.message.chat.id, call.from_user.id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_destino")
def admin_add_destino(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    admin_estado[call.from_user.id] = {"paso": "esperando_nombre_destino"}
    bot.send_message(
        call.message.chat.id,
        "✏️ <b>Escribe un nombre para este grupo o canal</b> "
        "(por ejemplo, «Mi grupo de avisos»):",
        parse_mode="HTML",
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("scanal_"))
def admin_setcanal_elegido(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    canal_key = call.data.split("_", 1)[1]
    if canal_key not in CANALES:
        bot.send_message(call.message.chat.id, "No encontré ese destino.")
        return
    admin_estado[call.from_user.id] = {"paso": "esperando_forward_canal", "canal": canal_key}
    nombre_canal = CANALES[canal_key]["nombre"]
    bot.send_message(
        call.message.chat.id,
        f"📡 <b>Configurar grupo o canal — {html.escape(nombre_canal)}</b>\n\n"
        "<b>Opción 1 — Escribe el ID del canal:</b>\n"
        "Ejemplo: <code>-1003561176552</code>\n\n"
        "<b>Opción 2 — Reenvía un mensaje del grupo o canal:</b>\n"
        "Abre el destino → mantén presionado un mensaje → <b>Reenviar</b> hacia aquí.\n\n"
        "⚠️ El bot debe estar en el grupo o ser <b>administrador</b> del canal para publicar.",
        parse_mode="HTML"
    )

# ─── Crear botón: Paso 0 (elegir canal) ──────────────────────────
@bot.callback_query_handler(func=lambda call: call.data == "admin_crear_boton")
def admin_crear_boton(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "➕ <b>¿Para qué destino es este conjunto de botones?</b>",
        parse_mode="HTML",
        reply_markup=markup_seleccionar_canal("cboton")
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("cboton_"))
def admin_crear_boton_canal_elegido(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    canal_key = call.data.split("_", 1)[1]
    if canal_key not in CANALES:
        bot.send_message(call.message.chat.id, "No encontré ese conjunto de botones.")
        return
    admin_estado[call.from_user.id] = {
        "paso":           "esperando_media_grupo",
        "canal":          canal_key,
        "media_id":       None,
        "media_type":     None,
        "botones_sesion": [],
    }
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⏭️ Sin foto/video", callback_data="admin_skip_media"))
    bot.send_message(
        call.message.chat.id,
        f"🖼️ <b>Paso 1 — Foto o video de la publicación</b>\n"
        f"Destino: <b>{html.escape(CANALES[canal_key]['nombre'])}</b>\n\n"
        "Envía la <b>foto o video</b> que usarán todos los botones de esta publicación.\n"
        "Puedes agregar tantos botones como quieras sobre la misma imagen.\n\n"
        "O toca el botón si no quieres multimedia:",
        parse_mode="HTML",
        reply_markup=markup
    )

# ─── Ver botones ──────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data == "admin_ver_botones")
def admin_ver_botones(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    BOTONES_RETURN_CALLBACK[str(call.message.chat.id)] = "admin_volver"
    editar_o_enviar_panel(
        call.message.chat.id,
        "📋 <b>¿De qué destino quieres ver y administrar los botones?</b>",
        markup_seleccionar_canal("vbotones"),
        message=call.message,
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("vbotones_"))
def admin_ver_botones_canal_elegido(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    canal_key = call.data.split("_", 1)[1]
    if canal_key not in CANALES:
        bot.send_message(call.message.chat.id, "No encontré ese destino.")
        return
    mostrar_gestion_botones(
        call.message.chat.id, canal_key, message=call.message
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("preview_"))
def admin_previsualizar_botones(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    canal_key = call.data.split("_", 1)[1]
    if canal_key not in CANALES:
        bot.send_message(call.message.chat.id, "No encontré ese destino.")
        return
    try:
        mostrar_vista_previa_real(
            call.message.chat.id,
            canal_key,
            message=call.message,
            contexto="buttons",
        )
    except Exception:
        app.logger.exception("No se pudo mostrar la vista previa real de botones.")
        mostrar_gestion_botones(
            call.message.chat.id,
            canal_key,
            message=call.message,
            aviso="No pude mostrar la publicación guardada. Comprueba que sus archivos sigan disponibles.",
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith("btnpreview_nav|"))
def admin_navegar_vista_previa(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    partes = call.data.split("|", 3)
    if (
        len(partes) != 4
        or partes[1] not in ("buttons", "rec")
        or partes[2] not in CANALES
    ):
        bot.answer_callback_query(call.id, "No entendí esa vista previa.")
        return
    try:
        indice = int(partes[3])
    except ValueError:
        bot.answer_callback_query(call.id, "No entendí esa selección.")
        return
    bot.answer_callback_query(call.id)
    try:
        mostrar_vista_previa_real(
            call.message.chat.id,
            partes[2],
            message=call.message,
            contexto=partes[1],
            indice_media=indice,
        )
    except Exception:
        app.logger.exception("No se pudo cambiar el archivo de la vista previa.")
        mostrar_error_vista_previa(
            call.message,
            partes[2],
            partes[1],
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith("btnpreview_info|"))
def admin_indicador_pagina_vista_previa(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("btnpreview_back|"))
def admin_regresar_desde_vista_previa(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    partes = call.data.split("|", 2)
    if (
        len(partes) != 3
        or partes[1] not in ("buttons", "rec")
        or partes[2] not in CANALES
    ):
        bot.answer_callback_query(call.id, "No entendí a dónde regresar.")
        return
    bot.answer_callback_query(call.id)
    if partes[1] == "buttons":
        mostrar_gestion_botones(
            call.message.chat.id,
            partes[2],
            message=call.message,
        )
    else:
        botones_key = obtener_botones_key_panel_recurrente(
            call.message.chat.id,
            call.message,
            partes[2],
        )
        mostrar_menu_recurrente(
            call.message.chat.id,
            botones_key,
            partes[2],
            message=call.message,
        )


def mostrar_error_vista_previa(message, destino_key, contexto):
    aviso = (
        "No pude mostrar la publicación guardada. "
        "Comprueba que sus archivos sigan disponibles."
    )
    if contexto == "rec":
        botones_key = obtener_botones_key_panel_recurrente(
            message.chat.id,
            message,
            destino_key,
        )
        mostrar_menu_recurrente(
            message.chat.id,
            botones_key,
            destino_key,
            message=message,
            aviso=aviso,
        )
    else:
        mostrar_gestion_botones(
            message.chat.id,
            destino_key,
            message=message,
            aviso=aviso,
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith("botones_menu|"))
def callback_volver_menu_botones(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    _, canal_key = call.data.split("|", 1)
    if canal_key not in CANALES:
        bot.answer_callback_query(call.id, "No encontré ese destino.")
        return
    bot.answer_callback_query(call.id)
    mostrar_gestion_botones(
        call.message.chat.id, canal_key, message=call.message
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("botones_media_lista|")
)
def admin_lista_multimedia_botones(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    canal_key = call.data.split("|", 1)[1]
    if canal_key not in CANALES:
        bot.answer_callback_query(call.id, "No encontré ese destino.")
        return
    bot.answer_callback_query(call.id)
    mostrar_lista_media_botones(
        call.message.chat.id,
        canal_key,
        message=call.message,
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("botones_lote_item|")
)
def admin_abrir_boton_lote(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    partes = call.data.split("|", 2)
    if len(partes) != 3 or partes[1] not in CANALES:
        bot.answer_callback_query(call.id, "No encontré ese botón.")
        return
    try:
        indice = int(partes[2])
    except ValueError:
        bot.answer_callback_query(call.id, "No entendí la selección.")
        return
    bot.answer_callback_query(call.id)
    mostrar_editor_boton_lote(
        call.message.chat.id, partes[1], indice, message=call.message
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("botones_lote_lista|")
)
def admin_volver_lista_botones_lote(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    canal_key = call.data.split("|", 1)[1]
    bot.answer_callback_query(call.id)
    mostrar_lista_media_botones(
        call.message.chat.id, canal_key, message=call.message
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("botones_lote_preview|")
)
def admin_volver_vista_previa_lote(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    canal_key = call.data.split("|", 1)[1]
    bot.answer_callback_query(call.id)
    mostrar_vista_previa_botones_lote(call.message.chat.id, canal_key)


def iniciar_edicion_texto_boton_lote(call, tipo_campo):
    partes = call.data.split("|", 2)
    if len(partes) != 3 or partes[1] not in CANALES:
        bot.answer_callback_query(call.id, "No encontré ese botón.")
        return
    try:
        indice = int(partes[2])
    except ValueError:
        bot.answer_callback_query(call.id, "No entendí la selección.")
        return
    estado = admin_estado.get(call.from_user.id, {})
    botones = estado.get("botones_borrador", [])
    if (
        estado.get("tipo_editor") != "botones_lote"
        or estado.get("canal_key") != partes[1]
        or not 0 <= indice < len(botones)
    ):
        bot.answer_callback_query(call.id, "El borrador venció; vuelve a abrirlo.")
        return
    estado["paso"] = (
        "esperando_nombre_boton_lote"
        if tipo_campo == "nombre"
        else "esperando_url_boton_lote"
    )
    estado["indice_boton_borrador"] = indice
    estado["panel_message_id"] = call.message.message_id
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "↩️ Cancelar edición",
        callback_data=f"botones_lote_cancelar_input|{partes[1]}",
    ))
    texto = (
        "Escribe el nuevo nombre del botón."
        if tipo_campo == "nombre"
        else "Escribe el nuevo enlace completo, empezando por https://"
    )
    editar_o_enviar_panel(
        call.message.chat.id, texto, markup, message=call.message,
        forzar_texto=True,
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("botones_lote_nombre|")
)
def admin_editar_nombre_boton_lote(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    iniciar_edicion_texto_boton_lote(call, "nombre")


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("botones_lote_url|")
)
def admin_editar_url_boton_lote(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    iniciar_edicion_texto_boton_lote(call, "url")


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("botones_lote_cancelar_input|")
)
def admin_cancelar_input_boton_lote(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    canal_key = call.data.split("|", 1)[1]
    estado = admin_estado.get(call.from_user.id, {})
    estado["paso"] = "editar_botones_lote"
    bot.answer_callback_query(call.id, "Edición cancelada.")
    mostrar_lista_media_botones(
        call.message.chat.id, canal_key, message=call.message
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("botones_lote_nuevo|")
)
def admin_agregar_boton_lote(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    canal_key = call.data.split("|", 1)[1]
    estado = admin_estado.get(call.from_user.id, {})
    if estado.get("tipo_editor") != "botones_lote" or estado.get("canal_key") != canal_key:
        bot.answer_callback_query(call.id, "El borrador venció; vuelve a abrirlo.")
        return
    estado["paso"] = "esperando_nombre_nuevo_boton_lote"
    estado["panel_message_id"] = call.message.message_id
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "↩️ Cancelar", callback_data=f"botones_lote_cancelar_input|{canal_key}"
    ))
    editar_o_enviar_panel(
        call.message.chat.id,
        "Escribe el nombre del nuevo botón.",
        markup,
        message=call.message,
        forzar_texto=True,
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("botones_lote_media|")
)
def admin_cambiar_media_botones_lote(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    canal_key = call.data.split("|", 1)[1]
    estado = admin_estado.get(call.from_user.id, {})
    if estado.get("tipo_editor") != "botones_lote" or estado.get("canal_key") != canal_key:
        bot.answer_callback_query(call.id, "El borrador venció; vuelve a abrirlo.")
        return
    estado["paso"] = "esperando_media_botones_lote"
    estado["panel_message_id"] = call.message.message_id
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "↩️ Cancelar",
        callback_data=f"botones_lote_cancelar_input|{canal_key}",
    ))
    editar_o_enviar_panel(
        call.message.chat.id,
        "Envíame una foto, video, documento, audio o animación para usar como "
        "multimedia única de la publicación. Reemplazará la imagen actual; no "
        "tienes que enviar un archivo por cada botón.",
        markup,
        message=call.message,
        forzar_texto=True,
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("botones_lote_confirmar|")
)
def admin_confirmar_borrador_botones(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    canal_key = call.data.split("|", 1)[1]
    estado = admin_estado.get(call.from_user.id, {})
    if estado.get("tipo_editor") != "botones_lote" or estado.get("canal_key") != canal_key:
        bot.answer_callback_query(call.id, "El borrador venció; vuelve a abrirlo.")
        return
    botones = estado.get("botones_borrador", [])
    if not botones:
        bot.answer_callback_query(call.id, "Agrega por lo menos un botón.", show_alert=True)
        return
    invalidos = [
        indice + 1 for indice, boton in enumerate(botones)
        if not str(boton.get("texto") or "").strip()
        or not str(boton.get("url") or "").startswith(("https://", "http://"))
    ]
    if invalidos:
        bot.answer_callback_query(
            call.id,
            f"Revisa nombre o enlace del botón {invalidos[0]}.",
            show_alert=True,
        )
        return
    guardar_botones_custom(canal_key, botones)
    guardar_media_compartida_botones(
        canal_key, estado.get("media_borrador", {})
    )
    estado["paso"] = "botones_lote_preview"
    bot.answer_callback_query(call.id, "Cambios guardados. Revisa la vista previa.")
    mostrar_vista_previa_botones_lote(call.message.chat.id, canal_key)


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("botones_lote_descartar|")
)
def admin_descartar_borrador_botones(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    canal_key = call.data.split("|", 1)[1]
    admin_estado.pop(call.from_user.id, None)
    bot.answer_callback_query(call.id, "Borrador descartado.")
    mostrar_gestion_botones(
        call.message.chat.id, canal_key, message=call.message
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("botones_lote_publicar|")
)
def admin_elegir_destino_publicar_borrador(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    canal_key = call.data.split("|", 1)[1]
    estado = admin_estado.get(call.from_user.id, {})
    if estado.get("tipo_editor") != "botones_lote" or estado.get("canal_key") != canal_key:
        bot.answer_callback_query(call.id, "El borrador venció; vuelve a abrirlo.")
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    for destino_key, info in CANALES.items():
        estado_destino = "✅" if obtener_canal_id(destino_key) else "⚠️"
        markup.add(types.InlineKeyboardButton(
            f"{estado_destino} {info['nombre']}",
            callback_data=f"botones_lote_destino|{canal_key}|{destino_key}",
        ))
    markup.add(types.InlineKeyboardButton(
        "↩️ Regresar a vista previa",
        callback_data=f"botones_lote_preview|{canal_key}",
    ))
    estado["panel_message_id"] = call.message.message_id
    bot.answer_callback_query(call.id)
    editar_o_enviar_panel(
        call.message.chat.id,
        "📤 <b>¿A qué grupo o canal quieres enviar la publicación actualizada?</b>",
        markup,
        message=call.message,
        forzar_texto=True,
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("botones_lote_destino|")
)
def admin_confirmar_destino_borrador(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    partes = call.data.split("|", 2)
    if len(partes) != 3 or partes[1] not in CANALES or partes[2] not in CANALES:
        bot.answer_callback_query(call.id, "No encontré el destino.")
        return
    canal_key, destino_key = partes[1], partes[2]
    canal_dest = obtener_canal_id(destino_key)
    if not canal_dest:
        bot.answer_callback_query(call.id, "Ese grupo o canal no está configurado.", show_alert=True)
        return
    estado = admin_estado.get(call.from_user.id, {})
    if estado.get("tipo_editor") != "botones_lote" or estado.get("canal_key") != canal_key:
        bot.answer_callback_query(call.id, "El borrador venció.")
        return
    estado["destino_publicacion"] = destino_key
    estado["panel_message_id"] = call.message.message_id
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton(
            "✅ Publicar ahora",
            callback_data=f"botones_lote_publicar_confirmar|{canal_key}|{destino_key}",
        ),
        types.InlineKeyboardButton(
            "❌ Cancelar",
            callback_data=f"botones_lote_preview|{canal_key}",
        ),
    )
    bot.answer_callback_query(call.id)
    editar_o_enviar_panel(
        call.message.chat.id,
        f"Confirma publicar esta imagen y los {len(estado.get('botones_borrador', []))} botones "
        f"en <b>{html.escape(CANALES[destino_key]['nombre'])}</b>.",
        markup,
        message=call.message,
        forzar_texto=True,
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("botones_lote_publicar_confirmar|")
)
def admin_publicar_borrador_botones(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    partes = call.data.split("|", 2)
    if len(partes) != 3 or partes[1] not in CANALES or partes[2] not in CANALES:
        bot.answer_callback_query(call.id, "No encontré el destino.")
        return
    canal_key, destino_key = partes[1], partes[2]
    estado = admin_estado.get(call.from_user.id, {})
    if estado.get("tipo_editor") != "botones_lote" or estado.get("canal_key") != canal_key:
        bot.answer_callback_query(call.id, "El borrador venció.")
        return
    canal_dest = obtener_canal_id(destino_key)
    if not canal_dest:
        bot.answer_callback_query(call.id, "Ese destino ya no está disponible.")
        return
    botones = estado.get("botones_borrador", [])
    if not botones:
        bot.answer_callback_query(call.id, "No hay botones para publicar.")
        return
    markup_publicacion = construir_markup_botones(botones)
    media = estado.get("media_borrador", {})
    try:
        if media.get("media_type"):
            mensaje = enviar_media_compartida_botones(
                int(canal_dest), media, "Enlaces disponibles:", markup_publicacion
            )
            media_id = media.get("media_id")
            if not media_id:
                objeto_media = getattr(mensaje, media.get("media_type"), None)
                if media.get("media_type") == "photo":
                    fotos = getattr(mensaje, "photo", None) or []
                    objeto_media = fotos[-1] if fotos else None
                media_id = getattr(objeto_media, "file_id", None)
            media_type = media.get("media_type")
        else:
            mensaje = bot.send_message(
                int(canal_dest),
                "Enlaces disponibles:",
                reply_markup=markup_publicacion,
            )
            media_id = media_type = None
        guardar_ultima_publicacion(
            canal_key, canal_dest, mensaje, "Enlaces disponibles:",
            media_id, media_type,
        )
        bot.answer_callback_query(call.id, "Publicación enviada.")
        admin_estado.pop(call.from_user.id, None)
        markup_fin = types.InlineKeyboardMarkup()
        markup_fin.add(types.InlineKeyboardButton(
            "↩️ Volver a administrar botones",
            callback_data=f"botones_menu|{canal_key}",
        ))
        editar_o_enviar_panel(
            call.message.chat.id,
            f"✅ Publicación enviada a <b>{html.escape(CANALES[destino_key]['nombre'])}</b>.",
            markup_fin,
            message=call.message,
            forzar_texto=True,
        )
    except Exception as error:
        app.logger.exception("No se pudo publicar el borrador de botones.")
        bot.answer_callback_query(call.id, "No pude publicar; revisa los permisos del bot.", show_alert=True)
        markup_error = types.InlineKeyboardMarkup()
        markup_error.add(types.InlineKeyboardButton(
            "↩️ Regresar a la vista previa",
            callback_data=f"botones_lote_preview|{canal_key}",
        ))
        editar_o_enviar_panel(
            call.message.chat.id,
            f"❌ No se pudo publicar: <code>{html.escape(str(error))}</code>",
            markup_error,
            message=call.message,
            forzar_texto=True,
        )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("botones_media_item|")
)
def admin_elegir_boton_para_media(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    partes = call.data.split("|", 2)
    if len(partes) != 3 or partes[1] not in CANALES:
        bot.answer_callback_query(call.id, "No encontré ese botón.")
        return
    try:
        indice = int(partes[2])
    except ValueError:
        bot.answer_callback_query(call.id, "No entendí la selección.")
        return
    bot.answer_callback_query(call.id)
    mostrar_editor_media_boton(
        call.message.chat.id,
        partes[1],
        indice,
        message=call.message,
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("botones_media_subir|")
)
def admin_iniciar_actualizacion_media_boton(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    partes = call.data.split("|", 2)
    if len(partes) != 3 or partes[1] not in CANALES:
        bot.answer_callback_query(call.id, "No encontré ese botón.")
        return
    try:
        indice = int(partes[2])
    except ValueError:
        bot.answer_callback_query(call.id, "No entendí la selección.")
        return
    botones = cargar_botones_custom(partes[1])
    if indice < 0 or indice >= len(botones):
        bot.answer_callback_query(call.id, "Ese botón ya no existe.")
        return
    bot.answer_callback_query(call.id)
    admin_estado[call.from_user.id] = {
        "paso": "esperando_media_boton_update",
        "canal_key": partes[1],
        "boton_idx": indice,
        "panel_message_id": call.message.message_id,
    }
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "↩️ Cancelar",
        callback_data=f"botones_media_cancelar|{partes[1]}|{indice}",
    ))
    editar_o_enviar_panel(
        call.message.chat.id,
        f"📤 <b>Actualizar multimedia — "
        f"{html.escape(str(botones[indice].get('texto') or 'Botón'))}</b>\n\n"
        "Envíame una foto, vídeo, documento, audio o animación. "
        "Se reemplazará únicamente el archivo de este botón; "
        "su etiqueta y enlace permanecerán iguales.",
        markup,
        message=call.message,
        forzar_texto=True,
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("botones_media_cancelar|")
)
def admin_cancelar_actualizacion_media_boton(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    partes = call.data.split("|", 2)
    if len(partes) != 3 or partes[1] not in CANALES:
        bot.answer_callback_query(call.id, "No encontré ese destino.")
        return
    try:
        indice = int(partes[2])
    except ValueError:
        bot.answer_callback_query(call.id, "No entendí la selección.")
        return
    bot.answer_callback_query(call.id, "Actualización cancelada.")
    admin_estado.pop(call.from_user.id, None)
    mostrar_editor_media_boton(
        call.message.chat.id,
        partes[1],
        indice,
        message=call.message,
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("botones_recurrente|")
)
def admin_abrir_recurrentes_desde_botones(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    canal_key = call.data.split("|", 1)[1]
    if canal_key not in CANALES:
        bot.answer_callback_query(call.id, "No encontré ese destino.")
        return
    bot.answer_callback_query(call.id)
    mostrar_menu_recurrente(
        call.message.chat.id,
        canal_key,
        canal_key,
        message=call.message,
    )


def guardar_media_en_boton(message, media_id, media_type):
    uid = message.from_user.id
    estado = admin_estado.get(uid, {})
    if estado.get("paso") != "esperando_media_boton_update":
        return False
    canal_key = estado.get("canal_key")
    indice = estado.get("boton_idx")
    panel_message_id = estado.get("panel_message_id")
    botones = cargar_botones_custom(canal_key) if canal_key in CANALES else []
    if indice is None or indice < 0 or indice >= len(botones):
        admin_estado.pop(uid, None)
        eliminar_mensaje_disparador(message)
        editar_o_enviar_panel(
            message.chat.id,
            "Ese botón ya no existe; no guardé el archivo.",
            types.InlineKeyboardMarkup(),
            message_id=panel_message_id,
            forzar_texto=True,
        )
        return True
    botones[indice]["media_id"] = media_id
    botones[indice]["media_type"] = media_type
    guardar_botones_custom(canal_key, botones)
    admin_estado.pop(uid, None)
    eliminar_mensaje_disparador(message)
    mostrar_gestion_botones(
        message.chat.id,
        canal_key,
        message_id=panel_message_id,
        aviso=(
            "Multimedia actualizada. El nombre y el enlace se conservaron; "
            "los mensajes recurrentes ya guardados no se modificaron."
        ),
    )
    return True


def guardar_media_botones_lote(message, media_id, media_type):
    uid = message.from_user.id
    estado = admin_estado.get(uid, {})
    if (
        estado.get("tipo_editor") != "botones_lote"
        or estado.get("paso") != "esperando_media_botones_lote"
    ):
        return False
    estado["media_borrador"] = {
        "media_id": media_id,
        "media_type": media_type,
    }
    estado["paso"] = "editar_botones_lote"
    panel_message_id = estado.get("panel_message_id")
    eliminar_mensaje_disparador(message)
    mostrar_lista_media_botones(
        message.chat.id,
        estado.get("canal_key"),
        message_id=panel_message_id,
        aviso="Multimedia reemplazada en el borrador. Confirma para guardarla.",
    )
    return True


def guardar_media_reglamento(message, media_id, media_type):
    uid = message.from_user.id
    estado = admin_estado.get(uid, {})
    if estado.get("paso") != "esperando_media_reglas":
        return False
    canal_key = estado.get("canal_key")
    pagina = estado.get("pagina", 0)
    panel_message_id = estado.get("panel_message_id")
    posicion = estado.get("posicion")
    admin_estado.pop(uid, None)
    eliminar_mensaje_disparador(message)
    if canal_key not in CANALES or posicion not in ("before", "after"):
        editar_o_enviar_panel(
            message.chat.id,
            "No encontré el destino o la ubicación de este archivo.",
            types.InlineKeyboardMarkup(),
            message_id=panel_message_id,
            forzar_texto=True,
        )
        return True
    actualizar_ajustes_grupo(
        canal_key,
        lambda ajustes: ajustes.update({
            f"rules_media_{posicion}": {
                "media_id": media_id,
                "media_type": media_type,
            }
        }),
    )
    mostrar_editor_reglamento(
        message.chat.id,
        canal_key,
        pagina,
        message_id=panel_message_id,
        aviso="Multimedia guardado.",
    )
    return True


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


def mostrar_menu_recurrente(chat_id, botones_key, destino_key, message=None, aviso=None):
    recurrente = cargar_config().get("recurrentes", {}).get(destino_key, {})
    botones_destino = cargar_botones_custom(destino_key)
    ultima = buscar_ultima_publicacion_destino(destino_key)
    markup = types.InlineKeyboardMarkup(row_width=1)

    if recurrente.get("activo"):
        markup.add(types.InlineKeyboardButton(
            "⏸️ Pausar o eliminar publicación recurrente",
            callback_data=f"rec_pausar_menu|{destino_key}",
        ))
        restante = max(0, int(float(recurrente.get("proximo_envio", time.time())) - time.time()))
        estado = (
            f"🟢 Activo cada {formato_intervalo(int(recurrente['intervalo_segundos']))}.\n"
            f"Conjunto de botones: {html.escape(CANALES.get(recurrente.get('botones_key'), {}).get('nombre', 'desconocido'))}.\n"
            f"Próxima publicación: en aproximadamente {formato_intervalo(max(60, restante))}."
        )
    elif recurrente:
        estado = "⏸️ Pausado. El último mensaje recurrente publicado se conserva."
    else:
        estado = "🔴 No hay una publicación recurrente configurada en este destino."

    if ultima:
        ultima_botones_key, publicacion = ultima
        cantidad_media = len(media_items_de_publicacion(publicacion))
        tiene_texto = bool(str(publicacion.get("texto") or "").strip())
        resumen_publicacion = (
            "\n\n<b>Publicación real disponible:</b> "
            f"{'mensaje' if tiene_texto else 'sin texto'}"
            f"{' y ' if tiene_texto and cantidad_media else ''}"
            f"{f'{cantidad_media} archivo(s) multimedia' if cantidad_media else ''}."
        )
        markup.add(types.InlineKeyboardButton(
            "🔁 Repetir la última publicación",
            callback_data=f"rec_repetir_ultima|{destino_key}",
        ))
    else:
        resumen_publicacion = "\n\nNo hay una publicación real guardada para previsualizar."

    if botones_destino:
        markup.add(types.InlineKeyboardButton(
            "🔁 Repetir los botones actuales",
            callback_data=f"rec_repetir_botones|{destino_key}",
        ))
        nombres_botones = "\n".join(
            f"• {html.escape(str(boton.get('texto') or 'Botón'))}"
            for boton in botones_destino[:12]
        )
        if len(botones_destino) > 12:
            nombres_botones += f"\n• … y {len(botones_destino) - 12} más"
        resumen_botones = (
            f"\n\n<b>Botones configurados para este destino "
            f"({len(botones_destino)}):</b>\n{nombres_botones}"
        )
    else:
        resumen_botones = "\n\nEste destino todavía no tiene botones guardados."

    markup.add(types.InlineKeyboardButton(
        "👁️ Vista previa real",
        callback_data=f"rec_preview|{destino_key}",
    ))
    markup.add(types.InlineKeyboardButton(
        "🆕 Crear un mensaje recurrente",
        callback_data=f"rec_config|{destino_key}|{destino_key}",
    ))
    markup.add(
        types.InlineKeyboardButton(
            "🔙 Elegir otro destino", callback_data="rec_choose"
        ),
        types.InlineKeyboardButton(
            "Volver a los botones", callback_data=f"botones_menu|{botones_key}"
        ),
    )
    texto_menu = (
        f"⏰ <b>Mensajes recurrentes — {html.escape(CANALES[destino_key]['nombre'])}</b>\n\n"
        f"{estado}{resumen_publicacion}{resumen_botones}\n\n"
        "El contenido real solo aparecerá al pulsar «Vista previa real». "
        "Al publicarse el siguiente mensaje, el bot intentará borrar el recurrente anterior "
        "de este destino. El primer envío será después del intervalo elegido."
    )
    if aviso:
        texto_menu = f"✅ {html.escape(aviso)}\n\n" + texto_menu
    panel = editar_o_enviar_panel(
        chat_id,
        texto_menu,
        markup,
        message=message,
        forzar_texto=True,
    )
    guardar_contexto_recurrente_panel(
        chat_id,
        getattr(panel, "message_id", None),
        botones_key,
        destino_key,
    )
    return panel

@bot.callback_query_handler(func=lambda call: call.data.startswith("rec_menu_"))
def admin_menu_recurrente(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    editar_o_enviar_panel(
        call.message.chat.id,
        "⏰ <b>Mensajes recurrentes</b>\nSelecciona un destino guardado:",
        markup_destinos_recurrentes(),
        message=call.message,
    )


@bot.callback_query_handler(func=lambda call: call.data == "rec_choose")
def admin_elegir_otro_destino_recurrente(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    editar_o_enviar_panel(
        call.message.chat.id,
        "⏰ <b>Mensajes recurrentes</b>\nSelecciona un destino guardado:",
        markup_destinos_recurrentes(),
        message=call.message,
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("rec_destino|"))
def admin_recurrente_elegir_destino(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    partes = call.data.split("|", 2)
    if len(partes) != 3 or partes[1] not in CANALES or partes[2] not in CANALES:
        bot.send_message(call.message.chat.id, "No encontré el conjunto o el destino.")
        return
    mostrar_menu_recurrente(
        call.message.chat.id, partes[1], partes[2], message=call.message
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("rec_preview|"))
def admin_previsualizar_recurrente(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    destino_key = call.data.split("|", 1)[1]
    if destino_key not in CANALES:
        bot.answer_callback_query(call.id, "No encontré ese destino.")
        return
    bot.answer_callback_query(call.id)
    try:
        mostrar_vista_previa_real(
            call.message.chat.id,
            destino_key,
            message=call.message,
            contexto="rec",
        )
    except Exception:
        app.logger.exception("No se pudo mostrar la vista previa recurrente.")
        mostrar_error_vista_previa(
            call.message,
            destino_key,
            "rec",
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith("rec_repetir_"))
def admin_repetir_contenido_recurrente(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    partes = call.data.split("|", 1)
    if len(partes) != 2:
        bot.send_message(call.message.chat.id, "No entendí el contenido seleccionado.")
        return

    accion, destino_key = partes[0], partes[1]
    if destino_key not in CANALES or not obtener_canal_id(destino_key):
        bot.send_message(call.message.chat.id, "Configura primero el grupo o canal.")
        return

    ultima = buscar_ultima_publicacion_destino(destino_key)
    if accion == "rec_repetir_ultima":
        if not ultima:
            bot.send_message(call.message.chat.id, "Ya no encontré una publicación anterior.")
            return
        botones_key, publicacion = ultima
        texto = publicacion.get("texto", "")
        media_items = media_items_de_publicacion(publicacion)
    elif accion == "rec_repetir_botones":
        botones_key = destino_key
        botones = cargar_botones_custom(destino_key)
        if not botones:
            bot.send_message(call.message.chat.id, "Este destino no tiene botones guardados.")
            return
        primer_archivo = next(
            (
                {"media_id": boton["media_id"], "media_type": boton["media_type"]}
                for boton in botones
                if boton.get("media_id") and boton.get("media_type")
            ),
            None,
        )
        media_items = [primer_archivo] if primer_archivo else []
        texto = "Elige una opción:"
    else:
        bot.send_message(call.message.chat.id, "No reconocí esa opción.")
        return

    admin_estado[call.from_user.id] = {
        "paso": "esperando_intervalo_recurrente",
        "tipo_recurrente": "repetir",
        "botones_key": botones_key,
        "canal": destino_key,
        "texto_recurrente": texto,
        "media_items": media_items,
        "media_id": media_items[0]["media_id"] if len(media_items) == 1 else None,
        "media_type": media_items[0]["media_type"] if len(media_items) == 1 else None,
    }
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Cancelar", callback_data="rec_abortar"))
    bot.send_message(
        call.message.chat.id,
        "⏱️ <b>¿Cada cuánto quieres repetir este contenido?</b>\n\n"
        "Escribe un intervalo como <code>30m</code>, <code>2h</code> o <code>1d</code> "
        "(mínimo 1 minuto, máximo 365 días).",
        parse_mode="HTML",
        reply_markup=markup,
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("rec_config|"))
def admin_configurar_recurrente(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    partes = call.data.split("|", 2)
    if len(partes) != 3:
        bot.send_message(call.message.chat.id, "No entendí la selección.")
        return
    botones_key, destino_key = partes[1], partes[2]
    if botones_key not in CANALES or destino_key not in CANALES:
        bot.send_message(call.message.chat.id, "No encontré el conjunto o el destino.")
        return
    if not obtener_canal_id(destino_key):
        bot.send_message(
            call.message.chat.id,
            f"Primero configura el grupo o canal {html.escape(CANALES[destino_key]['nombre'])}.",
            parse_mode="HTML",
            reply_markup=markup_menu_botones(botones_key),
        )
        return
    admin_estado[call.from_user.id] = {
        "paso": "esperando_intervalo_recurrente",
        "tipo_recurrente": "nuevo",
        "botones_key": botones_key,
        "canal": destino_key,
        "media_items": [],
        "media_id": None,
        "media_type": None,
    }
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Cancelar", callback_data="rec_abortar"))
    bot.send_message(
        call.message.chat.id,
        "⏱️ <b>¿Cada cuánto quieres publicar?</b>\n\n"
        "Escribe un intervalo como <code>30m</code>, <code>2h</code> o <code>1d</code> "
        "(mínimo 1 minuto, máximo 365 días).",
        parse_mode="HTML",
        reply_markup=markup,
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("rec_pausar|"))
def admin_pausar_recurrente(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    destino_key = call.data.split("|", 1)[1]
    if destino_key not in CANALES:
        bot.send_message(call.message.chat.id, "No encontré ese destino.")
        return
    def pausar(cfg):
        recurrente = cfg.get("recurrentes", {}).get(destino_key)
        if recurrente:
            recurrente["activo"] = False
    with RECURRING_LOCK:
        actualizar_config(pausar)
    recurrente = cargar_config().get("recurrentes", {}).get(destino_key, {})
    mostrar_menu_recurrente(
        call.message.chat.id,
        recurrente.get("botones_key", destino_key),
        destino_key,
        message=call.message,
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("rec_pausar_menu|"))
def admin_menu_pausar_recurrente(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    destino_key = call.data.split("|", 1)[1]
    if destino_key not in CANALES:
        bot.send_message(call.message.chat.id, "No encontré ese destino.")
        return
    recurrente = cargar_config().get("recurrentes", {}).get(destino_key)
    if not recurrente:
        bot.send_message(call.message.chat.id, "No hay una programación para este destino.")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(
            "⏸️ Pausar y conservar el mensaje",
            callback_data=f"rec_pausar|{destino_key}",
        ),
        types.InlineKeyboardButton(
            "🗑️ Eliminar la programación y el mensaje",
            callback_data=f"rec_eliminar|{destino_key}",
        ),
        types.InlineKeyboardButton(
            "↩️ Cancelar",
            callback_data=f"rec_cancelar_pausa|{destino_key}",
        ),
    )
    editar_o_enviar_panel(
        call.message.chat.id,
        f"¿Qué quieres hacer con la publicación recurrente de "
        f"<b>{html.escape(CANALES[destino_key]['nombre'])}</b>?\n\n"
        "Pausar conserva la programación y el mensaje actual. Eliminar quita la "
        "programación e intenta borrar del grupo o canal todos los mensajes que publicó.",
        markup,
        message=call.message,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("rec_cancelar_pausa|"))
def admin_cancelar_pausa_recurrente(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    destino_key = call.data.split("|", 1)[1]
    if destino_key not in CANALES:
        bot.send_message(call.message.chat.id, "No encontré ese destino.")
        return
    recurrente = cargar_config().get("recurrentes", {}).get(destino_key, {})
    mostrar_menu_recurrente(
        call.message.chat.id,
        recurrente.get("botones_key", destino_key),
        destino_key,
        message=call.message,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("rec_eliminar|"))
def admin_eliminar_recurrente(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    destino_key = call.data.split("|", 1)[1]
    if destino_key not in CANALES:
        bot.send_message(call.message.chat.id, "No encontré ese destino.")
        return

    with RECURRING_LOCK:
        recurrente = cargar_config().get("recurrentes", {}).get(destino_key, {})
        ids_mensajes = recurrente.get("ultimo_message_ids") or [
            recurrente.get("ultimo_message_id")
        ]
        ids_mensajes = list(dict.fromkeys(filter(None, ids_mensajes)))
        chat_destino = recurrente.get("ultimo_chat_id") or obtener_canal_id(destino_key)

        def eliminar_programacion(cfg):
            cfg.get("recurrentes", {}).pop(destino_key, None)
            publicaciones = cfg.get("ultima_publicacion", {})
            for botones_key, publicacion in list(publicaciones.items()):
                if (
                    isinstance(publicacion, dict)
                    and str(publicacion.get("chat_id")) == str(chat_destino)
                    and publicacion.get("message_id") in ids_mensajes
                ):
                    publicaciones.pop(botones_key, None)

        actualizar_config(eliminar_programacion)

    errores = 0
    if chat_destino:
        for message_id in ids_mensajes:
            try:
                bot.delete_message(int(chat_destino), int(message_id))
            except Exception:
                errores += 1
                app.logger.exception("No se pudo borrar el mensaje recurrente eliminado.")
    elif ids_mensajes:
        errores = len(ids_mensajes)

    resultado = "🗑️ Programación eliminada."
    if errores:
        resultado += (
            f" No pude borrar {errores} mensaje(s) del grupo o canal; "
            "revisa los permisos del bot."
        )
    elif ids_mensajes:
        resultado += " El mensaje publicado también fue borrado."
    else:
        resultado += " No había un mensaje publicado actual registrado."
    mostrar_menu_recurrente(
        call.message.chat.id,
        recurrente.get("botones_key", destino_key),
        destino_key,
        message=call.message,
        aviso=resultado,
    )


def mostrar_confirmacion_recurrente(chat_id, uid):
    estado = admin_estado.get(uid, {})
    botones_key = estado.get("botones_key")
    destino_key = estado.get("canal")
    if botones_key not in CANALES or destino_key not in CANALES:
        bot.send_message(chat_id, "No encontré el destino. Vuelve a abrir el panel.")
        admin_estado.pop(uid, None)
        return
    botones = cargar_botones_custom(botones_key)
    media_items = normalizar_media_items(
        estado.get("media_id"),
        estado.get("media_type"),
        estado.get("media_items"),
    )
    texto = estado.get("texto_recurrente", "")
    if not texto.strip() and not media_items:
        bot.send_message(chat_id, "La publicación necesita texto o al menos un archivo.")
        admin_estado.pop(uid, None)
        return
    try:
        enviar_publicacion_con_botones(
            chat_id,
            texto,
            construir_markup_botones(botones) if botones else None,
            estado.get("media_id"),
            estado.get("media_type"),
            media_items=estado.get("media_items"),
        )
    except Exception:
        app.logger.exception("No se pudo previsualizar el mensaje recurrente.")
        bot.send_message(
            chat_id,
            "No pude enviar la vista previa. Revisa el texto o los archivos y vuelve a configurarlo.",
        )
        return

    intervalo = formato_intervalo(estado["intervalo_segundos"])
    programa_actual = cargar_config().get("recurrentes", {}).get(destino_key, {})
    aviso_reemplazo = (
        " Esta acción reemplazará la programación recurrente actual de este destino."
        if programa_actual.get("activo")
        else ""
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(
            "✅ Activar y publicar cada intervalo",
            callback_data=f"rec_confirmar|{botones_key}|{destino_key}",
        ),
        types.InlineKeyboardButton(
            "❌ Cancelar",
            callback_data=f"rec_cancelar|{botones_key}|{destino_key}",
        ),
    )
    estado["paso"] = "confirmar_recurrente"
    bot.send_message(
        chat_id,
        f"Esta es la vista previa. Al confirmar, el primer envío será dentro de "
        f"<b>{html.escape(intervalo)}</b> y luego se repetirá con ese intervalo. "
        "Al enviarse, sustituirá al mensaje recurrente anterior de este destino."
        f"{aviso_reemplazo}",
        parse_mode="HTML",
        reply_markup=markup,
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("rec_confirmar|"))
def admin_confirmar_recurrente(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    partes = call.data.split("|", 2)
    estado = admin_estado.get(uid, {})
    if len(partes) != 3:
        bot.send_message(call.message.chat.id, "No entendí la selección.")
        return
    botones_key, destino_key = partes[1], partes[2]
    if (
        estado.get("paso") != "confirmar_recurrente"
        or estado.get("botones_key") != botones_key
        or estado.get("canal") != destino_key
    ):
        bot.send_message(call.message.chat.id, "La configuración venció; abre de nuevo el menú recurrente.")
        return
    with RECURRING_LOCK:
        anterior = cargar_config().get("recurrentes", {}).get(destino_key, {})
        media_items = normalizar_media_items(
            estado.get("media_id"),
            estado.get("media_type"),
            estado.get("media_items"),
        )
        nuevo = {
            "activo": True,
            "botones_key": botones_key,
            "destino_key": destino_key,
            "intervalo_segundos": int(estado["intervalo_segundos"]),
            "texto": estado["texto_recurrente"],
            "media_id": media_items[0]["media_id"] if len(media_items) == 1 else None,
            "media_type": media_items[0]["media_type"] if len(media_items) == 1 else None,
            "media_items": media_items,
            "proximo_envio": time.time() + int(estado["intervalo_segundos"]),
            "ultimo_message_id": anterior.get("ultimo_message_id"),
            "ultimo_message_ids": anterior.get("ultimo_message_ids"),
            "ultimo_chat_id": anterior.get("ultimo_chat_id"),
            "ultimo_envio": anterior.get("ultimo_envio"),
        }
        def guardar_recurrente(cfg):
            cfg.setdefault("recurrentes", {})[destino_key] = nuevo
        actualizar_config(guardar_recurrente)
    admin_estado.pop(uid, None)
    mostrar_menu_recurrente(
        call.message.chat.id,
        botones_key,
        destino_key,
        message=call.message,
        aviso="Publicación recurrente activada. El primer envío se hará después del intervalo elegido.",
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("rec_cancelar|"))
def admin_cancelar_recurrente(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    partes = call.data.split("|", 2)
    admin_estado.pop(call.from_user.id, None)
    if len(partes) == 3 and partes[1] in CANALES and partes[2] in CANALES:
        mostrar_menu_recurrente(
            call.message.chat.id,
            partes[1],
            partes[2],
            message=call.message,
        )

@bot.callback_query_handler(func=lambda call: call.data == "rec_sin_media")
def admin_recurrente_sin_media(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    estado = admin_estado.get(call.from_user.id, {})
    if estado.get("paso") != "esperando_media_recurrente":
        return
    estado["media_id"] = None
    estado["media_type"] = None
    estado["media_items"] = []
    mostrar_confirmacion_recurrente(call.message.chat.id, call.from_user.id)

@bot.callback_query_handler(func=lambda call: call.data == "rec_media_agregar")
def admin_recurrente_agregar_otro_media(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    estado = admin_estado.get(call.from_user.id, {})
    if estado.get("paso") != "esperando_media_recurrente":
        bot.answer_callback_query(call.id, "La configuración ya no está activa.")
        return
    bot.answer_callback_query(call.id, "Envía el siguiente archivo.")
    bot.send_message(
        call.message.chat.id,
        "Envía otra foto, video, documento o audio. Puedes añadir hasta 10 archivos.",
    )

@bot.callback_query_handler(func=lambda call: call.data == "rec_media_listo")
def admin_recurrente_media_listo(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    estado = admin_estado.get(call.from_user.id, {})
    if estado.get("paso") != "esperando_media_recurrente":
        bot.send_message(call.message.chat.id, "La configuración ya no está activa.")
        return
    mostrar_confirmacion_recurrente(call.message.chat.id, call.from_user.id)

@bot.callback_query_handler(func=lambda call: call.data == "rec_abortar")
def admin_abortar_configuracion_recurrente(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    estado = admin_estado.pop(call.from_user.id, {})
    botones_key = estado.get("botones_key")
    destino_key = estado.get("canal")
    if botones_key in CANALES and destino_key in CANALES:
        mostrar_menu_recurrente(
            call.message.chat.id,
            botones_key,
            destino_key,
            message=call.message,
            aviso="Configuración recurrente cancelada.",
        )

# ─── Eliminar botón ───────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data == "admin_eliminar_boton")
def admin_eliminar_boton_menu(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "🗑️ <b>¿De cuál canal quieres eliminar un botón?</b>",
        parse_mode="HTML",
        reply_markup=markup_seleccionar_canal("ebotones")
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("ebotones_"))
def admin_eliminar_boton_canal_elegido(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    canal_key = call.data.split("_", 1)[1]
    if canal_key not in CANALES:
        bot.send_message(call.message.chat.id, "No encontré ese destino.")
        return
    botones = cargar_botones_custom(canal_key)
    if not botones:
        bot.send_message(
            call.message.chat.id,
            f"📋 No hay botones para eliminar en {html.escape(CANALES[canal_key]['nombre'])}.",
            parse_mode="HTML",
            reply_markup=markup_menu_botones(canal_key),
        )
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for i, b in enumerate(botones):
        markup.add(types.InlineKeyboardButton(
            f"🗑️ {b['texto']}", callback_data=f"admin_del_confirm_{canal_key}_{i}"
        ))
    markup.add(types.InlineKeyboardButton(
        "❌ Cancelar", callback_data=f"admin_cancelar_{canal_key}"
    ))
    bot.send_message(
        call.message.chat.id,
        f"¿Cuál botón de {html.escape(CANALES[canal_key]['nombre'])} deseas eliminar?",
        parse_mode="HTML",
        reply_markup=markup,
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_del_confirm_"))
def admin_pedir_confirmacion_eliminar(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    resto = call.data[len("admin_del_confirm_"):]
    try:
        canal_key, idx_str = resto.rsplit("_", 1)
        idx = int(idx_str)
    except (ValueError, TypeError):
        bot.send_message(call.message.chat.id, "No entendí qué botón seleccionaste.")
        return
    botones = cargar_botones_custom(canal_key) if canal_key in CANALES else []
    if idx < 0 or idx >= len(botones):
        bot.send_message(call.message.chat.id, "Ese botón ya no existe.")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(
            "Sí, eliminar",
            callback_data=f"admin_del_{canal_key}_{idx}",
        ),
        types.InlineKeyboardButton(
            "No, volver",
            callback_data=f"admin_cancelar_{canal_key}",
        ),
    )
    bot.send_message(
        call.message.chat.id,
        f"¿Eliminar el botón <b>{html.escape(botones[idx]['texto'])}</b> "
        f"de {html.escape(CANALES[canal_key]['nombre'])}?",
        parse_mode="HTML",
        reply_markup=markup,
    )

@bot.callback_query_handler(
    func=lambda call: call.data.startswith("admin_del_")
    and not call.data.startswith("admin_del_confirm_")
)
def admin_confirmar_eliminar(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    resto = call.data[len("admin_del_"):]
    canal_key, idx_str = resto.rsplit("_", 1)
    if canal_key not in CANALES:
        bot.send_message(call.message.chat.id, "No encontré ese destino.")
        return
    idx     = int(idx_str)
    botones = cargar_botones_custom(canal_key)
    if 0 <= idx < len(botones):
        eliminado = botones.pop(idx)
        guardar_botones_custom(canal_key, botones)
        bot.edit_message_text(
            f"✅ Botón <b>{html.escape(eliminado['texto'])}</b> eliminado de "
            f"{html.escape(CANALES[canal_key]['nombre'])}.",
            call.message.chat.id, call.message.message_id, parse_mode="HTML"
        )
        mostrar_gestion_botones(call.message.chat.id, canal_key)
    else:
        bot.send_message(call.message.chat.id, "❌ Botón no encontrado.")

# ─── Publicar en canal ────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data == "admin_publicar")
def admin_publicar(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "📤 <b>¿En cuál canal deseas publicar?</b>\n"
        "La publicación se enviará <b>únicamente</b> a ese canal, con sus propios botones.",
        parse_mode="HTML",
        reply_markup=markup_seleccionar_canal("pubcanal")
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("pubcanal_"))
def admin_publicar_canal_elegido(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    botones_key = call.data[len("pubcanal_"):]
    if botones_key not in CANALES:
        bot.send_message(call.message.chat.id, "No encontré ese conjunto de botones.")
        return
    botones = cargar_botones_custom(botones_key)
    if not botones:
        bot.send_message(call.message.chat.id,
            f"📋 No hay botones en {html.escape(CANALES[botones_key]['nombre'])}. "
            "Crea uno desde Ver y administrar botones.",
            parse_mode="HTML",
        )
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for destino_key, info in CANALES.items():
        estado = "✅" if obtener_canal_id(destino_key) else "⚠️"
        markup.add(types.InlineKeyboardButton(
            f"{estado} {info['nombre']}",
            callback_data=f"sendto|{botones_key}|{destino_key}",
        ))
    markup.add(types.InlineKeyboardButton(
        "🔙 Volver a los botones", callback_data=f"botones_menu|{botones_key}"
    ))
    bot.send_message(
        call.message.chat.id,
        f"📤 <b>¿A qué grupo o canal envío los botones de "
        f"{html.escape(CANALES[botones_key]['nombre'])}?</b>",
        parse_mode="HTML",
        reply_markup=markup,
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("sendto|"))
def admin_enviar_botones_a_destino(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    partes = call.data.split("|", 2)
    if len(partes) != 3:
        bot.send_message(call.message.chat.id, "No entendí el destino seleccionado.")
        return
    botones_key, destino_key = partes[1], partes[2]
    if botones_key not in CANALES or destino_key not in CANALES:
        bot.send_message(call.message.chat.id, "No encontré el conjunto de botones o el destino.")
        return
    if not cargar_botones_custom(botones_key):
        bot.send_message(call.message.chat.id, "Ese conjunto de botones está vacío.")
        return
    if not obtener_canal_id(destino_key):
        bot.send_message(
            call.message.chat.id,
            f"Primero configura el grupo o canal {html.escape(CANALES[destino_key]['nombre'])}.",
            parse_mode="HTML",
            reply_markup=markup_menu_botones(botones_key),
        )
        return
    admin_estado[call.from_user.id] = {
        "paso": "esperando_texto_publicar",
        "canal": destino_key,
        "botones_key": botones_key,
    }
    bot.send_message(
        call.message.chat.id,
        f"📝 <b>Escribe el texto</b> que acompañará los botones en "
        f"{html.escape(CANALES[destino_key]['nombre'])}:",
        parse_mode="HTML"
    )

# ─── Cancelar / Volver ────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_cancelar_"))
def admin_cancelar_gestion_botones(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    canal_key = call.data[len("admin_cancelar_"):]
    if canal_key not in CANALES:
        bot.send_message(call.message.chat.id, "No encontré ese destino.")
        return
    bot.edit_message_text(
        "❌ Eliminación cancelada.",
        call.message.chat.id,
        call.message.message_id,
    )
    mostrar_gestion_botones(call.message.chat.id, canal_key)

@bot.callback_query_handler(func=lambda call: call.data == "admin_cancelar")
def admin_cancelar(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    estado = admin_estado.pop(call.from_user.id, {})
    bot.edit_message_text("❌ Operación cancelada.", call.message.chat.id, call.message.message_id)
    botones_key = estado.get("botones_key") or estado.get("canal")
    if botones_key in CANALES:
        mostrar_gestion_botones(call.message.chat.id, botones_key)

@bot.callback_query_handler(func=lambda call: call.data == "admin_volver")
def admin_volver(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        return
    bot.answer_callback_query(call.id)
    mostrar_panel_admin(call.message.chat.id, message=call.message)

# ─── Skip multimedia ──────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data == "admin_skip_media")
def admin_skip_media(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    uid    = call.from_user.id
    estado = admin_estado.get(uid, {})
    paso   = estado.get("paso")

    if paso == "esperando_media_grupo":
        # Sin media → pasar directo a pedir nombre del primer botón
        admin_estado[uid]["paso"] = "esperando_nombre_en_grupo"
        bot.send_message(
            call.message.chat.id,
            "✏️ <b>Nombre del botón</b>\n\nEscribe el texto que aparecerá en el botón:",
            parse_mode="HTML"
        )

    elif paso == "esperando_media_publicar":
        # Publicar sin media
        _publicar_en_canal(
            call.message.chat.id,
            estado.get("canal"),
            estado.get("texto_publicar", ""),
            None,
            None,
            estado.get("botones_key"),
        )
        admin_estado.pop(uid, None)

    elif paso == "esperando_media_recurrente":
        estado["media_id"] = None
        estado["media_type"] = None
        estado["media_items"] = []
        mostrar_confirmacion_recurrente(call.message.chat.id, uid)

# ── Agregar otro botón en la misma sesión ─────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data == "admin_otro_boton")
def admin_otro_boton(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    admin_estado[uid]["paso"] = "esperando_nombre_en_grupo"
    bot.send_message(
        call.message.chat.id,
        "✏️ <b>Nombre del siguiente botón:</b>\n\nEscribe el texto que aparecerá en el botón:",
        parse_mode="HTML"
    )

# ── Terminar sesión de botones ────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data == "admin_listo_grupo")
def admin_listo_grupo(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    uid    = call.from_user.id
    estado = admin_estado.pop(uid, {})
    sesion = estado.get("botones_sesion", [])
    canal_key = estado.get("canal")
    resumen = "\n".join(f"  • {b['texto']}" for b in sesion)
    bot.send_message(
        call.message.chat.id,
        f"🎉 <b>¡Publicación lista!</b>\n\n"
        f"<b>{len(sesion)} botón(es) creados:</b>\n{html.escape(resumen)}",
        parse_mode="HTML",
    )
    if canal_key in CANALES:
        mostrar_gestion_botones(call.message.chat.id, canal_key)

# ── FLUJO DE TEXTO DEL ADMIN ──────────────────────────────────────────────────
@bot.message_handler(
    func=lambda m: (
        str(m.from_user.id) == str(ADMIN_ID)
        and m.chat.type == "private"
        and m.from_user.id in admin_estado
    ),
    content_types=['text']
)
def admin_flujo_texto(message):
    uid    = message.from_user.id
    estado = admin_estado.get(uid, {})
    paso   = estado.get("paso")
    texto_recibido = (message.text or "").strip()
    eliminar_mensaje_disparador(message)

    if texto_recibido.lower() == "/cancelar":
        if paso in (
            "esperando_nombre_boton_lote",
            "esperando_url_boton_lote",
            "esperando_nombre_nuevo_boton_lote",
            "esperando_url_nuevo_boton_lote",
            "esperando_media_botones_lote",
        ):
            estado["paso"] = "editar_botones_lote"
            mostrar_lista_media_botones(
                message.chat.id,
                estado.get("canal_key"),
                message_id=estado.get("panel_message_id"),
                aviso="Edición cancelada; el borrador sigue sin guardar.",
            )
            return
        if paso in (
            "esperando_datos_metodo_pago",
            "esperando_foto_metodos_pago",
        ):
            panel_message_id = estado.get("panel_message_id")
            admin_estado.pop(uid, None)
            mostrar_admin_config_pagos(
                message.chat.id,
                message_id=panel_message_id,
                aviso="Edición cancelada; no se guardaron cambios.",
            )
            return
        if paso == "esperando_media_boton_update":
            canal_key = estado.get("canal_key")
            panel_message_id = estado.get("panel_message_id")
            admin_estado.pop(uid, None)
            if canal_key in CANALES:
                mostrar_gestion_botones(
                    message.chat.id,
                    canal_key,
                    message_id=panel_message_id,
                    aviso="Actualización cancelada.",
                )
            return
        if paso == "esperando_media_reglas":
            canal_key = estado.get("canal_key")
            pagina = estado.get("pagina", 0)
            panel_message_id = estado.get("panel_message_id")
            admin_estado.pop(uid, None)
            if canal_key in CANALES:
                mostrar_editor_reglamento(
                    message.chat.id,
                    canal_key,
                    pagina,
                    message_id=panel_message_id,
                    aviso="Carga de multimedia cancelada.",
                )
            return
        if paso == "esperando_teclado_reglas":
            canal_key = estado.get("canal_key")
            pagina = estado.get("pagina", 0)
            panel_message_id = estado.get("panel_message_id")
            admin_estado.pop(uid, None)
            if canal_key in CANALES:
                mostrar_teclado_reglamento(
                    message.chat.id,
                    canal_key,
                    pagina,
                    message_id=panel_message_id,
                    aviso="Edición cancelada.",
                )
            return
        if paso == "esperando_texto_captcha":
            canal_key = estado.get("canal_key")
            pagina = estado.get("pagina", 0)
            panel_message_id = estado.get("panel_message_id")
            admin_estado.pop(uid, None)
            if canal_key in CANALES:
                mostrar_menu_funcion_grupo(
                    message.chat.id,
                    canal_key,
                    "captcha",
                    pagina,
                    message_id=panel_message_id,
                    aviso="Edición cancelada.",
                )
            return
        if paso == "esperando_excepcion_moderacion":
            canal_key = estado.get("canal_key")
            pagina = estado.get("pagina", 0)
            policy_id = estado.get("policy_id")
            panel_message_id = estado.get("panel_message_id")
            admin_estado.pop(uid, None)
            if canal_key in CANALES and policy_id in GROUP_MODERATION_POLICY_LABELS:
                policy = _politica_ajuste(
                    obtener_ajustes_grupo(canal_key) or {}, policy_id
                )
                seccion = (
                    "forward" if policy_id.startswith("forward_") else
                    "quotes" if policy_id.startswith("quote_") else
                    "internet" if policy_id == "internet_links" else "telegram"
                )
                mostrar_menu_antispam(
                    message.chat.id,
                    canal_key,
                    pagina,
                    message_id=panel_message_id,
                    seccion=seccion,
                    policy_id=policy_id,
                    aviso="Edición cancelada.",
                )
            return
        if paso == "esperando_valor_antiflood":
            canal_key = estado.get("canal_key")
            pagina = estado.get("pagina", 0)
            panel_message_id = estado.get("panel_message_id")
            admin_estado.pop(uid, None)
            if canal_key in CANALES:
                mostrar_menu_antiflood(
                    message.chat.id,
                    canal_key,
                    pagina,
                    message_id=panel_message_id,
                )
            return
        if paso in (
            "esperando_ajuste_grupo",
            "esperando_atajo_grupo",
            "esperando_videochat_button_label",
        ):
            canal_key = estado.get("canal_key")
            pagina = estado.get("pagina", 0)
            panel_message_id = estado.get("panel_message_id")
            feature = estado.get("feature", "atajos")
            admin_estado.pop(uid, None)
            if estado.get("volver_a_editor_reglas") and canal_key in CANALES:
                mostrar_editor_reglamento(
                    message.chat.id,
                    canal_key,
                    pagina,
                    message_id=panel_message_id,
                    aviso="Edición cancelada.",
                )
            else:
                mostrar_menu_funcion_grupo(
                    message.chat.id,
                    canal_key,
                    feature,
                    pagina,
                    message_id=panel_message_id,
                    aviso="Edición cancelada.",
                )
            return
        if paso in ("esperando_chat_compartido", "esperando_lookup_publico", "lookup_result"):
            selector_message_id = estado.get("selector_message_id")
            admin_estado[uid] = {
                "paso": "esperando_chat_compartido",
                "selector_message_id": selector_message_id,
                "toolbar_message_id": estado.get("toolbar_message_id"),
            }
            if selector_message_id:
                mostrar_selector_destinos(
                    message.chat.id,
                    message_id=selector_message_id,
                )
            reemplazar_teclado_selector(
                message.chat.id,
                uid,
                teclado_selector_grupos(),
                "Búsqueda cancelada. Usa «Buscar grupo» o «Buscar canal» para continuar.",
            )
            return
        admin_estado.pop(uid, None)
        instalar_teclado_persistente(
            message.chat.id,
            "⌨️ Atajos de administración disponibles en la barra inferior.",
            teclado_atajos_admin(),
        )
        editar_o_enviar_panel(
            message.chat.id,
            "Acción cancelada.",
            types.InlineKeyboardMarkup(),
        )
        return

    if paso == "esperando_datos_metodo_pago":
        metodo = estado.get("metodo_pago")
        panel_message_id = estado.get("panel_message_id")
        if metodo not in NOMBRE_METODO:
            admin_estado.pop(uid, None)
            mostrar_admin_config_pagos(
                message.chat.id,
                message_id=panel_message_id,
                aviso="No reconocí el método; no se guardó el mensaje.",
            )
            return
        if not texto_recibido:
            aviso_error = "El mensaje no puede estar vacío."
        elif len(texto_recibido) > 3000:
            aviso_error = "El texto supera el límite de 3000 caracteres."
        else:
            aviso_error = None
        if aviso_error:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "❌ Cancelar",
                callback_data="admin_pagos_cancelar",
            ))
            editar_o_enviar_panel(
                message.chat.id,
                f"⚠️ {aviso_error}\n\nVuelve a enviar el texto completo. "
                "El mensaje enviado se borrará automáticamente.",
                markup,
                message_id=panel_message_id,
                protect_content=True,
            )
            return
        try:
            guardar_metodo_pago(metodo, texto_recibido)
        except Exception:
            app.logger.exception("No se pudo guardar un método de pago.")
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "❌ Cancelar",
                callback_data="admin_pagos_cancelar",
            ))
            editar_o_enviar_panel(
                message.chat.id,
                "No pude guardar el cambio. No se mostró el texto enviado. "
                "Intenta enviarlo de nuevo o pulsa cancelar.",
                markup,
                message_id=panel_message_id,
                protect_content=True,
            )
            return
        admin_estado.pop(uid, None)
        mostrar_admin_config_pagos(
            message.chat.id,
            message_id=panel_message_id,
            aviso=f"Se actualizó {NOMBRE_METODO[metodo]}.",
        )
        return

    if paso == "esperando_foto_metodos_pago":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "❌ Cancelar",
            callback_data="admin_pagos_cancelar",
        ))
        editar_o_enviar_panel(
            message.chat.id,
            "Envía la imagen del menú como una foto de Telegram, "
            "o pulsa cancelar. El texto recibido se borró y no se guardó.",
            markup,
            message_id=estado.get("panel_message_id"),
            protect_content=True,
        )
        return

    if paso == "esperando_media_boton_update":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "↩️ Cancelar",
            callback_data=(
                f"botones_media_cancelar|{estado.get('canal_key')}|"
                f"{estado.get('boton_idx')}"
            ),
        ))
        editar_o_enviar_panel(
            message.chat.id,
            "Envíame una foto, vídeo, documento, audio o animación para "
            "reemplazar el archivo de este botón. El texto se borró y no se guardó.",
            markup,
            message_id=estado.get("panel_message_id"),
            forzar_texto=True,
        )
        return
    if paso == "esperando_media_botones_lote":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "↩️ Cancelar",
            callback_data=f"botones_lote_cancelar_input|{estado.get('canal_key')}",
        ))
        editar_o_enviar_panel(
            message.chat.id,
            "En este paso necesito una foto, video, documento, audio o animación. "
            "El texto enviado se eliminó y no se guardó.",
            markup,
            message_id=estado.get("panel_message_id"),
            forzar_texto=True,
        )
        return

    if paso in (
        "esperando_nombre_boton_lote",
        "esperando_url_boton_lote",
        "esperando_nombre_nuevo_boton_lote",
        "esperando_url_nuevo_boton_lote",
    ):
        canal_key = estado.get("canal_key")
        panel_message_id = estado.get("panel_message_id")
        botones = estado.get("botones_borrador", [])
        if canal_key not in CANALES:
            admin_estado.pop(uid, None)
            return
        if paso == "esperando_nombre_boton_lote":
            indice = estado.get("indice_boton_borrador", -1)
            if not 0 <= indice < len(botones):
                mostrar_lista_media_botones(
                    message.chat.id, canal_key, message_id=panel_message_id,
                    aviso="Ese botón ya no está en el borrador.",
                )
                return
            if not texto_recibido:
                mostrar_editor_boton_lote(
                    message.chat.id, canal_key, indice,
                    message_id=panel_message_id,
                    aviso="El nombre no puede quedar vacío.",
                )
                return
            botones[indice]["texto"] = texto_recibido[:64]
            estado["paso"] = "editar_botones_lote"
            mostrar_editor_boton_lote(
                message.chat.id, canal_key, indice, message_id=panel_message_id
            )
            return
        if paso == "esperando_url_boton_lote":
            indice = estado.get("indice_boton_borrador", -1)
            if not 0 <= indice < len(botones):
                mostrar_lista_media_botones(
                    message.chat.id, canal_key, message_id=panel_message_id,
                    aviso="Ese botón ya no está en el borrador.",
                )
                return
            if not texto_recibido.startswith(("https://", "http://")):
                estado["paso"] = "esperando_url_boton_lote"
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(
                    "↩️ Cancelar edición",
                    callback_data=f"botones_lote_cancelar_input|{canal_key}",
                ))
                editar_o_enviar_panel(
                    message.chat.id,
                    "❌ El enlace debe comenzar por https:// o http://. Inténtalo otra vez.",
                    markup,
                    message_id=panel_message_id,
                    forzar_texto=True,
                )
                return
            botones[indice]["url"] = texto_recibido
            estado["paso"] = "editar_botones_lote"
            mostrar_editor_boton_lote(
                message.chat.id, canal_key, indice, message_id=panel_message_id
            )
            return
        if paso == "esperando_nombre_nuevo_boton_lote":
            if not texto_recibido:
                editar_o_enviar_panel(
                    message.chat.id,
                    "El nombre no puede quedar vacío. Escribe el nombre del nuevo botón.",
                    types.InlineKeyboardMarkup(),
                    message_id=panel_message_id,
                    forzar_texto=True,
                )
                return
            estado["nombre_nuevo_boton_borrador"] = texto_recibido[:64]
            estado["paso"] = "esperando_url_nuevo_boton_lote"
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "↩️ Cancelar",
                callback_data=f"botones_lote_cancelar_input|{canal_key}",
            ))
            editar_o_enviar_panel(
                message.chat.id,
                "Ahora envía el enlace completo, empezando por https://",
                markup,
                message_id=panel_message_id,
                forzar_texto=True,
            )
            return
        if paso == "esperando_url_nuevo_boton_lote":
            if not texto_recibido.startswith(("https://", "http://")):
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(
                    "↩️ Cancelar",
                    callback_data=f"botones_lote_cancelar_input|{canal_key}",
                ))
                editar_o_enviar_panel(
                    message.chat.id,
                    "❌ El enlace debe comenzar por https:// o http://. Inténtalo otra vez.",
                    markup,
                    message_id=panel_message_id,
                    forzar_texto=True,
                )
                return
            botones.append({
                "texto": estado.pop("nombre_nuevo_boton_borrador", "Nuevo enlace"),
                "url": texto_recibido,
                "media_id": None,
                "media_type": None,
            })
            estado["paso"] = "editar_botones_lote"
            mostrar_lista_media_botones(
                message.chat.id, canal_key, message_id=panel_message_id,
                aviso="Nuevo enlace añadido al borrador.",
            )
            return

    if texto_recibido.split("@", 1)[0] == "/start":
        admin_estado.pop(uid, None)
        instalar_teclado_persistente(
            message.chat.id,
            "⌨️ Atajos de administración disponibles en la barra inferior.",
            teclado_atajos_admin(),
        )
        mostrar_metodos_pago(message.chat.id)
        return

    if paso in ("esperando_chat_compartido", "esperando_lookup_publico") and texto_recibido.startswith("@"):
        if not re.fullmatch(r"@[A-Za-z0-9_]{5,32}", texto_recibido):
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "↩️ Volver a destinos guardados",
                callback_data="grupo_selector",
            ))
            editar_o_enviar_panel(
                message.chat.id,
                "Ese @usuario no tiene un formato válido. Escribe uno público o usa el selector de Telegram.",
                markup,
                message_id=estado.get("selector_message_id"),
            )
            return
        estado["paso"] = "esperando_lookup_publico"
        mostrar_resultado_busqueda_publica(
            message.chat.id,
            uid,
            texto_recibido,
            estado.get("selector_message_id"),
        )
        return

    if paso == "lookup_result":
        return

    if paso == "esperando_lookup_publico":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "↩️ Volver a destinos guardados",
            callback_data="grupo_selector",
        ))
        editar_o_enviar_panel(
            message.chat.id,
            "Escribe un @usuario público de grupo o canal, o vuelve a la lista.",
            markup,
            message_id=estado.get("selector_message_id"),
        )
        return

    if paso == "esperando_chat_compartido":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "↩️ Volver a destinos guardados",
            callback_data="grupo_selector",
        ))
        editar_o_enviar_panel(
            message.chat.id,
            "Usa los botones «Buscar grupo» o «Buscar canal» en la barra inferior, "
            "o escribe "
            "un @usuario público de grupo/canal.",
            markup,
            message_id=estado.get("selector_message_id"),
        )
        return

    if paso == "esperando_media_reglas":
        canal_key = estado.get("canal_key")
        posicion = "encima" if estado.get("posicion") == "before" else "debajo"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "↩️ Cancelar",
            callback_data=(
                f"grp_rules|editor|{canal_key}|{estado.get('pagina', 0)}"
            ),
        ))
        editar_o_enviar_panel(
            message.chat.id,
            f"Envía una foto, video, GIF o archivo multimedia para colocarlo {posicion} "
            "del Reglamento, o pulsa /cancelar.",
            markup,
            message_id=estado.get("panel_message_id"),
        )
        return

    if paso == "esperando_teclado_reglas":
        canal_key = estado.get("canal_key")
        pagina = estado.get("pagina", 0)
        panel_message_id = estado.get("panel_message_id")
        error = None
        try:
            etiqueta, accion = separar_sintaxis_boton(texto_recibido)
            if not etiqueta or len(etiqueta) > 32:
                raise ValueError("La etiqueta debe tener entre 1 y 32 caracteres.")
            if len(accion) > 256:
                raise ValueError("La acción no puede superar 256 caracteres.")
            es_url = bool(re.fullmatch(
                r"https?://[^\s<>\"']{1,400}", accion, re.IGNORECASE
            ))
            if not es_url:
                coincidencia = re.fullmatch(
                    r"/([A-Za-z0-9_]{1,32})(?:@[A-Za-z0-9_]{5,32})?(?:\s+.{1,150})?",
                    accion,
                )
                if not coincidencia:
                    raise ValueError(
                        "La acción debe ser un enlace, /rules argumento o un comando personalizado."
                    )
                comando = coincidencia.group(1).casefold()
                ajustes = obtener_ajustes_grupo(canal_key) or {}
                if comando != "rules" and comando not in ajustes.get("custom_commands", {}):
                    raise ValueError(
                        "Solo se admiten /rules o comandos personalizados ya configurados."
                    )
            ajustes = obtener_ajustes_grupo(canal_key) or {}
            existentes = ajustes.get("rules_keyboard", [])
            if len(existentes) >= 20:
                raise ValueError("El teclado ya tiene 20 botones, el máximo permitido.")
            if any(
                str(item.get("label", "")).casefold() == etiqueta.casefold()
                for item in existentes
            ):
                raise ValueError("Ya existe un botón con esa etiqueta.")
        except (ValueError, AttributeError) as exc:
            error = str(exc) or "Usa el formato etiqueta=acción."
        if error:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "↩️ Volver al teclado",
                callback_data=f"grp_rules|keyboard|{canal_key}|{pagina}",
            ))
            editar_o_enviar_panel(
                message.chat.id,
                f"⚠️ {html.escape(error)}\n\n"
                "Ejemplos: <code>Ver spam=/rules spam</code> · "
                "<code>Sitio=https://ejemplo.com</code>.",
                markup,
                message_id=panel_message_id,
            )
            return
        actualizar_ajustes_grupo(
            canal_key,
            lambda ajustes: ajustes.setdefault("rules_keyboard", []).append({
                "label": etiqueta,
                "action": accion,
            }),
        )
        admin_estado.pop(uid, None)
        mostrar_teclado_reglamento(
            message.chat.id,
            canal_key,
            pagina,
            message_id=panel_message_id,
            aviso="Botón agregado.",
        )
        return

    if paso == "esperando_texto_captcha":
        canal_key = estado.get("canal_key")
        pagina = estado.get("pagina", 0)
        panel_message_id = estado.get("panel_message_id")
        captcha_text = "" if texto_recibido.lower() == "/vaciar" else texto_recibido
        if len(captcha_text) > 4000:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "↩️ Volver a CAPTCHA",
                callback_data=f"grupo_feature|{canal_key}|captcha|{pagina}",
            ))
            editar_o_enviar_panel(
                message.chat.id,
                "El mensaje CAPTCHA no puede superar 4000 caracteres. "
                "Envía uno más corto o escribe /cancelar.",
                markup,
                message_id=panel_message_id,
            )
            return
        actualizar_ajustes_grupo(
            canal_key, lambda ajustes: ajustes.update({"captcha_text": captcha_text})
        )
        admin_estado.pop(uid, None)
        mostrar_menu_funcion_grupo(
            message.chat.id,
            canal_key,
            "captcha",
            pagina,
            message_id=panel_message_id,
            aviso="Mensaje CAPTCHA guardado." if captcha_text else "Se restauró el mensaje predeterminado.",
        )
        return

    if paso == "esperando_excepcion_moderacion":
        canal_key = estado.get("canal_key")
        pagina = estado.get("pagina", 0)
        policy_id = estado.get("policy_id")
        panel_message_id = estado.get("panel_message_id")
        if canal_key not in CANALES or policy_id not in GROUP_MODERATION_POLICY_LABELS:
            admin_estado.pop(uid, None)
            instalar_teclado_persistente(
                message.chat.id,
                "La sesión de excepciones expiró.",
                teclado_atajos_admin(),
            )
            return
        quitar = texto_recibido.startswith("-")
        value = texto_recibido[1:].strip() if quitar else texto_recibido
        value = value.casefold()
        if not (re.fullmatch(r"\d{1,20}", value) or re.fullmatch(r"@[A-Za-z0-9_]{5,32}", value)):
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "↩️ Volver al ajuste",
                callback_data=f"gmod|policy|{canal_key}|{pagina}|{policy_id}|"
                + ("forward" if policy_id.startswith("forward_") else "quotes" if policy_id.startswith("quote_") else "internet" if policy_id == "internet_links" else "telegram"),
            ))
            editar_o_enviar_panel(
                message.chat.id,
                "Formato no válido. Envía un ID numérico o un @username (5–32 caracteres); "
                "antepone - para quitarlo.",
                markup,
                message_id=panel_message_id,
            )
            return
        cambio = {"mensaje": "Excepción guardada."}
        def cambiar_excepciones(ajustes_actuales):
            policy = ajustes_actuales.setdefault(
                "moderation_policies", {}
            ).setdefault(policy_id, {})
            exceptions = policy.setdefault("exceptions", [])
            if quitar:
                if value in exceptions:
                    exceptions.remove(value)
                    cambio["mensaje"] = "Excepción eliminada."
                else:
                    cambio["mensaje"] = "Ese ID o usuario no estaba en la lista."
            elif value not in exceptions:
                if len(exceptions) >= 50:
                    raise ValueError("Cada lista admite hasta 50 excepciones.")
                exceptions.append(value)
            else:
                cambio["mensaje"] = "Esa excepción ya estaba guardada."
        try:
            actualizar_ajustes_grupo(canal_key, cambiar_excepciones)
        except ValueError as error:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "↩️ Volver al ajuste",
                callback_data=f"gmod|policy|{canal_key}|{pagina}|{policy_id}|"
                + ("forward" if policy_id.startswith("forward_") else "quotes" if policy_id.startswith("quote_") else "internet" if policy_id == "internet_links" else "telegram"),
            ))
            editar_o_enviar_panel(
                message.chat.id,
                html.escape(str(error)),
                markup,
                message_id=panel_message_id,
            )
            return
        admin_estado.pop(uid, None)
        seccion = (
            "forward" if policy_id.startswith("forward_") else
            "quotes" if policy_id.startswith("quote_") else
            "internet" if policy_id == "internet_links" else "telegram"
        )
        mostrar_menu_antispam(
            message.chat.id,
            canal_key,
            pagina,
            message_id=panel_message_id,
            seccion=seccion,
            policy_id=policy_id,
            aviso=cambio["mensaje"],
        )
        return

    if paso == "esperando_valor_antiflood":
        canal_key = estado.get("canal_key")
        pagina = estado.get("pagina", 0)
        panel_message_id = estado.get("panel_message_id")
        field = estado.get("field")
        limits = {"limit": (1, 100), "window": (1, 300)}
        minimum, maximum = limits.get(field, (0, 0))
        try:
            value = int(texto_recibido)
            if not minimum <= value <= maximum:
                raise ValueError
        except ValueError:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "↩️ Volver a Anti-flood",
                callback_data=f"grupo_feature|{canal_key}|antiflood|{pagina}",
            ))
            editar_o_enviar_panel(
                message.chat.id,
                f"Envía un número entero entre {minimum} y {maximum}, o pulsa volver.",
                markup,
                message_id=panel_message_id,
            )
            return
        key = "flood_limit" if field == "limit" else "flood_window_seconds"
        actualizar_ajustes_grupo(
            canal_key, lambda ajustes: ajustes.update({key: value})
        )
        admin_estado.pop(uid, None)
        mostrar_menu_antiflood(
            message.chat.id,
            canal_key,
            pagina,
            message_id=panel_message_id,
        )
        return

    if paso == "esperando_videochat_button_label":
        canal_key = estado.get("canal_key")
        pagina = estado.get("pagina", 0)
        panel_message_id = estado.get("panel_message_id")
        etiqueta = texto_recibido.strip()
        ajustes = obtener_ajustes_grupo(canal_key) or {}
        error = None
        if not etiqueta or len(etiqueta) > 32 or "\n" in etiqueta:
            error = "El nombre debe tener entre 1 y 32 caracteres y ocupar una sola línea."
        elif etiqueta.casefold() in {
            str(item.get("label", "")).casefold()
            for item in atajos_fijos_grupo(ajustes)
            if item.get("action") != "__videochat_guide__"
        }:
            error = "Ese nombre está reservado para un atajo fijo del grupo."
        elif any(
            str(item.get("label", "")).strip().casefold() == etiqueta.casefold()
            for item in ajustes.get("quick_buttons", [])
        ):
            error = "Ese nombre ya se usa en otro atajo de este grupo."
        if error:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "↩️ Volver a atajos",
                callback_data=f"grupo_feature|{canal_key}|atajos|{pagina}",
            ))
            editar_o_enviar_panel(
                message.chat.id,
                f"⚠️ {html.escape(error)}\n\n"
                "Envía otro nombre o escribe /cancelar.",
                markup,
                message_id=panel_message_id,
            )
            return

        tenia_teclado = bool(
            ajustes.get("quick_buttons_message_id")
            and str(ajustes.get("quick_buttons_chat_id")) == str(obtener_canal_id(canal_key))
        )
        actualizar_ajustes_grupo(
            canal_key,
            lambda config: config.update({"videochat_button_label": etiqueta}),
        )
        admin_estado.pop(uid, None)
        aviso = "Nombre del botón actualizado."
        if tenia_teclado:
            try:
                publicar_teclado_atajos_grupo(
                    canal_key,
                    "📹 Se actualizó el botón de videochat y los atajos del grupo.",
                )
            except Exception:
                app.logger.exception("No se pudo actualizar el teclado del videochat.")
                aviso += " No pude reemplazar el teclado en el grupo; publícalo manualmente."
        mostrar_menu_atajos_grupo(
            message.chat.id,
            canal_key,
            pagina,
            message_id=panel_message_id,
            aviso=aviso,
        )
        return

    if paso == "esperando_atajo_grupo":
        canal_key = estado.get("canal_key")
        pagina = estado.get("pagina", 0)
        panel_message_id = estado.get("panel_message_id")
        error = None
        try:
            etiqueta, accion = separar_sintaxis_boton(texto_recibido)
            if not etiqueta or len(etiqueta) > 32:
                raise ValueError("La etiqueta debe tener entre 1 y 32 caracteres.")
            if len(accion) > 256:
                raise ValueError("La acción no puede superar 256 caracteres.")
            if not (
                re.fullmatch(r"https?://[^\s<>\"']{1,400}", accion, re.IGNORECASE)
                or re.fullmatch(
                    r"/[A-Za-z0-9_]{1,32}(?:@[A-Za-z0-9_]{5,32})?(?:\s+.{1,150})?",
                    accion,
                )
            ):
                raise ValueError("La acción debe ser un comando del bot o un enlace http(s).")
            if es_atajo_admin({"label": etiqueta, "action": accion}):
                raise ValueError("El acceso /admin solo se permite en tu chat privado con el bot.")
            ajustes = obtener_ajustes_grupo(canal_key) or {}
            existentes = ajustes.get("quick_buttons", [])
            if len(existentes) >= 20:
                raise ValueError("Este chat ya tiene 20 atajos, el máximo permitido.")
            if any(
                str(item.get("label", "")).casefold() == etiqueta.casefold()
                for item in existentes
            ):
                raise ValueError("Ya existe un atajo con esa etiqueta.")
            if etiqueta.casefold() in {
                str(item.get("label", "")).casefold()
                for item in atajos_fijos_grupo(ajustes)
                if item.get("action") != "__videochat_guide__"
            }:
                raise ValueError("Ese nombre está reservado para un atajo fijo del grupo.")
            if (
                str(ajustes.get("type", "")).lower() != "canal"
                and etiqueta.casefold() == etiqueta_boton_videochat(ajustes).casefold()
            ):
                raise ValueError("Ese nombre está reservado para el botón de videochat.")
        except (ValueError, AttributeError) as exc:
            error = str(exc) or "Usa el formato etiqueta=acción."

        if error:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "↩️ Volver a atajos",
                callback_data=f"grupo_feature|{canal_key}|atajos|{pagina}",
            ))
            editar_o_enviar_panel(
                message.chat.id,
                f"⚠️ {html.escape(error)}\n\n"
                "Envía <code>etiqueta=/rules</code>, <code>Etiqueta - rules</code> o "
                "<code>etiqueta=https://ejemplo.com</code>.",
                markup,
                message_id=panel_message_id,
            )
            return

        actualizar_ajustes_grupo(
            canal_key,
            lambda config: config.setdefault("quick_buttons", []).append({
                "label": etiqueta,
                "action": accion,
            }),
        )
        sincronizado = (
            actualizar_teclado_atajos_si_publicado(
                canal_key, "⌨️ Se actualizó la botonera del grupo."
            )
            if ajustes.get("quick_buttons_message_id") else None
        )
        admin_estado.pop(uid, None)
        mostrar_menu_atajos_grupo(
            message.chat.id,
            canal_key,
            pagina,
            message_id=panel_message_id,
            aviso=(
                "Atajo agregado y teclado actualizado."
                if sincronizado is True else
                "Atajo agregado; publica los atajos manualmente en el grupo."
                if sincronizado is False else
                "Atajo agregado."
            ),
        )
        return

    if paso == "esperando_canal_registro":
        editar_o_enviar_panel(
            message.chat.id,
            "Selecciona el canal con el botón de la barra inferior, o escribe /cancelar.",
            types.InlineKeyboardMarkup(),
        )
        return

    if paso == "esperando_ajuste_grupo":
        canal_key = estado.get("canal_key")
        feature = estado.get("feature")
        pagina = estado.get("pagina", 0)
        panel_message_id = estado.get("panel_message_id")
        texto_edicion = message.text
        if estado.get("edit_mode") == "remove" and not texto_edicion.strip().startswith("-"):
            texto_edicion = "-" + texto_edicion.strip()
        try:
            resultado = guardar_edicion_funcion_grupo(canal_key, feature, texto_edicion)
        except ValueError as error:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "↩️ Volver a personalizar mensaje"
                if estado.get("volver_a_editor_reglas")
                else "↩️ Volver a opciones",
                callback_data=(
                    f"grp_rules|editor|{canal_key}|{pagina}"
                    if estado.get("volver_a_editor_reglas")
                    else f"grupo_feature|{canal_key}|{feature}|{pagina}"
                ),
            ))
            editar_o_enviar_panel(
                message.chat.id,
                f"⚠️ {html.escape(str(error))}\n\nEnvía un valor nuevo o pulsa volver.",
                markup,
                message_id=panel_message_id,
            )
            return
        admin_estado.pop(uid, None)
        if estado.get("volver_a_editor_reglas"):
            mostrar_editor_reglamento(
                message.chat.id,
                canal_key,
                pagina,
                message_id=panel_message_id,
                aviso=resultado,
            )
        else:
            mostrar_menu_funcion_grupo(
                message.chat.id,
                canal_key,
                feature,
                pagina,
                message_id=panel_message_id,
                aviso=resultado,
            )
        return

    if paso == "esperando_nombre_topic":
        canal_key = estado.get("canal_key")
        pagina = estado.get("pagina", 0)
        nombre_topic = texto_recibido
        if not nombre_topic or len(nombre_topic) > 128:
            editar_o_enviar_panel(
                message.chat.id,
                "El nombre del tema debe tener entre 1 y 128 caracteres.",
                types.InlineKeyboardMarkup(),
            )
            return
        chat_id = obtener_canal_id(canal_key)
        try:
            tema = bot.create_forum_topic(chat_id, nombre_topic)
            admin_estado.pop(uid, None)
            mostrar_menu_funcion_grupo(
                message.chat.id,
                canal_key,
                "topics",
                pagina,
                aviso=(
                    f"✅ Tema creado: <b>{html.escape(nombre_topic)}</b> "
                    f"(ID {tema.message_thread_id})."
                ),
            )
        except Exception as error:
            editar_o_enviar_panel(
                message.chat.id,
                "No pude crear el tema. Comprueba que el bot sea administrador y que Topics esté activado.\n"
                f"<code>{html.escape(str(error))}</code>",
                types.InlineKeyboardMarkup(),
            )
        return

    if paso == "esperando_nombre_destino":
        nombre = (message.text or "").strip()
        if not nombre:
            editar_o_enviar_panel(
                message.chat.id,
                "Escribe un nombre para el grupo o canal.",
                types.InlineKeyboardMarkup(),
            )
            return
        if len(nombre) > 50:
            editar_o_enviar_panel(
                message.chat.id,
                "Usa un nombre de 50 caracteres o menos.",
                types.InlineKeyboardMarkup(),
            )
            return
        admin_estado[uid]["nombre_destino"] = nombre
        admin_estado[uid]["paso"] = "esperando_id_nuevo_destino"
        editar_o_enviar_panel(
            message.chat.id,
            "📨 Envía el ID numérico del grupo o canal, o reenvía un mensaje de texto enviado allí.\n\n"
            "⚠️ El bot debe estar en el grupo o ser administrador del canal para publicar.",
            types.InlineKeyboardMarkup(),
        )

    elif paso == "esperando_id_nuevo_destino":
        completar_destino_adicional(message, uid)

    # ── Configurar canal: esperar forward ──
    elif paso == "esperando_forward_canal":
        chat_id_detectado = extraer_chat_id_destino(message)

        if chat_id_detectado:
            canal_key = estado.get("canal", "goldpass")
            guardar_canal_id(canal_key, chat_id_detectado)
            admin_estado.pop(uid, None)
            editar_o_enviar_panel(
                message.chat.id,
                f"✅ <b>Destino configurado — {html.escape(CANALES[canal_key]['nombre'])}.</b>\n"
                f"ID guardado: <code>{chat_id_detectado}</code>\n\n"
                "Ahora puedes publicar desde /admin → Ver y administrar botones.",
                types.InlineKeyboardMarkup(),
            )
        else:
            editar_o_enviar_panel(
                message.chat.id,
                "⚠️ No pude detectar el grupo o canal.\n\n"
                "<b>Intenta una de estas opciones:</b>\n"
                "• Escribe el ID directamente, ej: <code>-1003561176552</code>\n"
                "• Reenvía un mensaje de texto enviado en el grupo o canal.",
                types.InlineKeyboardMarkup(),
            )

    # ── Recibir duración del Pase Exprés ──
    elif paso == "esperando_duracion_pase":
        texto_dur = (message.text or "").strip().lower()
        minutos = None
        try:
            if texto_dur.endswith('d'):
                minutos = int(texto_dur[:-1]) * 1440
            elif texto_dur.endswith('h'):
                minutos = int(texto_dur[:-1]) * 60
            elif texto_dur.endswith('m'):
                minutos = int(texto_dur[:-1])
            elif texto_dur.isdigit():
                minutos = int(texto_dur)
        except ValueError:
            minutos = None

        if not minutos or minutos <= 0:
            editar_o_enviar_panel(
                message.chat.id,
                "❌ No entendí la duración. Usa formato como <code>30m</code>, <code>2h</code> o <code>1d</code>.",
                types.InlineKeyboardMarkup(),
            )
            return

        vencimiento = (datetime.now() + timedelta(minutes=minutos)).strftime('%Y-%m-%d %H:%M:%S')
        actualizar_config(
            lambda cfg: cfg.update({"pase_expres": {"activo": True, "vence": vencimiento}})
        )
        admin_estado.pop(uid, None)

        if minutos >= 1440:
            dur_txt = f"{minutos // 1440} día(s)"
        elif minutos >= 60:
            dur_txt = f"{minutos // 60} hora(s)"
        else:
            dur_txt = f"{minutos} minuto(s)"

        editar_o_enviar_panel(
            message.chat.id,
            f"✅ <b>¡Pase Exprés activado!</b>\n\n"
            f"⏱️ Duración: <b>{dur_txt}</b>\n"
            f"📅 Vence: <b>{vencimiento}</b>\n\n"
            f"Cualquier usuario que abra /start verá el botón 🎟️ de acceso gratuito "
            f"al canal GoldPass hasta esa hora.",
            types.InlineKeyboardMarkup(),
        )

    elif paso == "esperando_intervalo_recurrente":
        intervalo = parsear_intervalo(message.text)
        if not intervalo:
            editar_o_enviar_panel(
                message.chat.id,
                "No entendí el intervalo. Usa, por ejemplo, <code>30m</code>, <code>2h</code> o <code>1d</code>.",
                types.InlineKeyboardMarkup(),
            )
            return
        admin_estado[uid]["intervalo_segundos"] = intervalo
        if admin_estado[uid].get("tipo_recurrente") == "repetir":
            mostrar_confirmacion_recurrente(message.chat.id, uid)
            return
        admin_estado[uid]["paso"] = "esperando_texto_recurrente"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Cancelar", callback_data="rec_abortar"))
        editar_o_enviar_panel(
            message.chat.id,
            "📝 <b>Escribe el texto del mensaje recurrente</b> (hasta 1024 caracteres).",
            markup,
        )

    elif paso == "esperando_texto_recurrente":
        texto = (message.text or "").strip()
        if not texto:
            editar_o_enviar_panel(
                message.chat.id, "El mensaje necesita texto.", types.InlineKeyboardMarkup()
            )
            return
        if len(texto) > 1024:
            editar_o_enviar_panel(
                message.chat.id,
                "El texto no puede superar 1024 caracteres.",
                types.InlineKeyboardMarkup(),
            )
            return
        admin_estado[uid]["texto_recurrente"] = texto
        admin_estado[uid]["paso"] = "esperando_media_recurrente"
        admin_estado[uid]["media_items"] = []
        admin_estado[uid]["media_id"] = None
        admin_estado[uid]["media_type"] = None
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                "⏭️ Continuar sin archivos", callback_data="rec_sin_media"
            ),
            types.InlineKeyboardButton("❌ Cancelar", callback_data="rec_abortar"),
        )
        editar_o_enviar_panel(
            message.chat.id,
            "📎 Envía una foto, video, documento o audio para acompañar el mensaje. "
            "Puedes añadir hasta 10 archivos, o continuar sin multimedia.",
            markup,
        )

    # ── Recibir enlace de pago por link (admin lo crea y lo envía aquí) ──
    elif paso == "esperando_link_pago":
        enlace = (message.text or "").strip()
        if not enlace.startswith("http"):
            editar_o_enviar_panel(
                message.chat.id,
                "❌ El enlace debe comenzar con <code>https://</code>. Inténtalo de nuevo:",
                types.InlineKeyboardMarkup(),
            )
            return
        user_id_pago = estado.get("user_id_pago")
        metodo_link  = estado.get("metodo_link", "pago_usa_link")
        admin_estado.pop(uid, None)

        datos_texto = (
            f"🔗🇺🇸 <b>PAGO POR LINK</b>\n\n"
            f"{enlace}"
            f"{_AVISO_LINK}"
        )
        markup = types.InlineKeyboardMarkup(row_width=1)
        try:
            markup.add(types.InlineKeyboardButton(
                "📋 Copiar datos",
                copy_text=types.CopyTextButton(
                    text=f"🔗🇺🇸 PAGO POR LINK\n\n{enlace}{_AVISO_LINK}"
                )
            ))
        except Exception:
            pass
        markup.add(
            types.InlineKeyboardButton("✅ Aprobado",  callback_data=f"adap_{user_id_pago}"),
            types.InlineKeyboardButton("❌ Rechazado", callback_data=f"adrec_{user_id_pago}"),
        )
        datos_msg = editar_o_enviar_panel(
            int(ADMIN_ID), datos_texto,
            markup,
            protect_content=True,
        )
        if user_id_pago in solicitudes_info:
            solicitudes_info[user_id_pago]['datos_msg_id'] = datos_msg.message_id
        else:
            solicitudes_info[user_id_pago] = {
                'metodo': metodo_link, 'username': 'sin_usuario',
                'notif_msg_id': None, 'datos_msg_id': datos_msg.message_id
            }

    # ── Crear botón: nombre ──
    elif paso == "esperando_nombre_en_grupo":
        admin_estado[uid]["nombre_boton"] = message.text
        admin_estado[uid]["paso"] = "esperando_url_en_grupo"
        editar_o_enviar_panel(
            message.chat.id,
            "🔗 <b>URL del botón</b>\n\n"
            "Escribe la URL a donde llevará el botón:\n"
            "Ejemplo: <code>https://t.me/TuCanal</code>",
            types.InlineKeyboardMarkup(),
        )

    # ── Crear botón: URL → guardar y preguntar si agregar otro ──
    elif paso == "esperando_url_en_grupo":
        url = message.text.strip()
        if not url.startswith("http"):
            editar_o_enviar_panel(
                message.chat.id,
                "❌ La URL debe comenzar con <code>http://</code> o <code>https://</code>.",
                types.InlineKeyboardMarkup(),
            )
            return
        nombre = admin_estado[uid].get("nombre_boton", "Botón")
        mid    = admin_estado[uid].get("media_id")
        mtyp   = admin_estado[uid].get("media_type")
        canal_key = admin_estado[uid].get("canal", "goldpass")
        botones = cargar_botones_custom(canal_key)
        botones.append({"texto": nombre, "url": url, "media_id": mid, "media_type": mtyp})
        guardar_botones_custom(canal_key, botones)
        admin_estado[uid].setdefault("botones_sesion", []).append({"texto": nombre, "url": url})
        admin_estado[uid]["nombre_boton"] = ""
        _preguntar_otro_boton(message.chat.id, uid)

    # ── Publicar rápido: texto del mensaje ──
    elif paso == "esperando_texto_rapido":
        texto_rapido = message.text
        mid  = admin_estado[uid].get("media_id")
        mtyp = admin_estado[uid].get("media_type")
        canal_key = admin_estado[uid].get("canal", "goldpass")
        admin_estado[uid]["paso"] = admin_estado[uid].get("paso_previo", "esperando_nombre_en_grupo")
        _publicar_en_canal(message.chat.id, canal_key, texto_rapido, mid, mtyp)

    elif paso == "esperando_texto_publicar":
        admin_estado[uid]["texto_publicar"] = message.text
        admin_estado[uid]["paso"] = "esperando_media_publicar"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⏭️ Sin foto/video", callback_data="admin_skip_media"))
        editar_o_enviar_panel(
            message.chat.id,
            "🖼️ <b>¿Foto o video para el mensaje?</b>\n\n"
            "Envíame la imagen o video ahora.\n"
            "O toca el botón para publicar solo con texto:",
            markup,
        )

# ── FOTO DEL ADMIN ─────────────────────────────────────────────────────────────
@bot.message_handler(
    func=lambda m: (
        str(m.from_user.id) == str(ADMIN_ID)
        and m.chat.type == "private"
        and m.from_user.id in admin_estado
    ),
    content_types=['photo']
)
def admin_foto(message):
    uid    = message.from_user.id
    estado = admin_estado.get(uid, {})
    paso   = estado.get("paso")
    foto_id = message.photo[-1].file_id

    if guardar_foto_menu_pagos(message, foto_id):
        return
    if guardar_media_reglamento(message, foto_id, "photo"):
        return
    if guardar_media_en_boton(message, foto_id, "photo"):
        return
    if guardar_media_botones_lote(message, foto_id, "photo"):
        return
    if rechazar_media_metodo_pago(message):
        return

    if paso == "esperando_id_nuevo_destino":
        if completar_destino_adicional(message, uid):
            eliminar_mensaje_disparador(message)
        return

    if paso == "esperando_media_grupo":
        admin_estado[uid]["media_id"]   = foto_id
        admin_estado[uid]["media_type"] = "photo"
        admin_estado[uid]["paso"]       = "esperando_nombre_en_grupo"
        bot.send_message(
            message.chat.id,
            "✅ <b>Foto guardada.</b>\n\n"
            "✏️ <b>Nombre del primer botón:</b>\n\nEscribe el texto que aparecerá en el botón:",
            parse_mode="HTML"
        )
        eliminar_mensaje_disparador(message)

    elif paso == "esperando_media_publicar":
        texto = estado.get("texto_publicar", "")
        canal_key = estado.get("canal", "goldpass")
        botones_key = estado.get("botones_key")
        admin_estado.pop(uid, None)
        _publicar_en_canal(message.chat.id, canal_key, texto, foto_id, "photo", botones_key)
        eliminar_mensaje_disparador(message)

    elif paso == "esperando_media_recurrente":
        agregar_media_recurrente(message, foto_id, "photo")
        eliminar_mensaje_disparador(message)

# ── VIDEO DEL ADMIN ────────────────────────────────────────────────────────────
@bot.message_handler(
    func=lambda m: (
        str(m.from_user.id) == str(ADMIN_ID)
        and m.chat.type == "private"
        and m.from_user.id in admin_estado
    ),
    content_types=['video']
)
def admin_video(message):
    uid    = message.from_user.id
    estado = admin_estado.get(uid, {})
    paso   = estado.get("paso")
    video_id = message.video.file_id

    if rechazar_archivo_foto_pagos(message):
        return
    if guardar_media_reglamento(message, video_id, "video"):
        return
    if guardar_media_en_boton(message, video_id, "video"):
        return
    if guardar_media_botones_lote(message, video_id, "video"):
        return
    if rechazar_media_metodo_pago(message):
        return

    if paso == "esperando_id_nuevo_destino":
        if completar_destino_adicional(message, uid):
            eliminar_mensaje_disparador(message)
        return

    if paso == "esperando_media_grupo":
        admin_estado[uid]["media_id"]   = video_id
        admin_estado[uid]["media_type"] = "video"
        admin_estado[uid]["paso"]       = "esperando_nombre_en_grupo"
        bot.send_message(
            message.chat.id,
            "✅ <b>Video guardado.</b>\n\n"
            "✏️ <b>Nombre del primer botón:</b>\n\nEscribe el texto que aparecerá en el botón:",
            parse_mode="HTML"
        )
        eliminar_mensaje_disparador(message)

    elif paso == "esperando_media_publicar":
        texto = estado.get("texto_publicar", "")
        canal_key = estado.get("canal", "goldpass")
        botones_key = estado.get("botones_key")
        admin_estado.pop(uid, None)
        _publicar_en_canal(message.chat.id, canal_key, texto, video_id, "video", botones_key)
        eliminar_mensaje_disparador(message)

    elif paso == "esperando_media_recurrente":
        agregar_media_recurrente(message, video_id, "video")
        eliminar_mensaje_disparador(message)

@bot.message_handler(
    func=lambda m: (
        str(m.from_user.id) == str(ADMIN_ID)
        and m.chat.type == "private"
        and m.from_user.id in admin_estado
    ),
    content_types=["document"],
)
def admin_documento(message):
    uid = message.from_user.id
    estado = admin_estado.get(uid, {})
    if rechazar_archivo_foto_pagos(message):
        return
    if guardar_media_reglamento(message, message.document.file_id, "document"):
        return
    if guardar_media_en_boton(message, message.document.file_id, "document"):
        return
    if guardar_media_botones_lote(message, message.document.file_id, "document"):
        return
    if rechazar_media_metodo_pago(message):
        return
    if estado.get("paso") == "esperando_id_nuevo_destino":
        if completar_destino_adicional(message, uid):
            eliminar_mensaje_disparador(message)
    elif estado.get("paso") == "esperando_media_recurrente":
        agregar_media_recurrente(message, message.document.file_id, "document")
        eliminar_mensaje_disparador(message)

@bot.message_handler(
    func=lambda m: (
        str(m.from_user.id) == str(ADMIN_ID)
        and m.chat.type == "private"
        and m.from_user.id in admin_estado
    ),
    content_types=["audio"],
)
def admin_audio(message):
    uid = message.from_user.id
    estado = admin_estado.get(uid, {})
    if rechazar_archivo_foto_pagos(message):
        return
    if guardar_media_reglamento(message, message.audio.file_id, "audio"):
        return
    if guardar_media_en_boton(message, message.audio.file_id, "audio"):
        return
    if guardar_media_botones_lote(message, message.audio.file_id, "audio"):
        return
    if rechazar_media_metodo_pago(message):
        return
    if estado.get("paso") == "esperando_media_recurrente":
        agregar_media_recurrente(message, message.audio.file_id, "audio")
        eliminar_mensaje_disparador(message)

@bot.message_handler(
    func=lambda m: (
        str(m.from_user.id) == str(ADMIN_ID)
        and m.chat.type == "private"
        and m.from_user.id in admin_estado
    ),
    content_types=["animation"],
)
def admin_animacion(message):
    uid = message.from_user.id
    estado = admin_estado.get(uid, {})
    if rechazar_archivo_foto_pagos(message):
        return
    if guardar_media_reglamento(message, message.animation.file_id, "animation"):
        return
    if guardar_media_en_boton(message, message.animation.file_id, "animation"):
        return
    if guardar_media_botones_lote(message, message.animation.file_id, "animation"):
        return
    if rechazar_media_metodo_pago(message):
        return
    if estado.get("paso") == "esperando_media_recurrente":
        agregar_media_recurrente(message, message.animation.file_id, "animation")

# ── Helpers internos ──────────────────────────────────────────────────────────
def _preguntar_otro_boton(chat_id, uid):
    sesion  = admin_estado.get(uid, {}).get("botones_sesion", [])
    resumen = "\n".join(f"  • {html.escape(b['texto'])}" for b in sesion)
    markup  = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ Agregar otro botón a esta foto", callback_data="admin_otro_boton"),
        types.InlineKeyboardButton("📤 Publicar ahora en el canal",    callback_data="admin_publicar_ahora"),
        types.InlineKeyboardButton("✅ Listo",                          callback_data="admin_listo_grupo"),
    )
    bot.send_message(
        chat_id,
        f"✅ <b>Botón agregado.</b>\n\n"
        f"<b>Botones en esta publicación ({len(sesion)}):</b>\n{resumen}\n\n"
        f"¿Deseas agregar otro botón a esta misma foto/video?",
        parse_mode="HTML", reply_markup=markup
    )

# ── Publicar ahora (desde botón rápido en _preguntar_otro_boton) ────────────
@bot.callback_query_handler(func=lambda call: call.data == "admin_publicar_ahora")
def admin_publicar_ahora_cb(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    uid    = call.from_user.id
    estado = admin_estado.get(uid, {})
    canal_key = estado.get("canal", "goldpass")
    if not obtener_canal_id(canal_key):
        bot.send_message(call.message.chat.id,
            f"⚠️ El destino {html.escape(CANALES[canal_key]['nombre'])} no está configurado. "
            "Ve a /admin → Grupos y canales.",
            parse_mode="HTML",
        )
        return
    # Guardar paso actual para restaurar después de pedir texto
    admin_estado[uid]["paso_previo"] = estado.get("paso", "")
    admin_estado[uid]["paso"] = "esperando_texto_rapido"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⏭️ Sin texto", callback_data="admin_publicar_ahora_sin_texto"))
    bot.send_message(
        call.message.chat.id,
        "📝 ¿Qué texto acompañará la publicación?\n\nO toca el botón para publicar sin texto:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin_publicar_ahora_sin_texto")
def admin_publicar_ahora_sin_texto(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    uid    = call.from_user.id
    estado = admin_estado.get(uid, {})
    mid    = estado.get("media_id")
    mtyp   = estado.get("media_type")
    canal_key = estado.get("canal", "goldpass")
    admin_estado[uid]["paso"] = estado.get("paso_previo", "esperando_nombre_en_grupo")
    _publicar_en_canal(call.message.chat.id, canal_key, "", mid, mtyp)

def _publicar_en_canal(chat_id_admin, canal_key, texto, media_id, media_type, botones_key=None):
    canal_dest = obtener_canal_id(canal_key)
    botones_key = botones_key or canal_key
    botones = cargar_botones_custom(botones_key)
    markup_pub   = construir_markup_botones(botones)

    if not canal_dest:
        bot.send_message(chat_id_admin,
            f"❌ El destino {html.escape(CANALES[canal_key]['nombre'])} no está configurado. "
            "Ve a /admin → Grupos y canales.",
            parse_mode="HTML",
        )
        return

    try:
        mensaje = enviar_publicacion_con_botones(
            int(canal_dest), texto, markup_pub, media_id, media_type
        )
        guardar_ultima_publicacion(
            botones_key, canal_dest, mensaje, texto, media_id, media_type
        )
        bot.send_message(chat_id_admin,
            f"✅ <b>¡Publicado en {html.escape(CANALES[canal_key]['nombre'])}!</b>",
            parse_mode="HTML",
            reply_markup=markup_menu_botones(botones_key),
        )
    except Exception as error:
        bot.send_message(chat_id_admin,
            f"❌ <b>Error al publicar:</b>\n<code>{html.escape(str(error))}</code>\n\n"
            "Asegúrate de que el bot esté en el grupo o sea administrador del canal.",
            parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════
# 1. BIENVENIDA
# ═══════════════════════════════════════════════════════════════════
@bot.message_handler(commands=['start'])
def bienvenida(message):
    eliminar_mensaje_disparador(message)
    if message.chat.type != "private":
        return
    if str(message.from_user.id) == str(ADMIN_ID):
        try:
            instalar_teclado_persistente(
                message.chat.id,
                "⌨️ Atajos de administración disponibles en la barra inferior.",
                teclado_atajos_admin(),
                forzar=True,
            )
        except Exception:
            app.logger.exception(
                "No se pudo instalar el teclado de administración al iniciar el chat."
            )
    mostrar_metodos_pago(message.chat.id)

# ─── Respuesta automática de Telegram Business ───────────────────────────
def _conexion_business_perfil_autorizado(connection_id):
    if not connection_id:
        return False
    ahora = time.monotonic()
    with BUSINESS_CONNECTION_LOCK:
        cacheado = BUSINESS_CONNECTION_CACHE.get(connection_id)
        if cacheado and cacheado[0] > ahora:
            return cacheado[1]

    autorizada = False
    owner_id = None
    try:
        conexion = bot.get_business_connection(connection_id)
        propietario = getattr(conexion, "user", None)
        owner_id = str(propietario.id) if propietario else None
        autorizada = bool(
            getattr(conexion, "is_enabled", False)
            and owner_id in BUSINESS_PROFILE_OWNER_IDS
        )
    except Exception as error:
        # Fallar cerrado: no responder si Telegram no permite verificar la conexión.
        _log_business_diagnostic(
            "business_connection_api_error",
            "Telegram no permitió verificar la conexión de perfil (tipo de error: %s).",
            type(error).__name__,
        )
        autorizada = False

    with BUSINESS_CONNECTION_LOCK:
        BUSINESS_CONNECTION_CACHE[connection_id] = (
            ahora + (300 if autorizada else 30),
            autorizada,
        )
        if autorizada:
            BUSINESS_CONNECTION_OWNER_CACHE[connection_id] = owner_id
        else:
            BUSINESS_CONNECTION_OWNER_CACHE.pop(connection_id, None)

    if not autorizada:
        _log_business_diagnostic(
            "business_connection_not_authorized",
            "Se ignoró la conexión de perfil: está desactivada o no pertenece al propietario configurado.",
        )

    if autorizada:
        def guardar_conexion(config):
            conexiones = config.setdefault("business_connection_ids", [])
            if connection_id not in conexiones:
                conexiones.append(connection_id)
        try:
            actualizar_config(guardar_conexion)
        except Exception:
            app.logger.warning("No se pudo guardar la conexión Business autorizada.")
    return autorizada


@bot.business_connection_handler()
def registrar_conexion_business(connection):
    connection_id = getattr(connection, "id", None)
    if not connection_id:
        return
    propietario = getattr(connection, "user", None)
    owner_id = str(propietario.id) if propietario else None
    owner_matches = bool(
        owner_id and owner_id in BUSINESS_PROFILE_OWNER_IDS
    )
    autorizada = bool(
        getattr(connection, "is_enabled", False)
        and owner_matches
    )
    _log_business_diagnostic(
        "business_connection_update",
        "Telegram actualizó la conexión de perfil: habilitada=%s, propietario_correcto=%s.",
        bool(getattr(connection, "is_enabled", False)),
        owner_matches,
    )
    with BUSINESS_CONNECTION_LOCK:
        BUSINESS_CONNECTION_CACHE[connection_id] = (
            time.monotonic() + 300,
            autorizada,
        )
        if autorizada:
            BUSINESS_CONNECTION_OWNER_CACHE[connection_id] = owner_id
        else:
            BUSINESS_CONNECTION_OWNER_CACHE.pop(connection_id, None)

    def guardar_estado(config):
        conexiones = config.setdefault("business_connection_ids", [])
        if autorizada:
            if connection_id not in conexiones:
                conexiones.append(connection_id)
        else:
            config["business_connection_ids"] = [
                existente for existente in conexiones
                if existente != connection_id
            ]
    try:
        actualizar_config(guardar_estado)
    except Exception:
        app.logger.warning("No se pudo guardar el estado de una conexión Business.")


def _es_mensaje_entrante_business(message):
    connection_id = getattr(message, "business_connection_id", None)
    sender = getattr(message, "from_user", None)

    if message.chat.type != "private" or not connection_id or not sender:
        return False
    if not _conexion_business_perfil_autorizado(connection_id):
        return False
    if getattr(sender, "is_bot", False):
        return False
    if str(sender.id) in BUSINESS_PROFILE_OWNER_IDS:
        return False
    if getattr(message, "sender_business_bot", None):
        return False
    return True


def _welcome_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("Canal gratuito", url=WELCOME_CHANNEL_URL))
    markup.row(
        types.InlineKeyboardButton("X", url=WELCOME_X_URL),
        types.InlineKeyboardButton("Instagram", url=WELCOME_INSTAGRAM_URL),
    )
    return markup


@bot.business_message_handler(
    func=_es_mensaje_entrante_business,
    content_types=[
        "text", "photo", "video", "document", "audio", "voice", "sticker",
        "location", "contact", "animation", "video_note", "poll", "venue", "dice",
    ],
)
def respuesta_automatica_business(message):
    connection_id = message.business_connection_id
    chat_id = message.chat.id
    owner_id = BUSINESS_CONNECTION_OWNER_CACHE.get(connection_id)
    if not owner_id:
        _log_business_diagnostic(
            "business_connection_owner_missing",
            "Se omitió el saludo: no se encontró el perfil propietario de la conexión autorizada.",
        )
        return
    owner_key = hashlib.sha256(owner_id.encode("utf-8")).hexdigest()
    already_replied = (
        (WELCOME_QUERY.chat_id == chat_id)
        & (WELCOME_QUERY.business_owner_key == owner_key)
    )

    # El lock evita respuestas duplicadas si llegan varios mensajes juntos.
    # Solo se guarda el contacto después de que Telegram acepta el envío.
    with WELCOME_REPLY_LOCK:
        greeted_for_profile = WELCOME_SENT_DB.contains(already_replied)
        # Los registros anteriores no distinguían perfiles: se conservan para la cuenta principal.
        previously_greeted_legacy = (
            owner_id == str(ADMIN_ID)
            and WELCOME_SENT_DB.contains(WELCOME_QUERY.chat_id == chat_id)
        )
        if greeted_for_profile or previously_greeted_legacy:
            _log_business_diagnostic(
                "welcome_already_sent",
                "Se omitió el saludo automático: este perfil ya saludó a este chat.",
            )
            return

        _log_business_diagnostic(
            "welcome_send_attempt",
            "Se aceptó un mensaje de perfil nuevo para el saludo automático.",
        )
        try:
            with open(WELCOME_PHOTO_PATH, "rb") as photo:
                bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=WELCOME_MESSAGE,
                    reply_markup=_welcome_markup(),
                    business_connection_id=connection_id,
                )
        except Exception:
            app.logger.exception("No se pudo enviar el saludo automático de Telegram Business.")
            try:
                bot.send_message(
                    chat_id=chat_id,
                    text=WELCOME_MESSAGE,
                    reply_markup=_welcome_markup(),
                    business_connection_id=connection_id,
                )
            except Exception:
                app.logger.exception(
                    "Tampoco se pudo enviar el saludo de Telegram Business sin foto."
                )
                return

        try:
            WELCOME_SENT_DB.insert({
                "chat_id": chat_id,
                "business_owner_key": owner_key,
            })
            app.logger.info("Se envió el saludo automático de Telegram Business.")
        except Exception:
            app.logger.exception(
                "El saludo se envió, pero no se pudo guardar el registro anti-duplicados."
            )

# ─── Botón "Usar otro método de pago" (reinicia el ciclo de pago) ────
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
@bot.message_handler(content_types=['photo'])
def recibir_pago(message):
    if message.chat.type != "private":
        return
    if str(message.from_user.id) == str(ADMIN_ID):
        return   # Las fotos del admin se manejan en admin_foto
    bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
    bot.send_message(
        int(ADMIN_ID),
        f"💰 <b>COMPROBANTE RECIBIDO</b>\n"
        f"👤 @{message.from_user.username or 'sin_usuario'}\n"
        f"🆔 <code>{message.from_user.id}</code>",
        parse_mode="HTML",
        _force_new_message=True,
    )
    eliminar_mensaje_disparador(message)
    bot.send_message(message.chat.id,
        "✅ Comprobante recibido. En breve verificamos tu pago.", protect_content=True)

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

WEBHOOK_ALLOWED_UPDATES = [
    "message", "callback_query", "chat_join_request",
    "chat_member", "my_chat_member", "business_connection",
    "business_message"
]

if __name__ == "__main__":
    bot_mode = os.environ.get("BOT_MODE", "webhook").strip().lower()
    port = int(os.environ.get("PORT", 10000))

    try:
        capacidad_grupos = getattr(bot.get_me(), "can_join_groups", None)
        if capacidad_grupos is False:
            print(
                "⚠️ Telegram tiene desactivado el ingreso a grupos para este bot. "
                "En BotFather usa /setjoingroups y selecciona Enable."
            )
        elif capacidad_grupos is True:
            print("✅ Telegram permite añadir este bot a grupos.")
    except Exception:
        print("⚠️ No se pudo comprobar el permiso global para unirse a grupos.")

    if bot_mode == "polling":
        if not bot.delete_webhook(drop_pending_updates=False):
            raise RuntimeError("No se pudo quitar el webhook anterior de Telegram.")

        print(
            f"🚀 Bot activo por polling en el puerto {port}; "
            "se conservarán las actualizaciones pendientes."
        )
        threading.Thread(
            target=lambda: bot.infinity_polling(
                timeout=20,
                skip_pending=False,
                long_polling_timeout=20,
                allowed_updates=WEBHOOK_ALLOWED_UPDATES,
            ),
            name="telegram-polling",
            daemon=True,
        ).start()
    elif bot_mode == "webhook":
        webhook_base_url = (
            os.environ.get("RENDER_EXTERNAL_URL")
            or os.environ.get("WEBHOOK_URL")
            or ""
        ).rstrip("/")
        if not webhook_base_url:
            raise RuntimeError(
                "Falta RENDER_EXTERNAL_URL o WEBHOOK_URL para registrar el webhook."
            )

        webhook_url = f"{webhook_base_url}{WEBHOOK_PATH}"
        if not bot.set_webhook(
            url=webhook_url,
            secret_token=WEBHOOK_SECRET,
            allowed_updates=WEBHOOK_ALLOWED_UPDATES,
        ):
            raise RuntimeError("Telegram no aceptó el registro del webhook.")

        print(f"🚀 Bot activo por webhook en el puerto {port}.")
    else:
        raise RuntimeError(f"Modo de bot no reconocido: {bot_mode}")

    app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)
