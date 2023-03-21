from django.db import models
from user.models import TAccount
from django.forms.models import model_to_dict
from django.db.models import Count

# Create your models here.
#2023-03-02: 用户收藏切片
class UserCollectSlide(models.Model):
    id = models.AutoField(primary_key = True)
    tslide = models.ForeignKey(to='TSlide',on_delete=models.CASCADE,db_constraint=False,related_name='collect')
    user = models.ForeignKey(to='user.TAccount',on_delete=models.CASCADE,db_constraint=False,related_name='collect')
    create_time = models.DateTimeField(auto_now_add=True)
    is_delete = models.BooleanField(default=False,verbose_name='web上传文件，重名覆盖，标记删除')
    class Meta:
        managed = True
        db_table = 't_user_collect_slide'

'''
   2023/1/6新增：记录切片和诊断结果的数据库表
   1、切片名重名了，就直接覆盖
'''
class SlideDiagnoseModel(models.Model):
      id = models.AutoField(primary_key=True)
      slide_name = models.CharField(max_length=512,verbose_name='切片名字',null=True)
      diagnose_result = models.CharField(max_length=512,verbose_name='诊断结果',null=True)
      create_time = models.DateTimeField(auto_now_add=True,verbose_name='数据创建时间')
      update_time = models.DateTimeField(auto_now=True,verbose_name='数据更新时间')
      class Meta:
          managed = True
          db_table = 't_slide_diagnose_result' #在数据库中，表名


class TSlide(models.Model):
    slide_id = models.AutoField(primary_key=True)
    slide_file_name = models.CharField(max_length=100, blank=True, null=True)
    slide_path = models.CharField(max_length=500, blank=True, null=True)
    status = models.IntegerField(blank=True, null=True) #2023-02-06,数值1=已标注，数值2=已检验，数值0=未标注未检验
    has_data = models.IntegerField(blank=True, null=True) #2023-02-06 是否生成数据文件
    create_time = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    confirm_time = models.DateTimeField(blank=True, null=True)
    real_width = models.IntegerField(blank=True, null=True)
    real_height = models.IntegerField(blank=True, null=True)
    confirm_account = models.ForeignKey(TAccount, models.DO_NOTHING, db_column='confirm_account', blank=True, null=True)
    cut_count = models.IntegerField(blank=True, null=True) #2023-02-06,切割次数,大于0就是已经切割
    atrophy = models.IntegerField(blank=True, null=True)
    is_diagnostic = models.IntegerField(blank=True, null=True) #2023-02-06，null=未处理，数值1=智能诊断了，2=计算中
    level = models.IntegerField(blank=True, null=True) #病情等级，1=轻度，2=中度，3=重度
    ratio = models.FloatField(blank=True, null=True)
    scanning_time = models.DateTimeField('扫描时间', blank=True, null=True,auto_now_add=True)
    #2023-2-27新增，切片的父切片文件id字段
    father_slide_id = models.IntegerField(verbose_name='小切片的父切片',default=0) #0代表这个切片没有父切片，【是TSlide表的id值】
    #2023-03-03在web上传文件选择重名覆盖时，重名的切片会直接数据库记录设置已经删除记录
    is_delete = models.BooleanField(default=False,verbose_name='web上传文件，重名覆盖，标记删除')
    #2023-03-08：标识切片进行过旧版本的智能诊断操作（被AI用户生成过标注信息，一个切片会有十几万条标注）
    has_old_ai = models.SmallIntegerField(default=0,verbose_name='切片进行过旧版本智能诊断')
    #2023-03-13 web端上传的切片是小切片时，用来标识,1表明该切片的小切片（无法切割），也是大切片（但其没有父切片），在首页展示和和收藏展示需要表明出来
    is_small_slide = models.SmallIntegerField(default=0,verbose_name='web上传的是小切片')
    #2023-03-16最后一次智能诊断时间，判断该时间于当前时间距离，超过一定时间，就自动判断智能智能诊断完成了
    diagnose_time = models.DateTimeField(null=True)

    class Meta:
        managed = True
        db_table = 't_slide'

    @property
    def mark_user(self):
        creators = self.tslidelabel_set.values('creator_id').annotate(count=Count("creator"))\
            .values("creator__real_name", "count")
        mark_info = []
        if creators:
            for c in creators:
                creator = c['creator__real_name'].replace("\r", "") if c['creator__real_name'] else " "
                mark_info.append(creator + "(" + str(c['count']) + ")")
        return ','.join(mark_info)

    @property
    def is_scope(self):
        return TSlideLabel.objects.filter(slide=self).count()

class TSlideLabel(models.Model):
    slide_label_id = models.AutoField(primary_key=True)
    slide_file_name = models.CharField(max_length=100, blank=True, null=True)
    label_title = models.CharField(max_length=200, blank=True, null=True)
    label_desc = models.CharField(max_length=1000, blank=True, null=True)
    label_info = models.TextField(blank=True, null=True)
    create_time = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    update_time = models.DateTimeField(blank=True, null=True, auto_now=True)
    slide = models.ForeignKey(TSlide, models.DO_NOTHING, blank=True, null=True)
    creator = models.ForeignKey(TAccount, models.DO_NOTHING, db_column='creator', blank=True, null=True)
    is_scope = models.IntegerField("是否是固定框", blank=True, null=True)
    type = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = True
        db_table = 't_slide_label'


class TSlideImage(models.Model):
    slide_image_id = models.AutoField(primary_key=True)
    slide = models.ForeignKey(TSlide, models.DO_NOTHING, blank=True, null=True)
    path = models.CharField(max_length=255, blank=True, null=True)
    # 1: twogland 二值图  2: cam 热力图 3: 截图 4：中心图
    type = models.IntegerField(blank=True, null=True)
    #type = 4 中心坐标
    note = models.TextField(blank=True, null=True)
    #截图使用 0主系统 1 萎缩系统 2 胃炎系统 3 活动性系统 4 肠上皮化生系统
    system = models.IntegerField(blank=True, null=True)
    #中心图分类 1杯状细胞 goblet 2淋巴细胞和浆细胞yancell 3中性粒细胞neutrophil
    cell_type = models.IntegerField(blank=True, null=True)
    '''2023-02-28:GPU智能诊断接口修改，新增2个字段part和result'''
    part = models.IntegerField(verbose_name='诊断部分',null=True)
    #1萎缩性，肠上皮化生，活动性，炎症
    result = models.IntegerField(verbose_name='诊断结果',null=True)
    #0无、1轻度、2中度、3重度
    #说明，一个切片进行新的智能诊断接口处理后，会产生四张图片，每张图片对应一个诊断部分和诊断结果。

    class Meta:
        managed = True
        db_table = 't_slide_image'


class TSlideDiagnose(models.Model):
    slide_diagnose_id = models.AutoField(primary_key=True)
    rise = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    gender = models.CharField(max_length=255, blank=True, null=True)
    age = models.CharField(max_length=255, blank=True, null=True)
    number = models.CharField(max_length=255, blank=True, null=True)#病历号
    department = models.CharField(max_length=255, blank=True, null=True)
    hospital = models.CharField(max_length=255, blank=True, null=True)
    part = models.CharField(max_length=255, blank=True, null=True)
    content = models.CharField(max_length=255, blank=True, null=True)
    diagnose = models.CharField(max_length=255, blank=True, null=True)
    doctor = models.CharField(max_length=255, blank=True, null=True)
    slide = models.ForeignKey(TSlide, models.DO_NOTHING, blank=True, null=True)
    image = models.ManyToManyField(TSlideImage, through='SlideDiagnoseImage')
    create_time = models.DateTimeField(blank=True, null=True, auto_now_add=True)
    #0主系统 1 萎缩系统 2 胃炎系统 3 活动性系统 4 肠上皮化生系统
    system = models.IntegerField(blank=True, null=True)
    #新增2022/12/06，在settings.SLIDE_TYPE.get(1) 拿到对应的中文
    slide_type = models.SmallIntegerField(default=1,verbose_name='暂时就是这个{1:"CT/活检"}')
    # 病理诊断中整体诊断的结果
    check_entirety_result=models.CharField(max_length=512,default='无',verbose_name="医生手动输入诊断结果")
    #新增2022/12/06， part=1 在settings.PART_OF_SELECTION.get(part)[1]拿到对应的中文，level=1,在settings.DIAGNOSE_LEVEL.get(level) 拿到对应的中文
    #新增2022/12/06，病理中，各个部位的诊断结果
    check_part_result = models.TextField(null=True,verbose_name="[{'part':胃体,'level':胃体的诊断情况,'note':'备注情况'},]")

    #2023-03-07诊断报告新增 显著可见、诊断部位（四个，[{'part':'','level'}]）、详解、打印次数、病历号
    clearly_visible = models.CharField(max_length=255,null=True,verbose_name='显著可见')
    four_part_result = models.CharField(max_length=255,null=True,verbose_name='[{"part":1,"result":1}]') #看public/web_upload_public.py下两个常量
    detailed_explanation = models.CharField(max_length=512,null=True,verbose_name='详解')
    print_count = models.IntegerField(default=0,verbose_name='打印次数')
    medical_number = models.CharField(max_length=128,null=True,verbose_name='病历号')#多的字段，没有用，病历号是上面的number
    '''
    切片号=切片外键.slide_file_name.split('.')[0]
    送检时间=切片外键.create_time
    '''


    class Meta:
        managed = True
        db_table = 't_slide_diagnose'


class SlideDiagnoseImage(models.Model):
    id = models.AutoField(primary_key=True)
    #slide_diagnose = models.ForeignKey(TSlideDiagnose, models.RESTRICT)
    #slide_image = models.ForeignKey(TSlideImage, models.RESTRICT)
    slide_diagnose = models.ForeignKey(TSlideDiagnose, models.PROTECT)
    slide_image = models.ForeignKey(TSlideImage, models.PROTECT)
    class Meta:
        managed = True
        db_table = 't_slide_diagnose_image'

class SlideDiagnoseContent(models.Model):
    id = models.AutoField(primary_key=True)
    number = models.IntegerField('编号', blank=True, null=True)
    # 0 无 1轻度 2中度 3重度
    atrophy = models.IntegerField('疾病程度', blank=True, null=True)
    part = models.CharField('部位', blank=True, null=True, max_length=255)
    content = models.TextField('内容')
    t_slide_diagnose = models.ForeignKey(TSlideDiagnose, models.RESTRICT)

    class Meta:
        managed = True
        db_table = 't_slide_diagnose_content'
