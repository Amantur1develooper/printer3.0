import uuid
from django.db import models
from django.utils import timezone
from django.conf import settings


class PrintTariff(models.Model):
    PAPER_FORMAT_CHOICES = [('A4', 'A4'), ('A3', 'A3')]
    COLOR_CHOICES = [('bw', 'Чёрно-белая'), ('color', 'Цветная')]

    terminal = models.ForeignKey(
        'printers.PrinterTerminal',
        verbose_name='Принтер',
        on_delete=models.CASCADE,
        related_name='tariffs',
    )
    paper_format = models.CharField('Формат', max_length=4, choices=PAPER_FORMAT_CHOICES, default='A4')
    color = models.CharField('Цвет', max_length=10, choices=COLOR_CHOICES, default='bw')
    duplex = models.BooleanField('Двусторонняя', default=False)
    price_per_sheet = models.DecimalField('Цена за лист (сом)', max_digits=8, decimal_places=2)
    is_active = models.BooleanField('Активен', default=True)

    class Meta:
        verbose_name = 'Тариф'
        verbose_name_plural = 'Тарифы'
        unique_together = ('terminal', 'paper_format', 'color', 'duplex')

    def __str__(self):
        side = 'двусторонняя' if self.duplex else 'односторонняя'
        color_label = dict(self.COLOR_CHOICES).get(self.color, self.color)
        return f'{self.paper_format} {color_label} {side} — {self.price_per_sheet} сом'


class PaperStock(models.Model):
    PAPER_FORMAT_CHOICES = [('A4', 'A4'), ('A3', 'A3')]

    terminal = models.ForeignKey(
        'printers.PrinterTerminal',
        verbose_name='Принтер',
        on_delete=models.CASCADE,
        related_name='paper_stocks',
    )
    paper_format = models.CharField('Формат', max_length=4, choices=PAPER_FORMAT_CHOICES, default='A4')
    sheets_available = models.IntegerField('Листов в наличии', default=0)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Остаток бумаги'
        verbose_name_plural = 'Остатки бумаги'
        unique_together = ('terminal', 'paper_format')

    def __str__(self):
        return f'{self.terminal.name} / {self.paper_format}: {self.sheets_available} листов'


class Order(models.Model):
    STATUS_CHOICES = [
        ('created', 'Создан'),
        ('calculated', 'Рассчитан'),
        ('awaiting_payment', 'Ожидает оплаты'),
        ('receipt_uploaded', 'Чек загружен'),
        ('paid', 'Оплачен'),
        ('queued', 'В очереди печати'),
        ('printing', 'Печатается'),
        ('printed', 'Распечатан'),
        ('error', 'Ошибка'),
        ('cancelled', 'Отменён'),
    ]

    COLOR_CHOICES = [('bw', 'Чёрно-белая'), ('color', 'Цветная')]
    ORIENTATION_CHOICES = [
        ('as_is', 'Как в документе'),
        ('portrait', 'Портрет'),
        ('landscape', 'Альбом'),
    ]
    PAPER_FORMAT_CHOICES = [('A4', 'A4'), ('A3', 'A3')]

    order_number = models.CharField('Номер заказа', max_length=30, unique=True, editable=False)

    # Printer terminal
    terminal = models.ForeignKey(
        'printers.PrinterTerminal',
        verbose_name='Принтер',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='orders',
    )

    # Customer
    customer_name = models.CharField('Имя', max_length=100)
    customer_phone = models.CharField('Телефон', max_length=20)
    customer_comment = models.TextField('Комментарий', blank=True)

    # File
    file = models.FileField('Файл', upload_to='uploads/%Y/%m/%d/')
    original_filename = models.CharField('Исходное имя файла', max_length=255)

    # Print parameters
    copies = models.PositiveIntegerField('Количество копий', default=1)
    color = models.CharField('Цвет', max_length=10, choices=COLOR_CHOICES, default='bw')
    duplex = models.BooleanField('Двусторонняя', default=False)
    paper_format = models.CharField('Формат бумаги', max_length=4, choices=PAPER_FORMAT_CHOICES, default='A4')
    page_range = models.CharField('Диапазон страниц', max_length=100, blank=True,
                                   help_text='Например: 1-5,7,9-12. Пусто = все страницы.')
    orientation = models.CharField('Ориентация', max_length=20, choices=ORIENTATION_CHOICES, default='as_is')
    even_only = models.BooleanField('Только чётные', default=False)
    odd_only = models.BooleanField('Только нечётные', default=False)

    # Calculated
    total_pages = models.PositiveIntegerField('Всего страниц в файле', default=0)
    selected_pages = models.PositiveIntegerField('Выбрано страниц', default=0)
    sheets_per_copy = models.PositiveIntegerField('Листов на копию', default=0)
    total_sheets = models.PositiveIntegerField('Всего листов', default=0)
    price_per_sheet = models.DecimalField('Цена за лист', max_digits=8, decimal_places=2, default=0)
    total_cost = models.DecimalField('Итого (сом)', max_digits=10, decimal_places=2, default=0)

    # Payment
    status = models.CharField('Статус', max_length=20, choices=STATUS_CHOICES, default='created')
    payment_receipt = models.ImageField('Чек оплаты', upload_to='receipts/%Y/%m/%d/', blank=True)
    payment_amount = models.DecimalField('Оплачено', max_digits=10, decimal_places=2, null=True, blank=True)
    payment_confirmed_at = models.DateTimeField('Подтверждено', null=True, blank=True)
    transaction_id = models.CharField('ID транзакции', max_length=100, blank=True)

    # QR code
    qr_code = models.ImageField('QR-код', upload_to='qrcodes/', blank=True)

    # Timestamps
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    printed_at = models.DateTimeField('Распечатан', null=True, blank=True)
    error_message = models.TextField('Сообщение об ошибке', blank=True)

    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'
        ordering = ['-created_at']

    def __str__(self):
        return f'Заказ {self.order_number} — {self.customer_name}'

    def save(self, *args, **kwargs):
        if not self.order_number:
            today = timezone.now().strftime('%Y%m%d')
            last = Order.objects.filter(order_number__startswith=f'OP-{today}-').order_by('order_number').last()
            if last:
                seq = int(last.order_number.split('-')[-1]) + 1
            else:
                seq = 1
            self.order_number = f'OP-{today}-{seq:04d}'
        super().save(*args, **kwargs)

    def get_status_color(self):
        colors = {
            'created': 'secondary',
            'calculated': 'info',
            'awaiting_payment': 'warning',
            'receipt_uploaded': 'warning',
            'paid': 'primary',
            'queued': 'primary',
            'printing': 'info',
            'printed': 'success',
            'error': 'danger',
            'cancelled': 'dark',
        }
        return colors.get(self.status, 'secondary')

    def get_status_display_ru(self):
        return dict(self.STATUS_CHOICES).get(self.status, self.status)
