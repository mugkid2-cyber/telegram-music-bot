TELEGRAM_MESSAGE_LIMIT = 4096

# невидимый символ-разделитель — упоминание есть, а видимого текста нет
_INVISIBLE_CHAR = "\u2063"


def build_invisible_mentions(user_ids: list[int]) -> list[str]:
    """HTML-фрагменты упоминаний без видимого текста: уведомление участнику
    придёт, а сообщение не захламляется списком @username."""
    return [f'<a href="tg://user?id={user_id}">{_INVISIBLE_CHAR}</a>' for user_id in user_ids]


def chunk_html_message(
    base_text: str,
    mention_fragments: list[str],
    limit: int = TELEGRAM_MESSAGE_LIMIT,
) -> list[str]:
    """Собирает текст поздравления + как можно больше невидимых упоминаний
    в одно сообщение. Если участников чата много и все упоминания не влезли
    в лимит одного сообщения — оставшиеся уходят отдельными сообщениями
    (без повторения текста поздравления)."""
    if not mention_fragments:
        return [base_text]

    chunks: list[str] = []
    current = base_text

    for fragment in mention_fragments:
        candidate = current + fragment
        if len(candidate) > limit:
            chunks.append(current)
            current = fragment
        else:
            current = candidate

    chunks.append(current)
    return chunks