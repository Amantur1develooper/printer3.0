#!/bin/bash
# Локальный запуск без Docker (для разработки и теста)

set -e

cd "$(dirname "$0")"

# 1. Создаём виртуальное окружение если нет
if [ ! -d "venv" ]; then
    echo "[*] Создаём виртуальное окружение..."
    python3 -m venv venv
fi

# 2. Активируем
source venv/bin/activate

# 3. Устанавливаем пакеты
echo "[*] Устанавливаем зависимости..."
pip install -q -r requirements.txt

# 4. Создаём .env если нет
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "[*] Создан .env (SQLite, DEBUG=True) — можно сразу запускать"
fi

# 5. Миграции
echo "[*] Создаём и применяем миграции..."
python manage.py makemigrations orders printers --no-input
python manage.py migrate --no-input

# 6. Создаём суперпользователя если нет
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@local.com', 'admin123')
    print('[*] Создан суперпользователь: admin / admin123')
else:
    print('[*] Суперпользователь admin уже существует')
"

# 7. Создаём начальные тарифы и остатки бумаги
python manage.py shell -c "
from orders.models import PrintTariff, PaperStock

tariffs = [
    ('A4', 'bw',    False, 5),
    ('A4', 'bw',    True,  4),
    ('A4', 'color', False, 15),
    ('A4', 'color', True,  12),
]
for fmt, clr, dup, price in tariffs:
    obj, created = PrintTariff.objects.get_or_create(
        paper_format=fmt, color=clr, duplex=dup,
        defaults={'price_per_sheet': price, 'is_active': True}
    )
    if created:
        print(f'[*] Тариф создан: {fmt} {clr} duplex={dup} = {price} сом')

PaperStock.objects.get_or_create(paper_format='A4', defaults={'sheets_available': 500})
PaperStock.objects.get_or_create(paper_format='A3', defaults={'sheets_available': 100})
print('[*] Остатки бумаги OK')
"

echo ""
echo "======================================="
echo "  Сайт:    http://127.0.0.1:8000"
echo "  Админка: http://127.0.0.1:8000/admin"
echo "  Логин:   admin / admin123"
echo "======================================="
echo ""

# 8. Запускаем сервер
python manage.py runserver
