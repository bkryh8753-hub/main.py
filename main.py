import os
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.error import BadRequest

BOT_TOKEN = '8784250340:AAHHoe50PbsbqlNaFhpI4nFQFhImxxwHnhI'
OWNER_ID = 7093004518 # ايديك انت - المطور الاساسي
BOT_USERNAME = "GHClone5Bot" # خليه زي ما هو او غيره

app = Flask(__name__)

# نخزن اعدادات كل قروب هنا
groups = {} # {chat_id: {"channel": "@xxx", "admins": [id1, id2], "users": set()}}

@app.route('/')
def home():
    return f"@{BOT_USERNAME} by Owner"

def get_group(chat_id):
    if chat_id not in groups:
        groups[chat_id] = {"channel": None, "admins": [], "users": set()}
    return groups[chat_id]

async def is_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id == OWNER_ID:
        return True
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
        return member.status in ['administrator', 'creator']
    except:
        return False

async def is_subscribed(user_id, channel, context):
    if not channel:
        return True
    try:
        member = await context.bot.get_chat_member(channel, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

def sub_keyboard(channel):
    btn = [[InlineKeyboardButton("اشترك بالقناة 🔔", url=f"https://t.me/{channel[1:]}")],
           [InlineKeyboardButton("تحققت ✅", callback_data="check_sub")]]
    return InlineKeyboardMarkup(btn)

def admin_panel():
    btn = [
        [InlineKeyboardButton("📢 اذاعة", callback_data="broadcast"),
         InlineKeyboardButton("👥 الاحصائيات", callback_data="stats")],
        [InlineKeyboardButton("⚙️ ضبط القناة", callback_data="setchannel"),
         InlineKeyboardButton("➕ اضافة ادمن", callback_data="addadmin")],
        [InlineKeyboardButton("👑 حقوق المطور", url="https://t.me/ZERO_MAX_COOL")]
    ]
    return InlineKeyboardMarkup(btn)

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text(
            f"👋 اهلا\n\nضيفني قروبك واعطيني ادمن عشان اشتغل\n\n👑 المطور: @ZERO_MAX_COOL"
        )
        return

    g = get_group(chat.id)
    g["users"].add(update.effective_user.id)

    # لازم البوت يكون ادمن
    bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
    if bot_member.status not in ['administrator', 'creator']:
        await update.message.reply_text("⚠️ لازم ترفعني ادمن اول عشان اشتغل")
        return

    if await is_group_admin(update, context):
        await update.message.reply_text("🔰 لوحة تحكم القروب:", reply_markup=admin_panel())
    else:
        if g["channel"] and not await is_subscribed(update.effective_user.id, g["channel"], context):
            await update.message.reply_text(
                f"⚠️ لازم تشترك بـ {g['channel']} اول",
                reply_markup=sub_keyboard(g["channel"])
            )
        else:
            await update.message.reply_text("✅ البوت شغال")

# /admin
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_group_admin(update, context):
        return
    await update.message.reply_text("🔰 لوحة التحكم:", reply_markup=admin_panel())

# /setchannel @channel
async def setchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_group_admin(update, context):
        return
    if not context.args:
        await update.message.reply_text("استخدم: /setchannel @يوزر_القناة")
        return

    channel = context.args[0]
    if not channel.startswith('@'):
        await update.message.reply_text("❌ لازم يبدأ بـ @")
        return

    g = get_group(update.effective_chat.id)
    g["channel"] = channel
    await update.message.reply_text(f"✅ تم ضبط قناة الاشتراك: {channel}\n\nلازم اكون ادمن فيها عشان اقدر اتحقق")

# /addadmin
async def addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_group_admin(update, context):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ اعمل رد على الشخص اللي تبغى تضيفه ادمن")
        return

    new_admin = update.message.reply_to_message.from_user.id
    g = get_group(update.effective_chat.id)
    if new_admin not in g["admins"]:
        g["admins"].append(new_admin)
    await update.message.reply_text(f"✅ تم اضافة {update.message.reply_to_message.from_user.first_name} كادمن")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    g = get_group(chat_id)

    if query.data == "check_sub":
        if await is_subscribed(user_id, g["channel"], context):
            await query.edit_message_text("✅ تم التحقق")
        else:
            await query.answer("❌ ما اشتركت", show_alert=True)
        return

    if not await is_group_admin(update, context):
        return

    if query.data == "stats":
        await query.edit_message_text(
            f"📊 احصائيات القروب:\n\n👥 المستخدمين: {len(g['users'])}\n📢 القناة: {g['channel'] or 'ما متحددة'}\n👑 المطور: @ZERO_MAX_COOL",
            reply_markup=admin_panel()
        )

    elif query.data == "broadcast":
        context.user_data['broadcast'] = chat_id
        await query.edit_message_text("📢 ارسل الرسالة الحين للاذاعة:\n/cancel للالغاء")

    elif query.data == "setchannel":
        await query.edit_message_text("⚙️ ارسل: /setchannel @يوزر_القناة", reply_markup=admin_panel())

    elif query.data == "addadmin":
        await query.edit_message_text("➕ اعمل رد على الشخص واكتب /addadmin", reply_markup=admin_panel())

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    g = get_group(chat_id)
    g["users"].add(user_id)

    # وضع الاذاعة
    if context.user_data.get('broadcast') == chat_id and await is_group_admin(update, context):
        context.user_data.pop('broadcast')
        sent = 0
        for uid in g["users"].copy():
            try:
                await context.bot.copy_message(uid, chat_id, update.message.message_id)
                sent += 1
            except:
                g["users"].discard(uid)
        await update.message.reply_text(f"✅ تم الارسال لـ {sent}", reply_markup=admin_panel())
        return

    # تحقق الاشتراك للاعضاء
    if not await is_group_admin(update, context):
        if g["channel"] and not await is_subscribed(user_id, g["channel"], context):
            await update.message.reply_text(
                f"⚠️ اشترك بـ {g['channel']} اول",
                reply_markup=sub_keyboard(g["channel"])
            )
            await update.message.delete()
            return

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop('broadcast', None)
    await update.message.reply_text("تم الالغاء", reply_markup=admin_panel())

def run_bot():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_cmd))
    application.add_handler(CommandHandler("setchannel", setchannel))
    application.add_handler(CommandHandler("addadmin", addadmin))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_msg))
    application.run_polling()

if __name__ == '__main__':
    threading.Thread(target=run_bot).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
