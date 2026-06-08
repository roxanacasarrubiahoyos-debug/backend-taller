from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.payments.models import WorkshopSubscriptionPlan
from apps.payments.subscription_serializers import (
    WorkshopOwnerSubscriptionSerializer,
    WorkshopSubscriptionPlanPublicSerializer,
)
from apps.payments.subscription_service import (
    create_checkout_session,
    get_or_create_owner_subscription,
    verify_checkout_session,
)
from apps.users.permissions import IsWorkshopOwner


@api_view(['GET'])
@permission_classes([AllowAny])
def public_subscription_plans(request):
    qs = WorkshopSubscriptionPlan.objects.filter(is_active=True, is_public=True)
    return Response(WorkshopSubscriptionPlanPublicSerializer(qs, many=True).data)


@api_view(['GET'])
@permission_classes([IsWorkshopOwner])
def my_subscription(request):
    owner = request.user.owner_profile
    sub = get_or_create_owner_subscription(owner)
    return Response(WorkshopOwnerSubscriptionSerializer(sub).data)


@api_view(['POST'])
@permission_classes([IsWorkshopOwner])
def create_subscription_checkout(request):
    plan_id = request.data.get('plan_id')
    if not plan_id:
        return Response({'error': 'plan_id es requerido'}, status=status.HTTP_400_BAD_REQUEST)

    plan = WorkshopSubscriptionPlan.objects.filter(
        pk=plan_id, is_active=True, is_public=True
    ).first()
    if not plan:
        return Response({'error': 'Plan no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    success_path = request.data.get('success_path') or '/auth/subscription-success'
    cancel_path = request.data.get('cancel_path') or '/taller/suscripcion'

    result = create_checkout_session(
        owner_profile=request.user.owner_profile,
        plan=plan,
        success_path=success_path,
        cancel_path=cancel_path,
    )
    if result.get('error'):
        return Response({'error': result['error']}, status=status.HTTP_400_BAD_REQUEST)
    return Response(result)


@api_view(['POST'])
@permission_classes([IsWorkshopOwner])
def verify_subscription_session(request):
    session_id = request.data.get('session_id')
    result = verify_checkout_session(session_id, request.user.owner_profile)
    if result.get('error'):
        return Response({'error': result['error']}, status=status.HTTP_400_BAD_REQUEST)
    sub = result['subscription']
    return Response({
        'active': result['active'],
        'subscription': WorkshopOwnerSubscriptionSerializer(sub).data,
    })
