import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp

BOT_TOKEN = '8660752780:AAFANZb8hGEmU6EMbKedriGhFR-snhKJHck'
ADMIN_IDS = [7093004518, 7762880539]
CHANNEL_USERNAME = "ZERO_MAX_COOL"
CHANNEL_LINK = f"https://t.me/{CHANNEL_USERNAME}"

logging.basicConfig(level=logging.INFO)

user_modes = {}
active_users = set()
admin_states = {}
user_links = {}

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

def quality_keyboard(formats):
    seen = set()
    buttons = []
    for f in sorted(formats, key=lambda x: x.get('height', 0), reverse=True):
        height = f.get('height')
        if not height or height in seen: continue
        seen.add(height)
        size_mb = f.get('filesize') or f.get('filesize_approx')
        size_text = f" ~{size_mb/1024/1024:.0f}MB" if size_mb else ""
        buttons.append([InlineKeyboardButton(f"📺 {height}p{size_text}", callback_data=f"dl_{height}")])
    buttons.append([InlineKeyboardButton("❌ إلغاء", callback_data="cancel_dl")])
    return InlineKeyboardMarkup(buttons)

async def check_subscription(user_id, context):
    try:
        member = await context.bot.get_chat_member(chat_id=f"@{CHANNEL_USERNAME}", user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

def is_url(text):
    return text.startswith(('http://', 'https://', 'www.'))

async def get_video_formats(url):
    try:
        opts = {'quiet': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = [f for f in info.get('formats', []) if f.get('vcodec')!= 'none' and f.get('ext') == 'mp4']
            return formats, info.get('title', 'بدون عنوان')[:64]
    except:
        return [], None

async def download_media(url, msg, media_type, quality=None):
    try:
        if media_type == 'song':
            fmt = 'bestaudio[ext=m4a]/bestaudio/best'
        else:
            fmt = f'best[height<={quality}][ext=mp4]/best' if quality else 'best[height<=720][ext=mp4]/best'
        
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
            if os.path.exists(filename) and os.path.getsize(filename) > 10240:
                return filename, info.get('title', 'بدون عنوان')[:64]
    except Exception as e:
        await msg.edit_text(f'❌ **فشل التحميل**\n\n`{str(e)[:200]}`', parse_mode='Markdown')
        return None, None
    return None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    first_name = update.message.from_user.first_name
    active_users.add(user_id)

    if not await check_subscription(user_id, context) and user_id not in ADMIN_IDS:
        await update.message.reply_text(
            f'⚠️ **لاستخدام البوت يجب الاشتراك أولاً**',
            parse_mode='Markdown',
            reply_markup=join_channel_keyboard()
        )
        return

    await update.message.reply_text(
        f'✨ **أهلاً {first_name}** ✨\n'
        f'🤖 **بوت التحميل**\n\n'
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
            await context.bot.send_message(chat_id=user_id, text="**اختار نوع التحميل:**", parse_mode='Markdown', reply_markup=main_keyboard(user_id))
        else:
            await query.answer(text="❌ ما مشترك", show_alert=True)
        return

    if query.data == "back_main":
        await query.edit_message_text('**اختار نوع التحميل:**', parse_mode='Markdown', reply_markup=main_keyboard(user_id))
        return

    if query.data == "admin_panel":
        if user_id not in ADMIN_IDS: return
        await query.edit_message_text('👨‍💻 **لوحة تحكم المطور**', reply_markup=admin_keyboard(), parse_mode='Markdown')
        return

    if query.data == "admin_count":
        if user_id not in ADMIN_IDS: return
        await query.edit_message_text(
            f'📊 **عدد المستخدمين**\n\n👥 **اللي كلموا البوت:** `{len(active_users)}`',
            parse_mode='Markdown',
            reply_markup=admin_keyboard()
        )
        return

    if query.data == "admin_broadcast":
        if user_id not in ADMIN_IDS: return
        admin_states[user_id] = 'waiting_broadcast'
        await query.edit_message_text('📢 **ارسل رسالة الإذاعة**\n\nاكتب /cancel للإلغاء', parse_mode='Markdown')
        return

    if query.data == "cancel_dl":
        user_links.pop(user_id, None)
        await query.edit_message_text('❌ **تم الإلغاء**', parse_mode='Markdown')
        return

    if query.data.startswith("dl_"):
        quality = int(query.data.split("_")[1])
        link = user_links.get(user_id)
        if not link:
            await query.edit_message_text('❌ **انتهت صلاحية الرابط**', parse_mode='Markdown')
            return

        msg = await query.edit_message_text('⏳ **جاري التحميل...**', parse_mode='Markdown')
        filename, title = await download_media(link, msg, 'video', quality)
        user_links.pop(user_id, None)

        if not filename:
            return

        await msg.edit_text('📤 **جاري الرفع...**', parse_mode='Markdown')
        with open(filename, 'rb') as file:
            await context.bot.send_video(chat_id=query.message.chat_id, video=file, caption=f"🎬 **{title}**\n📺 `{quality}p`", parse_mode='Markdown')
        os.remove(filename)
        await msg.delete()
        return

    if query.data == "mode_song":
        user_modes[user_id] = "song"
        await query.edit_message_text('🎧 **وضع الأغاني مفعل**\n\n📝 **ارسل رابط يوتيوب:**', parse_mode='Markdown')
    elif query.data == "mode_video":
        user_modes[user_id] = "video"
        await query.edit_message_text('🎬 **وضع الفيديو مفعل**\n\n📝 **ارسل رابط يوتيوب:**', parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip() if update.message.text else None
    active_users.add(user_id)

    if user_id in ADMIN_IDS and admin_states.get(user_id) == 'waiting_broadcast':
        if text == '/cancel':
            admin_states.pop(user_id, None)
            await update.message.reply_text('❌ **تم إلغاء الإذاعة**')
            return

        sent = failed = 0
        await update.message.reply_text('⏳ **جاري إرسال الإذاعة...**')
        for uid in active_users.copy():
            try:
                if update.message.photo:
                    await context.bot.send_photo(uid, update.message.photo[-1].file_id, caption=update.message.caption)
                elif update.message.video:
                    await context.bot.send_video(uid, update.message.video.file_id, caption=update.message.caption)
                elif update.message.text:
                    await context.bot.send_message(uid, f'📢 **إعلان:**\n\n{text}', parse_mode='Markdown')
                sent += 1
                await asyncio.sleep(0.05)
            except:
                failed += 1
        admin_states.pop(user_id, None)
        await update.message.reply_text(f'✅ **تم**\n📤 نجح: `{sent}`\n❌ فشل: `{failed}`', parse_mode='Markdown')
        return

    if not await check_subscription(user_id, context) and user_id not in ADMIN_IDS:
        await update.message.reply_text('⚠️ **اشترك أولاً**', reply_markup=join_channel_keyboard())
        return

    if user_id not in user_modes:
        await update.message.reply_text('⚠️ **اختار نوع التحميل من /start**', reply_markup=main_keyboard(user_id))
        return

    media_type = user_modes[user_id]
    msg = await update.message.reply_text('⏳ **جاري التحضير...**', parse_mode='Markdown')
    
    if not is_url(text):
        await msg.edit_text('❌ **ارسل رابط صحيح**', parse_mode='Markdown')
        return

    if media_type == "video":
        formats, title = await get_video_formats(text)
        if not formats:
            await msg.edit_text('❌ **ما قدرت أجيب الجودات**', parse_mode='Markdown')
            return
        user_links[user_id] = text
        await msg.edit_text(f'🎬 **{title}**\n\n**اختار الجودة:**', parse_mode='Markdown', reply_markup=quality_keyboard(formats))
        return
    else:
        filename, title = await download_media(text, msg, 'song')

    if not filename:
        return

    await msg.edit_text('📤 **جاري الرفع...**', parse_mode='Markdown')
    with open(filename, 'rb') as file:
        await context.bot.send_audio(chat_id=update.message.chat_id, audio=file, caption=f"🎧 **{title}**", parse_mode='Markdown')
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
