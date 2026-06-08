import stripe
from django.conf import settings
from apps.payments.models import CommissionConfig


stripe.api_key = settings.STRIPE_SECRET_KEY


class StripeService:
    """
    Servicio de integración con Stripe para pagos y comisiones.
    """

    @staticmethod
    def get_active_commission() -> float:
        """Porcentaje de comisión vigente (misma regla que GET commission/current/)."""
        config = CommissionConfig.get_applicable_for_date()
        return float(config.percentage) if config else 10.0

    @staticmethod
    def create_payment_intent(amount_usd: float, customer_id: str, metadata: dict, payment_method_id: str = None) -> dict:
        """
        Crea el intento de pago para el cliente.
        Si se proporciona payment_method_id, crea y confirma en un solo paso (flujo oficial Stripe).

        Args:
            amount_usd: Monto en dólares
            customer_id: ID del customer en Stripe
            metadata: Datos adicionales (incident_id, assignment_id, etc.)
            payment_method_id: ID del PaymentMethod (si se confirma automáticamente)

        Returns:
            dict con client_secret, payment_intent_id y status
        """
        if not settings.STRIPE_SECRET_KEY:
            return {
                'error': 'Stripe not configured',
                'client_secret': None,
                'payment_intent_id': None
            }

        try:
            payload = {
                'amount': int(amount_usd * 100),  # Stripe usa centavos
                'currency': 'usd',
                'metadata': metadata,
            }

            # Si hay payment_method_id, crear y confirmar en un solo paso
            if payment_method_id:
                payload['payment_method'] = payment_method_id
                payload['confirm'] = True
                payload['off_session'] = False
                if customer_id:
                    payload['customer'] = customer_id
            else:
                # Cliente confirma en la app (CardField → PaymentMethod → confirm)
                payload['automatic_payment_methods'] = {'enabled': True}
                if customer_id:
                    payload['customer'] = customer_id

            intent = stripe.PaymentIntent.create(**payload)

            return {
                'client_secret': intent.client_secret,
                'payment_intent_id': intent.id,
                'status': intent.status,
                'requires_action': intent.status == 'requires_action',
                'next_action': intent.next_action if hasattr(intent, 'next_action') else None
            }
        except stripe.error.CardError as e:
            return {
                'error': e.user_message or str(e),
                'client_secret': None,
                'payment_intent_id': None,
                'status': 'failed'
            }
        except Exception as e:
            return {
                'error': str(e),
                'client_secret': None,
                'payment_intent_id': None,
                'status': 'failed'
            }

    @staticmethod
    def transfer_to_workshop(amount_usd: float, stripe_account_id: str, metadata: dict) -> dict:
        """
        Transfiere el monto neto al taller vía Stripe Connect.

        Args:
            amount_usd: Monto neto a transferir
            stripe_account_id: ID de la cuenta Connect del taller
            metadata: Datos adicionales

        Returns:
            dict con transfer_id o error
        """
        if not settings.STRIPE_SECRET_KEY:
            return {'error': 'Stripe not configured', 'transfer_id': None}

        try:
            transfer = stripe.Transfer.create(
                amount=int(amount_usd * 100),
                currency='usd',
                destination=stripe_account_id,
                metadata=metadata,
            )
            return {'transfer_id': transfer.id}
        except Exception as e:
            return {'error': str(e), 'transfer_id': None}

    @staticmethod
    def create_stripe_account_link(account_id: str, refresh_url: str, return_url: str) -> dict:
        """
        Crea un enlace para que el taller conecte su cuenta Stripe (onboarding).

        Args:
            account_id: ID de la cuenta Connect
            refresh_url: URL de refresco si expira
            return_url: URL de retorno al completar

        Returns:
            dict con url del onboarding o error
        """
        if not settings.STRIPE_SECRET_KEY:
            return {'error': 'Stripe not configured', 'url': None}

        try:
            link = stripe.AccountLink.create(
                account=account_id,
                refresh_url=refresh_url,
                return_url=return_url,
                type='account_onboarding',
            )
            return {'url': link.url}
        except Exception as e:
            return {'error': str(e), 'url': None}

    @staticmethod
    def create_connected_account(email: str, country: str = 'US') -> dict:
        """
        Crea una cuenta Connect para un taller.

        Args:
            email: Email del dueño del taller
            country: Código de país (US, CO, etc.)

        Returns:
            dict con account_id o error
        """
        if not settings.STRIPE_SECRET_KEY:
            return {'error': 'Stripe not configured', 'account_id': None}

        try:
            account = stripe.Account.create(
                type='express',
                email=email,
                country=country,
                capabilities={
                    'transfers': {'requested': True},
                },
            )
            return {'account_id': account.id}
        except Exception as e:
            return {'error': str(e), 'account_id': None}

    @staticmethod
    def create_customer(email: str, name: str = '', phone: str = '') -> dict:
        """Crear customer para clientes móviles."""
        if not settings.STRIPE_SECRET_KEY:
            return {'error': 'Stripe not configured', 'customer_id': None}
        try:
            customer = stripe.Customer.create(
                email=email or None,
                name=name or None,
                phone=phone or None,
            )
            return {'customer_id': customer.id}
        except Exception as e:
            return {'error': str(e), 'customer_id': None}

    @staticmethod
    def handle_webhook(payload: bytes, sig_header: str):
        """
        Verifica y procesa un webhook de Stripe.

        Args:
            payload: Cuerpo de la petición (bytes)
            sig_header: Header 'Stripe-Signature'

        Returns:
            stripe.Event object

        Raises:
            ValueError si la firma es inválida
        """
        if not settings.STRIPE_WEBHOOK_SECRET:
            raise ValueError('Stripe webhook secret not configured')

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
            return event
        except ValueError as e:
            raise ValueError(f'Invalid payload: {e}')
        except stripe.error.SignatureVerificationError as e:
            raise ValueError(f'Invalid signature: {e}')
