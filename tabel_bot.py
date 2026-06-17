import logging
import os
import ssl
from datetime import datetime, date
from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler, CallbackQueryHandler
)
from telegram.request import HTTPXRequest
from database import (
    init_db, xodimlar_royxati, xodim_qosh, xodim_olish,
    xodim_yangilash, xodim_ochirish, tabel_belgilash,
    bugungi_tabel, tabel_belgilanganmi, get_sozlama, set_sozlama,
    oylik_maosh_hisoblash, oylik_maosh_olish
)
from excel_tabel import oylik_tabel_excel

load_dotenv()
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Conversation states
(XODIM_ISM, XODIM_LAVOZIM, XODIM_MAOSH,
 TABEL_XODIM, TABEL_SMEN, TABEL_HOLAT, TABEL_KECHIKISH, TABEL_IZOH,
 MAOSH_OY, SOZLAMA_KALIT, SOZLAMA_QIYMAT) = range(11)


def admin_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("👥 Xodimlar"), KeyboardButton("📋 Tabel belgilash")],
        [KeyboardButton("📊 Bugungi holat"), KeyboardButton("💰 Maosh hisobi")],
        [KeyboardButton("📥 Excel hisobot"), KeyboardButton("⚙️ Sozlamalar")]
    ], resize_keyboard=True)


def holat_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Keldi", callback_data="holat_Keldi"),
         InlineKeyboardButton("❌ Kelmadi", callback_data="holat_Kelmadi")],
        [InlineKeyboardButton("🏥 Kasallik", callback_data="holat_Kasallik"),
         InlineKeyboardButton("🌴 Ta'til", callback_data="holat_Ta'til")],
    ])


def check_admin(user_id):
    return user_id == ADMIN_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not check_admin(user.id):
        await update.message.reply_text(
            "⛔ Sizda bu botdan foydalanish huquqi yo'q.\n"
            "Zavod administratori bilan bog'laning."
        )
        return

    await update.message.reply_text(
        f"👋 Salom, {user.first_name}!\n\n"
        f"🏭 Zavod Tabel va Maosh tizimiga xush kelibsiz!\n\n"
        f"Tugmalardan foydalaning:",
        reply_markup=admin_keyboard()
    )


# ===== XODIMLAR =====
async def xodimlar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id):
        return

    xodimlar = xodimlar_royxati()
    if not xodimlar:
        matn = "👥 Xodimlar ro'yxati bo'sh.\n\n/xodim_qosh — yangi xodim qo'shish"
    else:
        matn = f"👥 XODIMLAR RO'YXATI ({len(xodimlar)} ta)\n\n"
        for x in xodimlar:
            matn += f"#{x[0]} {x[1]} — {x[2]} ({x[3]:,} so'm/soat)\n"
        matn += "\n/xodim_qosh — yangi xodim\n/xodim_ochir — xodimni o'chirish"

    await update.message.reply_text(matn)


async def xodim_qoshish_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "👤 Yangi xodim qo'shish\n\nXodimning to'liq ismini kiriting (F.I.O):",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Bekor")]], resize_keyboard=True)
    )
    return XODIM_ISM


async def xodim_ism(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_keyboard())
        return ConversationHandler.END
    context.user_data['yangi_ism'] = update.message.text.strip()
    await update.message.reply_text("💼 Lavozimini kiriting (masalan: Tikuvchi, Operator, Mexanik):")
    return XODIM_LAVOZIM


async def xodim_lavozim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['yangi_lavozim'] = update.message.text.strip()
    default_maosh = get_sozlama('soatlik_maosh_default') or '15000'
    await update.message.reply_text(
        f"💰 Soatlik maoshini kiriting (so'mda)\n"
        f"Default: {int(default_maosh):,} so'm"
    )
    return XODIM_MAOSH


async def xodim_maosh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        maosh = int(update.message.text.strip().replace(' ', '').replace(',', ''))
        ism = context.user_data['yangi_ism']
        lavozim = context.user_data['yangi_lavozim']
        xid = xodim_qosh(ism, lavozim, maosh)
        await update.message.reply_text(
            f"✅ Xodim qo'shildi!\n\n"
            f"#{xid} {ism}\n"
            f"💼 {lavozim}\n"
            f"💰 {maosh:,} so'm/soat",
            reply_markup=admin_keyboard()
        )
    except ValueError:
        await update.message.reply_text("⚠️ Raqam kiriting!")
        return XODIM_MAOSH
    return ConversationHandler.END


# ===== TABEL BELGILASH =====
async def tabel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id):
        return

    xodimlar = xodimlar_royxati()
    if not xodimlar:
        await update.message.reply_text(
            "⚠️ Xodimlar ro'yxati bo'sh!\nAvval /xodim_qosh buyrug'i bilan xodim qo'shing."
        )
        return ConversationHandler.END

    # Inline tugmalar
    tugmalar = []
    for x in xodimlar:
        tugmalar.append([InlineKeyboardButton(
            f"{x[1]} ({x[2]})",
            callback_data=f"xodim_{x[0]}"
        )])
    tugmalar.append([InlineKeyboardButton("❌ Bekor", callback_data="bekor")])

    await update.message.reply_text(
        "📋 Tabel belgilash\n\nXodimni tanlang:",
        reply_markup=InlineKeyboardMarkup(tugmalar)
    )
    return TABEL_XODIM


async def tabel_xodim_tanlash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "bekor":
        await query.message.reply_text("Bekor qilindi.", reply_markup=admin_keyboard())
        return ConversationHandler.END

    xodim_id = int(query.data.split('_')[1])
    xodim = xodim_olish(xodim_id)
    context.user_data['tabel_xodim_id'] = xodim_id
    context.user_data['tabel_xodim_ism'] = xodim[1]

    await query.message.reply_text(
        f"👤 {xodim[1]}\n\nSmeni tanlang:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌅 1-smen (07:00-19:00)", callback_data="smen_1-smen")],
            [InlineKeyboardButton("🌙 2-smen (19:00-07:00)", callback_data="smen_2-smen")],
            [InlineKeyboardButton("❌ Bekor", callback_data="bekor")]
        ])
    )
    return TABEL_SMEN


async def tabel_smen_tanlash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "bekor":
        await query.message.reply_text("Bekor qilindi.", reply_markup=admin_keyboard())
        return ConversationHandler.END

    smen = query.data.split('_', 1)[1]
    context.user_data['tabel_smen'] = smen
    xodim_ism = context.user_data['tabel_xodim_ism']
    bugun = date.today().isoformat()

    # Mavjud holatni tekshirish
    mavjud = tabel_belgilanganmi(
        context.user_data['tabel_xodim_id'], bugun, smen
    )
    matn = f"👤 {xodim_ism} | {smen}\n📅 {bugun}"
    if mavjud:
        matn += f"\n⚠️ Hozirgi holat: {mavjud}"

    await query.message.reply_text(
        matn + "\n\nHolatni tanlang:",
        reply_markup=holat_keyboard()
    )
    return TABEL_HOLAT


async def tabel_holat_tanlash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    holat = query.data.split('_', 1)[1]
    context.user_data['tabel_holat'] = holat

    if holat == 'Keldi':
        await query.message.reply_text(
            "⏰ Kechikish bormi? (daqiqada)\nYo'q bo'lsa 0 kiriting:"
        )
        return TABEL_KECHIKISH
    else:
        await tabel_saqlash(query.message, context)
        return ConversationHandler.END


async def tabel_kechikish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        kechikish = int(update.message.text.strip())
        context.user_data['tabel_kechikish'] = kechikish
    except ValueError:
        await update.message.reply_text("⚠️ Raqam kiriting (0 yoki daqiqa soni):")
        return TABEL_KECHIKISH

    await tabel_saqlash(update.message, context)
    return ConversationHandler.END


async def tabel_saqlash(message, context):
    bugun = date.today().isoformat()
    holat = context.user_data.get('tabel_holat')
    kechikish = context.user_data.get('tabel_kechikish', 0)

    tabel_belgilash(
        xodim_id=context.user_data['tabel_xodim_id'],
        sana=bugun,
        smen=context.user_data['tabel_smen'],
        holat=holat,
        kechikish=kechikish,
        belgilagan=f"Master"
    )

    emoji = {'Keldi': '✅', 'Kelmadi': '❌', 'Kasallik': '🏥', "Ta'til": '🌴'}
    kech_matn = f"\n⏰ Kechikish: {kechikish} daqiqa" if kechikish > 0 else ""

    await message.reply_text(
        f"{emoji.get(holat, '📋')} Saqlandi!\n\n"
        f"👤 {context.user_data['tabel_xodim_ism']}\n"
        f"📅 {bugun} | {context.user_data['tabel_smen']}\n"
        f"📌 Holat: {holat}{kech_matn}",
        reply_markup=admin_keyboard()
    )
    context.user_data.clear()


# ===== BUGUNGI HOLAT =====
async def bugungi_holat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id):
        return

    bugun = date.today().isoformat()
    tabel = bugungi_tabel(bugun)
    xodimlar = xodimlar_royxati()

    belgilangan_ids = {t[1] for t in tabel}
    keldi = [t for t in tabel if t[4] == 'Keldi']
    kelmadi = [t for t in tabel if t[4] == 'Kelmadi']
    kasallik = [t for t in tabel if t[4] == 'Kasallik']
    tatil = [t for t in tabel if t[4] == "Ta'til"]

    matn = f"📊 BUGUNGI HOLAT — {bugun}\n"
    matn += f"{'='*30}\n"
    matn += f"✅ Keldi: {len(keldi)} ta\n"
    matn += f"❌ Kelmadi: {len(kelmadi)} ta\n"
    matn += f"🏥 Kasallik: {len(kasallik)} ta\n"
    matn += f"🌴 Ta'til: {len(tatil)} ta\n"

    # Belgilanmaganlar
    belgilanmagan = [x for x in xodimlar if x[0] not in belgilangan_ids]
    if belgilanmagan:
        matn += f"\n⚠️ Hali belgilanmagan ({len(belgilanmagan)} ta):\n"
        for x in belgilanmagan[:10]:
            matn += f"  • {x[1]}\n"
        if len(belgilanmagan) > 10:
            matn += f"  ... va yana {len(belgilanmagan)-10} ta\n"

    await update.message.reply_text(matn)


# ===== MAOSH HISOBI =====
async def maosh_hisobi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id):
        return

    oy = datetime.now().strftime('%Y-%m')
    oylik_maosh_hisoblash(oy)
    maoshlar = oylik_maosh_olish(oy)

    if not maoshlar:
        await update.message.reply_text("⚠️ Bu oy uchun tabel ma'lumotlari yo'q.")
        return

    matn = f"💰 MAOSH HISOBI — {oy}\n{'='*30}\n"
    jami = 0
    for m in maoshlar:
        matn += f"👤 {m[10]}\n"
        matn += f"   ⏱ {m[2]:.0f} soat | 💰 {m[7]:,} so'm\n"
        if m[5] > 0:
            matn += f"   ⏰ Kechikish: {m[5]} daqiqa\n"
        jami += m[7]

    matn += f"\n{'='*30}\n💵 JAMI: {jami:,} so'm"
    await update.message.reply_text(matn)


# ===== EXCEL HISOBOT =====
async def excel_hisobot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id):
        return

    oy = datetime.now().strftime('%Y-%m')
    await update.message.reply_text(f"⏳ {oy} uchun Excel hisobot tayyorlanmoqda...")

    try:
        fayl = oylik_tabel_excel(oy)
        with open(fayl, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=fayl,
                caption=f"📊 Tabel va Maosh hisoboti — {oy}"
            )
    except Exception as e:
        logger.error(f"Excel xato: {e}")
        await update.message.reply_text(f"❌ Xatolik: {e}")


# ===== SOZLAMALAR =====
async def sozlamalar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id):
        return

    soatlik = get_sozlama('soatlik_maosh_default')
    chegara = get_sozlama('kechikish_chegara')

    matn = (
        f"⚙️ SOZLAMALAR\n\n"
        f"💰 Default soatlik maosh: {int(soatlik or 0):,} so'm\n"
        f"⏰ Kechikish chegara: {chegara} daqiqa\n\n"
        f"/sozlama_maosh — maoshni o'zgartirish\n"
        f"/sozlama_kechikish — kechikish chegarasini o'zgartirish\n"
        f"/xodim_qosh — yangi xodim qo'shish\n"
        f"/xodim_royxat — xodimlar ro'yxati\n"
        f"/xodim_ochir — xodimni o'chirish"
    )
    await update.message.reply_text(matn)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Bekor qilindi.", reply_markup=admin_keyboard())
    context.user_data.clear()
    return ConversationHandler.END


def main():
    init_db()

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    request = HTTPXRequest(connection_pool_size=8)
    app = Application.builder().token(BOT_TOKEN).request(request).build()

    # Xodim qo'shish
    xodim_conv = ConversationHandler(
        entry_points=[CommandHandler("xodim_qosh", xodim_qoshish_start)],
        states={
            XODIM_ISM: [MessageHandler(filters.TEXT & ~filters.COMMAND, xodim_ism)],
            XODIM_LAVOZIM: [MessageHandler(filters.TEXT & ~filters.COMMAND, xodim_lavozim)],
            XODIM_MAOSH: [MessageHandler(filters.TEXT & ~filters.COMMAND, xodim_maosh)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Tabel belgilash
    tabel_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📋 Tabel belgilash$"), tabel_start)],
        states={
            TABEL_XODIM: [CallbackQueryHandler(tabel_xodim_tanlash)],
            TABEL_SMEN: [CallbackQueryHandler(tabel_smen_tanlash)],
            TABEL_HOLAT: [CallbackQueryHandler(tabel_holat_tanlash)],
            TABEL_KECHIKISH: [MessageHandler(filters.TEXT & ~filters.COMMAND, tabel_kechikish)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(xodim_conv)
    app.add_handler(tabel_conv)
    app.add_handler(CommandHandler("xodim_royxat", xodimlar_menu))
    app.add_handler(MessageHandler(filters.Regex("^👥 Xodimlar$"), xodimlar_menu))
    app.add_handler(MessageHandler(filters.Regex("^📊 Bugungi holat$"), bugungi_holat))
    app.add_handler(MessageHandler(filters.Regex("^💰 Maosh hisobi$"), maosh_hisobi))
    app.add_handler(MessageHandler(filters.Regex("^📥 Excel hisobot$"), excel_hisobot))
    app.add_handler(MessageHandler(filters.Regex("^⚙️ Sozlamalar$"), sozlamalar_menu))

    logger.info("Tabel bot ishga tushdi...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, stop_signals=None)


if __name__ == "__main__":
    main()
