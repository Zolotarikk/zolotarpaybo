from datetime import datetime, timedelta
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import config

HEADERS = [
    "№",
    "Дата",
    "Начало",
    "Конец",
    "Услуга",
    "Минут",
    "Цена, BYN",
    "Клиент",
    "Username",
    "Телефон",
    "Статус",
    "Создана",
]
WIDTHS = [6, 12, 8, 8, 28, 8, 11, 24, 18, 17, 12, 17]
STATUS_RU = {"active": "Активна", "cancelled": "Отменена"}


def style_header(sheet, widths):
    """Оформляет заголовок: цвет, закрепление, фильтры, ширина колонок."""
    fill = PatternFill("solid", fgColor="2F5496")
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions


def build_xlsx(rows) -> bytes:
    """Собирает Excel-файл: лист со всеми записями и лист со сводкой по услугам."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Записи"
    sheet.append(HEADERS)

    offset = timedelta(hours=config.TIMEZONE_OFFSET_HOURS)
    by_service = {}  # услуга -> [записей, выручка]; считаем только активные записи
    for (
        booking_id,
        start,
        end,
        service,
        price,
        full_name,
        username,
        phone,
        status,
        created,
    ) in rows:
        created_local = None
        if created:
            # В базе время создания хранится по UTC: переводим в местное
            created_local = datetime.strptime(created, "%Y-%m-%d %H:%M:%S") + offset
        sheet.append(
            [
                booking_id,
                start.date(),
                start.time(),
                end.time(),
                service,
                int((end - start).total_seconds() // 60),
                price,
                full_name or "",
                f"@{username}" if username else "",
                phone or "",
                STATUS_RU.get(status, status),
                created_local,
            ]
        )
        if status == "active":
            totals = by_service.setdefault(service, [0, 0])
            totals[0] += 1
            totals[1] += price

    # Форматы дат и времени, отменённые записи серым цветом
    grey = Font(color="999999")
    for row in sheet.iter_rows(min_row=2):
        row[1].number_format = "DD.MM.YYYY"
        row[2].number_format = "HH:MM"
        row[3].number_format = "HH:MM"
        row[11].number_format = "DD.MM.YYYY HH:MM"
        if row[10].value == STATUS_RU["cancelled"]:
            for cell in row:
                cell.font = grey
    style_header(sheet, WIDTHS)

    # Сводка по услугам
    summary = workbook.create_sheet("По услугам (без отмен)")
    summary.append(["Услуга", "Записей", "Выручка, BYN"])
    for service, (count, revenue) in sorted(
        by_service.items(), key=lambda item: -item[1][1]
    ):
        summary.append([service, count, revenue])
    summary.append(
        [
            "Итого",
            sum(count for count, _ in by_service.values()),
            sum(revenue for _, revenue in by_service.values()),
        ]
    )
    for cell in summary[summary.max_row]:
        cell.font = Font(bold=True)
    style_header(summary, [30, 10, 14])

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()