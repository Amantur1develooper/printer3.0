#!/bin/bash
# Первоначальная настройка проекта

set -e

echo "=== Настройка Онлайн Принтер ==="

# Копируем .env
if [ ! -f .env ]; then
    cp .env.example .env
    echo "[*] Создан файл .env — отредактируйте его перед запуском!"
fi

# Запускаем контейнеры
docker compose up -d --build

echo "[*] Ждём запуска базы данных..."
sleep 8

# Миграции
docker compose exec web python manage.py migrate

# Создаём суперпользователя
echo ""
echo "[*] Создаём суперпользователя для админки:"
docker compose exec web python manage.py createsuperuser

# Загружаем начальные тарифы и бумагу
docker compose exec web python manage.py shell -c "
from orders.models import PrintTariff, PaperStock

# Тарифы
tariffs = [
    ('A4', 'bw',    False, 5),
    ('A4', 'bw',    True,  4),
    ('A4', 'color', False, 15),
    ('A4', 'color', True,  12),
]
for fmt, clr, dup, price in tariffs:
    PrintTariff.objects.get_or_create(
        paper_format=fmt, color=clr, duplex=dup,
        defaults={'price_per_sheet': price, 'is_active': True}
    )
print('Тарифы созданы')

# Бумага
PaperStock.objects.get_or_create(paper_format='A4', defaults={'sheets_available': 500})
PaperStock.objects.get_or_create(paper_format='A3', defaults={'sheets_available': 100})
print('Остатки бумаги созданы')
"

echo ""
echo "=== Готово! ==="
echo "Сайт доступен по адресу: http://localhost"
echo "Админка: http://localhost/admin"
echo ""
echo "Для запуска клиента принтера на ноутбуке:"
echo "  pip install requests"
echo "  python printer_client.py --server http://ВАШ-СЕРВЕР --token <токен-из-админки>"
