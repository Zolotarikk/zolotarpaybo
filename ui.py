from html import escape


def client_html(user_id: int, full_name: str | None, username: str | None, phone: str | None) -> str:
    """Клиент для админа: ссылка на профиль, @username и телефон (HTML)."""
    name = escape(full_name or "Клиент")
    parts = [f'<a href="tg://user?id={user_id}">{name}</a>']
    if username:
        parts.append(f"@{escape(username)}")
    if phone:
        parts.append(f"📞 {escape(phone)}")
    return " · ".join(parts)