# Generated by Django 3.1.2 on 2023-01-08 01:48

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('user', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SlideDiagnoseImage',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
            ],
            options={
                'db_table': 't_slide_diagnose_image',
                'managed': True,
            },
        ),
        migrations.CreateModel(
            name='TSlide',
            fields=[
                ('slide_id', models.AutoField(primary_key=True, serialize=False)),
                ('slide_file_name', models.CharField(blank=True, max_length=100, null=True)),
                ('slide_path', models.CharField(blank=True, max_length=500, null=True)),
                ('status', models.IntegerField(blank=True, null=True)),
                ('has_data', models.IntegerField(blank=True, null=True)),
                ('create_time', models.DateTimeField(auto_now_add=True, null=True)),
                ('confirm_time', models.DateTimeField(blank=True, null=True)),
                ('real_width', models.IntegerField(blank=True, null=True)),
                ('real_height', models.IntegerField(blank=True, null=True)),
                ('cut_count', models.IntegerField(blank=True, null=True)),
                ('atrophy', models.IntegerField(blank=True, null=True)),
                ('is_diagnostic', models.IntegerField(blank=True, null=True)),
                ('level', models.IntegerField(blank=True, null=True)),
                ('ratio', models.FloatField(blank=True, null=True)),
                ('scanning_time', models.DateTimeField(blank=True, null=True, verbose_name='扫描时间')),
                ('confirm_account', models.ForeignKey(blank=True, db_column='confirm_account', null=True, on_delete=django.db.models.deletion.DO_NOTHING, to='user.taccount')),
            ],
            options={
                'db_table': 't_slide',
                'managed': True,
            },
        ),
        migrations.CreateModel(
            name='TSlideLabel',
            fields=[
                ('slide_label_id', models.AutoField(primary_key=True, serialize=False)),
                ('slide_file_name', models.CharField(blank=True, max_length=100, null=True)),
                ('label_title', models.CharField(blank=True, max_length=200, null=True)),
                ('label_desc', models.CharField(blank=True, max_length=1000, null=True)),
                ('label_info', models.TextField(blank=True, null=True)),
                ('create_time', models.DateTimeField(auto_now_add=True, null=True)),
                ('update_time', models.DateTimeField(auto_now=True, null=True)),
                ('is_scope', models.IntegerField(blank=True, null=True, verbose_name='是否是固定框')),
                ('type', models.CharField(blank=True, max_length=255, null=True)),
                ('creator', models.ForeignKey(blank=True, db_column='creator', null=True, on_delete=django.db.models.deletion.DO_NOTHING, to='user.taccount')),
                ('slide', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.DO_NOTHING, to='dataCtrl.tslide')),
            ],
            options={
                'db_table': 't_slide_label',
                'managed': True,
            },
        ),
        migrations.CreateModel(
            name='TSlideImage',
            fields=[
                ('slide_image_id', models.AutoField(primary_key=True, serialize=False)),
                ('path', models.CharField(blank=True, max_length=255, null=True)),
                ('type', models.IntegerField(blank=True, null=True)),
                ('note', models.TextField(blank=True, null=True)),
                ('system', models.IntegerField(blank=True, null=True)),
                ('cell_type', models.IntegerField(blank=True, null=True)),
                ('slide', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.DO_NOTHING, to='dataCtrl.tslide')),
            ],
            options={
                'db_table': 't_slide_image',
                'managed': True,
            },
        ),
        migrations.CreateModel(
            name='TSlideDiagnose',
            fields=[
                ('slide_diagnose_id', models.AutoField(primary_key=True, serialize=False)),
                ('rise', models.CharField(blank=True, max_length=255, null=True)),
                ('name', models.CharField(blank=True, max_length=255, null=True)),
                ('gender', models.CharField(blank=True, max_length=255, null=True)),
                ('age', models.CharField(blank=True, max_length=255, null=True)),
                ('number', models.CharField(blank=True, max_length=255, null=True)),
                ('department', models.CharField(blank=True, max_length=255, null=True)),
                ('hospital', models.CharField(blank=True, max_length=255, null=True)),
                ('part', models.CharField(blank=True, max_length=255, null=True)),
                ('content', models.CharField(blank=True, max_length=255, null=True)),
                ('diagnose', models.CharField(blank=True, max_length=255, null=True)),
                ('doctor', models.CharField(blank=True, max_length=255, null=True)),
                ('create_time', models.DateTimeField(auto_now_add=True, null=True)),
                ('system', models.IntegerField(blank=True, null=True)),
                ('slide_type', models.SmallIntegerField(default=1, verbose_name='暂时就是这个{1:"CT/活检"}')),
                ('check_entirety_result', models.CharField(default='无', max_length=512, verbose_name='医生手动输入诊断结果')),
                ('check_part_result', models.TextField(null=True, verbose_name="[{'part':胃体,'level':胃体的诊断情况,'note':'备注情况'},]")),
                ('image', models.ManyToManyField(through='dataCtrl.SlideDiagnoseImage', to='dataCtrl.TSlideImage')),
                ('slide', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.DO_NOTHING, to='dataCtrl.tslide')),
            ],
            options={
                'db_table': 't_slide_diagnose',
                'managed': True,
            },
        ),
        migrations.AddField(
            model_name='slidediagnoseimage',
            name='slide_diagnose',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='dataCtrl.tslidediagnose'),
        ),
        migrations.AddField(
            model_name='slidediagnoseimage',
            name='slide_image',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='dataCtrl.tslideimage'),
        ),
        migrations.CreateModel(
            name='SlideDiagnoseContent',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('number', models.IntegerField(blank=True, null=True, verbose_name='编号')),
                ('atrophy', models.IntegerField(blank=True, null=True, verbose_name='疾病程度')),
                ('part', models.CharField(blank=True, max_length=255, null=True, verbose_name='部位')),
                ('content', models.TextField(verbose_name='内容')),
                ('t_slide_diagnose', models.ForeignKey(on_delete=django.db.models.deletion.RESTRICT, to='dataCtrl.tslidediagnose')),
            ],
            options={
                'db_table': 't_slide_diagnose_content',
                'managed': True,
            },
        ),
    ]
