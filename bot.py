"""
Video → GIF Telegram Bot (single file)
--------------------------------------
Requirements:
  pip install python-telegram-bot==21.6
  FFmpeg installed on the machine (apt install ffmpeg / brew install ffmpeg)

Run:
  BOT_TOKEN=123456:ABC... python bot.py
"""

import asyncio
import logging
import os
import uuid
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ============================================================
# CONFIG
# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")  # set as env var when running
if not BOT_TOKEN:
    raise SystemExit("Set BOT_TOKEN environment variable before running.")

MAX_FILE_MB = 20
MAX_DURATION_SECONDS = 15
TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)

DEFAULT_SETTINGS = {"quality": "medium", "width": 480, "fps": 15, "trim": 0}
QUALITY_PRESETS = {"low": 128, "medium": 200, "high": 256}

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
log = logging.getLogger("video2gif")

# ============================================================
# STATE (in-memory — replace with DB for production)
# ============================================================
user_settings: dict[int, dict] = {}
pending_videos: dict[int, dict] = {}

# ============================================================
# FFMPEG CONVERSION
# ============================================================
async def _run(cmd: list[str]) -> None:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg failed:\n{stderr.decode(errors='ignore')[:800]}")


async def convert_video_to_gif(
    input_path: str,
    width: int = 480,
    fps: int = 15,
    quality: str = "medium",
    trim_seconds: int | None = None,
) -> str:
    output_path = TEMP_DIR / f"{uuid.uuid4().hex}.gif"
    palette_path = TEMP_DIR / f"{uuid.uuid4().hex}_palette.png"
    colors = QUALITY_PRESETS.get(quality, 200)

    trim = f"trim=duration={trim_seconds},setpts=PTS-STARTPTS," if trim_seconds else ""

    await _run([
        "ffmpeg", "-y", "-i", input_path,
        "-vf", f"{trim}fps={fps},scale={width}:-1:flags=lanczos,palettegen=max_colors={colors}",
        str(palette_path),
    ])

    await _run([
        "ffmpeg", "-y", "-i", input_path, "-i", str(palette_path),
        "-lavfi", f"{trim}fps={fps},scale={width}:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer",
        "-loop", "0", str(output_path),
    ])

    try:
        os.remove(palette_path)
    except OSError:
        pass

    return str(output_path)


def cleanup(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


# ============================================================
# KEYBOARDS
# ============================================================
def settings_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    s = user_settings.setdefault(chat_id, DEFAULT_SETTINGS.copy())
    m = lambda cond: "✅ " if cond else ""

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{m(s['quality']=='low')}Low", callback_data="q:low"),
            InlineKeyboardButton(f"{m(s['quality']=='medium')}Medium", callback_data="q:medium"),
            InlineKeyboardButton(f"{m(s['quality']=='high')}High", callback_data="q:high"),
        ],
        [
            InlineKeyboardButton(f"{m(s['width']==320)}320", callback_data="w:320"),
            InlineKeyboardButton(f"{m(s['width']==480)}480", callback_data="w:480"),
            InlineKeyboardButton(f"{m(s['width']==640)}640", callback_data="w:640"),
        ],
        [
            InlineKeyboardButton(f"{m(s['fps']==10)}10", callback_data="f:10"),
            InlineKeyboardButton(f"{m(s['fps']==15)}15", callback_data="f:15"),
            InlineKeyboardButton(f"{m(s['fps']==24)}24", callback_data="f:24"),
        ],
        [
            InlineKeyboardButton(f"{m(s['trim']==0)}Full", callback_data="t:0"),
            InlineKeyboardButton(f"{m(s['trim']==5)}First 5s", callback_data="t:5"),
            InlineKeyboardButton(f"{m(s['trim']==10)}First 10s", callback_data="t:10"),
        ],
        [
            InlineKeyboardButton("🎬 Convert to GIF", callback_data="convert"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
        ],
    ])


def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📹 Send a video to convert", callback_data="hint_send")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="hint_settings")],
        [InlineKeyboardButton("ℹ️ How it works", callback_data="hint_help")],
    ])


# ============================================================
# COMMAND HANDLERS
# ============================================================
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🎬 *Video → GIF Converter*\n\n"
        "Send me a short video (up to 20 MB, up to 15 seconds) and I'll "
        "turn it into a GIF right here in Telegram.\n\nTap below to begin."
    )
    await update.message.reply_text(
        text, parse_mode=ParseMode.MARKDOWN, reply_markup=start_keyboard()
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📖 *How it works*\n\n"
        f"1. Send a video file (mp4, mov, avi, mkv, webm).\n"
        f"2. Max size: {MAX_FILE_MB} MB.\n"
        f"3. Max duration: {MAX_DURATION_SECONDS}s.\n"
        "4. Pick quality, width, FPS and trim.\n"
        "5. Tap *Convert to GIF* and wait a few seconds.\n\n"
        "Everything happens inside Telegram — no external links."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "⚙️ *Default settings*\nAdjust once, used for future videos.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=settings_keyboard(update.effective_chat.id),
    )


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    pending_videos.pop(update.effective_chat.id, None)
    await update.message.reply_text("❌ Cancelled.")


# ============================================================
# VIDEO HANDLER
# ============================================================
async def on_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    chat_id = update.effective_chat.id

    video = msg.video or msg.document or msg.animation
    if video is None:
        await msg.reply_text("Please send a video file.")
        return

    if video.file_size and video.file_size > MAX_FILE_MB * 1024 * 1024:
        await msg.reply_text(f"⚠️ File too large. Limit is {MAX_FILE_MB} MB.")
        return

    duration = getattr(video, "duration", 0) or 0
    if duration and duration > MAX_DURATION_SECONDS:
        await msg.reply_text(
            f"⚠️ Video is {duration}s. Trim to {MAX_DURATION_SECONDS}s or less."
        )
        return

    await msg.chat.send_action(ChatAction.TYPING)
    status = await msg.reply_text("⬇️ Downloading video…")

    try:
        tg_file = await ctx.bot.get_file(video.file_id)
        in_path = TEMP_DIR / f"{video.file_unique_id}.mp4"
        await tg_file.download_to_drive(custom_path=str(in_path))
    except Exception as e:
        log.exception("Download failed")
        await status.edit_text(f"❌ Download failed: {e}")
        return

    pending_videos[chat_id] = {"path": str(in_path), "duration": duration}

    await status.edit_text(
        f"✅ Video received ({duration}s).\nChoose your GIF settings:",
        reply_markup=settings_keyboard(chat_id),
    )


# ============================================================
# CALLBACK HANDLER
# ============================================================
async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    chat_id = update.effective_chat.id
    data = q.data

    if data == "hint_send":
        await q.message.reply_text("📹 Just send me a video file now.")
        return
    if data == "hint_settings":
        await cmd_settings(update, ctx)
        return
    if data == "hint_help":
        await cmd_help(update, ctx)
        return
    if data == "cancel":
        pending_videos.pop(chat_id, None)
        await q.message.edit_text("❌ Cancelled.")
        return

    s = user_settings.setdefault(chat_id, DEFAULT_SETTINGS.copy())

    if data.startswith("q:"):
        s["quality"] = data.split(":")[1]
        await q.message.edit_reply_markup(settings_keyboard(chat_id))
        return
    if data.startswith("w:"):
        s["width"] = int(data.split(":")[1])
        await q.message.edit_reply_markup(settings_keyboard(chat_id))
        return
    if data.startswith("f:"):
        s["fps"] = int(data.split(":")[1])
        await q.message.edit_reply_markup(settings_keyboard(chat_id))
        return
    if data.startswith("t:"):
        s["trim"] = int(data.split(":")[1])
        await q.message.edit_reply_markup(settings_keyboard(chat_id))
        return

    if data == "convert":
        pending = pending_videos.get(chat_id)
        if not pending:
            await q.message.edit_text("⚠️ No video in queue. Send one first.")
            return

        await q.message.edit_text("🎞 Converting… this may take a few seconds.")
        await ctx.bot.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)

        try:
            gif_path = await convert_video_to_gif(
                input_path=pending["path"],
                width=s["width"],
                fps=s["fps"],
                quality=s["quality"],
                trim_seconds=s["trim"] or None,
            )
        except Exception as e:
            log.exception("Conversion failed")
            await q.message.edit_text(f"❌ Conversion failed:\n{e}")
            return

        try:
            with open(gif_path, "rb") as f:
                await ctx.bot.send_animation(
                    chat_id=chat_id, animation=f, caption="✅ Here's your GIF."
                )
        finally:
            cleanup(gif_path)
            cleanup(pending["path"])
            pending_videos.pop(chat_id, None)

        await q.message.edit_text(
            "Done. Send another video to convert again.",
            reply_markup=start_keyboard(),
        )


# ============================================================
# MAIN
# ============================================================
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(MessageHandler(
        filters.VIDEO | filters.Document.VIDEO | filters.ANIMATION, on_video
    ))
    app.add_handler(CallbackQueryHandler(on_callback))

    log.info("Bot starting…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
