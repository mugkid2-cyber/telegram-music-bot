from __future__ import annotations

# Палитра близка к тому, как Telegram красит имена в чатах —
# по остатку от деления user_id на длину списка.
NAME_COLORS: list[tuple[int, int, int]] = [
    (237, 88, 86),    # красный
    (240, 147, 43),   # оранжевый
    (139, 179, 43),   # оливковый
    (49, 173, 129),   # зелёный
    (49, 160, 216),   # голубой
    (85, 132, 227),   # синий
    (168, 99, 219),   # фиолетовый
    (219, 89, 149),   # розовый
]


def color_for_user(user_id: int) -> tuple[int, int, int]:
    return NAME_COLORS[user_id % len(NAME_COLORS)]


def avatar_fallback_color(user_id: int) -> tuple[int, int, int]:
    return NAME_COLORS[(user_id * 7 + 3) % len(NAME_COLORS)]
