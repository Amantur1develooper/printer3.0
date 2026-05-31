from django.contrib import admin
from django.utils.html import format_html
from .models import PrinterTerminal


class TariffInline(admin.TabularInline):
    from orders.models import PrintTariff
    model = PrintTariff
    extra = 4
    fields = ('paper_format', 'color', 'duplex', 'price_per_sheet', 'is_active')
    verbose_name = 'Тариф'
    verbose_name_plural = 'Тарифы (цены за лист)'

    def get_queryset(self, request):
        from orders.models import PrintTariff
        self.model = PrintTariff
        return super().get_queryset(request)


class PaperStockInline(admin.TabularInline):
    from orders.models import PaperStock
    model = PaperStock
    extra = 1
    fields = ('paper_format', 'sheets_available')
    verbose_name = 'Бумага'
    verbose_name_plural = 'Остатки бумаги'

    def get_queryset(self, request):
        from orders.models import PaperStock
        self.model = PaperStock
        return super().get_queryset(request)


@admin.register(PrinterTerminal)
class PrinterTerminalAdmin(admin.ModelAdmin):
    list_display = ('name', 'address', 'is_active', 'is_online', 'paper_summary', 'last_seen', 'map_link')
    list_editable = ('is_active',)
    readonly_fields = ('token', 'is_online', 'last_seen', 'map_preview')
    inlines = [TariffInline, PaperStockInline]

    fieldsets = (
        ('Основное', {
            'fields': ('name', 'address', 'description', 'photo', 'is_active'),
        }),
        ('Положение на карте', {
            'description': (
                'Найдите координаты: откройте 2gis.kg, нажмите правой кнопкой на точку → скопируйте. '
                'Или используйте latlong.net'
            ),
            'fields': ('latitude', 'longitude', 'map_preview'),
        }),
        ('Агент печати', {
            'description': 'Скачайте config.json и agent.py в личном кабинете: /dashboard/',
            'fields': ('server_url', 'system_printer_name', 'poll_interval'),
        }),
        ('Токен / статус', {
            'fields': ('token', 'is_online', 'last_seen'),
            'classes': ('collapse',),
        }),
    )

    def paper_summary(self, obj):
        stocks = obj.paper_stocks.all()
        if not stocks:
            return format_html('<span style="color:gray">—</span>')
        parts = []
        for s in stocks:
            color = 'green' if s.sheets_available > 50 else ('orange' if s.sheets_available > 5 else 'red')
            parts.append(f'<span style="color:{color}">{s.paper_format}: {s.sheets_available}</span>')
        return format_html(' | '.join(parts))
    paper_summary.short_description = 'Бумага (листов)'

    def map_link(self, obj):
        return format_html(
            '<a href="https://www.openstreetmap.org/?mlat={}&mlon={}&zoom=17" target="_blank">📍</a>',
            obj.latitude, obj.longitude
        )
    map_link.short_description = ''

    def map_preview(self, obj):
        if obj.pk:
            return format_html(
                '<a href="https://www.openstreetmap.org/?mlat={lat}&mlon={lng}&zoom=17" target="_blank">'
                'Широта: {lat}, Долгота: {lng} — проверить на карте</a>',
                lat=obj.latitude, lng=obj.longitude
            )
        return 'Сохраните чтобы увидеть предпросмотр'
    map_preview.short_description = 'Координаты'
