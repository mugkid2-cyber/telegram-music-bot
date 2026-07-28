from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot
from PIL import Image, ImageDraw, ImageFont

from app.icons.colors import avatar_fallback_color, color_for_user
from app.icons.models import MessageLog

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent / "assets"
FONT_REGULAR = ASSETS_DIR / "fonts" / "DejaVuSans.ttf"
FONT_BOLD = ASSETS_DIR / "fonts" / "DejaVuSans-Bold.ttf"

# ---- "Логические" (1x) границы размеров карточки. Это НЕ константы для
# рисования, а верхние/нижние пределы: конкретные значения на каждый
# рендер выбираются в _pick_layout_params() в зависимости от объёма
# цитаты. Раньше шрифт/ширина были жёстко зафиксированы, а высота росла
# неограниченно — при длинных цитатах или нескольких фото итоговое сжатие
# под лимит Telegram (одна сторона == 512px) уходило в 0.2-0.3, и текст
# становился нечитаемым. Теперь под большой объём заранее берутся более
# компактные (но всё ещё читаемые) размеры, а не аварийное сжатие в конце.
CARD_WIDTH_MIN = 420
CARD_WIDTH_MAX = 512
PADDING_MAX = 24
PADDING_MIN = 18
AVATAR_SIZE_MAX = 44
AVATAR_SIZE_MIN = 34
AVATAR_GAP_MAX = 12
AVATAR_GAP_MIN = 8
NAME_FONT_SIZE_MAX = 24
NAME_FONT_SIZE_MIN = 17
TEXT_FONT_SIZE_MAX = 26
TEXT_FONT_SIZE_MIN = 18  # ниже не опускаемся — дальше нечитаемо даже на телефоне
LINE_SPACING_MAX = 6
LINE_SPACING_MIN = 4
RUN_GAP_MAX = 18
RUN_GAP_MIN = 12
MESSAGE_GAP_MAX = 14
MESSAGE_GAP_MIN = 9
MAX_IMAGE_HEIGHT_MAX = 320
MAX_IMAGE_HEIGHT_MIN = 140

BG_COLOR = (24, 24, 27, 255)
TEXT_COLOR = (230, 230, 235, 255)
MUTED_TEXT_COLOR = (150, 150, 158, 255)
CORNER_RADIUS = 28
MAX_STICKER_SIDE = 512
NO_TEXT_PLACEHOLDER = "[медиа]"
IMAGE_CORNER_RADIUS = 16

# Рисуем карточку в SUPERSAMPLE-кратном разрешении и уменьшаем один раз в
# самом конце (одновременно вписывая в лимит Telegram) — так текст и фото
# остаются чёткими, а не "плывут" от двух последовательных resize.
SUPERSAMPLE = 2

# Калибровка "плотности" контента для _pick_layout_params: ниже этого
# скора берутся максимальные размеры, выше — минимальные, между —
# линейная интерполяция. Подобрано под MAX_WINDOW=10 сообщений с фото.
DENSITY_LOW = 8.0
DENSITY_HIGH = 55.0


@dataclass
class _RawContent:
    """Сырое содержимое сообщения: скачано и декодировано, но ещё не
    уложено под конкретные размеры карточки — это отдельный шаг
    (_layout_content), чтобы не дёргать сеть повторно при подборе
    параметров рендера."""

    kind: str  # "text" | "image"
    text: str | None = None
    image: Image.Image | None = None
    caption: str | None = None


@dataclass
class _MessageContent:
    kind: str
    lines: list[str] | None = None
    image: Image.Image | None = None
    caption_lines: list[str] | None = None


@dataclass
class _Run:
    user_id: int
    name: str
    color: tuple[int, int, int]
    raw_messages: list[_RawContent]
    avatar_bytes: bytes | None
    messages: list[_MessageContent] | None = None  # заполняется в layout-проходе
    avatar: Image.Image | None = None              # заполняется в layout-проходе (уже в SS-разрешении)


@dataclass
class _LayoutParams:
    card_width: int
    padding: int
    avatar_size: int
    avatar_gap: int
    name_font_size: int
    text_font_size: int
    line_spacing: int
    run_gap: int
    message_gap: int
    max_image_height: int

    @property
    def max_text_width(self) -> int:
        return self.card_width - self.padding * 2 - self.avatar_size - self.avatar_gap

    @property
    def image_caption_gap(self) -> int:
        return self.message_gap // 2 or 3


def _load_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    # жёстко режем аномально длинные "слова" (ссылки и т.п.)
    result: list[str] = []
    for line in lines:
        while draw.textlength(line, font=font) > max_width and len(line) > 1:
            cut = len(line) - 1
            while cut > 1 and draw.textlength(line[:cut], font=font) > max_width:
                cut -= 1
            result.append(line[:cut])
            line = line[cut:]
        result.append(line)
    return result


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _gradient_circle(size: int, color: tuple[int, int, int]) -> Image.Image:
    """Аватар-заглушка градиентом (а не плоской заливкой) — чтобы она
    выглядела как осознанный дизайн, а не как "аватарка не загрузилась".
    Актуально в первую очередь для пересланных сообщений, где у автора
    включена приватность и Telegram отдаёт только имя без ID — реальное
    фото в этом случае в принципе недоступно ни при каких условиях."""
    top = tuple(min(255, int(c * 1.18)) for c in color)
    bottom = tuple(max(0, int(c * 0.78)) for c in color)
    grad = Image.new("RGBA", (1, size), 0)
    for y in range(size):
        t = y / max(1, size - 1)
        grad.putpixel((0, y), (
            int(_lerp(top[0], bottom[0], t)),
            int(_lerp(top[1], bottom[1], t)),
            int(_lerp(top[2], bottom[2], t)),
            255,
        ))
    return grad.resize((size, size))


def _make_circle_avatar(
    image_bytes: bytes | None,
    fallback_letter: str,
    fallback_color: tuple[int, int, int],
    size: int,
) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)

    if image_bytes:
        try:
            img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
            w, h = img.size
            side = min(w, h)
            left, top = (w - side) // 2, (h - side) // 2
            img = img.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)
            out = Image.new("RGBA", (size, size))
            out.paste(img, (0, 0), mask)
            return out
        except Exception:
            pass

    out = _gradient_circle(size, fallback_color)
    draw = ImageDraw.Draw(out)
    font = _load_font(FONT_BOLD, int(size * 0.45))
    letter = fallback_letter.upper() if fallback_letter else "?"
    bbox = draw.textbbox((0, 0), letter, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]), letter, font=font, fill=(255, 255, 255, 255))
    out.putalpha(mask)
    return out


def _round_image_corners(img: Image.Image, radius: int) -> Image.Image:
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=radius, fill=255)
    out = img.copy()
    out.putalpha(mask)
    return out


async def fetch_photo_bytes(bot: Bot, file_id: str) -> bytes | None:
    """Скачивает файл по file_id, сохранённому в момент логирования сообщения."""
    try:
        file = await bot.get_file(file_id)
        buf = io.BytesIO()
        await bot.download_file(file.file_path, destination=buf)
        return buf.getvalue()
    except Exception:
        return None


async def fetch_avatar_bytes(bot: Bot, user_id: int) -> bytes | None:
    """
    Для реальных участников чата работает как обычно. Для авторов
    пересланных сообщений со скрытой приватностью user_id — это
    детерминированный псевдо-ID (см. message_log._stable_id_from_name),
    а не настоящий Telegram user_id, поэтому здесь предсказуемо ничего
    не найдётся и сработает fallback-аватар — это ограничение Telegram
    (сам API не отдаёт боту, кто скрыл пересылку), не баг рендера.
    """
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if not photos.photos:
            return None
        file_id = photos.photos[0][-1].file_id
        file = await bot.get_file(file_id)
        buf = io.BytesIO()
        await bot.download_file(file.file_path, destination=buf)
        return buf.getvalue()
    except Exception:
        return None


async def _fetch_raw_content(bot: Bot, m: MessageLog) -> _RawContent:
    """Только скачивание/декодирование — без укладки под размеры карточки,
    чтобы сеть не дёргалась повторно, если параметры layout'а потом
    пересчитаются под объём цитаты (см. _pick_layout_params)."""
    if m.media_kind == "photo" and m.media_file_id:
        photo_bytes = await fetch_photo_bytes(bot, m.media_file_id)
        if photo_bytes is not None:
            try:
                img = Image.open(io.BytesIO(photo_bytes)).convert("RGBA")
                caption = (m.text or "").strip() or None
                return _RawContent(kind="image", image=img, caption=caption)
            except Exception:
                logger.warning("не удалось декодировать фото message_id=%s, показываю плейсхолдер", m.message_id)

    text = (m.text or "").strip() or NO_TEXT_PLACEHOLDER
    return _RawContent(kind="text", text=text)


def _estimate_density(runs: list[_Run]) -> float:
    """
    Грубая оценка "объёма" цитаты в условных строках — по ней подбираются
    размеры шрифта/карточки в _pick_layout_params. Считается ещё до
    layout-прохода, поэтому не привязана к конкретному шрифту/ширине —
    это именно оценка объёма контента, а не точный расчёт высоты.
    """
    score = 0.0
    for run in runs:
        score += 0.6  # заголовок с именем автора run'а
        for raw in run.raw_messages:
            if raw.kind == "image":
                score += 5.0
                if raw.caption:
                    score += len(raw.caption) / 40
            else:
                score += max(1.0, len(raw.text or "") / 40)
    return score


def _pick_layout_params(runs: list[_Run]) -> _LayoutParams:
    score = _estimate_density(runs)
    t = max(0.0, min(1.0, (score - DENSITY_LOW) / (DENSITY_HIGH - DENSITY_LOW)))

    return _LayoutParams(
        card_width=round(_lerp(CARD_WIDTH_MIN, CARD_WIDTH_MAX, t)),
        padding=round(_lerp(PADDING_MAX, PADDING_MIN, t)),
        avatar_size=round(_lerp(AVATAR_SIZE_MAX, AVATAR_SIZE_MIN, t)),
        avatar_gap=round(_lerp(AVATAR_GAP_MAX, AVATAR_GAP_MIN, t)),
        name_font_size=round(_lerp(NAME_FONT_SIZE_MAX, NAME_FONT_SIZE_MIN, t)),
        text_font_size=round(_lerp(TEXT_FONT_SIZE_MAX, TEXT_FONT_SIZE_MIN, t)),
        line_spacing=round(_lerp(LINE_SPACING_MAX, LINE_SPACING_MIN, t)),
        run_gap=round(_lerp(RUN_GAP_MAX, RUN_GAP_MIN, t)),
        message_gap=round(_lerp(MESSAGE_GAP_MAX, MESSAGE_GAP_MIN, t)),
        max_image_height=round(_lerp(MAX_IMAGE_HEIGHT_MAX, MAX_IMAGE_HEIGHT_MIN, t)),
    )


def _layout_content(
    raw: _RawContent,
    draw: ImageDraw.ImageDraw,
    text_font: ImageFont.FreeTypeFont,
    params: _LayoutParams,
) -> _MessageContent:
    if raw.kind == "image" and raw.image is not None:
        img = raw.image
        w, h = img.size
        # вписываем в колонку текста, не увеличивая маленькие фото
        scale = min(params.max_text_width / w, params.max_image_height / h, 1.0)
        new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
        img = img.resize(new_size, Image.LANCZOS)
        img = _round_image_corners(img, IMAGE_CORNER_RADIUS)
        caption_lines = (
            _wrap_text(draw, raw.caption, text_font, params.max_text_width) if raw.caption else None
        )
        return _MessageContent(kind="image", image=img, caption_lines=caption_lines)

    lines = _wrap_text(draw, raw.text or "", text_font, params.max_text_width)
    return _MessageContent(kind="text", lines=lines)


async def render_quote_card(bot: Bot, messages: list[MessageLog]) -> bytes:
    """
    Рендерит PNG карточку цитаты по образцу мессенджер-стикеров:
    группирует подряд идущие сообщения одного автора под одним
    аватаром/именем, каждое сообщение — отдельный "пузырь".

    Размер шрифта, ширина карточки и высота фото подбираются под объём
    цитаты (см. _pick_layout_params) — иначе длинная цитата или
    несколько фото при обязательном сжатии в 512px Telegram-стикера
    превращались в нечитаемое месиво. Сама карточка рисуется в
    SUPERSAMPLE-кратном разрешении и уменьшается один раз в самом
    конце — так текст и фото остаются чёткими.

    Возвращает PNG-байты, уже вписанные в требования Telegram
    (одна сторона ровно 512px, другая — не больше).
    """
    scratch_img = Image.new("RGBA", (10, 10))
    scratch_draw = ImageDraw.Draw(scratch_img)

    # 1. группировка подряд идущих сообщений одного автора (сырые данные —
    # только сеть/декодирование, без укладки под конкретные размеры)
    runs: list[_Run] = []
    avatar_bytes_cache: dict[int, bytes | None] = {}
    for m in messages:
        raw = await _fetch_raw_content(bot, m)
        if runs and runs[-1].user_id == m.user_id:
            runs[-1].raw_messages.append(raw)
            continue
        if m.user_id not in avatar_bytes_cache:
            avatar_bytes_cache[m.user_id] = await fetch_avatar_bytes(bot, m.user_id)
        runs.append(
            _Run(
                user_id=m.user_id,
                name=m.user_full_name,
                color=color_for_user(m.user_id),
                raw_messages=[raw],
                avatar_bytes=avatar_bytes_cache[m.user_id],
            )
        )

    # 2. подбор размеров под объём цитаты + укладка (wrap текста, ресайз фото)
    params = _pick_layout_params(runs)
    text_font = _load_font(FONT_REGULAR, params.text_font_size)  # только для замера переносов строк
    ss = SUPERSAMPLE

    avatar_img_cache: dict[int, Image.Image] = {}
    for run in runs:
        if run.user_id not in avatar_img_cache:
            # аватар сразу строится в SS-разрешении — без промежуточного
            # downscale-потом-upscale, который "мылил" бы фото
            avatar_img_cache[run.user_id] = _make_circle_avatar(
                run.avatar_bytes, run.name[:1], avatar_fallback_color(run.user_id), params.avatar_size * ss
            )
        run.avatar = avatar_img_cache[run.user_id]
        run.messages = [_layout_content(raw, scratch_draw, text_font, params) for raw in run.raw_messages]

    # 3. считаем высоту карточки (в "логических" 1x пикселях)
    line_h = params.text_font_size + params.line_spacing
    name_h = params.name_font_size + 10
    height = params.padding * 2
    for i, run in enumerate(runs):
        height += name_h
        for j, content in enumerate(run.messages):
            if content.kind == "image":
                height += content.image.height
                if content.caption_lines:
                    height += params.image_caption_gap + len(content.caption_lines) * line_h
            else:
                height += len(content.lines) * line_h
            if j != len(run.messages) - 1:
                height += params.message_gap
        if i != len(runs) - 1:
            height += params.run_gap
    height = max(height, params.avatar_size + params.padding * 2)
    width = params.card_width

    # 4. рисуем в SUPERSAMPLE-кратном разрешении
    card = Image.new("RGBA", (width * ss, height * ss), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle((0, 0, width * ss, height * ss), radius=CORNER_RADIUS * ss, fill=BG_COLOR)

    name_font_ss = _load_font(FONT_BOLD, params.name_font_size * ss)
    text_font_ss = _load_font(FONT_REGULAR, params.text_font_size * ss)

    y = params.padding * ss
    text_x = (params.padding + params.avatar_size + params.avatar_gap) * ss
    for i, run in enumerate(runs):
        card.paste(run.avatar, (params.padding * ss, int(y)), run.avatar)
        draw.text((text_x, y - 2 * ss), run.name, font=name_font_ss, fill=run.color + (255,))
        y += name_h * ss
        for j, content in enumerate(run.messages):
            if content.kind == "image":
                img_ss = content.image.resize(
                    (content.image.width * ss, content.image.height * ss), Image.LANCZOS
                )
                card.paste(img_ss, (text_x, int(y)), img_ss)
                y += content.image.height * ss
                if content.caption_lines:
                    y += params.image_caption_gap * ss
                    for line in content.caption_lines:
                        draw.text((text_x, y), line, font=text_font_ss, fill=TEXT_COLOR)
                        y += line_h * ss
            else:
                for line in content.lines:
                    draw.text((text_x, y), line, font=text_font_ss, fill=TEXT_COLOR)
                    y += line_h * ss
            if j != len(run.messages) - 1:
                y += params.message_gap * ss
        if i != len(runs) - 1:
            y += params.run_gap * ss

    # 5. один финальный resize: одновременно снимаем SUPERSAMPLE и вписываем
    # в требования Telegram для статичных стикеров (одна сторона == 512,
    # другая — не больше). Размеры уже подобраны под объём цитаты в шаге 2,
    # так что здесь обычно лёгкое уменьшение, а не аварийное сжатие, как
    # было раньше при фиксированных размерах.
    telegram_scale = MAX_STICKER_SIDE / max(width, height)
    final_w = max(1, round(width * telegram_scale))
    final_h = max(1, round(height * telegram_scale))
    card = card.resize((final_w, final_h), Image.LANCZOS)

    out = io.BytesIO()
    card.save(out, format="PNG", optimize=True)
    data = out.getvalue()
    if len(data) > 512 * 1024:
        # подстраховка на случай очень длинной цитаты — пережимаем компактнее
        out = io.BytesIO()
        card.convert("RGB").save(out, format="WEBP", quality=80, method=6)
        data = out.getvalue()
    return data