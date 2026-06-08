from django.conf import settings
from apps.workshops.models import Workshop
from apps.workshops.eligibility import (
    workshop_assignment_block_reason,
    workshop_handles_incident_type,
)
from apps.workshops.geo import coordinate_pair, distance_km
from apps.assignments.models import Assignment
from decimal import Decimal


class AssignmentEngine:
    """
    Motor inteligente de asignación de talleres a incidentes.
    """

    @staticmethod
    def _collect_candidates(incident, *, strict_service_type: bool) -> list:
        incident_location = coordinate_pair(incident.latitude, incident.longitude)
        if incident_location is None:
            return []
        incident_type = str(incident.incident_type or '').strip()

        qs = Workshop.objects.filter(is_active=True).select_related(
            'owner', 'owner__subscription'
        )
        if not getattr(settings, 'ASSIGNMENT_ALLOW_UNVERIFIED', False):
            qs = qs.filter(is_verified=True)
        workshops = qs.prefetch_related('technicians')

        candidates = []
        for workshop in workshops:
            if workshop_assignment_block_reason(workshop):
                continue
            if strict_service_type and not workshop_handles_incident_type(workshop, incident_type):
                continue

            dist_km = distance_km(
                incident_location,
                (workshop.latitude, workshop.longitude),
            )
            if dist_km is None:
                continue
            max_radius_km = min(float(workshop.radius_km or 15), 20.0)
            if dist_km > max_radius_km:
                continue

            score = (1 / (dist_km + 0.1)) * float(workshop.rating_avg or 3.0)
            candidates.append({
                'workshop': workshop,
                'distance_km': round(dist_km, 2),
                'score': score,
                'relaxed_service_match': not strict_service_type,
            })

        candidates.sort(key=lambda x: x['score'], reverse=True)
        return candidates

    @staticmethod
    def find_and_notify_workshops(incident) -> list:
        """
        Encuentra talleres candidatos y crea Assignment en estado offered.
        Primero coincide tipo de servicio; si no hay nadie, reintenta sin ese filtro.
        """
        strict_list = AssignmentEngine._collect_candidates(
            incident, strict_service_type=True
        )
        relaxed_list = AssignmentEngine._collect_candidates(
            incident, strict_service_type=False
        )

        merged = []
        seen_ids = set()

        # Siempre priorizar talleres muy cercanos (< 1 km), aunque el rubro no coincida
        for candidate in relaxed_list:
            if candidate['distance_km'] <= 1.0 and candidate['workshop'].id not in seen_ids:
                merged.append(candidate)
                seen_ids.add(candidate['workshop'].id)

        for candidate in strict_list:
            if len(merged) >= 5:
                break
            if candidate['workshop'].id not in seen_ids:
                merged.append(candidate)
                seen_ids.add(candidate['workshop'].id)

        for candidate in relaxed_list:
            if len(merged) >= 5:
                break
            if candidate['workshop'].id not in seen_ids:
                merged.append(candidate)
                seen_ids.add(candidate['workshop'].id)

        top_candidates = merged[:5]
        if top_candidates and not strict_list:
            print(
                f"[AssignmentEngine] Incidente {incident.id}: "
                f"solo ofertas en modo amplio (tipo {incident.incident_type})."
            )

        for candidate in top_candidates:
            w = candidate['workshop']
            if Assignment.objects.filter(incident=incident, workshop=w).exists():
                continue
            assignment_row = Assignment.objects.create(
                incident=incident,
                workshop=w,
                distance_km=Decimal(str(candidate['distance_km'])),
                status='offered',
            )

            try:
                owner_user = candidate['workshop'].owner.user

                if owner_user.fcm_token:
                    from apps.notifications.firebase_service import FirebaseService
                    firebase = FirebaseService()
                    firebase.send_notification(
                        token=owner_user.fcm_token,
                        title='Nueva solicitud de emergencia',
                        body=f"Incidente tipo {incident.get_incident_type_display()} a {candidate['distance_km']} km",
                        data={
                            'incident_id': str(incident.id),
                            'type': 'new_request',
                            'distance_km': str(candidate['distance_km']),
                        },
                    )

                from apps.notifications.models import NotificationType
                from apps.notifications.web_panel_notify import deliver_to_web_panel_user

                deliver_to_web_panel_user(
                    user=owner_user,
                    title='Nueva solicitud de emergencia',
                    body=(
                        f"Incidente tipo {incident.get_incident_type_display()} "
                        f"a {candidate['distance_km']} km"
                    ),
                    notification_type=NotificationType.NEW_REQUEST,
                    incident=incident,
                    data={
                        'type': 'new_request',
                        'workshop_id': w.id,
                        'incident_id': incident.id,
                        'assignment_id': assignment_row.id,
                    },
                    sse_payload={
                        'event': 'new_assignment_offer',
                        'workshop_id': w.id,
                        'incident_id': incident.id,
                        'assignment_id': assignment_row.id,
                        'distance_km': float(candidate['distance_km']),
                        'title': 'Nueva solicitud de emergencia',
                        'body': (
                            f"Incidente tipo {incident.get_incident_type_display()} "
                            f"a {candidate['distance_km']} km"
                        ),
                    },
                )

            except Exception as e:
                print(f"Error sending notification to workshop {candidate['workshop'].id}: {e}")

        if not top_candidates:
            print(
                f"[AssignmentEngine] Sin candidatos para incidente {incident.id}: "
                f"tipo={incident.incident_type}, ubicación=({incident.latitude},{incident.longitude}). "
                "Revisa: verificado, suscripción activa, técnico disponible, radio_km y coordenadas del taller."
            )

        return top_candidates
