import re

import config


def normalize_phone(raw: str) -> str | None:
    """Приводит номер к виду +375291234567. Если это не похоже на номер, возвращает None."""
    digits = re.sub(r"\D", "", raw)
    code = config.PHONE_COUNTRY_CODE
    if raw.strip().startswith("+"):
        pass  # номер уже в международном формате
    elif code == "375" and digits.startswith("80") and len(digits) == 11:
        digits = code + digits[2:]  # 8 029 123-45-67 -> 375291234567
    elif code == "7" and digits.startswith("8") and len(digits) == 11:
        digits = code + digits[1:]  # 8 916 123-45-67 -> 79161234567
    elif len(digits) == 9:
        digits = code + digits  # 29 123-45-67 -> 375291234567
    if not 10 <= len(digits) <= 15:
        return None
    return "+" + digits