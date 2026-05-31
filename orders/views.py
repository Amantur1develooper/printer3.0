import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.utils import timezone

from .models import Order, PaperStock, PrintTariff
from .forms import UploadForm, ConfigureForm, ReceiptUploadForm
from .utils import (count_pdf_pages, calculate_order, check_paper_availability,
                    generate_payment_qr, get_tariff_data_for_terminal)


def map_view(request):
    """Home page: map with all active printers."""
    from printers.models import PrinterTerminal
    terminals = PrinterTerminal.objects.filter(is_active=True)
    terminals_json = json.dumps([t.to_map_dict() for t in terminals])
    return render(request, 'orders/map.html', {
        'terminals': terminals,
        'terminals_json': terminals_json,
    })


def upload_view(request, terminal_id):
    """Step 1: Upload PDF + enter name & phone for a chosen printer."""
    from printers.models import PrinterTerminal
    terminal = get_object_or_404(PrinterTerminal, id=terminal_id, is_active=True)

    error = None
    if request.method == 'POST':
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            f = form.cleaned_data['file']
            try:
                page_count = count_pdf_pages(f)
            except Exception as e:
                form.add_error('file', f'Не удалось прочитать PDF: {e}')
                return render(request, 'orders/upload.html', {'form': form, 'terminal': terminal})

            try:
                f.seek(0)
                order = Order(
                    terminal=terminal,
                    original_filename=f.name,
                    total_pages=page_count,
                    status='created',
                    customer_name=form.cleaned_data['customer_name'],
                    customer_phone=form.cleaned_data['customer_phone'],
                    customer_comment=form.cleaned_data.get('customer_comment', ''),
                )
                order.file.save(f.name, f, save=False)
                order.save()
                return redirect('configure', order_id=order.id)
            except Exception as e:
                error = f'Ошибка при сохранении: {e}. Запустите run_local.sh для настройки базы данных.'
    else:
        form = UploadForm()

    return render(request, 'orders/upload.html', {'form': form, 'terminal': terminal, 'error': error})


def configure_view(request, order_id):
    """Step 2: Configure print settings and calculate cost."""
    order = get_object_or_404(Order, id=order_id, status__in=['created', 'calculated'])

    tariff_data = get_tariff_data_for_terminal(order.terminal)

    if request.method == 'POST':
        form = ConfigureForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            duplex = cd['duplex'] == 'true'

            try:
                result = calculate_order(
                    terminal=order.terminal,
                    total_pages=order.total_pages,
                    copies=cd['copies'],
                    duplex=duplex,
                    color=cd['color'],
                    paper_format=cd['paper_format'],
                    page_range=cd.get('page_range', ''),
                    even_only=cd.get('even_only', False),
                    odd_only=cd.get('odd_only', False),
                )
            except ValueError as e:
                form.add_error(None, str(e))
                return render(request, 'orders/configure.html', {
                    'form': form, 'order': order, 'tariff_data': json.dumps(tariff_data)
                })

            paper_ok, available = check_paper_availability(
                order.terminal, cd['paper_format'], result['total_sheets']
            )
            if not paper_ok:
                form.add_error(None,
                    f'Недостаточно бумаги {cd["paper_format"]} на этом принтере. '
                    f'Доступно: {available} листов, нужно: {result["total_sheets"]}.'
                )
                return render(request, 'orders/configure.html', {
                    'form': form, 'order': order, 'tariff_data': json.dumps(tariff_data)
                })

            order.copies = cd['copies']
            order.color = cd['color']
            order.duplex = duplex
            order.paper_format = cd['paper_format']
            order.page_range = cd.get('page_range', '')
            order.orientation = cd['orientation']
            order.even_only = cd.get('even_only', False)
            order.odd_only = cd.get('odd_only', False)
            order.selected_pages = result['selected_pages']
            order.sheets_per_copy = result['sheets_per_copy']
            order.total_sheets = result['total_sheets']
            order.price_per_sheet = result['price_per_sheet']
            order.total_cost = result['total_cost']
            order.status = 'calculated'
            order.save()

            if not order.qr_code:
                qr_file = generate_payment_qr(order)
                order.qr_code.save(qr_file.name, qr_file, save=True)

            return redirect('payment', order_id=order.id)
    else:
        form = ConfigureForm()

    return render(request, 'orders/configure.html', {
        'form': form,
        'order': order,
        'tariff_data': json.dumps(tariff_data),
    })


def calculate_ajax(request):
    """AJAX endpoint for live price calculation."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
        order = Order.objects.select_related('terminal').get(id=data.get('order_id'))
        duplex = data.get('duplex') == 'true'

        result = calculate_order(
            terminal=order.terminal,
            total_pages=order.total_pages,
            copies=int(data.get('copies', 1)),
            duplex=duplex,
            color=data.get('color', 'bw'),
            paper_format=data.get('paper_format', 'A4'),
            page_range=data.get('page_range', ''),
            even_only=data.get('even_only', False),
            odd_only=data.get('odd_only', False),
        )
        paper_ok, available = check_paper_availability(order.terminal, data.get('paper_format', 'A4'), result['total_sheets'])
        result['paper_ok'] = paper_ok
        result['paper_available'] = available
        return JsonResponse(result)
    except (Order.DoesNotExist, ValueError, KeyError) as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception:
        return JsonResponse({'error': 'Ошибка расчёта'}, status=500)


def payment_view(request, order_id):
    """Step 3: Show QR code and accept receipt upload."""
    order = get_object_or_404(Order, id=order_id,
                               status__in=['calculated', 'awaiting_payment', 'receipt_uploaded'])

    if request.method == 'POST':
        # Сохранить фото чека если загрузили (опционально)
        if request.FILES.get('payment_receipt'):
            order.payment_receipt = request.FILES['payment_receipt']
        order.transaction_id = request.POST.get('transaction_id', '')

        # TODO: временно авто-подтверждение. После подключения банка — заменить на реальную проверку.
        order.status = 'queued'
        order.payment_confirmed_at = timezone.now()
        order.save()

        # Списать бумагу
        try:
            from orders.models import PaperStock
            stock = PaperStock.objects.get(terminal=order.terminal, paper_format=order.paper_format)
            stock.sheets_available = max(0, stock.sheets_available - order.total_sheets)
            stock.save(update_fields=['sheets_available'])
        except Exception:
            pass

        messages.success(request, 'Отлично! Ваш заказ в очереди на печать.')
        return redirect('tracking', order_number=order.order_number)
    else:
        order.status = 'awaiting_payment'
        order.save()

    from django.conf import settings
    return render(request, 'orders/payment.html', {
        'order': order,
        'payment_phone': settings.PAYMENT_PHONE,
        'payment_recipient': settings.PAYMENT_RECIPIENT,
    })


def tracking_view(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    details = [
        ('Файл',      order.original_filename),
        ('Страниц',   f'{order.selected_pages} из {order.total_pages}'),
        ('Листов',    f'{order.sheets_per_copy} × {order.copies} коп. = {order.total_sheets}'),
        ('Цвет',      order.get_color_display()),
        ('Тип',       'Двусторонняя' if order.duplex else 'Односторонняя'),
        ('Формат',    order.paper_format),
        ('Создан',    order.created_at.strftime('%d.%m.%Y %H:%M')),
    ]
    if order.printed_at:
        details.append(('Распечатан', order.printed_at.strftime('%d.%m.%Y %H:%M')))
    return render(request, 'orders/tracking.html', {'order': order, 'details': details})


def tracking_status_ajax(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    return JsonResponse({
        'status': order.status,
        'status_display': order.get_status_display_ru(),
        'status_color': order.get_status_color(),
        'error_message': order.error_message,
        'printed_at': order.printed_at.isoformat() if order.printed_at else None,
    })
