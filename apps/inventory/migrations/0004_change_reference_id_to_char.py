from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0003_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='stocktransaction',
            name='reference_id',
            field=models.CharField(max_length=64, blank=True, null=True),
        ),
    ]
