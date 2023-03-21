# Generated by Django 3.1.2 on 2023-03-08 10:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dataCtrl', '0008_auto_20230308_0633'),
    ]

    operations = [
        migrations.AddField(
            model_name='tslide',
            name='has_old_ai',
            field=models.SmallIntegerField(default=0, verbose_name='切片进行过旧版本智能诊断'),
        ),
        migrations.AlterField(
            model_name='tslidediagnose',
            name='four_part_result',
            field=models.CharField(max_length=255, null=True, verbose_name='[{"part":1,"result":1}]'),
        ),
    ]
