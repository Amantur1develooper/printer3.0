import json
import os
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.utils import timezone

from .models import PrinterTerminal
from orders.models import Order


def get_terminal(request):
    """Authenticate terminal by token from Authorization header or ?token= param."""
    token = request.GET.get('token') or request.headers.get('X-Terminal-Token')
    if not token:
        return None
    try:
        terminal = PrinterTerminal.objects.get(token=token)
        terminal.is_online = True
        terminal.last_seen = timezone.now()
        terminal.save(update_fields=['is_online', 'last_seen'])
        return terminal
    except PrinterTerminal.DoesNotExist:
        return None


# ── Dashboard ────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    terminals = PrinterTerminal.objects.prefetch_related('paper_stocks', 'tariffs').all()
    terminal_data = []
    for t in terminals:
        queued  = Order.objects.filter(terminal=t, status='queued').count()
        printing = Order.objects.filter(terminal=t, status='printing').count()
        today   = Order.objects.filter(terminal=t, status='printed',
                                       printed_at__date=timezone.localdate()).count()
        terminal_data.append({
            'terminal': t,
            'queued': queued,
            'printing': printing,
            'today': today,
        })
    return render(request, 'dashboard/index.html', {'terminal_data': terminal_data})


@login_required
def download_config(request, terminal_id):
    terminal = get_object_or_404(PrinterTerminal, id=terminal_id)
    config = terminal.get_config_dict(request)
    response = HttpResponse(
        json.dumps(config, ensure_ascii=False, indent=2),
        content_type='application/json',
    )
    response['Content-Disposition'] = 'attachment; filename="config.json"'
    return response


@login_required
def download_agent(request, terminal_id):
    agent_path = os.path.join(os.path.dirname(__file__), 'agent_template.py')
    with open(agent_path, encoding='utf-8') as f:
        content = f.read()
    response = HttpResponse(content, content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="agent.py"'
    return response


# ── Printer API ───────────────────────────────────────────────────────

@csrf_exempt
def jobs_list(request):
    """
    GET /api/printer/jobs/?token=<uuid>
    Returns next queued job for the terminal.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'GET required'}, status=405)

    terminal = get_terminal(request)
    if not terminal:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    job = Order.objects.filter(status='queued').order_by('created_at').first()
    if not job:
        return JsonResponse({'jobs': []})

    return JsonResponse({
        'jobs': [{
            'id': job.id,
            'order_number': job.order_number,
            'file_url': request.build_absolute_uri(job.file.url),
            'original_filename': job.original_filename,
            'copies': job.copies,
            'color': job.color,
            'duplex': job.duplex,
            'paper_format': job.paper_format,
            'page_range': job.page_range,
            'orientation': job.orientation,
            'even_only': job.even_only,
            'odd_only': job.odd_only,
            'total_sheets': job.total_sheets,
        }]
    })


@csrf_exempt
def job_pickup(request, order_id):
    """
    POST /api/printer/jobs/<order_id>/pickup/?token=<uuid>
    Terminal picks up the job — status -> printing.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    terminal = get_terminal(request)
    if not terminal:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        order = Order.objects.get(id=order_id, status='queued')
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Job not found or already taken'}, status=404)

    order.status = 'printing'
    order.save(update_fields=['status'])
    return JsonResponse({'ok': True, 'order_number': order.order_number})


@csrf_exempt
def job_complete(request, order_id):
    """
    POST /api/printer/jobs/<order_id>/complete/?token=<uuid>
    Terminal reports job done — status -> printed.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    terminal = get_terminal(request)
    if not terminal:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        order = Order.objects.get(id=order_id, status='printing')
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Job not found'}, status=404)

    order.status = 'printed'
    order.printed_at = timezone.now()
    order.save(update_fields=['status', 'printed_at'])
    return JsonResponse({'ok': True})


@csrf_exempt
def job_error(request, order_id):
    """
    POST /api/printer/jobs/<order_id>/error/?token=<uuid>
    Body: {"message": "описание ошибки"}
    Terminal reports an error.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    terminal = get_terminal(request)
    if not terminal:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        order = Order.objects.get(id=order_id, status='printing')
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Job not found'}, status=404)

    try:
        body = json.loads(request.body)
        msg = body.get('message', 'Неизвестная ошибка')
    except (json.JSONDecodeError, AttributeError):
        msg = 'Ошибка без описания'

    order.status = 'error'
    order.error_message = msg
    order.save(update_fields=['status', 'error_message'])
    return JsonResponse({'ok': True})
