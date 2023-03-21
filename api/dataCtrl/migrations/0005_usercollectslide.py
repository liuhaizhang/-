# Generated by Django 3.1.2 on 2023-03-02 02:42

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0001_initial'),
        ('dataCtrl', '0004_auto_20230227_2358'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserCollectSlide',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('create_time', models.DateTimeField(auto_now_add=True)),
                ('tslide', models.ForeignKey(db_constraint=False, on_delete=django.db.models.deletion.CASCADE, related_name='collect', to='dataCtrl.tslide')),
                ('user', models.ForeignKey(db_constraint=False, on_delete=django.db.models.deletion.CASCADE, related_name='collect', to='user.taccount')),
            ],
            options={
                'db_table': 't_user_collect_slide',
                'managed': True,
            },
        ),
    ]
