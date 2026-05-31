import math
import qrcode
from io import BytesIO
from django.core.files.base import ContentFile
from django.conf import settings


def count_pdf_pages(file_obj):
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_obj)
        return len(reader.pages)
    except Exception as e:
        raise ValueError(f'Не удалось прочитать PDF: {e}')


def parse_page_range(page_range_str, total_pages):
    if not page_range_str or not page_range_str.strip():
        return list(range(1, total_pages + 1))

    pages = set()
    for part in page_range_str.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            try:
                start, end = part.split('-', 1)
                pages.update(range(int(start.strip()), int(end.strip()) + 1))
            except ValueError:
                raise ValueError(f'Неверный диапазон страниц: "{part}"')
        else:
            try:
                pages.add(int(part))
            except ValueError:
                raise ValueError(f'Неверный номер страницы: "{part}"')

    valid = sorted(p for p in pages if 1 <= p <= total_pages)
    if not valid:
        raise ValueError('Указанный диапазон не содержит страниц документа.')
    return valid


def calculate_order(terminal, total_pages, copies, duplex, color, paper_format,
                    page_range='', even_only=False, odd_only=False):
    """
    Calculate sheets and cost for an order using the terminal's own tariffs.
    Returns dict: selected_pages, sheets_per_copy, total_sheets, price_per_sheet, total_cost
    """
    from orders.models import PrintTariff

    pages = parse_page_range(page_range, total_pages)
    if even_only and not odd_only:
        pages = [p for p in pages if p % 2 == 0]
    elif odd_only and not even_only:
        pages = [p for p in pages if p % 2 != 0]

    if not pages:
        raise ValueError('После фильтра (чётные/нечётные) страниц не осталось.')

    selected_pages = len(pages)
    sheets_per_copy = math.ceil(selected_pages / 2) if duplex else selected_pages
    total_sheets = sheets_per_copy * copies

    try:
        tariff = PrintTariff.objects.get(
            terminal=terminal,
            paper_format=paper_format,
            color=color,
            duplex=duplex,
            is_active=True,
        )
    except PrintTariff.DoesNotExist:
        raise ValueError(
            f'Тариф ({paper_format}, {"ч/б" if color == "bw" else "цветная"}, '
            f'{"двусторонняя" if duplex else "односторонняя"}) не задан для этого принтера. '
            f'Обратитесь к администратору.'
        )

    total_cost = tariff.price_per_sheet * total_sheets

    return {
        'selected_pages': selected_pages,
        'sheets_per_copy': sheets_per_copy,
        'total_sheets': total_sheets,
        'price_per_sheet': float(tariff.price_per_sheet),
        'total_cost': float(total_cost),
    }


def check_paper_availability(terminal, paper_format, sheets_needed):
    """Returns (ok: bool, available: int) using terminal's own paper stock."""
    from orders.models import PaperStock

    threshold = getattr(settings, 'MIN_PAPER_THRESHOLD', 5)
    try:
        stock = PaperStock.objects.get(terminal=terminal, paper_format=paper_format)
        available = stock.sheets_available
    except PaperStock.DoesNotExist:
        return False, 0

    return available >= sheets_needed + threshold, available


def get_tariff_data_for_terminal(terminal):
    """Return tariff dict for frontend JS price calculator."""
    from orders.models import PrintTariff
    tariffs = PrintTariff.objects.filter(terminal=terminal, is_active=True)
    return {
        f'{t.paper_format}_{t.color}_{"duplex" if t.duplex else "single"}': float(t.price_per_sheet)
        for t in tariffs
    }


def generate_payment_qr(order):
    phone = getattr(settings, 'PAYMENT_PHONE', '+996 700 000000')
    recipient = getattr(settings, 'PAYMENT_RECIPIENT', 'Онлайн Принтер')

    lines = [
        f'Оплата заказа #{order.order_number}',
        f'Сумма: {order.total_cost} сом',
        f'Получатель: {recipient}',
        f'Телефон: {phone}',
        f'Комментарий: {order.order_number}',
    ]
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data('\n'.join(lines))
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')

    buf = BytesIO()
    img.save(buf, format='PNG')
    return ContentFile(buf.getvalue(), name=f'qr_{order.order_number}.png')
