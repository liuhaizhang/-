# Generated by Django 3.1.2 on 2023-03-02 18:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dataCtrl', '0005_usercollectslide'),
    ]

    operations = [
        migrations.AddField(
            model_name='tslide',
            name='is_delete',
            field=models.BooleanField(default=False, verbose_name='web上传文件，重名覆盖，标记删除'),
        ),
        migrations.AddField(
            model_name='usercollectslide',
            name='is_delete',
            field=models.BooleanField(default=False, verbose_name='web上传文件，重名覆盖，标记删除'),
        ),
    ]