import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp
import asyncio

BOT_TOKEN = '8660752780:AAFANZb8hGEmU6EMbKedriGhFR-snhKJHck'
ADMIN_IDS = [7093004518, 7762880539]  # ← الادمنز
CHANNEL_USERNAME = "ZERO_MAX_COOL"
CHANNEL_LINK = f"https://t.me/{CHANNEL_USERNAME}"

logging.basicConfig(level=logging.INFO)

user_modes = {}
active_users = set()
admin_states = {}

def main_keyboard(user_id):
    buttons = [
        [InlineKeyboardButton("🎧 أغنية / صوت", callback_data="mode_song")],
        [InlineKeyboardButton("🎬 فيديو", callback_data="mode_video")]
    ]
    if user_id in ADMIN_IDS:
        buttons.append([InlineKeyboardButton("👨‍💻 لوحة الأدمن", callback_data="admin_panel")])
    return InlineKeyboardMarkup(buttons)

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 إذاعة للكل", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📊 عدد المستخدمين", callback_data="admin_count")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
    ])

def join_channel_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 اشترك الآن", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ تحققت من الاشتراك", callback_data="check_subscription")]
    ])

async def check_subscription(user_id, context):
    try:
        member = await context.bot.get_chat_member(chat_id=f"@{CHANNEL_USERNAME}", user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    first_name = update.message.from_user.first_name
    active_users.add(user_id)

    if not await check_subscription(user_id, context) and user_id not in ADMIN_IDS:
        await update.message.reply_text(
            f'⚠️ **لاستخدام البوت يجب الاشتراك أولاً**\n\n'
            f'اضغط "اشترك الآن" ثم "تحققت من الاشتراك"',
            parse_mode='Markdown',
            reply_markup=join_channel_keyboard()
        )
        return

    await update.message.reply_text(
        f'✨ **أهلاً {first_name}** ✨\n'
        f'━━━━━━━━━━━━━━━━━━\n'
        f'🤖 **بوت التحميل والبحث**\n'
        f'✅ **اكتب اسم الأغنية/الفيديو أو ارسل رابط**\n\n'
        f'**اختار نوع التحميل:**',
        parse_mode='Markdown',
        reply_markup=main_keyboard(user_id)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    first_name = query.from_user.first_name
    await query.answer()

    if query.data == "check_subscription":
        if await check_subscription(user_id, context):
            await query.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="**اختار نوع التحميل:**",
                parse_mode='Markdown',
                reply_markup=main_keyboard(user_id)
            )
        else:
            await query.answer(text="❌ ما مشترك. اشترك أول", show_alert=True)
        return

    if query.data == "back_main":
        await query.edit_message_text(
            f'✨ **أهلاً {first_name}** ✨\n'
            f'━━━━━━━━━━━━━━━━━━\n'
            f'🤖 **بوت التحميل والبحث**\n\n'
            f'**اختار نوع التحميل:**',
            parse_mode='Markdown',
            reply_markup=main_keyboard(user_id)
        )
        return

    if query.data == "admin_panel":
        if user_id not in ADMIN_IDS: return
        await query.edit_message_text(
            f'👨‍💻 **لوحة تحكم المطور**\n━━━━━━━━━━━━━━━━━━\n\n'
            f'📢 الإذاعة توصل لكل اللي كلموا البوت قبل',
            reply_markup=admin_keyboard(),
            parse_mode='Markdown'
        )
        return

    if query.data == "admin_count":
        if user_id not in ADMIN_IDS: return
        await query.edit_message_text(
            f'📊 **عدد المستخدمين**\n━━━━━━━━━━━━━━━━━━\n\n'
            f'👥 **اللي كلموا البوت:** `{len(active_users)}`\n'
            f'🤖 **الحالة:** `شغال 100%`',
            parse_mode='Markdown',
            reply_markup=admin_keyboard()
        )
        return

    if query.data == "admin_broadcast":
        if user_id not in ADMIN_IDS: return
        admin_states[user_id] = 'waiting_broadcast'
        await query.edit_message_text(
            '📢 **ارسل رسالة الإذاعة**\n\n'
            'تقدر ترسل نص، صورة، فيديو، أو صوت\n'
            'اكتب /cancel للإلغاء',
            parse_mode='Markdown'
        )
        return

    if query.data == "mode_song":
        user_modes[user_id] = "song"
        await query.edit_message_text('🎧 **وضع الأغاني مفعل**\n\n📝 **اكتب اسم الأغنية:**', parse_mode='Markdown')
    elif query.data == "mode_video":
        user_modes[user_id] = "video"
        await query.edit_message_text('🎬 **وضع الفيديو مفعل**\n\n📝 **اكتب اسم الفيديو:**', parse_mode='Markdown')

def is_url(text):
    return text.startswith(('http://', 'https://', 'www.'))

async def download_media(url, msg, media_type):
    try:
        fmt = 'bestaudio[ext=m4a]/bestaudio/best' if media_type == 'song' else 'best[height<=720][ext=mp4]/best'
        opts = {
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'format': fmt,
            'outtmpl': f'{media_type}.%(ext)s',
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if os.path.exists(filename) and os.path.getsize(filename) > 10 * 1024:
                return filename, info.get('title', 'بدون عنوان')[:64]
    except Exception as e:
        await msg.edit_text(f'❌ **فشل التحميل**\n\n**السبب:** `{str(e)[:200]}`', parse_mode='Markdown')
        return None, None
    return None, None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip() if update.message.text else None
    active_users.add(user_id)

    # مهمة الاذاعة للادمن
    if user_id in ADMIN_IDS and admin_states.get(user_id) == 'waiting_broadcast':
        if text == '/cancel':
            admin_states.pop(user_id, None)
            await update.message.reply_text('❌ **تم إلغاء الإذاعة**', parse_mode='Markdown')
            return

        sent = 0
        failed = 0
        await update.message.reply_text('⏳ **جاري إرسال الإذاعة...**', parse_mode='Markdown')

        for uid in active_users.copy():
            try:
                if update.message.photo:
                    await context.bot.send_photo(chat_id=uid, photo=update.message.photo[-1].file_id, caption=update.message.caption)
                elif update.message.video:
                    await context.bot.send_video(chat_id=uid, video=update.message.video.file_id, caption=update.message.caption)
                elif update.message.audio:
                    await context.bot.send_audio(chat_id=uid, audio=update.message.audio.file_id, caption=update.message.caption)
                elif update.message.text:
                    await context.bot.send_message(chat_id=uid, text=f'📢 **إعلان من الإدارة:**\n\n{text}', parse_mode='Markdown')
                sent += 1
                await asyncio.sleep(0.05)
            except:
                failed += 1

        admin_states.pop(user_id, None)
        await update.message.reply_text(
            f'✅ **تم الإرسال**\n\n'
            f'📤 نجح: `{sent}`\n'
            f'❌ فشل: `{failed}`',
            parse_mode='Markdown'
        )
        return

    if not await check_subscription(user_id, context) and user_id not in ADMIN_IDS:
        await update.message.reply_text('⚠️ **اشترك أولاً**', reply_markup=join_channel_keyboard())
        return

    if user_id not in user_modes:
        await update.message.reply_text('⚠️ **اختار نوع التحميل أول من /start**', reply_markup=main_keyboard(user_id))
        return

    media_type = user_modes[user_id]
    msg = await update.message.reply_text('⏳ **جاري التحضير...**', parse_mode='Markdown')
    
    if is_url(text):
        filename, title = await download_media(text, msg, media_type)
    else:
        await msg.edit_text('❌ **حالياً يدعم الروابط فقط**\nارسل رابط يوتيوب/تيك توك', parse_mode='Markdown')
        return

    if not filename or not os.path.exists(filename):
        return

    await msg.edit_text('📤 **جاري الرفع...**', parse_mode='Markdown')
    file_size = os.path.getsize(filename)

    if file_size > 52428800:
        os.remove(filename)
        await msg.edit_text('❌ **الملف اكبر من 50MB**', parse_mode='Markdown')
        return

    with open(filename, 'rb') as file:
        if media_type == "song":
            await context.bot.send_audio(chat_id=update.message.chat_id, audio=file, caption=f"🎧 **{title}**", parse_mode='Markdown')
        else:
            await context.bot.send_video(chat_id=update.message.chat_id, video=file, caption=f"🎬 **{title}**", parse_mode='Markdown')

    os.remove(filename)
    await msg.delete()

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    print("✅ البوت شغال...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
