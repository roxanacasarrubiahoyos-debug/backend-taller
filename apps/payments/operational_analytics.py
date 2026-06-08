"""
Analítica operacional y KPIs para el panel admin.
Todos los valores se calculan desde incidentes, asignaciones y métricas de ciclo en BD.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from django.db.models import Avg, Count
from django.utils import timezone

from apps.assignments.models import Assignment, AssignmentStatus
from apps.incidents.models import (
    Incident,
    IncidentCycleMetric,
    IncidentStatus,
    IncidentType,
)
from apps.payments.reports_views import _decimal_to_float, _incident_base_qs, _parse_dates
from apps.workshops.models import Workshop

# Minutos sin taller aceptado → considerado "no atendido" (operativo)
UNATTENDED_THRESHOLD_MINUTES = 60

# SLA: si no hay ETA pactada al aceptar, umbral plataforma (minutos hasta llegada)
DEFAULT_SLA_ARRIVAL_MINUTES = 45

INCIDENT_TYPE_GROUP_LABELS: dict[str, str] = {
    'battery': 'Batería',
    'tire': 'Llanta',
    'engine': 'Motor',
    'accident': 'Choque / accidente',
    'locksmith': 'Otros',
    'overheating': 'Otros',
    'other': 'Otros',
    'uncertain': 'Otros',
}


def _sec_delta(start, end) -> int | None:
    if not start or not end:
        return None
    return max(0, int((end - start).total_seconds()))


def _avg(values: list[int | float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _type_group_label(incident_type: str) -> str:
    return INCIDENT_TYPE_GROUP_LABELS.get(incident_type, 'Otros')


def _compute_timing_kpis(incident_qs, assign_qs) -> dict:
    """Tiempos reales desde created_at / accepted_at / arrived_at (todas las asignaciones aceptadas)."""
    report_to_assign: list[int] = []
    assign_to_arrival: list[int] = []

    for a in assign_qs.filter(accepted_at__isnull=False).select_related('incident'):
        s1 = _sec_delta(a.incident.created_at, a.accepted_at)
        if s1 is not None:
            report_to_assign.append(s1)
        if a.arrived_at:
            s2 = _sec_delta(a.accepted_at, a.arrived_at)
            if s2 is not None:
                assign_to_arrival.append(s2)

    cycle = IncidentCycleMetric.objects.filter(assignment__incident__in=incident_qs).aggregate(
        avg_assign=Avg('seconds_to_assignment'),
        avg_arrival=Avg('seconds_to_arrival'),
        avg_resolution=Avg('seconds_total_resolution'),
    )

    avg_report = _avg(report_to_assign)
    avg_arrival = _avg(assign_to_arrival)

    return {
        'avg_report_to_assignment_seconds': avg_report,
        'avg_assignment_seconds': avg_report,
        'avg_arrival_seconds': avg_arrival,
        'avg_assignment_to_arrival_seconds': avg_arrival,
        'avg_resolution_seconds': _decimal_to_float(cycle['avg_resolution']),
        'avg_assignment_seconds_completed_only': _decimal_to_float(cycle['avg_assign']),
        'avg_arrival_seconds_completed_only': _decimal_to_float(cycle['avg_arrival']),
        'assignments_with_accepted_count': len(report_to_assign),
        'assignments_with_arrival_count': len(assign_to_arrival),
    }


def _compute_sla(assign_qs) -> dict:
    eligible = 0
    met = 0
    for a in assign_qs.filter(
        accepted_at__isnull=False,
        arrived_at__isnull=False,
    ):
        actual_min = (a.arrived_at - a.accepted_at).total_seconds() / 60.0
        threshold = a.estimated_arrival_minutes or DEFAULT_SLA_ARRIVAL_MINUTES
        eligible += 1
        if actual_min <= threshold:
            met += 1
    pct = round((met / eligible) * 100.0, 1) if eligible else None
    return {
        'sla_compliance_pct': pct,
        'sla_cases_measured': eligible,
        'sla_cases_met': met,
        'sla_default_minutes': DEFAULT_SLA_ARRIVAL_MINUTES,
    }


def _compute_unattended(incident_qs) -> dict:
    now = timezone.now()
    threshold = now - timedelta(minutes=UNATTENDED_THRESHOLD_MINUTES)
    stuck_statuses = [
        IncidentStatus.PENDING,
        IncidentStatus.ANALYZING,
        IncidentStatus.WAITING_WORKSHOP,
    ]
    unattended_qs = incident_qs.filter(
        status__in=stuck_statuses,
        created_at__lte=threshold,
    ).exclude(
        assignments__status__in=[
            AssignmentStatus.ACCEPTED,
            AssignmentStatus.IN_ROUTE,
            AssignmentStatus.ARRIVED,
            AssignmentStatus.IN_SERVICE,
            AssignmentStatus.COMPLETED,
        ],
    ).distinct()
    cancelled = incident_qs.filter(status=IncidentStatus.CANCELLED).count()
    unattended = unattended_qs.count()
    total = incident_qs.count()
    return {
        'incidents_cancelled': cancelled,
        'incidents_unattended': unattended,
        'cancellation_rate_pct': round((cancelled / total) * 100.0, 1) if total else 0.0,
    }


def _incidents_by_type_grouped(incident_qs) -> list[dict]:
    raw = list(
        incident_qs.values('incident_type').annotate(count=Count('id')).order_by('-count')
    )
    grouped: dict[str, int] = defaultdict(int)
    for row in raw:
        label = _type_group_label(row['incident_type'] or 'other')
        grouped[label] += row['count']
    order = ['Batería', 'Llanta', 'Motor', 'Choque / accidente', 'Otros']
    return [
        {'label': label, 'count': grouped[label]}
        for label in order
        if grouped[label] > 0
    ] + [
        {'label': k, 'count': v}
        for k, v in grouped.items()
        if k not in order
    ]


def _top_geo_zones(incident_qs, limit: int = 10) -> list[dict]:
    buckets: dict[str, dict] = {}
    for inc in incident_qs.filter(latitude__isnull=False, longitude__isnull=False).only(
        'latitude', 'longitude', 'address_text'
    ):
        lat = round(float(inc.latitude), 2)
        lng = round(float(inc.longitude), 2)
        key = f'{lat},{lng}'
        if key not in buckets:
            addr = (inc.address_text or '').strip()
            short_addr = addr[:48] + ('…' if len(addr) > 48 else '') if addr else ''
            buckets[key] = {
                'zone_key': key,
                'latitude': lat,
                'longitude': lng,
                'label': short_addr or f'Zona {lat}, {lng}',
                'count': 0,
            }
        buckets[key]['count'] += 1
    rows = sorted(buckets.values(), key=lambda x: -x['count'])
    return rows[:limit]


def _top_workshops_efficiency(assign_qs, limit: int = 10) -> list[dict]:
    stats: dict[int, dict] = {}
    for a in assign_qs.filter(accepted_at__isnull=False).select_related('workshop'):
        wid = a.workshop_id
        if wid not in stats:
            stats[wid] = {
                'workshop_id': wid,
                'name': a.workshop.name,
                'response_seconds': [],
                'arrival_seconds': [],
                'completed_count': 0,
            }
        s = _sec_delta(a.incident.created_at, a.accepted_at)
        if s is not None:
            stats[wid]['response_seconds'].append(s)
        if a.arrived_at:
            s2 = _sec_delta(a.accepted_at, a.arrived_at)
            if s2 is not None:
                stats[wid]['arrival_seconds'].append(s2)
        if a.status == AssignmentStatus.COMPLETED:
            stats[wid]['completed_count'] += 1

    rows = []
    for st in stats.values():
        avg_resp = _avg(st['response_seconds'])
        avg_arr = _avg(st['arrival_seconds'])
        if avg_resp is None:
            continue
        rows.append({
            'workshop_id': st['workshop_id'],
            'name': st['name'],
            'avg_response_seconds': avg_resp,
            'avg_arrival_seconds': avg_arr,
            'completed_count': st['completed_count'],
            'cases_count': len(st['response_seconds']),
        })

    rows.sort(key=lambda x: (x['avg_response_seconds'], -x['completed_count']))
    return rows[:limit]


def build_operational_dashboard(request) -> dict:
    date_from, date_to = _parse_dates(request)
    incident_qs = _incident_base_qs(request, date_from, date_to)
    assign_qs = Assignment.objects.filter(incident__in=incident_qs)

    total = incident_qs.count()
    completed = incident_qs.filter(status=IncidentStatus.COMPLETED).count()
    active = incident_qs.exclude(
        status__in=[IncidentStatus.COMPLETED, IncidentStatus.CANCELLED]
    ).count()

    timing = _compute_timing_kpis(incident_qs, assign_qs)
    sla = _compute_sla(assign_qs)
    unattended = _compute_unattended(incident_qs)

    from django.db.models.functions import TruncDate

    by_day_rows = list(
        incident_qs.annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )
    for row in by_day_rows:
        d = row.get('day')
        if hasattr(d, 'isoformat'):
            row['day'] = d.isoformat()
        elif d is not None:
            row['day'] = str(d)[:10]

    workshops_filter = list(
        Workshop.objects.filter(is_active=True)
        .order_by('name')
        .values('id', 'name')[:200]
    )

    return {
        'meta': {
            'date_from': date_from.isoformat(),
            'date_to': date_to.isoformat(),
            'generated_at': timezone.now().isoformat(),
        },
        'filters_applied': {
            'workshop_id': request.query_params.get('workshop_id') or None,
            'incident_status': request.query_params.get('incident_status') or None,
            'incident_type': request.query_params.get('incident_type') or None,
        },
        'workshops_filter': workshops_filter,
        'kpis': {
            'incidents_total': total,
            'incidents_active': active,
            'incidents_completed': completed,
            'resolution_rate_pct': round((completed / total) * 100.0, 1) if total else 0.0,
            'verified_workshops_total': Workshop.objects.filter(
                is_verified=True, is_active=True
            ).count(),
            **timing,
            **sla,
            **unattended,
        },
        'charts': {
            'incidents_by_type_grouped': _incidents_by_type_grouped(incident_qs),
            'incidents_by_day': by_day_rows,
            'top_workshops_efficiency': _top_workshops_efficiency(assign_qs),
            'top_geo_zones': _top_geo_zones(incident_qs),
            'incidents_by_status': list(
                incident_qs.values('status')
                .annotate(count=Count('id'))
                .order_by('-count')
            ),
        },
    }
