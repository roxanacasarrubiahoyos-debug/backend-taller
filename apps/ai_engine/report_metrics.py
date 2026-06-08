"""
Métricas resumidas para reportes narrados por voz (admin y taller).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Sum
from django.utils import timezone

from apps.assignments.models import Assignment, AssignmentStatus
from apps.incidents.models import Incident, IncidentCycleMetric, IncidentStatus, IncidentType
from apps.payments.models import Payment, PaymentStatus
from apps.payments.reports_views import _decimal_to_float, _parse_dates, build_reports_payload
from apps.workshops.models import Workshop, WorkshopRating


def _label_map(choices) -> dict[str, str]:
    return {c[0]: c[1] for c in choices}


def _workshop_status_breakdown(assign_qs, status_labels: dict[str, str]) -> list[dict]:
    """Conteo por cada estado de asignación (incluye ceros)."""
    raw = {r['status']: r['count'] for r in assign_qs.values('status').annotate(count=Count('id'))}
    return [
        {
            'status': code,
            'status_label': status_labels.get(code, code),
            'count': raw.get(code, 0),
        }
        for code, _ in AssignmentStatus.choices
    ]


def _build_workshop_narrative(
    *,
    workshop: Workshop,
    kpis: dict,
    status_breakdown: list[dict],
    type_breakdown: list[dict],
    report_focus: str,
    dates_source: str,
    date_from: date,
    date_to: date,
    filters: dict,
) -> str:
    """Texto descriptivo en español para el dueño del taller."""
    parts: list[str] = []

    if report_focus == 'offered' and dates_source in ('none', 'default_month'):
        parts.append(
            f'En «{workshop.name}» tienes {kpis["offered_pending"]} incidente(s) disponible(s) '
            f'esperando tu respuesta (ofertas pendientes).'
        )
    elif dates_source in ('none', 'default_month'):
        parts.append(
            f'Resumen de «{workshop.name}»: {kpis["assignments_total"]} asignación(es) '
            f'en total (todos los estados, sin filtrar por fecha).'
        )
    else:
        parts.append(
            f'Resumen de «{workshop.name}» del {date_from.strftime("%d/%m/%Y")} '
            f'al {date_to.strftime("%d/%m/%Y")}: {kpis["assignments_total"]} asignación(es).'
        )

    status_bits = [
        f'{r["status_label"]}: {r["count"]}'
        for r in status_breakdown
        if r['count'] > 0
    ]
    if status_bits:
        parts.append('Desglose por estado de asignación: ' + '; '.join(status_bits) + '.')
    elif kpis['assignments_total'] == 0:
        parts.append('No hay asignaciones que coincidan con los filtros aplicados.')

    if type_breakdown:
        type_bits = [
            f'{r.get("type_label", r.get("incident_type", ""))}: {r["count"]}'
            for r in type_breakdown
            if r['count'] > 0
        ]
        if type_bits:
            parts.append('Por tipo de incidente: ' + '; '.join(type_bits) + '.')

    if report_focus in ('general', 'payments', '') or kpis['payments_count']:
        if kpis['payments_count']:
            parts.append(
                f'Ingresos en el período: {kpis["payments_count"]} pago(s), '
                f'neto Bs. {kpis["earnings_net_period"]} (bruto Bs. {kpis["earnings_gross_period"]}).'
            )

    if report_focus in ('general', 'technicians', ''):
        parts.append(
            f'Técnicos: {kpis["technicians_available"]} disponible(s) de {kpis["technicians_total"]} en tu equipo.'
        )

    if filters.get('assignment_status'):
        parts.append(f'Filtro aplicado: solo asignaciones en estado «{filters["assignment_status"]}».')
    if filters.get('incident_type'):
        parts.append(f'Filtro aplicado: solo incidentes tipo «{filters["incident_type"]}».')

    return ' '.join(parts)


def slim_admin_voice_metrics(request) -> dict:
    """Resumen de plataforma para narración admin (sin tablas voluminosas)."""
    payload = build_reports_payload(request)
    kpis = payload['kpis']
    charts = payload['charts']

    status_labels = _label_map(IncidentStatus.choices)
    type_labels = _label_map(IncidentType.choices)

    incidents_by_status = [
        {'status': status_labels.get(r['status'], r['status']), 'count': r['count']}
        for r in charts['incidents_by_status']
    ]
    incidents_by_type = [
        {'type': type_labels.get(r['incident_type'], r['incident_type']), 'count': r['count']}
        for r in charts['incidents_by_type'][:6]
    ]

    top_workshops = [
        {
            'name': r.get('assignment__workshop__name') or '—',
            'payments': r.get('payments_count', 0),
            'commission': str(r.get('commission') or '0'),
        }
        for r in payload.get('top_workshops', [])[:5]
    ]

    return {
        'audience': 'admin',
        'period': payload['meta'],
        'filters': payload.get('filters_applied', {}),
        'kpis': {
            'incidents_total': kpis['incidents_total'],
            'incidents_completed': kpis['incidents_completed'],
            'incidents_active': kpis['incidents_active'],
            'incidents_cancelled': kpis['incidents_cancelled'],
            'resolution_rate_pct': kpis['resolution_rate_pct'],
            'payments_settled_count': kpis['payments_settled_count'],
            'revenue_total': kpis['revenue_total'],
            'commission_total': kpis['commission_total'],
            'workshop_net_total': kpis['workshop_net_total'],
            'avg_assignment_seconds': kpis['avg_assignment_seconds'],
            'avg_arrival_seconds': kpis['avg_arrival_seconds'],
            'avg_resolution_seconds': kpis['avg_resolution_seconds'],
            'avg_rating': kpis['avg_rating'],
            'new_clients_in_period': kpis['new_clients_in_period'],
            'new_workshops_in_period': kpis['new_workshops_in_period'],
            'verified_workshops_total': kpis['verified_workshops_total'],
            'sla_compliance_pct': kpis.get('sla_compliance_pct'),
            'incidents_unattended': kpis.get('incidents_unattended'),
            'cancellation_rate_pct': kpis.get('cancellation_rate_pct'),
        },
        'incidents_by_status': incidents_by_status,
        'incidents_by_type': incidents_by_type,
        'top_workshops': top_workshops,
        'top_geo_zones': (charts.get('top_geo_zones') or [])[:3],
    }


def build_workshop_voice_metrics(request, workshop: Workshop) -> dict:
    """Métricas exclusivas del taller del dueño autenticado."""
    date_from, date_to = _parse_dates(request)
    status_labels = _label_map(AssignmentStatus.choices)
    type_labels = _label_map(IncidentType.choices)

    assign_qs = Assignment.objects.filter(
        workshop=workshop,
        incident__created_at__date__gte=date_from,
        incident__created_at__date__lte=date_to,
    )

    by_status = list(
        assign_qs.values('status').annotate(count=Count('id')).order_by('-count')
    )
    assignments_by_status = [
        {'status': status_labels.get(r['status'], r['status']), 'count': r['count']}
        for r in by_status
    ]

    by_type = list(
        assign_qs.values('incident__incident_type')
        .annotate(count=Count('id'))
        .order_by('-count')[:6]
    )
    incidents_by_type = [
        {
            'type': type_labels.get(r['incident__incident_type'], r['incident__incident_type']),
            'count': r['count'],
        }
        for r in by_type
    ]

    payments_qs = Payment.objects.filter(
        assignment__workshop=workshop,
        assignment__incident__created_at__date__gte=date_from,
        assignment__incident__created_at__date__lte=date_to,
        status__in=[PaymentStatus.CLIENT_PAID, PaymentStatus.COMMISSION_SETTLED],
    )
    pay_agg = payments_qs.aggregate(
        net=Sum('workshop_net_amount'),
        gross=Sum('total_amount'),
        count=Count('id'),
    )

    ratings_qs = WorkshopRating.objects.filter(
        workshop=workshop,
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    )
    rating_agg = ratings_qs.aggregate(avg=Avg('score'), count=Count('id'))

    cycle = IncidentCycleMetric.objects.filter(
        assignment__workshop=workshop,
        assignment__incident__created_at__date__gte=date_from,
        assignment__incident__created_at__date__lte=date_to,
    ).aggregate(
        avg_response=Avg('seconds_to_assignment'),
        avg_arrival=Avg('seconds_to_arrival'),
        avg_resolution=Avg('seconds_total_resolution'),
    )

    technicians_total = workshop.technicians.count()
    technicians_available = workshop.technicians.filter(is_available=True).count()

    offered = assign_qs.filter(status=AssignmentStatus.OFFERED).count()
    active = assign_qs.filter(
        status__in=[
            AssignmentStatus.ACCEPTED,
            AssignmentStatus.IN_ROUTE,
            AssignmentStatus.ARRIVED,
            AssignmentStatus.IN_SERVICE,
        ]
    ).count()
    completed = assign_qs.filter(status=AssignmentStatus.COMPLETED).count()
    rejected = assign_qs.filter(status=AssignmentStatus.REJECTED).count()

    sub = getattr(getattr(workshop, 'owner', None), 'subscription', None)
    subscription_status = getattr(sub, 'status', None) if sub else None
    subscription_operational = bool(sub and sub.is_operational)

    start_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    completed_this_month = Assignment.objects.filter(
        workshop=workshop,
        status=AssignmentStatus.COMPLETED,
        completed_at__gte=start_of_month,
    ).count()

    return {
        'audience': 'workshop_owner',
        'workshop': {
            'id': workshop.id,
            'name': workshop.name,
            'rating_avg': float(workshop.rating_avg or 0),
            'total_services_lifetime': workshop.total_services,
            'is_verified': workshop.is_verified,
        },
        'period': {
            'date_from': date_from.isoformat(),
            'date_to': date_to.isoformat(),
            'generated_at': timezone.now().isoformat(),
        },
        'kpis': {
            'assignments_total': assign_qs.count(),
            'offered_pending': offered,
            'active_services': active,
            'completed_in_period': completed,
            'rejected_in_period': rejected,
            'completed_this_month': completed_this_month,
            'payments_count': pay_agg['count'] or 0,
            'earnings_net_period': str(pay_agg['net'] or Decimal('0')),
            'earnings_gross_period': str(pay_agg['gross'] or Decimal('0')),
            'ratings_count': rating_agg['count'] or 0,
            'ratings_avg_period': (
                round(float(rating_agg['avg']), 2) if rating_agg['avg'] is not None else None
            ),
            'technicians_total': technicians_total,
            'technicians_available': technicians_available,
            'avg_response_seconds': _decimal_to_float(cycle['avg_response']),
            'avg_arrival_seconds': _decimal_to_float(cycle['avg_arrival']),
            'avg_resolution_seconds': _decimal_to_float(cycle['avg_resolution']),
            'subscription_status': subscription_status,
            'subscription_operational': subscription_operational,
        },
        'assignments_by_status': assignments_by_status,
        'incidents_by_type': incidents_by_type,
    }


def build_workshop_reports_payload(request, workshop: Workshop) -> dict:
    """Reporte completo del taller (preview + export Excel), solo datos de ese taller."""
    date_from, date_to = _parse_dates(request)
    status_labels = _label_map(AssignmentStatus.choices)
    type_labels = _label_map(IncidentType.choices)
    incident_status_labels = _label_map(IncidentStatus.choices)
    report_focus = request.query_params.get('report_focus') or ''
    dates_source = request.query_params.get('dates_source') or ''
    ast = request.query_params.get('assignment_status') or ''

    offered_pending = Assignment.objects.filter(
        workshop=workshop,
        status=AssignmentStatus.OFFERED,
    ).count()

    if report_focus == 'offered' and dates_source in ('none', 'default_month'):
        assign_qs = Assignment.objects.filter(
            workshop=workshop,
            status=AssignmentStatus.OFFERED,
        )
    elif report_focus == 'general' and dates_source in ('none', 'default_month') and not ast:
        assign_qs = Assignment.objects.filter(workshop=workshop)
    else:
        assign_qs = Assignment.objects.filter(
            workshop=workshop,
            offered_at__date__gte=date_from,
            offered_at__date__lte=date_to,
        )

    if ast:
        assign_qs = assign_qs.filter(status=ast)
    st = request.query_params.get('incident_status')
    if st:
        assign_qs = assign_qs.filter(incident__status=st)
    it = request.query_params.get('incident_type')
    if it:
        assign_qs = assign_qs.filter(incident__incident_type=it)

    assignments_by_status = _workshop_status_breakdown(assign_qs, status_labels)
    incidents_by_type_raw = list(
        assign_qs.values('incident__incident_type')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    incidents_by_type = [
        {
            'incident_type': r['incident__incident_type'],
            'type_label': type_labels.get(r['incident__incident_type'], r['incident__incident_type']),
            'count': r['count'],
        }
        for r in incidents_by_type_raw
    ]

    payments_qs = Payment.objects.filter(
        assignment__workshop=workshop,
        assignment__incident__created_at__date__gte=date_from,
        assignment__incident__created_at__date__lte=date_to,
        status__in=[PaymentStatus.CLIENT_PAID, PaymentStatus.COMMISSION_SETTLED],
    )
    ps = request.query_params.get('payment_status')
    if ps:
        payments_qs = payments_qs.filter(status=ps)

    pay_agg = payments_qs.aggregate(
        net=Sum('workshop_net_amount'),
        gross=Sum('total_amount'),
        count=Count('id'),
    )

    ratings_qs = WorkshopRating.objects.filter(
        workshop=workshop,
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    )
    rating_agg = ratings_qs.aggregate(avg=Avg('score'), count=Count('id'))

    cycle = IncidentCycleMetric.objects.filter(
        assignment__workshop=workshop,
        assignment__incident__created_at__date__gte=date_from,
        assignment__incident__created_at__date__lte=date_to,
    ).aggregate(
        avg_response=Avg('seconds_to_assignment'),
        avg_arrival=Avg('seconds_to_arrival'),
        avg_resolution=Avg('seconds_total_resolution'),
    )

    offered_in_period = assign_qs.filter(status=AssignmentStatus.OFFERED).count()
    active = assign_qs.filter(
        status__in=[
            AssignmentStatus.ACCEPTED,
            AssignmentStatus.IN_ROUTE,
            AssignmentStatus.ARRIVED,
            AssignmentStatus.IN_SERVICE,
        ]
    ).count()
    completed = assign_qs.filter(status=AssignmentStatus.COMPLETED).count()
    rejected = assign_qs.filter(status=AssignmentStatus.REJECTED).count()

    assignment_rows = list(
        assign_qs.select_related(
            'incident', 'incident__client__user', 'incident__vehicle', 'technician',
        )
        .order_by('-offered_at')[:500]
        .values(
            'id',
            'status',
            'incident_id',
            'incident__incident_type',
            'incident__status',
            'incident__priority',
            'incident__address_text',
            'offered_at',
            'accepted_at',
            'completed_at',
            'service_cost',
            'distance_km',
            'technician__name',
            'incident__client__user__first_name',
            'incident__client__user__last_name',
            'incident__vehicle__brand',
            'incident__vehicle__model',
        )
    )
    for row in assignment_rows:
        fn = row.pop('incident__client__user__first_name', '') or ''
        ln = row.pop('incident__client__user__last_name', '') or ''
        row['client_name'] = (fn + ' ' + ln).strip() or '—'
        row['vehicle_label'] = (
            f"{row.pop('incident__vehicle__brand', '') or ''} "
            f"{row.pop('incident__vehicle__model', '') or ''}".strip()
            or '—'
        )
        itype = row.pop('incident__incident_type', '')
        istatus = row.pop('incident__status', '')
        astatus = row.get('status', '')
        row['incident_type'] = itype
        row['incident_type_label'] = type_labels.get(itype, itype)
        row['incident_status'] = istatus
        row['incident_status_label'] = incident_status_labels.get(istatus, istatus)
        row['status_label'] = status_labels.get(astatus, astatus)
        row['priority'] = row.pop('incident__priority', None)
        row['address'] = (row.pop('incident__address_text', '') or '').strip() or None
        row['technician_name'] = row.pop('technician__name', None) or '—'
        sc = row.get('service_cost')
        if sc is not None:
            row['service_cost'] = str(sc)
        dk = row.get('distance_km')
        if dk is not None:
            row['distance_km'] = str(dk)
        for ts in ('offered_at', 'accepted_at', 'completed_at'):
            val = row.get(ts)
            row[ts] = val.isoformat() if val else None

    payment_rows = list(
        payments_qs.select_related('assignment__incident__client__user')
        .order_by('-paid_at', '-created_at')[:200]
        .values(
            'id',
            'total_amount',
            'workshop_net_amount',
            'status',
            'paid_at',
            'assignment__incident_id',
            'assignment__incident__client__user__first_name',
            'assignment__incident__client__user__last_name',
        )
    )
    for row in payment_rows:
        fn = row.pop('assignment__incident__client__user__first_name', '') or ''
        ln = row.pop('assignment__incident__client__user__last_name', '') or ''
        row['client_name'] = (fn + ' ' + ln).strip() or '—'
        row['incident_id'] = row.pop('assignment__incident_id')
        pa = row.get('paid_at')
        row['paid_at'] = pa.isoformat() if pa else None
        for k in ('total_amount', 'workshop_net_amount'):
            v = row.get(k)
            if v is not None:
                row[k] = str(v)

    filter_options = {
        'incident_status': [{'value': c[0], 'label': c[1]} for c in IncidentStatus.choices],
        'incident_type': [{'value': c[0], 'label': c[1]} for c in IncidentType.choices],
        'payment_status': [{'value': c[0], 'label': c[1]} for c in PaymentStatus.choices],
        'assignment_status': [{'value': c[0], 'label': c[1]} for c in AssignmentStatus.choices],
    }

    filters_applied = {
        'assignment_status': ast or None,
        'incident_status': request.query_params.get('incident_status') or None,
        'incident_type': request.query_params.get('incident_type') or None,
        'payment_status': request.query_params.get('payment_status') or None,
        'report_focus': report_focus or None,
        'dates_source': dates_source or None,
    }

    kpis = {
        'assignments_total': assign_qs.count(),
        'offered_pending': offered_pending,
        'offered_in_period': offered_in_period,
        'active_services': active,
        'completed_in_period': completed,
        'rejected_in_period': rejected,
        'payments_count': pay_agg['count'] or 0,
        'earnings_net_period': str(pay_agg['net'] or Decimal('0')),
        'earnings_gross_period': str(pay_agg['gross'] or Decimal('0')),
        'ratings_count': rating_agg['count'] or 0,
        'ratings_avg_period': (
            round(float(rating_agg['avg']), 2) if rating_agg['avg'] is not None else None
        ),
        'workshop_rating_avg': float(workshop.rating_avg or 0),
        'technicians_total': workshop.technicians.count(),
        'technicians_available': workshop.technicians.filter(is_available=True).count(),
        'avg_response_seconds': _decimal_to_float(cycle['avg_response']),
        'avg_arrival_seconds': _decimal_to_float(cycle['avg_arrival']),
        'avg_resolution_seconds': _decimal_to_float(cycle['avg_resolution']),
    }

    narrative = _build_workshop_narrative(
        workshop=workshop,
        kpis=kpis,
        status_breakdown=assignments_by_status,
        type_breakdown=incidents_by_type,
        report_focus=report_focus,
        dates_source=dates_source,
        date_from=date_from,
        date_to=date_to,
        filters=filters_applied,
    )

    return {
        'meta': {
            'date_from': date_from.isoformat(),
            'date_to': date_to.isoformat(),
            'generated_at': timezone.now().isoformat(),
            'workshop_id': workshop.id,
            'workshop_name': workshop.name,
        },
        'filters_applied': filters_applied,
        'filter_options': filter_options,
        'summary': {
            'narrative': narrative,
            'status_breakdown': assignments_by_status,
            'type_breakdown': incidents_by_type,
            'list_total': len(assignment_rows),
        },
        'kpis': kpis,
        'charts': {
            'assignments_by_status': assignments_by_status,
            'incidents_by_type': incidents_by_type,
        },
        'tables': {
            'recent_assignments': assignment_rows,
            'recent_payments': payment_rows,
        },
    }


def _incident_status_breakdown(incident_qs, status_labels: dict[str, str]) -> list[dict]:
    raw = {r['status']: r['count'] for r in incident_qs.values('status').annotate(count=Count('id'))}
    return [
        {
            'status': code,
            'status_label': status_labels.get(code, code),
            'count': raw.get(code, 0),
        }
        for code, _ in IncidentStatus.choices
    ]


def _technician_status_breakdown(assign_qs, status_labels: dict[str, str]) -> list[dict]:
    raw = {r['status']: r['count'] for r in assign_qs.values('status').annotate(count=Count('id'))}
    codes = [
        c[0]
        for c in AssignmentStatus.choices
        if c[0] not in (AssignmentStatus.OFFERED, AssignmentStatus.REJECTED)
    ]
    return [
        {'status': code, 'status_label': status_labels.get(code, code), 'count': raw.get(code, 0)}
        for code in codes
    ]


def _build_client_narrative(
    *,
    kpis: dict,
    status_breakdown: list[dict],
    type_breakdown: list[dict],
    report_focus: str,
    dates_source: str,
    date_from: date,
    date_to: date,
) -> str:
    parts: list[str] = []
    if report_focus == 'general' and dates_source in ('none', 'default_month'):
        parts.append(
            f'Tienes {kpis["incidents_total"]} solicitud(es) de emergencia en total (todos los estados).'
        )
    else:
        parts.append(
            f'Del {date_from.strftime("%d/%m/%Y")} al {date_to.strftime("%d/%m/%Y")}: '
            f'{kpis["incidents_total"]} solicitud(es).'
        )

    status_bits = [f'{r["status_label"]}: {r["count"]}' for r in status_breakdown if r['count'] > 0]
    if status_bits:
        parts.append('Por estado: ' + '; '.join(status_bits) + '.')
    elif kpis['incidents_total'] == 0:
        parts.append('No hay solicitudes en este período.')

    if type_breakdown:
        type_bits = [
            f'{r.get("type_label", r.get("incident_type", ""))}: {r["count"]}'
            for r in type_breakdown
            if r['count'] > 0
        ]
        if type_bits:
            parts.append('Por tipo: ' + '; '.join(type_bits) + '.')

    if kpis['payments_count'] or report_focus == 'payments':
        parts.append(
            f'Pagos: {kpis["payments_count"]} registrado(s), '
            f'total pagado Bs. {kpis["total_spent"]}, '
            f'pendientes: {kpis["pending_payments"]}.'
        )
    if kpis['incidents_active']:
        parts.append(f'En curso ahora: {kpis["incidents_active"]} solicitud(es).')

    return ' '.join(parts)


def _build_technician_narrative(
    *,
    workshop_name: str,
    kpis: dict,
    status_breakdown: list[dict],
    type_breakdown: list[dict],
    report_focus: str,
    dates_source: str,
    date_from: date,
    date_to: date,
) -> str:
    parts: list[str] = []
    if report_focus == 'general' and dates_source in ('none', 'default_month'):
        parts.append(
            f'Órdenes en «{workshop_name}»: {kpis["assignments_total"]} servicio(s) asignado(s) en total.'
        )
    else:
        parts.append(
            f'Órdenes del {date_from.strftime("%d/%m/%Y")} al {date_to.strftime("%d/%m/%Y")}: '
            f'{kpis["assignments_total"]} servicio(s).'
        )

    status_bits = [f'{r["status_label"]}: {r["count"]}' for r in status_breakdown if r['count'] > 0]
    if status_bits:
        parts.append('Por estado: ' + '; '.join(status_bits) + '.')

    if type_breakdown:
        type_bits = [
            f'{r.get("type_label", r.get("incident_type", ""))}: {r["count"]}'
            for r in type_breakdown
            if r['count'] > 0
        ]
        if type_bits:
            parts.append('Tipos de incidente: ' + '; '.join(type_bits) + '.')

    if kpis['active_services']:
        parts.append(f'Activas ahora: {kpis["active_services"]}.')
    if kpis['completed_in_period']:
        parts.append(f'Completadas en el período: {kpis["completed_in_period"]}.')
    if kpis.get('avg_arrival_seconds') is not None:
        mins = round(kpis['avg_arrival_seconds'] / 60, 1)
        parts.append(f'Tiempo promedio de llegada: {mins} min.')

    return ' '.join(parts)


def build_client_reports_payload(request, client_profile) -> dict:
    """Reporte del cliente móvil: solo sus incidentes y pagos."""
    date_from, date_to = _parse_dates(request)
    status_labels = _label_map(IncidentStatus.choices)
    type_labels = _label_map(IncidentType.choices)
    report_focus = request.query_params.get('report_focus') or ''
    dates_source = request.query_params.get('dates_source') or ''

    if report_focus == 'general' and dates_source in ('none', 'default_month'):
        incident_qs = Incident.objects.filter(client=client_profile)
    else:
        incident_qs = Incident.objects.filter(
            client=client_profile,
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        )

    st = request.query_params.get('incident_status')
    if st:
        incident_qs = incident_qs.filter(status=st)
    it = request.query_params.get('incident_type')
    if it:
        incident_qs = incident_qs.filter(incident_type=it)

    active_statuses = [
        IncidentStatus.PENDING,
        IncidentStatus.ANALYZING,
        IncidentStatus.WAITING_WORKSHOP,
        IncidentStatus.ASSIGNED,
        IncidentStatus.IN_PROGRESS,
    ]
    incidents_by_status = _incident_status_breakdown(incident_qs, status_labels)
    incidents_by_type_raw = list(
        incident_qs.values('incident_type').annotate(count=Count('id')).order_by('-count')
    )
    incidents_by_type = [
        {
            'incident_type': r['incident_type'],
            'type_label': type_labels.get(r['incident_type'], r['incident_type']),
            'count': r['count'],
        }
        for r in incidents_by_type_raw
    ]

    payments_qs = Payment.objects.filter(assignment__incident__client=client_profile)
    if not (report_focus == 'general' and dates_source in ('none', 'default_month')):
        payments_qs = payments_qs.filter(created_at__date__gte=date_from, created_at__date__lte=date_to)
    ps = request.query_params.get('payment_status')
    if ps:
        payments_qs = payments_qs.filter(status=ps)
    elif report_focus == 'payments':
        payments_qs = payments_qs.filter(
            status__in=[PaymentStatus.CLIENT_PAID, PaymentStatus.COMMISSION_SETTLED]
        )

    pay_agg = payments_qs.filter(
        status__in=[PaymentStatus.CLIENT_PAID, PaymentStatus.COMMISSION_SETTLED]
    ).aggregate(total=Sum('total_amount'), count=Count('id'))
    pending_payments = payments_qs.filter(status=PaymentStatus.PENDING).count()

    incident_rows = []
    incidents = list(
        incident_qs.select_related('vehicle')
        .prefetch_related('assignments__workshop', 'assignments__payment')
        .order_by('-created_at')[:500]
    )
    for inc in incidents:
        assignment = inc.assignments.order_by('-offered_at').first()
        workshop_name = assignment.workshop.name if assignment and assignment.workshop_id else '—'
        payment = getattr(assignment, 'payment', None) if assignment else None
        vehicle_label = (
            f'{inc.vehicle.brand} {inc.vehicle.model}'.strip() if inc.vehicle_id else '—'
        )
        incident_rows.append({
            'id': inc.id,
            'status': inc.status,
            'status_label': status_labels.get(inc.status, inc.status),
            'incident_type': inc.incident_type,
            'incident_type_label': type_labels.get(inc.incident_type, inc.incident_type),
            'vehicle_label': vehicle_label,
            'workshop_name': workshop_name,
            'payment_status': payment.status if payment else None,
            'payment_status_label': (
                payment.get_status_display() if payment else None
            ),
            'total_amount': str(payment.total_amount) if payment else None,
            'created_at': inc.created_at.isoformat() if inc.created_at else None,
            'closed_at': inc.closed_at.isoformat() if inc.closed_at else None,
        })

    payment_rows = list(
        payments_qs.select_related('assignment__workshop')
        .order_by('-paid_at', '-created_at')[:200]
        .values(
            'id',
            'total_amount',
            'status',
            'paid_at',
            'assignment__incident_id',
            'assignment__workshop__name',
        )
    )
    for row in payment_rows:
        row['incident_id'] = row.pop('assignment__incident_id')
        row['workshop_name'] = row.pop('assignment__workshop__name')
        pa = row.get('paid_at')
        row['paid_at'] = pa.isoformat() if pa else None
        if row.get('total_amount') is not None:
            row['total_amount'] = str(row['total_amount'])

    kpis = {
        'incidents_total': incident_qs.count(),
        'incidents_active': incident_qs.filter(status__in=active_statuses).count(),
        'incidents_completed': incident_qs.filter(status=IncidentStatus.COMPLETED).count(),
        'incidents_cancelled': incident_qs.filter(status=IncidentStatus.CANCELLED).count(),
        'payments_count': pay_agg['count'] or 0,
        'total_spent': str(pay_agg['total'] or Decimal('0')),
        'pending_payments': pending_payments,
    }

    filters_applied = {
        'incident_status': st or None,
        'incident_type': it or None,
        'payment_status': ps or None,
        'report_focus': report_focus or None,
        'dates_source': dates_source or None,
    }

    narrative = _build_client_narrative(
        kpis=kpis,
        status_breakdown=incidents_by_status,
        type_breakdown=incidents_by_type,
        report_focus=report_focus,
        dates_source=dates_source,
        date_from=date_from,
        date_to=date_to,
    )

    return {
        'meta': {
            'date_from': date_from.isoformat(),
            'date_to': date_to.isoformat(),
            'generated_at': timezone.now().isoformat(),
            'client_id': client_profile.id,
        },
        'filters_applied': filters_applied,
        'filter_options': {
            'incident_status': [{'value': c[0], 'label': c[1]} for c in IncidentStatus.choices],
            'incident_type': [{'value': c[0], 'label': c[1]} for c in IncidentType.choices],
            'payment_status': [{'value': c[0], 'label': c[1]} for c in PaymentStatus.choices],
        },
        'summary': {
            'narrative': narrative,
            'status_breakdown': incidents_by_status,
            'type_breakdown': incidents_by_type,
            'list_total': len(incident_rows),
        },
        'kpis': kpis,
        'charts': {
            'incidents_by_status': incidents_by_status,
            'incidents_by_type': incidents_by_type,
        },
        'tables': {
            'recent_incidents': incident_rows,
            'recent_payments': payment_rows,
        },
    }


def build_technician_reports_payload(request, technician) -> dict:
    """Reporte del técnico móvil: solo sus órdenes asignadas."""
    date_from, date_to = _parse_dates(request)
    status_labels = _label_map(AssignmentStatus.choices)
    type_labels = _label_map(IncidentType.choices)
    incident_status_labels = _label_map(IncidentStatus.choices)
    report_focus = request.query_params.get('report_focus') or ''
    dates_source = request.query_params.get('dates_source') or ''
    ast = request.query_params.get('assignment_status') or ''

    base_qs = Assignment.objects.filter(technician=technician).exclude(
        status__in=[AssignmentStatus.OFFERED, AssignmentStatus.REJECTED]
    )

    if report_focus == 'general' and dates_source in ('none', 'default_month') and not ast:
        assign_qs = base_qs
    else:
        assign_qs = base_qs.filter(
            offered_at__date__gte=date_from,
            offered_at__date__lte=date_to,
        )

    if ast:
        assign_qs = assign_qs.filter(status=ast)
    elif report_focus == 'active':
        assign_qs = assign_qs.filter(
            status__in=[
                AssignmentStatus.ACCEPTED,
                AssignmentStatus.IN_ROUTE,
                AssignmentStatus.ARRIVED,
                AssignmentStatus.IN_SERVICE,
            ]
        )
    elif report_focus == 'completed':
        assign_qs = assign_qs.filter(status=AssignmentStatus.COMPLETED)

    assignments_by_status = _technician_status_breakdown(assign_qs, status_labels)
    incidents_by_type_raw = list(
        assign_qs.values('incident__incident_type')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    incidents_by_type = [
        {
            'incident_type': r['incident__incident_type'],
            'type_label': type_labels.get(r['incident__incident_type'], r['incident__incident_type']),
            'count': r['count'],
        }
        for r in incidents_by_type_raw
    ]

    cycle = IncidentCycleMetric.objects.filter(assignment__technician=technician)
    if not (report_focus == 'general' and dates_source in ('none', 'default_month')):
        cycle = cycle.filter(
            assignment__offered_at__date__gte=date_from,
            assignment__offered_at__date__lte=date_to,
        )
    cycle_agg = cycle.aggregate(
        avg_arrival=Avg('seconds_to_arrival'),
        avg_resolution=Avg('seconds_total_resolution'),
    )

    active = assign_qs.filter(
        status__in=[
            AssignmentStatus.ACCEPTED,
            AssignmentStatus.IN_ROUTE,
            AssignmentStatus.ARRIVED,
            AssignmentStatus.IN_SERVICE,
        ]
    ).count()
    completed = assign_qs.filter(status=AssignmentStatus.COMPLETED).count()

    assignment_rows = list(
        assign_qs.select_related('incident', 'incident__vehicle', 'workshop')
        .order_by('-offered_at')[:500]
        .values(
            'id',
            'status',
            'incident_id',
            'incident__incident_type',
            'incident__status',
            'incident__address_text',
            'offered_at',
            'accepted_at',
            'completed_at',
            'workshop__name',
            'incident__vehicle__brand',
            'incident__vehicle__model',
        )
    )
    for row in assignment_rows:
        itype = row.pop('incident__incident_type', '')
        istatus = row.pop('incident__status', '')
        astatus = row.get('status', '')
        row['incident_type'] = itype
        row['incident_type_label'] = type_labels.get(itype, itype)
        row['incident_status'] = istatus
        row['incident_status_label'] = incident_status_labels.get(istatus, istatus)
        row['status_label'] = status_labels.get(astatus, astatus)
        row['workshop_name'] = row.pop('workshop__name', '') or '—'
        row['vehicle_label'] = (
            f"{row.pop('incident__vehicle__brand', '') or ''} "
            f"{row.pop('incident__vehicle__model', '') or ''}".strip()
            or '—'
        )
        row['address'] = (row.pop('incident__address_text', '') or '').strip() or None
        for ts in ('offered_at', 'accepted_at', 'completed_at'):
            val = row.get(ts)
            row[ts] = val.isoformat() if val else None

    workshop_name = technician.workshop.name if technician.workshop_id else 'Taller'

    kpis = {
        'assignments_total': assign_qs.count(),
        'active_services': active,
        'completed_in_period': completed,
        'avg_arrival_seconds': _decimal_to_float(cycle_agg['avg_arrival']),
        'avg_resolution_seconds': _decimal_to_float(cycle_agg['avg_resolution']),
    }

    filters_applied = {
        'assignment_status': ast or None,
        'report_focus': report_focus or None,
        'dates_source': dates_source or None,
    }

    narrative = _build_technician_narrative(
        workshop_name=workshop_name,
        kpis=kpis,
        status_breakdown=assignments_by_status,
        type_breakdown=incidents_by_type,
        report_focus=report_focus,
        dates_source=dates_source,
        date_from=date_from,
        date_to=date_to,
    )

    return {
        'meta': {
            'date_from': date_from.isoformat(),
            'date_to': date_to.isoformat(),
            'generated_at': timezone.now().isoformat(),
            'technician_id': technician.id,
            'workshop_name': workshop_name,
        },
        'filters_applied': filters_applied,
        'filter_options': {
            'assignment_status': [
                {'value': c[0], 'label': c[1]}
                for c in AssignmentStatus.choices
                if c[0] not in (AssignmentStatus.OFFERED, AssignmentStatus.REJECTED)
            ],
        },
        'summary': {
            'narrative': narrative,
            'status_breakdown': assignments_by_status,
            'type_breakdown': incidents_by_type,
            'list_total': len(assignment_rows),
        },
        'kpis': kpis,
        'charts': {
            'assignments_by_status': assignments_by_status,
            'incidents_by_type': incidents_by_type,
        },
        'tables': {
            'recent_assignments': assignment_rows,
        },
    }
