#!/usr/bin/env python3
"""
Online Printer — Agent
======================
Запуск:
    python agent.py

Агент читает config.json из той же папки,
постоянно опрашивает сервер и автоматически печатает документы.

Требования:
    pip install requests

Windows: установите SumatraPDF → https://www.sumatrapdfreader.org/
Mac/Linux: используется встроенная команда lp
"""

import json
import os
import sys
import time
import platform
import tempfile
import subprocess
import logging
from pathlib import Path

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-7s  %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('agent.log', encoding='utf-8'),
    ]
)
log = logging.getLogger('agent')

# ── Config ───────────────────────────────────────────────────────────
CONFIG_FILE = Path(__file__).parent / 'config.json'

def load_config():
    if not CONFIG_FILE.exists():
        log.error(f'Файл config.json не найден рядом с agent.py')
        log.error('Скачайте config.json в личном кабинете: /dashboard/')
        sys.exit(1)
    with open(CONFIG_FILE, encoding='utf-8') as f:
        return json.load(f)

# ── HTTP helpers ──────────────────────────────────────────────────────
def api_get(url, params=None, timeout=15):
    import requests
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f'GET {url} → {e}')
        return None

def api_post(url, params=None, json_data=None, timeout=15):
    import requests
    try:
        r = requests.post(url, params=params, json=json_data, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f'POST {url} → {e}')
        return None

def download_file(url, dest, timeout=60):
    import requests
    r = requests.get(url, stream=True, timeout=timeout)
    r.raise_for_status()
    with open(dest, 'wb') as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)

# ── Print ─────────────────────────────────────────────────────────────
def build_print_cmd(filepath, job, system_printer):
    copies   = job.get('copies', 1)
    duplex   = job.get('duplex', False)
    color    = job.get('color', 'bw')
    paper    = job.get('paper_format', 'A4')
    orient   = job.get('orientation', 'as_is')
    system   = platform.system()

    if system in ('Linux', 'Darwin'):
        cmd = ['lp']
        if system_printer:
            cmd += ['-d', system_printer]
        cmd += ['-n', str(copies)]
        cmd += ['-o', 'sides=' + ('two-sided-long-edge' if duplex else 'one-sided')]
        if color == 'bw':
            cmd += ['-o', 'ColorModel=Gray']
        if paper == 'A4':
            cmd += ['-o', 'media=A4']
        elif paper == 'A3':
            cmd += ['-o', 'media=A3']
        if orient == 'portrait':
            cmd += ['-o', 'orientation-requested=3']
        elif orient == 'landscape':
            cmd += ['-o', 'orientation-requested=4']
        cmd.append(filepath)
        return cmd

    elif system == 'Windows':
        # SumatraPDF — лучший вариант для тихой печати PDF на Windows
        sumatra_paths = [
            r'C:\Program Files\SumatraPDF\SumatraPDF.exe',
            r'C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe',
            str(Path.home() / 'AppData/Local/SumatraPDF/SumatraPDF.exe'),
        ]
        sumatra = next((p for p in sumatra_paths if os.path.exists(p)), None)

        settings_parts = []
        settings_parts.append('duplex' if duplex else 'simplex')
        settings_parts.append('bw' if color == 'bw' else 'color')
        settings_parts.append(f'{copies}x')
        settings = ','.join(settings_parts)

        if sumatra:
            if system_printer:
                cmd = [sumatra, f'-print-to', system_printer,
                       '-print-settings', settings, '-silent', filepath]
            else:
                cmd = [sumatra, '-print-to-default',
                       '-print-settings', settings, '-silent', filepath]
        else:
            # Fallback: PowerShell Print verb (без настроек копий/дуплекса)
            log.warning('SumatraPDF не найден. Используется PowerShell-печать (без настроек).')
            log.warning('Для полного контроля установите SumatraPDF: https://www.sumatrapdfreader.org/')
            cmd = [
                'powershell', '-NoProfile', '-NonInteractive', '-Command',
                f'Start-Process -FilePath "{filepath}" -Verb Print -Wait'
            ]
        return cmd

    else:
        raise RuntimeError(f'Неизвестная ОС: {system}')


def print_job(job, system_printer):
    order_number = job['order_number']
    file_url     = job['file_url']

    log.info(f'📥 Скачиваем файл для заказа {order_number} ...')

    suffix = '.pdf'
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name

    try:
        download_file(file_url, tmp_path)
        log.info(f'✅ Файл скачан ({Path(tmp_path).stat().st_size // 1024} КБ)')

        cmd = build_print_cmd(tmp_path, job, system_printer)
        log.info(f'🖨  Отправляем на печать: {" ".join(str(c) for c in cmd)}')

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if result.returncode != 0:
            err = result.stderr or result.stdout or 'Ошибка печати'
            log.error(f'❌ Ошибка: {err}')
            return False, err[:500]
        else:
            log.info(f'✅ Заказ {order_number} отправлен на принтер!')
            return True, None

    except subprocess.TimeoutExpired:
        msg = 'Таймаут печати (120 сек)'
        log.error(f'❌ {msg}')
        return False, msg
    except Exception as e:
        log.error(f'❌ {e}')
        return False, str(e)[:500]
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ── Main loop ─────────────────────────────────────────────────────────
def main():
    cfg = load_config()

    server   = cfg['server_url'].rstrip('/')
    token    = cfg['token']
    interval = cfg.get('poll_interval', 10)
    printer  = cfg.get('system_printer', '')
    name     = cfg.get('printer_name', 'Принтер')

    log.info('=' * 50)
    log.info(f'Online Printer Agent')
    log.info(f'Принтер : {name}')
    log.info(f'Сервер  : {server}')
    log.info(f'Интервал: {interval} сек')
    log.info(f'Система : {platform.system()} {platform.release()}')
    log.info('=' * 50)
    log.info('Агент запущен. Ctrl+C для остановки.\n')

    params = {'token': token}

    while True:
        try:
            data = api_get(f'{server}/api/printer/jobs/', params=params)

            if data is None:
                log.warning(f'Нет связи с сервером. Жду {interval}с...')
                time.sleep(interval)
                continue

            jobs = data.get('jobs', [])

            if not jobs:
                # Тихий режим — точка каждые 10 тиков
                print('.', end='', flush=True)
                time.sleep(interval)
                continue

            print()  # перенос строки после точек
            job = jobs[0]
            job_id = job['id']
            log.info(f'🔔 Новый заказ: {job["order_number"]} ({job["total_sheets"]} листов)')

            # Захватить задание
            picked = api_post(f'{server}/api/printer/jobs/{job_id}/pickup/', params=params)
            if not picked:
                log.warning('Не удалось захватить задание (уже взято?)')
                time.sleep(interval)
                continue

            # Печать
            ok, err_msg = print_job(job, printer)

            if ok:
                api_post(f'{server}/api/printer/jobs/{job_id}/complete/', params=params)
            else:
                api_post(f'{server}/api/printer/jobs/{job_id}/error/',
                         params=params, json_data={'message': err_msg})

        except KeyboardInterrupt:
            log.info('\n👋 Агент остановлен.')
            break
        except Exception as e:
            log.error(f'Неожиданная ошибка: {e}')
            time.sleep(interval)


if __name__ == '__main__':
    try:
        import requests  # noqa
    except ImportError:
        print('Установите requests:  pip install requests')
        sys.exit(1)
    main()
