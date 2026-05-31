import uuid
from django.db import models


class PrinterTerminal(models.Model):
    name = models.CharField('Название', max_length=100)
    token = models.UUIDField('Токен', default=uuid.uuid4, unique=True, editable=False)

    # Location
    address = models.CharField('Адрес', max_length=300)
    latitude = models.DecimalField('Широта', max_digits=9, decimal_places=6, default=42.870000)
    longitude = models.DecimalField('Долгота', max_digits=9, decimal_places=6, default=74.590000)
    description = models.TextField('Описание / режим работы', blank=True)
    photo = models.ImageField('Фото точки', upload_to='terminals/', blank=True)

    # Agent settings
    server_url = models.CharField(
        'URL сервера', max_length=300, blank=True,
        help_text='Например: http://192.168.1.100 или https://yoursite.com'
    )
    system_printer_name = models.CharField(
        'Имя принтера в системе', max_length=200, blank=True,
        help_text='Оставьте пустым — будет использоваться принтер по умолчанию. '
                  'Узнать: Windows → "lpstat -p", Mac/Linux → "lpstat -p"'
    )
    poll_interval = models.PositiveIntegerField(
        'Интервал опроса (сек)', default=10,
        help_text='Как часто агент проверяет новые задания'
    )

    # Status
    is_active = models.BooleanField('Принимает заказы', default=True)
    is_online = models.BooleanField('Онлайн', default=False)
    last_seen = models.DateTimeField('Последний раз в сети', null=True, blank=True)

    class Meta:
        verbose_name = 'Принтер'
        verbose_name_plural = 'Принтеры'
        ordering = ['name']

    def __str__(self):
        status = '🟢' if self.is_online else '🔴'
        return f'{status} {self.name} — {self.address}'

    def to_map_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'address': self.address,
            'description': self.description,
            'lat': float(self.latitude),
            'lng': float(self.longitude),
            'is_online': self.is_online,
            'photo': self.photo.url if self.photo else None,
        }

    def get_config_dict(self, request=None):
        server = self.server_url
        if not server and request:
            server = request.build_absolute_uri('/').rstrip('/')
        return {
            'server_url': server or 'http://localhost',
            'token': str(self.token),
            'printer_id': self.id,
            'printer_name': self.name,
            'system_printer': self.system_printer_name or '',
            'poll_interval': self.poll_interval,
        }
