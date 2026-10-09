import os
import threading
import time
import json
import hashlib
import hmac
import telebot
from telebot import types
from tinydb import TinyDB, Query
from datetime import datetime, timedelta
from flask import Flask, redirect, request

app = Flask(__name__)

@app.route('/')
def home():
    return redirect("https://caciquex.netlify.app", code=302)

# --- CONFIGURACIÓN ---

TOKEN = os.environ['TELEGRAM_TOKEN']
WEBHOOK_PATH = "/telegram-webhook"
WEBHOOK_SECRET = hashlib.sha256(
    f"telegram-webhook:{TOKEN}".encode("utf-8")
).hexdigest()

CANAL_ID = '-1003914257220'      # Canal VIP (suscripciones)
CanaL_ID = '-1003561176552'
ADMIN_ID = '7827130679'

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

bot = telebot.TeleBot(TOKEN, skip_pending=True)
db = TinyDB('usuarios.json')
WELCOME_SENT_DB = TinyDB(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "business_welcome_users.json")
).table("sent")
WELCOME_QUERY = Query()
WELCOME_REPLY_LOCK = threading.Lock()

@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    received_secret = request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token", ""
    )
    if not hmac.compare_digest(received_secret, WEBHOOK_SECRET):
        return "Unauthorized", 403
    if not request.is_json:
        return "Expected JSON", 415

    update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK", 200

solicitudes_pendientes = {}
admin_estado = {}

# {user_id: {'metodo': str, 'username': str, 'notif_msg_id': int, 'datos_msg_id': int}}
solicitudes_info = {}


CONFIG_FILE   = 'config.json'

# ── Canales de publicación de botones (independientes entre sí) ──────────────
# Cada canal tiene su propio ID de destino y su propio archivo de botones,
# así una publicación en uno nunca se envía ni comparte botones con el otro.
CANALES = {
    "goldpass": {"nombre": "🏆 GoldPass CX HOTGO", "archivo": "botones_goldpass.json"},
    "freeclub": {"nombre": "🆓 FREECLUB CX HUB",   "archivo": "botones_freeclub.json"},
}

# ── Config persistente (IDs de canal por clave, etc.) ─────────────────────────
def cargar_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def guardar_config(cfg):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def obtener_canal_id(canal_key):
    cfg = cargar_config()
    return cfg.get('canales', {}).get(canal_key)

def guardar_canal_id(canal_key, chat_id):
    cfg = cargar_config()
    cfg.setdefault('canales', {})[canal_key] = str(chat_id)
    guardar_config(cfg)

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

def markup_seleccionar_canal(callback_prefix):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, info in CANALES.items():
        markup.add(types.InlineKeyboardButton(info["nombre"], callback_data=f"{callback_prefix}_{key}"))
    markup.add(types.InlineKeyboardButton("🔙 Volver al panel", callback_data="admin_volver"))
    return markup

# ── Datos de pago ─────────────────────────────────────────────────────────────
_AVISO = "\n\n⚠️ Importante: Envía tu comprobante a este mismo chat cuando termines de procesar tu pedido para obtener el GoldPass."

DATOS_PAGO = {
    "pago_binance": (
        "🔸 BINANCE PAY\n"
        "ID: 913431478\n"
        "Correo: joselito.26pregunton@gmail.com"
        + _AVISO
    ),
    "pago_pm": (
        "🇻🇪 PAGO MÓVIL\n"
        "Banco: 0172\n"
        "Telf: 04226028818\n"
        "CI: 27.704.507"
        + _AVISO
    ),
    "pago_trans": (
        "🏦 MERCANTIL\n"
        "Banco: Mercantil\n"
        "Cuenta: 01050180601180179234"
        + _AVISO
    ),
    "pago_airtm": (
        "🌐 AIRTM\n"
        "Correo: @caciquex"
        + _AVISO
    ),
    "pago_wally": (
        "💜 WALLY\n"
        "ID/Correo: +18687882715"
        + _AVISO
    ),
    "pago_usa_bank": (
        "🇺🇸 CUENTA AMERICANA\n"
        "Titular: JOSE ALEJANDRO GONZALEZ\n"
        "Ruta: 101019644\n"
        "Cuenta: 215514970863\n"
        "Tipo: Checking"
        + _AVISO
    ),
    "pago_usa_link": (
        "💳 PAGO POR LINK\n"
        "→ Genera el enlace de cobro personalizado para este usuario.\n"
        "→ Recuerda informar la comisión adicional: 5.3% + 0.8% sobre el monto."
    ),
    "pago_visa_mc": (
        "💳 PAGO POR LINK (Visa/Mastercard)\n"
        "→ Genera el enlace de cobro personalizado para este usuario.\n"
        "→ Recuerda informar la comisión adicional: 5.3% + 0.8% sobre el monto."
    ),
    "pago_iban": (
        "💶 CUENTA CON EUROS (IBAN)\n"
        "Titular: Bridge Building Sp. Z.o.o.\n"
        "IBAN: LU424080000044042028\n"
        "BIC: BCIRLULL\n"
        "Banco: Banking Circle S.A.\n"
        "Dirección: 2 Boulevard de la Foire, L-1528 Luxembourg"
        + _AVISO
    ),
    "pago_mex": (
        "🇲🇽 CUENTA MÉXICO\n"
        "Titular: JOSE ALEJANDRO GONZALEZ\n"
        "CLABE: 646180546701126005"
        + _AVISO
    ),
    "pago_PayPal": (
        "🏦 PayPay\n"
        "Titular: JOSE ALEJANDRO GONZALEZ\n"
        "Correo: alemussett26@gmail.com"
        + _AVISO
    ),
}

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
    try:
        with open('portada.jpg', 'rb') as photo:
            bot.send_photo(chat_id, photo, caption=texto,
                reply_markup=markup, parse_mode="HTML", protect_content=True)
    except:
        bot.send_message(chat_id, texto,
            reply_markup=markup, parse_mode="HTML", protect_content=True)

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

def enviar_con_media(chat_id, texto, markup, boton):
    """Envía mensaje al chat con media del botón si tiene, o solo texto."""
    mid  = boton.get('media_id')
    mtyp = boton.get('media_type')
    if mid and mtyp == 'photo':
        return bot.send_photo(chat_id, mid, caption=texto, reply_markup=markup, parse_mode="HTML")
    elif mid and mtyp == 'video':
        return bot.send_video(chat_id, mid, caption=texto, reply_markup=markup, parse_mode="HTML")
    else:
        return bot.send_message(chat_id, texto, reply_markup=markup, parse_mode="HTML")

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

# ── Migración: configuración antigua (canal único) → canales independientes ──
# Antes existía un solo "canal_botones_id" compartido por todas las publicaciones.
# Ahora cada canal (GoldPass CX HOTGO / FREECLUB CX HUB) tiene su propio ID y su
# propio set de botones, así publicar en uno nunca llega ni comparte botones con el otro.
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

# ═══════════════════════════════════════════════════════════════════
# 👥 NUEVO MIEMBRO EN EL CANAL (entró directo, sin pasar por el bot)
# ═══════════════════════════════════════════════════════════════════
# Cuando alguien entra al canal directamente (link de invitación sin
# aprobación, añadido por un admin, etc.) se registra con 30 días.
# Requiere que el bot sea admin del canal con permiso de "ver miembros".
@bot.chat_member_handler()
def nuevo_miembro_directo(update):
    # Solo nos interesa el canal VIP
    if str(update.chat.id) != str(CANAL_ID):
        return
    miembro = update.new_chat_member
    # Solo cuando el estado pasa a member/administrator (entrada)
    if miembro.status not in ("member", "administrator", "creator"):
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
# Los links de un solo uso (pago externo) no generan "join request",
# entran directo. Solo el link fijo con suscripción de Stars dispara
# este evento, así que basta con aprobar cualquier solicitud entrante.
@bot.chat_join_request_handler()
def aprobar_solicitud_canal(chat_join_request):
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

# ═══════════════════════════════════════════════════════════════════
# 🛡️ PROTECCIÓN CONTRA GRUPOS
# ═══════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.chat.type != "private")
def bloquear_grupos(message):
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
def mostrar_panel_admin(chat_id):
    lineas_estado = []
    for key, info in CANALES.items():
        canal_id = obtener_canal_id(key)
        if canal_id:
            lineas_estado.append(f"✅ {info['nombre']}: <code>{canal_id}</code>")
        else:
            lineas_estado.append(f"⚠️ {info['nombre']}: no configurado")
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
        types.InlineKeyboardButton("➕ Crear nuevo botón",          callback_data="admin_crear_boton"),
        types.InlineKeyboardButton("📋 Ver botones creados",        callback_data="admin_ver_botones"),
        types.InlineKeyboardButton("🗑️ Eliminar un botón",         callback_data="admin_eliminar_boton"),
        types.InlineKeyboardButton("📤 Publicar en canal",          callback_data="admin_publicar"),
        types.InlineKeyboardButton("📡 Configurar canal destino",   callback_data="admin_setcanal"),
    )
    bot.send_message(
        chat_id,
        f"🔐 <b>PANEL DE ADMINISTRACIÓN</b>\n\n"
        f"{estado_canal}\n"
        f"{estado_pe}\n\n"
        f"¿Qué deseas hacer?",
        parse_mode="HTML",
        reply_markup=markup
    )

@bot.message_handler(commands=['admin'])
def panel_admin(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        return
    mostrar_panel_admin(message.chat.id)

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
    cfg = cargar_config()
    cfg["pase_expres"] = {"activo": False, "vence": None}
    guardar_config(cfg)
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
    bot.send_message(
        call.message.chat.id,
        "📡 <b>¿Cuál canal deseas configurar?</b>",
        parse_mode="HTML",
        reply_markup=markup_seleccionar_canal("scanal")
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("scanal_"))
def admin_setcanal_elegido(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    canal_key = call.data.split("_", 1)[1]
    admin_estado[call.from_user.id] = {"paso": "esperando_forward_canal", "canal": canal_key}
    nombre_canal = CANALES[canal_key]["nombre"]
    bot.send_message(
        call.message.chat.id,
        f"📡 <b>Configurar canal destino — {nombre_canal}</b>\n\n"
        "<b>Opción 1 — Escribe el ID del canal:</b>\n"
        "Ejemplo: <code>-1003561176552</code>\n\n"
        "<b>Opción 2 — Reenvía un mensaje del canal:</b>\n"
        "Abre el canal → mantén presionado un mensaje → <b>Reenviar</b> hacia aquí.\n\n"
        "⚠️ El bot debe ser <b>administrador</b> del canal para poder publicar.",
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
        "➕ <b>¿Para cuál canal es este botón?</b>",
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
        f"Canal: <b>{CANALES[canal_key]['nombre']}</b>\n\n"
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
    bot.send_message(
        call.message.chat.id,
        "📋 <b>¿De cuál canal quieres ver los botones?</b>",
        parse_mode="HTML",
        reply_markup=markup_seleccionar_canal("vbotones")
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("vbotones_"))
def admin_ver_botones_canal_elegido(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    canal_key = call.data.split("_", 1)[1]
    botones = cargar_botones_custom(canal_key)
    if not botones:
        bot.send_message(call.message.chat.id, f"📋 No hay botones creados aún para {CANALES[canal_key]['nombre']}.")
        return
    texto = f"📋 <b>BOTONES — {CANALES[canal_key]['nombre']}:</b>\n\n"
    for i, b in enumerate(botones, 1):
        media = "🖼️" if b.get('media_id') else "—"
        texto += f"{i}. {b['texto']}  {media}\n   🔗 <code>{b['url']}</code>\n\n"
    bot.send_message(call.message.chat.id, texto, parse_mode="HTML")

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
    botones = cargar_botones_custom(canal_key)
    if not botones:
        bot.send_message(call.message.chat.id, f"📋 No hay botones para eliminar en {CANALES[canal_key]['nombre']}.")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for i, b in enumerate(botones):
        markup.add(types.InlineKeyboardButton(f"🗑️ {b['texto']}", callback_data=f"admin_del_{canal_key}_{i}"))
    markup.add(types.InlineKeyboardButton("❌ Cancelar", callback_data="admin_cancelar"))
    bot.send_message(call.message.chat.id, f"¿Cuál botón de {CANALES[canal_key]['nombre']} deseas eliminar?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_del_"))
def admin_confirmar_eliminar(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    resto = call.data[len("admin_del_"):]
    canal_key, idx_str = resto.rsplit("_", 1)
    idx     = int(idx_str)
    botones = cargar_botones_custom(canal_key)
    if idx < len(botones):
        eliminado = botones.pop(idx)
        guardar_botones_custom(canal_key, botones)
        bot.edit_message_text(
            f"✅ Botón <b>{eliminado['texto']}</b> eliminado de {CANALES[canal_key]['nombre']}.",
            call.message.chat.id, call.message.message_id, parse_mode="HTML"
        )
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
    canal_key = call.data.split("_", 1)[1]
    botones = cargar_botones_custom(canal_key)
    if not botones:
        bot.send_message(call.message.chat.id,
            f"📋 No tienes botones creados para {CANALES[canal_key]['nombre']}. Crea uno primero con /admin → Crear botón.")
        return
    if not obtener_canal_id(canal_key):
        bot.send_message(call.message.chat.id,
            f"⚠️ No has configurado el ID del canal {CANALES[canal_key]['nombre']}.\n"
            "Ve a /admin → 📡 Configurar canal destino primero.")
        return
    admin_estado[call.from_user.id] = {"paso": "esperando_texto_publicar", "canal": canal_key}
    bot.send_message(
        call.message.chat.id,
        f"📝 <b>Escribe el texto del mensaje</b> que acompañará los botones en {CANALES[canal_key]['nombre']}:",
        parse_mode="HTML"
    )

# ─── Cancelar / Volver ────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data == "admin_cancelar")
def admin_cancelar(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        bot.answer_callback_query(call.id, "⛔ Sin permiso.")
        return
    bot.answer_callback_query(call.id)
    admin_estado.pop(call.from_user.id, None)
    bot.edit_message_text("❌ Operación cancelada.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_volver")
def admin_volver(call):
    if str(call.from_user.id) != str(ADMIN_ID):
        return
    bot.answer_callback_query(call.id)
    mostrar_panel_admin(call.message.chat.id)

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
        _publicar_en_canal(call.message.chat.id, estado.get("canal"), estado.get("texto_publicar", ""), None, None)
        admin_estado.pop(uid, None)

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
    sesion = admin_estado.pop(uid, {}).get("botones_sesion", [])
    resumen = "\n".join(f"  • {b['texto']}" for b in sesion)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Volver al panel", callback_data="admin_volver"))
    bot.send_message(
        call.message.chat.id,
        f"🎉 <b>¡Publicación lista!</b>\n\n"
        f"<b>{len(sesion)} botón(es) creados:</b>\n{resumen}\n\n"
        f"Ve a /admin → 📤 Publicar en canal para enviarlos.",
        parse_mode="HTML", reply_markup=markup
    )

# ── FLUJO DE TEXTO DEL ADMIN ──────────────────────────────────────────────────
@bot.message_handler(
    func=lambda m: str(m.from_user.id) == str(ADMIN_ID) and m.from_user.id in admin_estado,
    content_types=['text']
)
def admin_flujo_texto(message):
    uid    = message.from_user.id
    estado = admin_estado.get(uid, {})
    paso   = estado.get("paso")

    # ── Configurar canal: esperar forward ──
    if paso == "esperando_forward_canal":
        chat_id_detectado = None
        # Opción A: ID escrito directamente (ej: -1003561176552)
        texto_limpio = (message.text or "").strip()
        if texto_limpio.lstrip('-').isdigit():
            chat_id_detectado = int(texto_limpio)
        # Opción B: forward clásico (forward_from_chat)
        elif message.forward_from_chat:
            chat_id_detectado = message.forward_from_chat.id
        # Opción C: forward nuevo (forward_origin, Telegram API v7+)
        elif hasattr(message, 'forward_origin') and message.forward_origin:
            origin = message.forward_origin
            if hasattr(origin, 'chat') and origin.chat:
                chat_id_detectado = origin.chat.id

        if chat_id_detectado:
            canal_key = estado.get("canal", "goldpass")
            guardar_canal_id(canal_key, chat_id_detectado)
            admin_estado.pop(uid, None)
            bot.send_message(
                message.chat.id,
                f"✅ <b>Canal configurado correctamente — {CANALES[canal_key]['nombre']}.</b>\n"
                f"ID guardado: <code>{chat_id_detectado}</code>\n\n"
                f"Ahora puedes publicar desde /admin → 📤 Publicar en canal.",
                parse_mode="HTML"
            )
        else:
            bot.send_message(
                message.chat.id,
                "⚠️ No pude detectar el canal.\n\n"
                "<b>Intenta una de estas opciones:</b>\n"
                "• Escribe el ID directamente, ej: <code>-1003561176552</code>\n"
                "• Abre el canal, mantén presionado un mensaje y toca <b>Reenviar</b> hacia aquí.",
                parse_mode="HTML"
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
            bot.send_message(message.chat.id,
                "❌ No entendí la duración. Usa formato como <code>30m</code>, <code>2h</code> o <code>1d</code>.",
                parse_mode="HTML")
            return

        vencimiento = (datetime.now() + timedelta(minutes=minutos)).strftime('%Y-%m-%d %H:%M:%S')
        cfg = cargar_config()
        cfg["pase_expres"] = {"activo": True, "vence": vencimiento}
        guardar_config(cfg)
        admin_estado.pop(uid, None)

        if minutos >= 1440:
            dur_txt = f"{minutos // 1440} día(s)"
        elif minutos >= 60:
            dur_txt = f"{minutos // 60} hora(s)"
        else:
            dur_txt = f"{minutos} minuto(s)"

        bot.send_message(
            message.chat.id,
            f"✅ <b>¡Pase Exprés activado!</b>\n\n"
            f"⏱️ Duración: <b>{dur_txt}</b>\n"
            f"📅 Vence: <b>{vencimiento}</b>\n\n"
            f"Cualquier usuario que abra /start verá el botón 🎟️ de acceso gratuito "
            f"al canal GoldPass hasta esa hora.",
            parse_mode="HTML"
        )

    # ── Recibir enlace de pago por link (admin lo crea y lo envía aquí) ──
    elif paso == "esperando_link_pago":
        enlace = (message.text or "").strip()
        if not enlace.startswith("http"):
            bot.send_message(message.chat.id,
                "❌ El enlace debe comenzar con <code>https://</code>. Inténtalo de nuevo:",
                parse_mode="HTML")
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
        datos_msg = bot.send_message(
            int(ADMIN_ID), datos_texto,
            parse_mode="HTML", reply_markup=markup
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
        bot.send_message(
            message.chat.id,
            "🔗 <b>URL del botón</b>\n\n"
            "Escribe la URL a donde llevará el botón:\n"
            "Ejemplo: <code>https://t.me/TuCanal</code>",
            parse_mode="HTML"
        )

    # ── Crear botón: URL → guardar y preguntar si agregar otro ──
    elif paso == "esperando_url_en_grupo":
        url = message.text.strip()
        if not url.startswith("http"):
            bot.send_message(message.chat.id,
                "❌ La URL debe comenzar con <code>http://</code> o <code>https://</code>.",
                parse_mode="HTML")
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
        bot.send_message(
            message.chat.id,
            "🖼️ <b>¿Foto o video para el mensaje?</b>\n\n"
            "Envíame la imagen o video ahora.\n"
            "O toca el botón para publicar solo con texto:",
            parse_mode="HTML",
            reply_markup=markup
        )

# ── FOTO DEL ADMIN ─────────────────────────────────────────────────────────────
@bot.message_handler(
    func=lambda m: str(m.from_user.id) == str(ADMIN_ID) and m.from_user.id in admin_estado,
    content_types=['photo']
)
def admin_foto(message):
    uid    = message.from_user.id
    estado = admin_estado.get(uid, {})
    paso   = estado.get("paso")
    foto_id = message.photo[-1].file_id

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

    elif paso == "esperando_media_publicar":
        texto = estado.get("texto_publicar", "")
        canal_key = estado.get("canal", "goldpass")
        admin_estado.pop(uid, None)
        _publicar_en_canal(message.chat.id, canal_key, texto, foto_id, "photo")

# ── VIDEO DEL ADMIN ────────────────────────────────────────────────────────────
@bot.message_handler(
    func=lambda m: str(m.from_user.id) == str(ADMIN_ID) and m.from_user.id in admin_estado,
    content_types=['video']
)
def admin_video(message):
    uid    = message.from_user.id
    estado = admin_estado.get(uid, {})
    paso   = estado.get("paso")
    video_id = message.video.file_id

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

    elif paso == "esperando_media_publicar":
        texto = estado.get("texto_publicar", "")
        canal_key = estado.get("canal", "goldpass")
        admin_estado.pop(uid, None)
        _publicar_en_canal(message.chat.id, canal_key, texto, video_id, "video")

# ── Helpers internos ──────────────────────────────────────────────────────────
def _preguntar_otro_boton(chat_id, uid):
    sesion  = admin_estado.get(uid, {}).get("botones_sesion", [])
    resumen = "\n".join(f"  • {b['texto']}" for b in sesion)
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
            f"⚠️ Canal {CANALES[canal_key]['nombre']} no configurado. Ve a /admin → 📡 Configurar canal destino.")
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

def _publicar_en_canal(chat_id_admin, canal_key, texto, media_id, media_type):
    canal_dest   = obtener_canal_id(canal_key)
    botones      = cargar_botones_custom(canal_key)
    markup_pub   = construir_markup_botones(botones)

    if not canal_dest:
        bot.send_message(chat_id_admin,
            f"❌ Canal {CANALES[canal_key]['nombre']} no configurado. Ve a /admin → 📡 Configurar canal destino.")
        return

    try:
        if media_id and media_type == 'photo':
            bot.send_photo(int(canal_dest), media_id,
                caption=texto, reply_markup=markup_pub, parse_mode="HTML")
        elif media_id and media_type == 'video':
            bot.send_video(int(canal_dest), media_id,
                caption=texto, reply_markup=markup_pub, parse_mode="HTML")
        else:
            bot.send_message(int(canal_dest), texto,
                reply_markup=markup_pub, parse_mode="HTML")
        bot.send_message(chat_id_admin,
            f"✅ <b>¡Publicado en {CANALES[canal_key]['nombre']}!</b>", parse_mode="HTML")
    except Exception as e:
        bot.send_message(chat_id_admin,
            f"❌ <b>Error al publicar:</b>\n<code>{e}</code>\n\n"
            f"Asegúrate de que el bot sea <b>administrador</b> del canal.",
            parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════
# 1. BIENVENIDA
# ═══════════════════════════════════════════════════════════════════
@bot.message_handler(commands=['start'])
def bienvenida(message):
    mostrar_metodos_pago(message.chat.id)

# ─── Respuesta automática de Telegram Business ───────────────────────────
def _es_mensaje_entrante_business(message):
    connection_id = getattr(message, "business_connection_id", None)
    sender = getattr(message, "from_user", None)

    if message.chat.type != "private" or not connection_id or not sender:
        return False
    if getattr(sender, "is_bot", False):
        return False
    if str(sender.id) == str(ADMIN_ID):
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
    already_replied = WELCOME_QUERY.chat_id == chat_id

    # El lock evita respuestas duplicadas si llegan varios mensajes juntos.
    # Solo se guarda el contacto después de que Telegram acepta el envío.
    with WELCOME_REPLY_LOCK:
        if WELCOME_SENT_DB.contains(already_replied):
            return

        try:
            with open(WELCOME_PHOTO_PATH, "rb") as photo:
                bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=WELCOME_MESSAGE,
                    reply_markup=_welcome_markup(),
                    business_connection_id=connection_id,
                )
            WELCOME_SENT_DB.insert(
                {
                    "chat_id": chat_id,
                }
            )
        except Exception:
            app.logger.exception("No se pudo enviar el saludo automático de Telegram Business.")

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
        bot.send_message(
            call.message.chat.id,
            "⏰ <b>El Pase Exprés ya no está disponible.</b>\n\n"
            "Puedes acceder usando cualquiera de los métodos de pago. 👇",
            parse_mode="HTML"
        )
        return

    user_id  = call.from_user.id
    username = call.from_user.username or "sin_usuario"
    nombre   = call.from_user.first_name or "Usuario"

    # Mensaje de bienvenida al usuario
    msg_usuario = bot.send_message(
        call.message.chat.id,
        "🎟️ <b>¡BIENVENIDO AL TEMPLO CACIQUEX VIP!</b> 🎉\n\n"
        "Tu solicitud de <b>Pase Exprés Gratuito</b> fue recibida.\n\n"
        "⏳ <i>Estamos procesando tu acceso, en un momento te llegará el link de ingreso al canal.</i>\n\n"
        "🙏 <i>Gracias por tu paciencia.</i>",
        parse_mode="HTML", protect_content=True
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
        parse_mode="HTML", reply_markup=markup_admin
    )

    # Guardar para poder borrar mensajes al aprobar/rechazar
    solicitudes_info[user_id] = {
        'metodo': 'pase_expres', 'username': username,
        'notif_msg_id': notif_msg.message_id, 'datos_msg_id': None,
        'usuario_chat_id': call.message.chat.id,
        'usuario_msg_id':  msg_usuario.message_id,
    }

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
    db.upsert({'id': user_id, 'vence': vencimiento, 'username': username}, Query().id == user_id)

    # Borrar mensaje de "espera" del usuario
    u_chat = info.get('usuario_chat_id')
    u_msg  = info.get('usuario_msg_id')
    if u_chat and u_msg:
        try:
            bot.delete_message(u_chat, u_msg)
        except:
            pass

    # Enviar link al usuario
    markup_link = types.InlineKeyboardMarkup()
    markup_link.add(types.InlineKeyboardButton("🔓 Ingresar al canal GoldPass", url=CANAL_INVITE_LINK_EXTERNO))
    try:
        bot.send_message(
            user_id,
            "🎉 <b>¡Tu Pase Exprés ha sido aprobado!</b>\n\n"
            "Aquí tienes tu acceso al canal GoldPass. ¡Que lo disfrutes! 🥳\n\n"
            "⏳ <i>Válido por 30 días. Al vencer, te avisaremos para renovar.</i>",
            parse_mode="HTML", protect_content=True, reply_markup=markup_link
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

    bot.send_message(int(ADMIN_ID),
        "✅ <b>Pase Exprés aprobado.</b>\n"
        f"Usuario <code>{user_id}</code> notificado con su link de acceso.",
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

    # Borrar mensaje "espera" del usuario y notificarle
    u_chat = info.get('usuario_chat_id')
    u_msg  = info.get('usuario_msg_id')
    if u_chat and u_msg:
        try:
            bot.delete_message(u_chat, u_msg)
        except:
            pass
    try:
        bot.send_message(user_id,
            "❌ <b>Tu solicitud de Pase Exprés no pudo ser procesada en este momento.</b>\n\n"
            "Puedes intentarlo con cualquier método de pago usando /start.",
            parse_mode="HTML")
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
    bot.send_message(
        call.message.chat.id,
        "🇺🇸 <b>Cuenta USA — Elige tu forma de pago:</b>",
        parse_mode="HTML",
        reply_markup=markup,
        protect_content=True
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

    msg_usuario = bot.send_message(
        call.message.chat.id, _MSG_LINK,
        parse_mode="HTML", protect_content=True,
        reply_markup=_markup_solicitud_usuario()
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
        notif_msg    = bot.send_message(int(ADMIN_ID), texto_admin,
                                        parse_mode="HTML", reply_markup=markup_admin)
        notif_msg_id = notif_msg.message_id
    except Exception as e:
        try:
            notif_msg    = bot.send_message(int(ADMIN_ID),
                                            texto_admin + f"\n\n⚠️ Error al cargar botones: {e}",
                                            parse_mode="HTML")
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
    msg_usuario = bot.send_message(
        call.message.chat.id,
        "✨ <b>¡SOLICITUD RECIBIDA!</b> ✨\n\n"
        "⏳ Tu solicitud está <b>en proceso</b>.\n\n"
        "Nos comunicaremos contigo en breve con los datos de pago.\n\n"
        "🙏 <i>Gracias por tu paciencia.</i>",
        parse_mode="HTML", protect_content=True,
        reply_markup=_markup_solicitud_usuario()
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
            parse_mode="HTML", reply_markup=markup_admin
        )
        notif_msg_id = notif_msg.message_id
    except Exception as e:
        # Intento sin markup si hubo error con los botones
        try:
            notif_msg = bot.send_message(
                int(ADMIN_ID),
                texto_admin + f"\n\n⚠️ Error al cargar botones: {e}",
                parse_mode="HTML"
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
    # Borrar mensaje actual del usuario
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
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

    # Borrar mensaje del usuario
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass

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

    # Confirmar al usuario
    bot.send_message(
        call.message.chat.id,
        "✅ <b>Solicitud cancelada.</b>\n\n"
        "Si cambias de opinión, usa /start para volver al menú.",
        parse_mode="HTML"
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
    datos         = DATOS_PAGO.get(metodo, "Sin datos")
    nombre_metodo = NOMBRE_METODO.get(metodo, metodo)

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
        f"<code>{datos}</code>",
        parse_mode="HTML", reply_markup=markup
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

    # Registrar suscripción VIP (30 días) y enviar el link fijo de pago externo
    # (el admin ya verificó el pago → sin cobro de Stars; el bot aprueba la
    # solicitud de ingreso automáticamente cuando el usuario toque el link)
    vencimiento = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    username = info.get('username', '')
    if username == 'sin_usuario':
        username = ''
    db.upsert({'id': user_id, 'vence': vencimiento, 'username': username}, Query().id == user_id)

    markup_link = types.InlineKeyboardMarkup()
    markup_link.add(types.InlineKeyboardButton("🔓 Ingresar al canal GoldPass", url=CANAL_INVITE_LINK_EXTERNO))

    try:
        bot.send_message(
            user_id,
            "🎉 <b>¡Tu solicitud ha sido aprobada!</b>\n\n"
            "Aquí tienes tu link GoldPass del canal, que lo disfrutes. 🥳\n\n"
            "⏳ <i>Válido por 30 días. Al vencer, te enviaremos opciones para renovar.</i>",
            parse_mode="HTML", protect_content=True, reply_markup=markup_link
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

    # Borrar mensaje "Solicitud recibida" del chat del usuario
    u_chat = info.get('usuario_chat_id')
    u_msg  = info.get('usuario_msg_id')
    if u_chat and u_msg:
        try:
            bot.delete_message(u_chat, u_msg)
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
    if str(message.from_user.id) == str(ADMIN_ID):
        return   # Las fotos del admin se manejan en admin_foto
    bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
    bot.send_message(
        int(ADMIN_ID),
        f"💰 <b>COMPROBANTE RECIBIDO</b>\n"
        f"👤 @{message.from_user.username or 'sin_usuario'}\n"
        f"🆔 <code>{message.from_user.id}</code>",
        parse_mode="HTML"
    )
    bot.send_message(message.chat.id,
        "✅ Comprobante recibido. En breve verificamos tu pago.", protect_content=True)

# ═══════════════════════════════════════════════════════════════════
# 4. APROBACIÓN VIP /aprobar ID
# ═══════════════════════════════════════════════════════════════════
@bot.message_handler(commands=['aprobar'])
def aprobar(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        return
    try:
        user_id    = int(message.text.split()[1])
    except:
        bot.send_message(int(ADMIN_ID),
            "❌ Error. Usa: <code>/aprobar ID</code>", parse_mode="HTML")
        return

    vencimiento = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    db.upsert({'id': user_id, 'vence': vencimiento, 'username': ''}, Query().id == user_id)
    markup_link = types.InlineKeyboardMarkup()
    markup_link.add(types.InlineKeyboardButton("🔓 Ingresar al canal GoldPass", url=CANAL_INVITE_LINK_EXTERNO))

    try:
        bot.send_message(user_id,
            f"🎉 <b>¡ACCESO VIP APROBADO!</b>\n\n"
            f"Aquí tienes tu link GoldPass del canal, que lo disfrutes. 🥳\n\n"
            f"⏳ <i>Válido por 30 días. Al vencer, te enviaremos opciones para renovar.</i>",
            parse_mode="HTML", protect_content=True, reply_markup=markup_link)
        bot.send_message(int(ADMIN_ID),
            f"✅ Link VIP enviado a <code>{user_id}</code>.", parse_mode="HTML")
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
    if str(message.from_user.id) != str(ADMIN_ID):
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
    if str(message.from_user.id) != str(ADMIN_ID):
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
    if str(message.from_user.id) != str(ADMIN_ID):
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

    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 Bot activo por webhook en el puerto {port}.")
    app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)
