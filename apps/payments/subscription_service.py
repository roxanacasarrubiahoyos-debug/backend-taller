"""
Suscripciones de talleres vía Stripe Checkout (mode=subscription).
"""
from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

import stripe
from django.conf import settings
from django.utils import timezone

from apps.payments.models import (
    BillingInterval,
    WorkshopOwnerSubscription,
    WorkshopSubscriptionPlan,
    WorkshopSubscriptionStatus,
)
from apps.payments.stripe_service import StripeService

stripe.api_key = settings.STRIPE_SECRET_KEY


def _frontend_base() -> str:
    return getattr(settings, 'FRONTEND_URL', 'https://ahoringallego.smartcondominio.lat').rstrip('/')


def sync_plan_to_stripe(plan: WorkshopSubscriptionPlan) -> WorkshopSubscriptionPlan:
    """Crea o actualiza Product + Price en Stripe para un plan."""
    if not settings.STRIPE_SECRET_KEY:
        return plan

    if not plan.stripe_product_id:
        product = stripe.Product.create(
            name=plan.name,
            description=(plan.description or '')[:500] or None,
            metadata={'plan_id': str(plan.id)},
        )
        plan.stripe_product_id = product.id
    else:
        stripe.Product.modify(
            plan.stripe_product_id,
            name=plan.name,
            description=(plan.description or '')[:500] or None,
            active=plan.is_active,
        )

    amount_cents = int(Decimal(plan.price_amount) * 100)
    interval = plan.billing_interval or BillingInterval.MONTH

    need_new_price = True
    if plan.stripe_price_id:
        try:
            existing = stripe.Price.retrieve(plan.stripe_price_id)
            if (
                existing.get('unit_amount') == amount_cents
                and existing.get('currency') == plan.currency
                and existing.get('recurring', {}).get('interval') == interval
            ):
                need_new_price = False
        except stripe.error.StripeError:
            need_new_price = True

    if need_new_price:
        if plan.stripe_price_id:
            try:
                stripe.Price.modify(plan.stripe_price_id, active=False)
            except stripe.error.StripeError:
                pass
        price = stripe.Price.create(
            product=plan.stripe_product_id,
            unit_amount=amount_cents,
            currency=plan.currency,
            recurring={'interval': interval},
            metadata={'plan_id': str(plan.id)},
        )
        plan.stripe_price_id = price.id

    plan.save(
        update_fields=[
            'stripe_product_id',
            'stripe_price_id',
            'updated_at',
        ]
    )
    return plan


def ensure_owner_stripe_customer(owner_profile) -> str | None:
    if owner_profile.stripe_customer_id:
        return owner_profile.stripe_customer_id
    user = owner_profile.user
    result = StripeService.create_customer(
        email=user.email,
        name=f'{user.first_name} {user.last_name}'.strip() or user.username,
        phone=user.phone or '',
    )
    customer_id = result.get('customer_id')
    if customer_id:
        owner_profile.stripe_customer_id = customer_id
        owner_profile.save(update_fields=['stripe_customer_id'])
    return customer_id


def get_or_create_owner_subscription(owner_profile) -> WorkshopOwnerSubscription:
    sub, _ = WorkshopOwnerSubscription.objects.get_or_create(owner=owner_profile)
    return sub


def create_checkout_session(
    *,
    owner_profile,
    plan: WorkshopSubscriptionPlan,
    success_path: str = '/auth/subscription-success',
    cancel_path: str = '/auth/register',
) -> dict:
    if not plan.is_active or not plan.is_public:
        return {'error': 'Plan no disponible'}
    if not plan.stripe_price_id:
        sync_plan_to_stripe(plan)
    if not plan.stripe_price_id:
        return {'error': 'Plan sin precio Stripe configurado'}

    customer_id = ensure_owner_stripe_customer(owner_profile)
    if not customer_id:
        return {'error': 'No se pudo crear cliente Stripe'}

    sub = get_or_create_owner_subscription(owner_profile)
    sub.plan = plan
    sub.status = WorkshopSubscriptionStatus.PENDING
    sub.save(update_fields=['plan', 'status', 'updated_at'])

    base = _frontend_base()
    try:
        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode='subscription',
            line_items=[{'price': plan.stripe_price_id, 'quantity': 1}],
            success_url=f'{base}{success_path}?session_id={{CHECKOUT_SESSION_ID}}',
            cancel_url=f'{base}{cancel_path}?canceled=1',
            metadata={
                'owner_profile_id': str(owner_profile.id),
                'plan_id': str(plan.id),
                'user_id': str(owner_profile.user_id),
            },
            subscription_data={
                'metadata': {
                    'owner_profile_id': str(owner_profile.id),
                    'plan_id': str(plan.id),
                },
            },
        )
        return {'checkout_url': session.url, 'session_id': session.id}
    except stripe.error.StripeError as exc:
        return {'error': str(exc)}


def _dt_from_unix(ts) -> datetime | None:
    if not ts:
        return None
    return datetime.fromtimestamp(int(ts), tz=dt_timezone.utc)


def apply_stripe_subscription(stripe_sub: dict) -> WorkshopOwnerSubscription | None:
    owner_id = (stripe_sub.get('metadata') or {}).get('owner_profile_id')
    if not owner_id:
        return None

    from apps.users.models import WorkshopOwnerProfile
    from apps.workshops.models import Workshop

    try:
        owner = WorkshopOwnerProfile.objects.get(pk=int(owner_id))
    except (WorkshopOwnerProfile.DoesNotExist, ValueError, TypeError):
        return None

    sub = get_or_create_owner_subscription(owner)
    plan_id = (stripe_sub.get('metadata') or {}).get('plan_id')
    if plan_id:
        plan = WorkshopSubscriptionPlan.objects.filter(pk=int(plan_id)).first()
        if plan:
            sub.plan = plan

    status_map = {
        'active': WorkshopSubscriptionStatus.ACTIVE,
        'trialing': WorkshopSubscriptionStatus.ACTIVE,
        'past_due': WorkshopSubscriptionStatus.PAST_DUE,
        'canceled': WorkshopSubscriptionStatus.CANCELED,
        'unpaid': WorkshopSubscriptionStatus.PAST_DUE,
        'incomplete': WorkshopSubscriptionStatus.INCOMPLETE,
        'incomplete_expired': WorkshopSubscriptionStatus.CANCELED,
    }
    sub.status = status_map.get(stripe_sub.get('status'), WorkshopSubscriptionStatus.PENDING)
    sub.stripe_subscription_id = stripe_sub.get('id') or sub.stripe_subscription_id
    sub.cancel_at_period_end = bool(stripe_sub.get('cancel_at_period_end'))
    sub.current_period_start = _dt_from_unix(stripe_sub.get('current_period_start'))
    sub.current_period_end = _dt_from_unix(stripe_sub.get('current_period_end'))
    sub.save()

    # Crear taller automáticamente si no tiene uno
    if not Workshop.objects.filter(owner=owner).exists():
        user = owner.user
        Workshop.objects.create(
            owner=owner,
            name=f'Taller de {user.first_name or user.username}',
            address='Por completar',
            phone=user.phone or 'Por completar',
            email=user.email or '',
            latitude=0,
            longitude=0,
            services=[],
            is_active=True,
            is_verified=False,
        )

    return sub


def handle_checkout_session_completed(session: dict) -> WorkshopOwnerSubscription | None:
    if session.get('mode') != 'subscription':
        return None
    stripe_sub_id = session.get('subscription')
    if not stripe_sub_id:
        return None
    try:
        stripe_sub = stripe.Subscription.retrieve(stripe_sub_id)
        return apply_stripe_subscription(stripe_sub)
    except stripe.error.StripeError:
        return None


def verify_checkout_session(session_id: str, owner_profile) -> dict:
    if not session_id:
        return {'error': 'session_id requerido'}
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError as exc:
        return {'error': str(exc)}

    meta_owner = (session.get('metadata') or {}).get('owner_profile_id')
    if meta_owner and str(owner_profile.id) != str(meta_owner):
        return {'error': 'Sesión no pertenece a este usuario'}

    if session.get('payment_status') != 'paid' and session.get('status') != 'complete':
        return {'error': 'Pago aún no completado', 'status': session.get('status')}

    sub = handle_checkout_session_completed(session)
    if not sub:
        return {'error': 'No se pudo activar la suscripción'}

    return {
        'subscription': sub,
        'active': sub.is_operational,
    }