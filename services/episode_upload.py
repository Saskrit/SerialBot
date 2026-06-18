import logging
from datetime import datetime

from aiogram.types import Message

from database import repository as repo
from services.messages import format_date
from services.upload_parser import parse_episode_date, parse_upload_caption

logger = logging.getLogger(__name__)


def _video_message(message: Message) -> Message | None:
    if message.video or message.document:
        return message
    return None


async def save_episode_from_message(
    message: Message,
    *,
    caption: str | None = None,
    notify: bool = True,
    silent_empty_caption: bool = False,
    is_caption_edit: bool = False,
) -> tuple[bool, str]:
    """Save episode from a video/document message. Returns (success, status_message_html)."""
    video_msg = _video_message(message)
    if not video_msg:
        return False, "No video found in message."

    text = (caption if caption is not None else (message.caption or "")).strip()
    if not text:
        if silent_empty_caption and not is_caption_edit:
            logger.info(
                "Video msg %s uploaded without caption — waiting for caption edit",
                message.message_id,
            )
            return False, ""
        return False, "Caption is empty. Use: <code>Laughter Chef 3 | 17 June 2026</code>"

    serial, episode_date, error = await parse_upload_caption(text)
    if error or not serial or not episode_date:
        if silent_empty_caption and not is_caption_edit:
            return False, ""
        return False, error or "Could not parse caption."

    file_id = video_msg.video.file_id if video_msg.video else video_msg.document.file_id
    unique_id = (
        video_msg.video.file_unique_id
        if video_msg.video
        else video_msg.document.file_unique_id
    )

    ep_id, created = await repo.upsert_episode(
        serial_slug=serial["slug"],
        serial_name=serial["name"],
        episode_date=episode_date,
        file_id=file_id,
        file_unique_id=unique_id,
        message_id=message.message_id,
    )

    action = "saved" if created else "updated"
    logger.info(
        "Episode %s: %s — %s (%s)",
        action,
        serial["name"],
        format_date(episode_date),
        ep_id,
    )

    success_text = (
        f"✅ <b>Episode {action}</b>\n"
        f"Serial: <b>{serial['name']}</b>\n"
        f"Date: {format_date(episode_date)}\n"
        f"ID: <code>{ep_id}</code>"
    )

    if notify and message.bot:
        from config import ADMIN_IDS

        for admin_id in ADMIN_IDS:
            try:
                await message.bot.send_message(admin_id, success_text, parse_mode="HTML")
            except Exception:
                pass

    return True, success_text


async def save_episode_from_addepisode(command: Message) -> tuple[bool, str]:
    """Parse /addepisode reply — video caption first, then command arguments."""
    if not command.reply_to_message:
        return False, (
            "Reply to a video with a valid caption, or use:\n"
            "<code>/addepisode laughter-chef-3 | 17 June 2026</code>"
        )

    src = command.reply_to_message
    if not (src.video or src.document):
        return False, "Reply must be to a video message."

    video_caption = (src.caption or "").strip()
    if video_caption:
        serial, episode_date, error = await parse_upload_caption(video_caption)
        if serial and episode_date:
            return await _save_from_parsed(src, serial, episode_date)

    command_text = (command.text or "").strip()
    parts = command_text.split(maxsplit=1)
    if len(parts) > 1:
        rest = parts[1].strip()
        serial, episode_date, error = await parse_upload_caption(rest)
        if serial and episode_date:
            return await _save_from_parsed(src, serial, episode_date)

        slug_date = rest.split(maxsplit=1)
        if len(slug_date) == 2:
            slug = slug_date[0].lower().replace(" ", "-")
            serial = await repo.get_serial_by_slug(slug)
            episode_date = parse_episode_date(slug_date[1])
            if serial and episode_date:
                return await _save_from_parsed(src, serial, episode_date)

    return False, (
        "Could not parse episode details.\n\n"
        "Add caption to the video:\n"
        "<code>Laughter Chef 3 | 17 June 2026</code>\n\n"
        "Or reply with:\n"
        "<code>/addepisode laughter-chef-3 | 17 June 2026</code>"
    )


async def _save_from_parsed(
    video_message: Message,
    serial: dict,
    episode_date: datetime,
) -> tuple[bool, str]:
    file_id = (
        video_message.video.file_id
        if video_message.video
        else video_message.document.file_id
    )
    unique_id = (
        video_message.video.file_unique_id
        if video_message.video
        else video_message.document.file_unique_id
    )

    ep_id, created = await repo.upsert_episode(
        serial_slug=serial["slug"],
        serial_name=serial["name"],
        episode_date=episode_date,
        file_id=file_id,
        file_unique_id=unique_id,
        message_id=video_message.message_id,
    )
    action = "saved" if created else "updated"
    return True, (
        f"✅ Episode {action}: <b>{serial['name']}</b> — "
        f"{format_date(episode_date)} (<code>{ep_id}</code>)"
    )
