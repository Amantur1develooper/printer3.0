#!/usr/bin/env python3
"""
Клиент для ноутбука с принтером.
Запускать на ноутбуке, подключённом к принтеру.

Использование:
    python printer_client.py --server http://ваш-сервер.com --token <ваш-токен>

Токен берётся из Django Admin → Терминалы принтеров.
"""
import argparse
import os
import sys
import time
import tempfile
import subprocess
import platform
import requests

POLL_INTERVAL = 10  # секунд между запросами к серверу


def get_jobs(server, token):
    try:
        r = requests.get(f'{server}/api/printer/jobs/', params={'token': token}, timeout=15)
        r.raise_for_status()
        return r.json().get('jobs', [])
    except Exception as e:
        print(f'[!] Ошибка получения очереди: {e}')
        return []


def pickup_job(server, token, job_id):
    try:
        r = requests.post(f'{server}/api/printer/jobs/{job_id}/pickup/', params={'token': token}, timeout=15)
        return r.status_code == 200
    except Exception as e:
        print(f'[!] Ошибка захвата задания: {e}')
        return False


def complete_job(server, token, job_id):
    try:
        requests.post(f'{server}/api/printer/jobs/{job_id}/complete/', params={'token': token}, timeout=15)
    except Exception as e:
        print(f'[!] Ошибка подтверждения: {e}')


def report_error(server, token, job_id, message):
    try:
        requests.post(
            f'{server}/api/printer/jobs/{job_id}/error/',
            params={'token': token},
            json={'message': message},
            timeout=15,
        )
    except Exception as e:
        print(f'[!] Ошибка отправки ошибки: {e}')


def download_file(url, dest_path):
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    with open(dest_path, 'wb') as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)


def build_print_command(file_path, job):
    """Build OS-specific print command."""
    system = platform.system()
    copies = job.get('copies', 1)
    duplex = job.get('duplex', False)
    color = job.get('color', 'bw')
    paper = job.get('paper_format', 'A4')
    orientation = job.get('orientation', 'as_is')

    if system == 'Linux' or system == 'Darwin':
        cmd = ['lp', '-n', str(copies)]
        if duplex:
            cmd += ['-o', 'sides=two-sided-long-edge']
        else:
            cmd += ['-o', 'sides=one-sided']
        if color == 'bw':
            cmd += ['-o', 'ColorModel=Gray']
        if orientation == 'portrait':
            cmd += ['-o', 'orientation-requested=3']
        elif orientation == 'landscape':
            cmd += ['-o', 'orientation-requested=4']
        if paper == 'A4':
            cmd += ['-o', 'media=A4']
        elif paper == 'A3':
            cmd += ['-o', 'media=A3']
        cmd.append(file_path)
        return cmd

    elif system == 'Windows':
        # Windows: use Adobe Reader or SumatraPDF for PDF printing
        sumatrapdf = r'C:\Program Files\SumatraPDF\SumatraPDF.exe'
        if os.path.exists(sumatrapdf):
            cmd = [
                sumatrapdf,
                '-print-to-default',
                '-print-settings', f'{"duplex" if duplex else "simplex"},{"bw" if color == "bw" else "color"},{copies}x',
                file_path,
            ]
            return cmd
        # Fallback: shell print
        return ['rundll32', 'printui.dll,PrintUIEntry', '/p', f'/n "{file_path}"']

    else:
        raise RuntimeError(f'Неизвестная ОС: {system}')


def process_job(server, token, job):
    job_id = job['id']
    order_number = job['order_number']
    file_url = job['file_url']
    print(f'[*] Задание {order_number} (#{job_id}): скачиваем файл...')

    if not pickup_job(server, token, job_id):
        print(f'[!] Не удалось захватить задание {job_id} — возможно уже занято.')
        return

    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        download_file(file_url, tmp_path)
        print(f'[*] Файл скачан: {tmp_path}')

        cmd = build_print_command(tmp_path, job)
        print(f'[*] Команда печати: {" ".join(cmd)}')

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if result.returncode != 0:
            err_msg = result.stderr or result.stdout or 'Ошибка печати'
            print(f'[!] Ошибка: {err_msg}')
            report_error(server, token, job_id, err_msg[:500])
        else:
            print(f'[+] Заказ {order_number} успешно отправлен на печать!')
            complete_job(server, token, job_id)

    except subprocess.TimeoutExpired:
        msg = 'Таймаут печати (120 сек)'
        print(f'[!] {msg}')
        report_error(server, token, job_id, msg)
    except Exception as e:
        msg = str(e)
        print(f'[!] Неожиданная ошибка: {msg}')
        report_error(server, token, job_id, msg[:500])
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser(description='Клиент принтера для онлайн-принтера')
    parser.add_argument('--server', required=True, help='URL сервера, например http://192.168.1.10')
    parser.add_argument('--token', required=True, help='Токен терминала из админки')
    parser.add_argument('--interval', type=int, default=POLL_INTERVAL, help='Интервал опроса (сек)')
    args = parser.parse_args()

    server = args.server.rstrip('/')
    print(f'[*] Клиент принтера запущен. Сервер: {server}')
    print(f'[*] Опрос каждые {args.interval} секунд. Ctrl+C для остановки.\n')

    while True:
        jobs = get_jobs(server, args.token)
        if jobs:
            process_job(server, args.token, jobs[0])
        else:
            print(f'[.] Очередь пуста. Жду {args.interval}с...', end='\r')

        time.sleep(args.interval)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n[*] Остановлено.')
        sys.exit(0)
