"""
Crea o actualiza un usuario administrador para el panel web (/admin).

Uso:
  python manage.py create_web_admin
  python manage.py create_web_admin --username admin --password admin123
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.users.models import Role


class Command(BaseCommand):
    help = 'Crea o actualiza un usuario con role=admin para ingresar al panel web'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='admin', help='Nombre de usuario')
        parser.add_argument('--password', default='admin123', help='Contraseña')
        parser.add_argument('--email', default='admin@local.test', help='Email')

    def handle(self, *args, **options):
        User = get_user_model()
        username = options['username']
        password = options['password']
        email = options['email']

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': email,
                'role': Role.ADMIN,
                'is_staff': True,
                'is_superuser': True,
                'is_active': True,
            },
        )
        if not created:
            user.role = Role.ADMIN
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            if email:
                user.email = email

        user.set_password(password)
        user.save()

        verb = 'Creado' if created else 'Actualizado'
        self.stdout.write(
            self.style.SUCCESS(
                f'{verb}: usuario "{username}" con role=admin (panel web y Django admin).',
            ),
        )
        self.stdout.write(f'  Login panel: POST /api/web/auth/login/  user={username}')
        self.stdout.write(f'  Ruta Angular: /admin/dashboard')
