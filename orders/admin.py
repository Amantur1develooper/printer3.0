from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Sum, Count
from django.utils import timezone
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.template.response import TemplateResponse

from .models import Order, PrintTariff, PaperStock


@admin.register(PrintTariff)
class PrintTariffAdmin(admin.ModelAdmin):
    list_display = ('terminal', 'paper_format', 'color', 'duplex', 'price_per_sheet', 'is_active')
    list_editable = ('price_per_sheet', 'is_active')
    list_filter = ('terminal', 'paper_format', 'color', 'duplex', 'is_active')
    list_select_related = ('terminal',)


@admin.register(PaperStock)
class PaperStockAdmin(admin.ModelAdmin):
    list_display = ('terminal', 'paper_format', 'sheets_available', 'updated_at', 'stock_status')
    list_editable = ('sheets_available',)
    list_filter = ('terminal', 'paper_format')
    list_select_related = ('terminal',)

    def stock_status(self, obj):
        from django.conf import settings
        threshold = getattr(settings, 'MIN_PAPER_THRESHOLD', 5)
        if obj.sheets_available <= threshold:
            return format_html('<span style="color:red;font-weight:bold;">⚠ Мало бумаги!</span>')
        elif obj.sheets_available < 50:
            return format_html('<span style="color:orange;">Заканчивается</span>')
        return format_html('<span style="color:green;">OK</span>')
    stock_status.short_description = 'Состояние'


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'order_number', 'customer_name', 'customer_phone',
        'total_sheets', 'total_cost', 'colored_status', 'created_at', 'actions_column'
    )
    list_filter = ('status', 'color', 'duplex', 'paper_format', 'created_at')
    search_fields = ('order_number', 'customer_name', 'customer_phone', 'customer_email')
    readonly_fields = (
        'order_number', 'created_at', 'printed_at', 'payment_confirmed_at',
        'total_pages', 'selected_pages', 'sheets_per_copy', 'total_sheets',
        'price_per_sheet', 'total_cost', 'qr_preview', 'receipt_preview', 'file_link',
    )
    fieldsets = (
        ('Основное', {
            'fields': ('order_number', 'status', 'terminal', 'created_at')
        }),
        ('Клиент', {
            'fields': ('customer_name', 'customer_phone', 'customer_comment')
        }),
        ('Файл', {
            'fields': ('file', 'file_link', 'original_filename')
        }),
        ('Параметры печати', {
            'fields': ('copies', 'color', 'duplex', 'paper_format', 'page_range',
                       'orientation', 'even_only', 'odd_only')
        }),
        ('Расчёт', {
            'fields': ('total_pages', 'selected_pages', 'sheets_per_copy',
                       'total_sheets', 'price_per_sheet', 'total_cost')
        }),
        ('Оплата', {
            'fields': ('payment_receipt', 'receipt_preview', 'payment_amount',
                       'payment_confirmed_at', 'transaction_id', 'qr_preview')
        }),
        ('Ошибки', {
            'fields': ('error_message', 'printed_at'),
            'classes': ('collapse',),
        }),
    )

    actions = ['mark_paid', 'mark_queued', 'mark_cancelled', 'resend_to_queue']

    def colored_status(self, obj):
        colors = {
            'created': '#6c757d',
            'calculated': '#17a2b8',
            'awaiting_payment': '#ffc107',
            'receipt_uploaded': '#fd7e14',
            'paid': '#007bff',
            'queued': '#6610f2',
            'printing': '#17a2b8',
            'printed': '#28a745',
            'error': '#dc3545',
            'cancelled': '#343a40',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="color:white;background:{};padding:2px 8px;border-radius:4px;">{}</span>',
            color, obj.get_status_display_ru()
        )
    colored_status.short_description = 'Статус'

    def file_link(self, obj):
        if obj.file:
            return format_html('<a href="{}" target="_blank">Скачать файл</a>', obj.file.url)
        return '—'
    file_link.short_description = 'Ссылка на файл'

    def qr_preview(self, obj):
        if obj.qr_code:
            return format_html('<img src="{}" width="150">', obj.qr_code.url)
        return '—'
    qr_preview.short_description = 'QR-код'

    def receipt_preview(self, obj):
        if obj.payment_receipt:
            return format_html('<a href="{}" target="_blank"><img src="{}" width="200"></a>',
                               obj.payment_receipt.url, obj.payment_receipt.url)
        return '—'
    receipt_preview.short_description = 'Чек'

    def actions_column(self, obj):
        url = reverse('admin:orders_order_change', args=[obj.pk])
        return format_html('<a href="{}">Открыть</a>', url)
    actions_column.short_description = ''

    @admin.action(description='✅ Подтвердить оплату и поставить в очередь')
    def mark_paid(self, request, queryset):
        eligible = queryset.filter(status__in=['awaiting_payment', 'receipt_uploaded'])
        count = 0
        now = timezone.now()
        for order in eligible:
            order.status = 'queued'
            order.payment_confirmed_at = now
            order.save(update_fields=['status', 'payment_confirmed_at'])
            # Deduct paper stock
            try:
                stock = PaperStock.objects.get(paper_format=order.paper_format)
                stock.sheets_available = max(0, stock.sheets_available - order.total_sheets)
                stock.save(update_fields=['sheets_available'])
            except PaperStock.DoesNotExist:
                pass
            count += 1
        self.message_user(request, f'Оплата подтверждена, в очереди: {count} заказов.')

    @admin.action(description='🖨 Поставить в очередь (queued)')
    def mark_queued(self, request, queryset):
        updated = queryset.filter(status='paid').update(status='queued')
        self.message_user(request, f'В очереди: {updated} заказов.')

    @admin.action(description='❌ Отменить заказы')
    def mark_cancelled(self, request, queryset):
        updated = queryset.exclude(status__in=['printed', 'cancelled']).update(status='cancelled')
        self.message_user(request, f'Отменено: {updated} заказов.')

    @admin.action(description='🔁 Повторно в очередь')
    def resend_to_queue(self, request, queryset):
        updated = queryset.filter(status__in=['error', 'cancelled']).update(status='queued', error_message='')
        self.message_user(request, f'Повторно в очереди: {updated} заказов.')

    def get_urls(self):
        urls = super().get_urls()
        custom = [path('statistics/', self.admin_site.admin_view(self.statistics_view), name='orders_statistics')]
        return custom + urls

    def statistics_view(self, request):
        today = timezone.now().date()
        orders_today = Order.objects.filter(created_at__date=today)
        stats = {
            'total_orders_today': orders_today.count(),
            'sheets_today': orders_today.filter(status__in=['printed']).aggregate(s=Sum('total_sheets'))['s'] or 0,
            'revenue_paid': Order.objects.filter(status__in=['paid', 'queued', 'printing', 'printed']
                                                  ).aggregate(s=Sum('total_cost'))['s'] or 0,
            'revenue_cancelled': Order.objects.filter(status='cancelled'
                                                       ).aggregate(s=Sum('total_cost'))['s'] or 0,
            'errors_today': orders_today.filter(status='error').count(),
            'orders_by_status': list(
                Order.objects.values('status').annotate(count=Count('id')).order_by('-count')
            ),
            'recent_orders': Order.objects.select_related().order_by('-created_at')[:20],
        }
        context = {
            **self.admin_site.each_context(request),
            'title': 'Статистика',
            'stats': stats,
        }
        return TemplateResponse(request, 'admin/statistics.html', context)
