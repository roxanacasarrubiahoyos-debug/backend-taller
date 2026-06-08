from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from apps.users.models import User
from apps.users.serializers import (
    RegisterWorkshopOwnerSerializer, UserSerializer, ProfileUpdateSerializer
)
from apps.users.permissions import IsWorkshopOwner
from rest_framework.permissions import IsAuthenticated


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    """Registro de dueño de taller + checkout Stripe del plan elegido."""
    serializer = RegisterWorkshopOwnerSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        refresh = RefreshToken.for_user(user)

        from apps.payments.subscription_service import create_checkout_session
        from apps.workshops.models import Workshop

        plan = serializer.context.get('subscription_plan')
        checkout = create_checkout_session(
            owner_profile=user.owner_profile,
            plan=plan,
            success_path='/auth/subscription-success',
            cancel_path='/auth/register',
        )

        # Crear taller básico automáticamente al registrarse
        if not Workshop.objects.filter(owner=user.owner_profile).exists():
            Workshop.objects.create(
                owner=user.owner_profile,
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

        payload = {
            'user': UserSerializer(user).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            },
            'requires_subscription_payment': True,
        }
        if checkout.get('checkout_url'):
            payload['checkout_url'] = checkout['checkout_url']
            payload['checkout_session_id'] = checkout.get('session_id')
        elif checkout.get('error'):
            payload['checkout_error'] = checkout['error']

        return Response(payload, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    """Login de dueño de taller"""
    username = request.data.get('username')
    password = request.data.get('password')

    user = authenticate(username=username, password=password)

    if user is None:
        return Response({'error': 'Credenciales inválidas'}, status=status.HTTP_401_UNAUTHORIZED)

    if user.role not in ('workshop_owner', 'admin'):
        return Response({'error': 'Esta cuenta no puede acceder al panel web'}, status=status.HTTP_403_FORBIDDEN)

    refresh = RefreshToken.for_user(user)
    return Response({
        'user': UserSerializer(user).data,
        'tokens': {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }
    })


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def profile(request):
    """Ver y actualizar perfil (dueño de taller o administrador)"""
    if request.method == 'GET':
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    elif request.method == 'PUT':
        serializer = ProfileUpdateSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(UserSerializer(request.user).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_fcm_token(request):
    from apps.users.serializers import FCMTokenSerializer

    serializer = FCMTokenSerializer(data=request.data)
    if serializer.is_valid():
        request.user.fcm_token = serializer.validated_data['fcm_token']
        request.user.save(update_fields=['fcm_token'])
        return Response({
            'message': 'Token FCM actualizado',
            'token_type': 'expo' if request.user.fcm_token.startswith('ExponentPushToken') else 'fcm'
        })
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)