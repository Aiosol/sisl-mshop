# Generated by Django 5.1.6 on 2025-02-20 09:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('eshop', '0003_product_built_in_interface_product_communication_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='product',
            name='dimensions',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='Dimensions (W x H x D in mm):'),
        ),
    ]
