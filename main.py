import os
import asyncio
import requests
import nest_asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

nest_asyncio.apply()

BOT_TOKEN = '8660752780:AAFANZb8hGEmU6EMbKedriGhFR-snhKJHck'
ADMIN_ID = 7093004518
CHANNEL_USERNAME = "ZERO_MAX_COOL"
CHANNEL_LINK = f"https://t.me/{CHANNEL_USERNAME}"

user_modes = {}
active_users = set()
user_links = {}
search_results = {}
search_pages = {}
user_info = {}
admin_states = {}

def main_keyboard(user_id):
    buttons = [
        [InlineKeyboardButton("🎧 أغنية / صوت", callback_data="mode_song")],
        [InlineKeyboardButton("🎬 فيديو", callback_data="mode_video")]
    ]
    if user_id == ADMIN_ID:
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

def search_results_keyboard(results, prefix, page=0, per_page=20):
    buttons = []
    start = page * per_page
    end = start + per_page
    page_results = results[start:end]

    for i, item in enumerate(page_results, start=start):
        title = item.get('title', 'بدون عنوان')[:35]
        duration = item.get('duration_string', '')
        view_count = item.get('view_count')

        extra = []
        if duration:
            extra.append(duration)
        if view_count:
            views = int(view_count)
            if views >= 1000000:
                extra.append(f"{views/1000000:.1f}M")
            elif views >= 1000:
                extra.append(f"{views/1000:.0f}K")

        extra_text = f" [{' | '.join(extra)}]" if extra else ""
        btn_text = f"{i+1}. {title}{extra_text}"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"{prefix}_{i}")])

    nav_buttons = []
    if end < len(results):
        nav_buttons.append(InlineKeyboardButton("➡️ عرض المزيد", callback_data=f"more_{prefix}"))
    if page > 0:
        nav_buttons.insert(0, InlineKeyboardButton("⬅️ السابق", callback_data=f"prev_{prefix}"))

    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton("❌ إلغاء", callback_data="cancel_search")])
    return InlineKeyboardMarkup(buttons)

def quality_keyboard(formats):
    seen = set()
    buttons = []
    for f in sorted(formats, key=lambda x: x.get('height', 0), reverse=True):
        height = f.get('height')
        if not height or height in seen:
            continue
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

async def search_youtube(query, max_results=100):
    try:
        import yt_dlp
        opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'default_search': 'ytsearch',
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            return info.get('entries', [])
    except Exception as e:
        print(f"خطأ البحث: {e}")
        return []

async def get_video_formats(url):
    try:
        import yt_dlp
        opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = [f for f in info.get('formats', []) if f.get('vcodec')!= 'none' and f.get('ext') == 'mp4']
            return formats, info.get('title', 'بدون عنوان')[:64]
    except Exception as e:
        print(f"خطأ جلب الجودات: {e}")
        return [], None

async def get_thumbnail(url):
    try:
        import yt_dlp
        opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            thumb_url = info.get('thumbnail')
            if thumb_url:
                r = requests.get(thumb_url, timeout=10)
                if r.status_code == 200:
                    thumb_path = "thumb.jpg"
                    with open(thumb_path, 'wb') as f:
                        f.write(r.content)
                    return thumb_path
    except:
        pass
    return None

async def download_media(url, msg, media_type, quality=None):
    cobalt_apis = [
        "https://api.cobalt.tools/api/json",
        "https://co.wuk.sh/api/json",
        "https://cobalt-api.kwiatekmiki.com/api/json"
    ]

    for api_url in cobalt_apis:
        if quality or media_type == 'song':
            try:
                payload = {
                    "url": url,
                    "audioOnly": media_type == 'song',
                    "vCodec": "h264",
                    "vQuality": str(quality) if quality else "720"
                }
                r = requests.post(api_url, json=payload, timeout=60)
                data = r.json()
                if data.get('status') in ['stream', 'redirect', 'tunnel']:
                    file_url = data['url']
                    ext = 'm4a' if media_type == 'song' else 'mp4'
                    filename = f"{media_type}.{ext}"
                    quality_text = f" بجودة {quality}p" if quality else ""
                    await msg.edit_text(f'⏳ **جاري تحميل الملف{quality_text}...**', parse_mode='Markdown')
                    with requests.get(file_url, stream=True, timeout=180) as r:
                        r.raise_for_status()
                        with open(filename, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                    if os.path.exists(filename) and os.path.getsize(filename) > 10 * 1024:
                        return filename, "تم التحميل"
            except Exception as e:
                print(f"فشل Cobalt {api_url}: {e}")
                continue

    try:
        import yt_dlp
        if media_type == 'song':
            fmt = 'bestaudio[ext=m4a]/bestaudio/best'
        else:
            fmt = f'best[height<={quality}][ext=mp4]/best[height<={quality}]/best' if quality else 'best[height<=720][ext=mp4]/best'

        opts = {
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'format': fmt,
            'outtmpl': f'{media_type}.%(ext)s',
            'socket_timeout': 30,
            'retries': 10,
            'extractor_args': {'youtube': {'player_client': ['android', 'android_embedded', 'web']}},
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8',
                'Sec-Ch-Ua': '"Chromium";v="118", "Google Chrome";v="118"',
                'Sec-Ch-Ua-Platform': '"Windows"',
                'Referer': 'https://www.youtube.com/'
            },
        }
        if os.path.exists('cookies.txt'):
            opts['cookiefile'] = 'cookies.txt'

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if os.path.exists(filename) and os.path.getsize(filename) > 10 * 1024:
                title = info.get('title', 'بدون عنوان')[:64]
                return filename, title
    except Exception as e:
        error_msg = str(e)
        print(f"فشل yt-dlp: {error_msg}")
        if "Sign in to confirm" in error_msg or "bot" in error_msg.lower():
            await msg.edit_text(f'❌ **يوتيوب حاظر السيرفر حالياً**\n\nجرب تيك توك/انستا أو ارفع cookies.txt', parse_mode='Markdown')
        else:
            await msg.edit_text(f'❌ **فشل التحميل**\n\n**السبب:** `{error_msg[:200]}`', parse_mode='Markdown')
        return None, None

    await msg.edit_text(f'❌ **فشل التحميل من كل المصادر**', parse_mode='Markdown')
    return None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    first_name = update.message.from_user.first_name
    username = update.message.from_user.username
    user_info[user_id] = {'name': first_name, 'username': username}
    active_users.add(user_id)

    if not await check_subscription(user_id, context) and user_id!= ADMIN_ID:
        await update.message.reply_text(
            f'⚠️ **لاستخدام البوت يجب الاشتراك أولاً**\n\n'
            f'اضغط "اشترك الآن" ثم "تحققت من الاشتراك"',
            parse_mode='Markdown',
            reply_markup=join_channel_keyboard()
        )
        return

    user_modes.pop(user_id, None)
    user_links.pop(user_id, None)
    search_results.pop(user_id, None)
    search_pages.pop(user_id, None)
    await update.message.reply_text(
        f'✨ **أهلاً {first_name}** ✨\n'
        f'━━━━━━━━━━━━━━━━━━\n'
        f'🤖 **بوت التحميل والبحث**\n'
        f'✅ **اكتب اسم الأغنية/الفيديو أو ارسل رابط**\n'
        f'✅ **يوتيوب + تيك توك + فيسبوك + انستغرام**\n\n'
        f'**اختار نوع التحميل:**',
        parse_mode='Markdown',
        reply_markup=main_keyboard(user_id)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    first_name = query.from_user.first_name
    username = query.from_user.username
    user_info[user_id] = {'name': first_name, 'username': username}
    active_users.add(user_id)

    # أهم تعديل: نعمل answer مرة واحدة بس لكل زر
    if query.data == "check_subscription":
        if await check_subscription(user_id, context):
            await query.answer(text="منور/ة بوت التحميل 💫", show_alert=False, cache_time=1)
            await query.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="**اختار نوع التحميل:**",
                parse_mode='Markdown',
                reply_markup=main_keyboard(user_id)
            )
        else:
            await query.answer(text="❌ ما مشترك. اشترك أول", show_alert=True, cache_time=1)
        return

    # لباقي الأزرار
    await query.answer()

    if not await check_subscription(user_id, context) and user_id!= ADMIN_ID:
        await query.edit_message_text(
            f'⚠️ **لاستخدام البوت يجب الاشتراك أولاً**\n\n'
            f'اضغط "اشترك الآن" ثم "تحققت من الاشتراك"',
            parse_mode='Markdown',
            reply_markup=join_channel_keyboard()
        )
        return

    if query.data == "back_main":
        await query.edit_message_text(
            f'✨ **أهلاً {first_name}** ✨\n'
            f'━━━━━━━━━━━━━━━━━━\n'
            f'🤖 **بوت التحميل والبحث**\n'
            f'✅ **اكتب اسم الأغنية/الفيديو أو ارسل رابط**\n'
            f'✅ **يوتيوب + تيك توك + فيسبوك + انستغرام**\n\n'
            f'**اختار نوع التحميل:**',
            parse_mode='Markdown',
            reply_markup=main_keyboard(user_id)
        )
        return

    if query.data == "admin_panel":
        if user_id!= ADMIN_ID: return
        await query.edit_message_text(
            f'👨‍💻 **لوحة تحكم المطور**\n━━━━━━━━━━━━━━━━━━\n\n'
            f'📢 الإذاعة توصل لكل اللي كلموا البوت قبل',
            reply_markup=admin_keyboard(),
            parse_mode='Markdown'
        )
        return

    if query.data == "cancel_dl" or query.data == "cancel_search":
        user_links.pop(user_id, None)
        search_results.pop(user_id, None)
        search_pages.pop(user_id, None)
        await query.edit_message_text('❌ **تم الإلغاء**', parse_mode='Markdown')
        return

    if query.data.startswith("more_") or query.data.startswith("prev_"):
        prefix = query.data.split("_")[1]
        page_data = search_pages.get(user_id, {'page': 0, 'prefix': prefix})

        if query.data.startswith("more_"):
            page_data['page'] += 1
        else:
            page_data['page'] = max(0, page_data['page'] - 1)

        search_pages[user_id] = page_data
        results = search_results.get(user_id, [])
        await query.edit_message_text(
            f'✅ **لقيت {len(results)} نتائج**\n\n**اختار من القائمة:**\nصفحة {page_data["page"] + 1}/{(len(results)-1)//20 + 1}',
            parse_mode='Markdown',
            reply_markup=search_results_keyboard(results, prefix, page_data['page'])
        )
        return

    if query.data.startswith("song_"):
        idx = int(query.data.split("_")[1])
        results = search_results.get(user_id, [])
        if idx >= len(results):
            await query.edit_message_text('❌ **انتهت صلاحية البحث**', parse_mode='Markdown')
            return

        video_url = results[idx]['url']
        video_title = results[idx]['title']
        msg = await query.edit_message_text('⏳ **جاري تحضير الأغنية...**', parse_mode='Markdown')

        thumb_path = await get_thumbnail(video_url)
        filename, title = await download_media(video_url, msg, 'song')
        search_results.pop(user_id, None)
        search_pages.pop(user_id, None)

        if not filename or not os.path.exists(filename):
            if thumb_path and os.path.exists(thumb_path):
                os.remove(thumb_path)
            return

        await msg.edit_text(f'📤 **جاري الرفع...**', parse_mode='Markdown')
        file_size = os.path.getsize(filename)

        if file_size > 52428800 or file_size < 10240:
            os.remove(filename)
            if thumb_path and os.path.exists(thumb_path):
                os.remove(thumb_path)
            await msg.edit_text(f'❌ **حجم الملف غير صالح**\n\nالحجم: {file_size/1024/1024:.2f} MB', parse_mode='Markdown')
            return

        with open(filename, 'rb') as file:
            caption = f"🎧 **{title}**"
            if thumb_path and os.path.exists(thumb_path):
                with open(thumb_path, 'rb') as thumb:
                    await context.bot.send_audio(
                        chat_id=query.message.chat_id,
                        audio=file,
                        caption=caption,
                        parse_mode='Markdown',
                        thumbnail=thumb,
                        title=title,
                        performer=video_title.split(' - ')[0] if ' - ' in video_title else 'Unknown'
                    )
                os.remove(thumb_path)
            else:
                await context.bot.send_audio(chat_id=query.message.chat_id, audio=file, caption=caption, parse_mode='Markdown')

        os.remove(filename)
        await msg.delete()
        return

    if query.data.startswith("vid_"):
        idx = int(query.data.split("_")[1])
        results = search_results.get(user_id, [])
        if idx >= len(results):
            await query.edit_message_text('❌ **انتهت صلاحية البحث**', parse_mode='Markdown')
            return

        video_url = results[idx]['url']
        video_title = results[idx]['title']
        user_links[user_id] = video_url

        msg = await query.edit_message_text('🔍 **جاري جلب الجودات المتاحة...**', parse_mode='Markdown')
        formats, _ = await get_video_formats(video_url)

        if not formats:
            await msg.edit_text('❌ **ما قدرت أجيب جودات الفيديو**', parse_mode='Markdown')
            user_links.pop(user_id, None)
            return

        await msg.edit_text(
            f'🎬 **{video_title[:50]}**\n\n**اختار الجودة:**',
            parse_mode='Markdown',
            reply_markup=quality_keyboard(formats)
        )
        return

    if query.data.startswith("dl_"):
        quality = int(query.data.split("_")[1])
        link = user_links.get(user_id)
        if not link:
            await query.edit_message_text('❌ **انتهت صلاحية الرابط، ابحث مرة ثانية**', parse_mode='Markdown')
            return

        msg = await query.edit_message_text('⏳ **جاري التحضير...**', parse_mode='Markdown')
        filename, title = await download_media(link, msg, 'video', quality)
        user_links.pop(user_id, None)
        search_results.pop(user_id, None)
        search_pages.pop(user_id, None)

        if not filename or not os.path.exists(filename):
            return

        await msg.edit_text(f'📤 **جاري الرفع...**', parse_mode='Markdown')
        file_size = os.path.getsize(filename)

        if file_size > 52428800 or file_size < 10240:
            os.remove(filename)
            await msg.edit_text(f'❌ **حجم الملف غير صالح**\n\nالحجم: {file_size/1024/1024:.2f} MB', parse_mode='Markdown')
            return

        with open(filename, 'rb') as file:
            caption = f"🎬 **{title}**\n📺 الجودة: `{quality}p`"
            await context.bot.send_video(chat_id=query.message.chat_id, video=file, caption=caption, parse_mode='Markdown', supports_streaming=True)

        os.remove(filename)
        await msg.delete()
        return

    if query.data.startswith("admin_"):
        if user_id!= ADMIN_ID: return

        if query.data == "admin_broadcast":
            admin_states[user_id] = 'waiting_broadcast'
            await query.edit_message_text(
                '📢 **ارسل رسالة الإذاعة**\n\n'
                'تقدر ترسل نص، صورة، فيديو، أو صوت\n'
                'اكتب /cancel للإلغاء',
                parse_mode='Markdown'
            )
        elif query.data == "admin_count":
            await query.edit_message_text(
                f'📊 **عدد المستخدمين**\n━━━━━━━━━━━━━━━━━━\n\n'
                f'👥 **اللي كلموا البوت:** `{len(active_users)}`\n'
                f'🤖 **الحالة:** `شغال 100%`',
                parse_mode='Markdown',
                reply_markup=admin_keyboard()
            )
        return

    if query.data == "mode_song":
        user_modes[user_id] = "song"
        await query.edit_message_text(
            '🎧 **وضع الأغاني مفعل**\n━━━━━━━━━━━━━━━━━━\n\n📝 **اكتب اسم الفنان أو الأغنية:**\n\nمثال: `عمرو دياب` أو `تملي معاك`',
            parse_mode='Markdown'
        )
    elif query.data == "mode_video":
        user_modes[user_id] = "video"
        await query.edit_message_text(
            '🎬 **وضع الفيديو مفعل**\n━━━━━━━━━━━━━━━━━━\n\n📝 **اكتب اسم الفيديو:**\n\nمثال: `توم وجيري حلقة 1`',
            parse_mode='Markdown'
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip() if update.message.text else None
    username = update.message.from_user.username
    user_info[user_id] = {'name': update.message.from_user.first_name, 'username': username}
    active_users.add(user_id)

    if not await check_subscription(user_id, context) and user_id!= ADMIN_ID:
        await update.message.reply_text(
            f'⚠️ **لاستخدام البوت يجب الاشتراك أولاً**\n\n'
            f'اضغط "اشترك الآن" ثم "تحققت من الاشتراك"',
            parse_mode='Markdown',
            reply_markup=join_channel_keyboard()
        )
        return

    if user_id == ADMIN_ID and admin_states.get(user_id) == 'waiting_broadcast':
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

    if user_id not in user_modes:
        await update.message.reply_text(
            '⚠️ **اختار نوع التحميل أول من تحت /start**',
            parse_mode='Markdown',
            reply_markup=main_keyboard(user_id)
        )
        return

    media_type = user_modes[user_id]

    if is_url(text):
        if media_type == "video":
            msg = await update.message.reply_text('🔍 **جاري جلب الجودات المتاحة...**', parse_mode='Markdown')
            formats, title = await get_video_formats(text)
            if not formats:
                await msg.edit_text('❌ **ما قدرت أجيب جودات الفيديو**', parse_mode='Markdown')
                return
            user_links[user_id] = text
            await msg.edit_text(
                f'🎬 **{title}**\n\n**اختار الجودة:**',
                parse_mode='Markdown',
                reply_markup=quality_keyboard(formats)
            )
            return
        else:
            msg = await update.message.reply_text('⏳ **جاري التحضير...**', parse_mode='Markdown')
            filename, title = await download_media(text, msg, 'song')
    else:
        msg = await update.message.reply_text(f'🔍 **جاري البحث عن:** `{text}`', parse_mode='Markdown')
        results = await search_youtube(text, 100)

        if not results:
            await msg.edit_text('❌ **ما لقيت نتائج**\n\nجرب كلمات ثانية', parse_mode='Markdown')
            return

        search_results[user_id] = results
        search_pages[user_id] = {'page': 0, 'prefix': "song" if media_type == "song" else "vid"}
        prefix = "song" if media_type == "song" else "vid"
        await msg.edit_text(
            f'✅ **لقيت {len(results)} نتائج**\n\n**اختار من القائمة:**\nصفحة 1/{(len(results)-1)//20 + 1}',
            parse_mode='Markdown',
            reply_markup=search_results_keyboard(results, prefix, 0)
        )
        return

    if not filename or not os.path.exists(filename):
        return

    await msg.edit_text(f'📤 **جاري الرفع...**', parse_mode='Markdown')
    file_size = os.path.getsize(filename)

    if file_size > 52428800 or file_size < 10240:
        os.remove(filename)
        await msg.edit_text(f'❌ **حجم الملف غير صالح**\n\nالحجم: {file_size/1024/1024:.2f} MB', parse_mode='Markdown')
        return

    with open(filename, 'rb') as file:
        if media_type == "song":
            caption = f"🎧 **{title}**"
            thumb_path = await get_thumbnail(text) if is_url(text) else None
            if thumb_path and os.path.exists(thumb_path):
                with open(thumb_path, 'rb') as thumb:
                    await context.bot.send_audio(
                        chat_id=update.message.chat_id,
                        audio=file,
                        caption=caption,
                        parse_mode='Markdown',
                        thumbnail=thumb,
                        title=title
                    )
                os.remove(thumb_path)
            else:
                await context.bot.send_audio(chat_id=update.message.chat_id, audio=file, caption=caption, parse_mode='Markdown')
        else:
            caption = f"🎬 **{title}**"
            await context.bot.send_video(chat_id=update.message.chat_id, video=file, caption=caption, parse_mode='Markdown', supports_streaming=True)

    os.remove(filename)
    await msg.delete()

async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    print("✅ البوت شغال...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    asyncio.run(main())
