"""
Genera datos de demostración coherentes (Bolivia: America/La_Paz, coordenadas y textos).

Uso:
  python manage.py seed_database
  python manage.py seed_database --count 500
  python manage.py seed_database --clear

Contraseña por defecto de todos los usuarios sembrados: la mostrada al ejecutar (SEED_DEFAULT_PASSWORD).
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth.hashers import make_password
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.assignments.models import Assignment, AssignmentStatus
from apps.incidents.models import (
    Evidence,
    EvidenceType,
    Incident,
    IncidentCycleMetric,
    IncidentPriority,
    IncidentStatus,
    IncidentStatusHistory,
    IncidentType,
)
from apps.notifications.models import Notification, NotificationType
from apps.payments.models import CommissionConfig, Payment, PaymentStatus
from apps.users.models import ClientProfile, Role, User, WorkshopOwnerProfile
from apps.vehicles.models import Vehicle, VehicleType
from apps.workshops.models import ServiceCategory, Technician, Workshop, WorkshopRating

BOLIVIA_TZ = ZoneInfo("America/La_Paz")

# Centros aproximados (lat, lon) para dispersar incidentes y talleres de forma lógica
BOLIVIA_CITIES = (
    ("La Paz", Decimal("-16.5000"), Decimal("-68.1500")),
    ("El Alto", Decimal("-16.4897"), Decimal("-68.1928")),
    ("Santa Cruz de la Sierra", Decimal("-17.7833"), Decimal("-63.1821")),
    ("Cochabamba", Decimal("-17.3935"), Decimal("-66.1570")),
    ("Sucre", Decimal("-19.0333"), Decimal("-65.2597")),
    ("Oruro", Decimal("-17.9647"), Decimal("-67.1064")),
    ("Potosí", Decimal("-19.5723"), Decimal("-65.7550")),
    ("Tarija", Decimal("-21.5355"), Decimal("-64.7296")),
)

# PNG mínimo válido (1×1) para FileField de evidencias
MINIMAL_PNG = bytes(
    [
        0x89,
        0x50,
        0x4E,
        0x47,
        0x0D,
        0x0A,
        0x1A,
        0x0A,
        0x00,
        0x00,
        0x00,
        0x0D,
        0x49,
        0x48,
        0x44,
        0x52,
        0x00,
        0x00,
        0x00,
        0x01,
        0x00,
        0x00,
        0x00,
        0x01,
        0x08,
        0x06,
        0x00,
        0x00,
        0x00,
        0x1F,
        0x15,
        0xC4,
        0x89,
        0x00,
        0x00,
        0x00,
        0x0A,
        0x49,
        0x44,
        0x41,
        0x54,
        0x78,
        0x9C,
        0x63,
        0x00,
        0x01,
        0x00,
        0x00,
        0x05,
        0x00,
        0x01,
        0x0D,
        0x0A,
        0x2D,
        0xB4,
        0x00,
        0x00,
        0x00,
        0x00,
        0x49,
        0x45,
        0x4E,
        0x44,
        0xAE,
        0x42,
        0x60,
        0x82,
    ]
)

SEED_DEFAULT_PASSWORD = "SeedBolivia2026!"


def _bolivia_now():
    return timezone.now().astimezone(BOLIVIA_TZ)


def _jitter_lat_lon(lat: Decimal, lon: Decimal, spread: Decimal = Decimal("0.08")) -> tuple[Decimal, Decimal]:
    dlat = Decimal(str(random.uniform(-float(spread), float(spread))))
    dlon = Decimal(str(random.uniform(-float(spread), float(spread))))
    return (lat + dlat).quantize(Decimal("0.0000001")), (lon + dlon).quantize(Decimal("0.0000001"))


def _vin_for_index(i: int) -> str:
    raw = f"SEED{i:011d}X"
    return raw[:17].ljust(17, "0")


class Command(BaseCommand):
    help = "Inserta N registros coherentes por tabla de dominio (Bolivia, relaciones FK respetadas)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=1000,
            help="Filas por tabla de dominio (por defecto 1000).",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Elimina datos generados previamente por este comando (usuarios @seed.bo).",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=42,
            help="Semilla del generador pseudoaleatorio (reproducibilidad).",
        )

    def handle(self, *args, **options):
        n: int = options["count"]
        if n < 1:
            self.stderr.write(self.style.ERROR("--count debe ser >= 1"))
            return

        random.seed(options["seed"])

        if options["clear"]:
            self._clear_seed_data()
            self.stdout.write(self.style.SUCCESS("Datos @seed.bo eliminados."))
            return

        self.stdout.write(
            self.style.WARNING(
                f"Contraseña de usuarios sembrados: {SEED_DEFAULT_PASSWORD} "
                "(cámbiala en producción)."
            )
        )

        pwd = make_password(SEED_DEFAULT_PASSWORD)

        with transaction.atomic():
            self._seed_all(n, pwd)

        self.stdout.write(self.style.SUCCESS(f"Seed completado: {n} filas por tabla de dominio."))

    def _clear_seed_data(self):
        """Borra en orden seguro: clientes primero (incidentes/asignaciones), luego dueños (talleres), luego técnicos."""
        client_q = User.objects.filter(email__startswith="seed_client_", email__endswith="@seed.bo")
        owner_q = User.objects.filter(email__startswith="seed_owner_", email__endswith="@seed.bo")
        tech_q = User.objects.filter(email__startswith="seed_tech_", email__endswith="@seed.bo")

        CommissionConfig.objects.filter(description__startswith="[seed]").delete()

        client_q.delete()
        owner_q.delete()
        tech_q.delete()

    def _seed_all(self, n: int, pwd: str):
        now = timezone.now()
        # --- Usuarios (bulk_create no rellena auto_now_add) ---
        client_users = [
            User(
                username=f"seed_client_{i:04d}",
                email=f"seed_client_{i:04d}@seed.bo",
                first_name=random.choice(
                    ["María", "Juan", "Carla", "Luis", "Ana", "Diego", "Rosa", "Pedro", "Lucía", "Miguel"]
                ),
                last_name=random.choice(
                    ["Quispe", "Mamani", "Choque", "Condori", "Vargas", "Rojas", "Flores", "García", "López", "Torres"]
                ),
                role=Role.CLIENT,
                phone=f"+5917{random.randint(1000000, 9999999)}",
                is_active=True,
                is_staff=False,
                password=pwd,
                created_at=now,
                updated_at=now,
            )
            for i in range(n)
        ]
        User.objects.bulk_create(client_users, batch_size=500)
        client_users = list(
            User.objects.filter(email__startswith="seed_client_", email__endswith="@seed.bo").order_by("id")
        )

        owner_users = [
            User(
                username=f"seed_owner_{i:04d}",
                email=f"seed_owner_{i:04d}@seed.bo",
                first_name=random.choice(["Taller", "Servicio", "Mecánica", "Auto", "Ruta", "Express", "Sur", "Norte"]),
                last_name=random.choice(["S.R.L.", "S.A.", "Unipersonal", "Ltda.", "E.I.R.L."]),
                role=Role.WORKSHOP_OWNER,
                phone=f"+5917{random.randint(1000000, 9999999)}",
                is_active=True,
                is_staff=False,
                password=pwd,
                created_at=now,
                updated_at=now,
            )
            for i in range(n)
        ]
        User.objects.bulk_create(owner_users, batch_size=500)
        owner_users = list(
            User.objects.filter(email__startswith="seed_owner_", email__endswith="@seed.bo").order_by("id")
        )

        tech_users = [
            User(
                username=f"seed_tech_{i:04d}",
                email=f"seed_tech_{i:04d}@seed.bo",
                first_name=random.choice(["Jorge", "Fernando", "Óscar", "René", "Hugo", "Edson", "Marco", "Iván"]),
                last_name=random.choice(["Apaza", "Callisaya", "Ticona", "Zambrana", "Bautista", "Cruz", "Peña", "Rivera"]),
                role=Role.TECHNICIAN,
                phone=f"+5917{random.randint(1000000, 9999999)}",
                is_active=True,
                is_staff=False,
                password=pwd,
                created_at=now,
                updated_at=now,
            )
            for i in range(n)
        ]
        User.objects.bulk_create(tech_users, batch_size=500)
        tech_users = list(
            User.objects.filter(email__startswith="seed_tech_", email__endswith="@seed.bo").order_by("id")
        )

        streets = [
            "Av. Mariscal Santa Cruz",
            "Calle Comercio",
            "Av. 6 de Agosto",
            "Calle Potosí",
            "Av. Banzer",
            "Calle Sucre",
            "Av. Panamericana",
            "Calle Bolívar",
        ]

        # --- Perfiles cliente ---
        client_profiles = [
            ClientProfile(
                user=u,
                address=f"{random.choice(streets)} {random.randint(100, 8999)}, {BOLIVIA_CITIES[i % len(BOLIVIA_CITIES)][0]}",
                emergency_contact_name=random.choice(["Contacto", "Familiar", "Esposa", "Esposo"]),
                emergency_contact_phone=f"+5917{random.randint(1000000, 9999999)}",
            )
            for i, u in enumerate(client_users)
        ]
        ClientProfile.objects.bulk_create(client_profiles, batch_size=500)
        client_profiles = list(
            ClientProfile.objects.filter(user_id__in=[u.id for u in client_users]).select_related("user").order_by("id")
        )

        # --- Dueños y talleres ---
        owner_profiles = [
            WorkshopOwnerProfile(
                user=u,
                national_id=f"1010{i:08d}",
                stripe_account_id="",
            )
            for i, u in enumerate(owner_users)
        ]
        WorkshopOwnerProfile.objects.bulk_create(owner_profiles, batch_size=500)
        owner_profiles = list(
            WorkshopOwnerProfile.objects.filter(user_id__in=[u.id for u in owner_users]).order_by("id")
        )

        svc_pool = list(ServiceCategory.values)
        workshops = []
        for i in range(n):
            city_name, base_lat, base_lon = BOLIVIA_CITIES[i % len(BOLIVIA_CITIES)]
            lat, lon = _jitter_lat_lon(base_lat, base_lon, Decimal("0.05"))
            k = random.randint(2, 4)
            services = random.sample(svc_pool, k=k)
            workshops.append(
                Workshop(
                    owner=owner_profiles[i],
                    name=f"Taller Mecánico {city_name} #{i + 1:04d}",
                    description=f"Atención de emergencias y mecánica general en {city_name}. Radio de cobertura operativo.",
                    address=f"{random.choice(streets)} {random.randint(10, 999)}, Zona Central, {city_name}, Bolivia",
                    latitude=lat,
                    longitude=lon,
                    phone=f"+5914{random.randint(1000000, 9999999)}",
                    email=f"taller{i + 1:04d}@talleres-seed.bo",
                    services=services,
                    radius_km=random.choice([10, 15, 20, 25, 30]),
                    is_active=True,
                    is_verified=random.random() > 0.15,
                    rating_avg=Decimal(str(round(random.uniform(3.5, 5.0), 2))),
                    total_services=random.randint(0, 500),
                    created_at=now,
                )
            )
        Workshop.objects.bulk_create(workshops, batch_size=500)
        workshops = list(Workshop.objects.filter(owner_id__in=[o.id for o in owner_profiles]).order_by("id"))

        technicians = []
        for i in range(n):
            w = workshops[i]
            tlat, tlon = _jitter_lat_lon(w.latitude, w.longitude, Decimal("0.02"))
            technicians.append(
                Technician(
                    workshop=w,
                    user=tech_users[i],
                    name=f"{tech_users[i].first_name} {tech_users[i].last_name}",
                    phone=tech_users[i].phone,
                    specialties=random.sample(svc_pool, k=random.randint(1, 3)),
                    is_available=random.random() > 0.2,
                    current_latitude=tlat,
                    current_longitude=tlon,
                    last_location_update=_bolivia_now(),
                )
            )
        Technician.objects.bulk_create(technicians, batch_size=500)
        technicians = list(
            Technician.objects.filter(workshop_id__in=[w.id for w in workshops]).select_related("workshop").order_by("id")
        )

        # --- Vehículos (placa única) ---
        brands = ["Toyota", "Suzuki", "Nissan", "Chevrolet", "Hyundai", "Kia", "Ford", "Volkswagen", "Mitsubishi", "Renault"]
        models_ = ["RAV4", "Swift", "March", "D-Max", "Tucson", "Sportage", "Ranger", "Amarok", "L200", "Duster"]
        colors = ["Plata", "Blanco", "Negro", "Rojo", "Azul", "Gris", "Verde"]
        vehicles = []
        for i, cp in enumerate(client_profiles):
            city_name, base_lat, base_lon = BOLIVIA_CITIES[i % len(BOLIVIA_CITIES)]
            vehicles.append(
                Vehicle(
                    client=cp,
                    brand=random.choice(brands),
                    model=random.choice(models_),
                    year=random.randint(2008, 2025),
                    plate=f"SEED{i:05d}",
                    color=random.choice(colors),
                    vehicle_type=random.choice(list(VehicleType.values)),
                    vin=_vin_for_index(i),
                    is_active=True,
                    created_at=now,
                )
            )
        Vehicle.objects.bulk_create(vehicles, batch_size=500)
        vehicles = list(Vehicle.objects.filter(client_id__in=[c.id for c in client_profiles]).order_by("id"))

        incident_status_cycle = list(IncidentStatus.values)
        priorities = list(IncidentPriority.values)
        inc_types = [t for t in IncidentType.values if t != IncidentType.UNCERTAIN]

        incidents = []
        for i in range(n):
            cp = client_profiles[i]
            v = vehicles[i]
            city_name, base_lat, base_lon = BOLIVIA_CITIES[i % len(BOLIVIA_CITIES)]
            ilat, ilon = _jitter_lat_lon(base_lat, base_lon, Decimal("0.04"))
            itype = random.choice(inc_types)
            status = random.choices(
                incident_status_cycle,
                weights=[2, 2, 3, 5, 8, 45, 15],
                k=1,
            )[0]
            incidents.append(
                Incident(
                    client=cp,
                    vehicle=v,
                    status=status,
                    priority=random.choice(priorities),
                    incident_type=itype,
                    description=f"Emergencia vehicular tipo {itype} en {city_name}. Requiere asistencia.",
                    latitude=ilat,
                    longitude=ilon,
                    address_text=f"Km {random.randint(1, 120)} carretera a {city_name}, Bolivia",
                    ai_transcription="",
                    ai_classification_raw=None,
                    ai_summary=f"Clasificación simulada: {itype} en zona {city_name}.",
                    ai_confidence=round(random.uniform(0.55, 0.95), 3),
                    closed_at=_bolivia_now() if status in (IncidentStatus.COMPLETED, IncidentStatus.CANCELLED) else None,
                    created_at=now,
                    updated_at=now,
                )
            )
        Incident.objects.bulk_create(incidents, batch_size=500)
        incidents = list(Incident.objects.filter(client_id__in=[c.id for c in client_profiles]).order_by("id"))

        # Evidencias: FileField requiere save() por archivo
        for i, inc in enumerate(incidents):
            Evidence.objects.create(
                incident=inc,
                evidence_type=EvidenceType.IMAGE,
                file=ContentFile(MINIMAL_PNG, name=f"seed_ev_{inc.id}_{i}.png"),
                transcription="",
                transcription_done=False,
                image_analysis=None,
                label=random.choice(["vehículo", "llanta", "motor", "batería", "carretera"]),
            )

        admin_actor = client_users[0]
        for i, inc in enumerate(incidents):
            prev = IncidentStatus.PENDING if i % 3 == 0 else random.choice(incident_status_cycle)
            IncidentStatusHistory.objects.create(
                incident=inc,
                previous_status=prev,
                new_status=inc.status,
                changed_by=admin_actor,
                notes="Cambio de estado (datos de prueba).",
            )

        assignments = []
        for i in range(n):
            inc = incidents[i]
            w = workshops[i]
            tech = technicians[i]
            dist = Decimal(str(round(random.uniform(1.5, 45.0), 2)))
            st_weights = [5, 20, 3, 10, 8, 12, 42]
            st = random.choices(list(AssignmentStatus.values), weights=st_weights, k=1)[0]
            assignments.append(
                Assignment(
                    incident=inc,
                    workshop=w,
                    technician=tech,
                    status=st,
                    distance_km=dist,
                    estimated_arrival_minutes=random.randint(12, 90),
                    service_cost=Decimal(str(round(random.uniform(120, 2500), 2))) if st == AssignmentStatus.COMPLETED else None,
                    offered_at=now,
                )
            )
        Assignment.objects.bulk_create(assignments, batch_size=500)
        assignments = list(
            Assignment.objects.filter(incident_id__in=[x.id for x in incidents]).select_related("incident", "workshop").order_by("id")
        )

        # Ajustar marcas de tiempo coherentes con el estado
        for a in assignments:
            if a.status in (
                AssignmentStatus.ACCEPTED,
                AssignmentStatus.IN_ROUTE,
                AssignmentStatus.ARRIVED,
                AssignmentStatus.IN_SERVICE,
                AssignmentStatus.COMPLETED,
            ):
                a.accepted_at = _bolivia_now() - timedelta(minutes=random.randint(30, 200))
            if a.status in (
                AssignmentStatus.IN_ROUTE,
                AssignmentStatus.ARRIVED,
                AssignmentStatus.IN_SERVICE,
                AssignmentStatus.COMPLETED,
            ):
                a.arrived_at = _bolivia_now() - timedelta(minutes=random.randint(10, 120))
            if a.status == AssignmentStatus.COMPLETED:
                a.completed_at = _bolivia_now() - timedelta(minutes=random.randint(1, 60))
        Assignment.objects.bulk_update(assignments, ["accepted_at", "arrived_at", "completed_at"], batch_size=500)

        base_date = date.today() - timedelta(days=365 * 3)
        commission_configs = [
            CommissionConfig(
                percentage=Decimal(str(round(random.uniform(5.0, 15.0), 2))),
                description=f"[seed] Comisión período {i}",
                effective_from=base_date + timedelta(days=i * 2),
                created_by=None,
                is_active=(i == n - 1),
                created_at=now,
            )
            for i in range(n)
        ]
        CommissionConfig.objects.bulk_create(commission_configs, batch_size=500)

        payments = []
        for i, a in enumerate(assignments):
            total = Decimal(str(round(random.uniform(200, 3200), 2)))
            rate = commission_configs[i % len(commission_configs)].percentage
            comm = (total * rate / Decimal("100")).quantize(Decimal("0.01"))
            net = (total - comm).quantize(Decimal("0.01"))
            if a.status == AssignmentStatus.COMPLETED:
                pst = (
                    PaymentStatus.COMMISSION_SETTLED
                    if random.random() < 0.28
                    else PaymentStatus.CLIENT_PAID
                )
            else:
                pst = PaymentStatus.PENDING
            paid_at = _bolivia_now() if pst in (PaymentStatus.CLIENT_PAID, PaymentStatus.COMMISSION_SETTLED) else None
            settled_at = _bolivia_now() if pst == PaymentStatus.COMMISSION_SETTLED else None
            payments.append(
                Payment(
                    assignment=a,
                    commission_config=commission_configs[i % len(commission_configs)],
                    total_amount=total,
                    commission_rate=rate,
                    commission_amount=comm,
                    workshop_net_amount=net,
                    stripe_payment_intent_id=f"pi_seed_{a.id}",
                    stripe_transfer_id=f"tr_seed_{a.id}" if paid_at else "",
                    stripe_charge_id=f"ch_seed_{a.id}" if paid_at else "",
                    status=pst,
                    currency="bob",
                    paid_at=paid_at,
                    settled_at=settled_at,
                    created_at=now,
                )
            )
        Payment.objects.bulk_create(payments, batch_size=500)

        ratings = []
        for i, a in enumerate(assignments):
            cp = client_profiles[i]
            score = random.choices([1, 2, 3, 4, 5], weights=[2, 3, 8, 25, 62], k=1)[0]
            ratings.append(
                WorkshopRating(
                    workshop=a.workshop,
                    client=cp,
                    assignment=a,
                    score=score,
                    comment=random.choice(
                        [
                            "Buen servicio en ruta.",
                            "Técnico puntual, recomendado.",
                            "Resolveron el pinchazo rápido.",
                            "Atención correcta en La Paz.",
                            "",
                        ]
                    ),
                    created_at=now,
                )
            )
        WorkshopRating.objects.bulk_create(ratings, batch_size=500)

        metrics = []
        for i, a in enumerate(assignments):
            metrics.append(
                IncidentCycleMetric(
                    assignment=a,
                    seconds_to_assignment=random.randint(30, 600),
                    seconds_to_arrival=random.randint(300, 3600),
                    # seconds_to_total_resolution=random.randint(1800, 7200) if a.completed_at else None,
                    service_cost=a.service_cost,
                    ai_confidence=incidents[i].ai_confidence,
                    ai_predicted_type=incidents[i].incident_type,
                    created_at=now,
                )
            )
        IncidentCycleMetric.objects.bulk_create(metrics, batch_size=500)

        notif_types = list(NotificationType.values)
        notifications = []
        for i in range(n):
            u = random.choice(client_users + owner_users + tech_users)
            inc = incidents[i % len(incidents)]
            notifications.append(
                Notification(
                    user=u,
                    title=f"Notificación #{i + 1:04d}",
                    body=f"Evento relacionado con incidente en {BOLIVIA_CITIES[i % len(BOLIVIA_CITIES)][0]}.",
                    notification_type=random.choice(notif_types),
                    incident=inc,
                    data={"seed": True, "index": i},
                    is_read=random.random() > 0.4,
                    push_sent=False,
                    created_at=now,
                )
            )
        Notification.objects.bulk_create(notifications, batch_size=500)
