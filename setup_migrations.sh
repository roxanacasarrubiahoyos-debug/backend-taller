#!/bin/bash

# Script para configurar el backend y crear migraciones

echo "=== Setup Backend Emergencias Vehiculares ==="
echo ""

# Activar virtual environment
echo "1. Activando virtual environment..."
source venv/bin/activate

# Instalar dependencias
echo ""
echo "2. Instalando dependencias..."
pip install -r requirements.txt

# Verificar configuración
echo ""
echo "3. Verificando configuración de Django..."
python manage.py check

# Crear migraciones
echo ""
echo "4. Creando migraciones..."
python manage.py makemigrations users
python manage.py makemigrations workshops
python manage.py makemigrations vehicles
python manage.py makemigrations incidents
python manage.py makemigrations assignments
python manage.py makemigrations payments
python manage.py makemigrations notifications

# Aplicar migraciones
echo ""
echo "5. Aplicando migraciones..."
python manage.py migrate

echo ""
echo "=== Setup completado! ==="
echo ""
echo "Próximos pasos:"
echo "1. Crea un superusuario: python manage.py createsuperuser"
echo "2. En Django shell, asigna role='admin': user.role = 'admin'; user.save()"
echo "3. Ejecuta el servidor: python manage.py runserver"
echo "4. En otra terminal, ejecuta el worker: python manage.py qcluster"
