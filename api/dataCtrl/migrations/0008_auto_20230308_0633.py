# Generated by Django 3.1.2 on 2023-03-08 06:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dataCtrl', '0007_auto_20230302_2312'),
    ]

    operations = [
        migrations.AddField(
            model_name='tslidediagnose',
            name='clearly_visible',
            field=models.CharField(max_length=255, null=True, verbose_name='显著可见'),
        ),
        migrations.AddField(
            model_name='tslidediagnose',
            name='detailed_explanation',
            field=models.CharField(max_length=512, null=True, verbose_name='详解'),
        ),
        migrations.AddField(
            model_name='tslidediagnose',
            name='four_part_result',
            field=models.CharField(max_length=255, null=True, verbose_name='[{"part":"萎缩性","level":"无(-)"}]'),
        ),
        migrations.AddField(
            model_name='tslidediagnose',
            name='medical_number',
            field=models.CharField(max_length=128, null=True, verbose_name='病历号'),
        ),
        migrations.AddField(
            model_name='tslidediagnose',
            name='print_count',
            field=models.IntegerField(default=0, verbose_name='打印次数'),
        ),
    ]
