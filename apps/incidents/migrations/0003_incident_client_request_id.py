from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('incidents', '0002_incidentcyclemetric'),
    ]

    operations = [
        migrations.AddField(
            model_name='incident',
            name='client_request_id',
            field=models.CharField(blank=True, db_index=True, max_length=36, null=True, unique=True),
        ),
    ]
