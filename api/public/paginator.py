from django.core.paginator import Paginator
from django.core import serializers
from django.forms import model_to_dict
from dataCtrl.models import TSlide,UserCollectSlide,TSlideImage,TSlideLabel
from public.web_upload_public import DIAGNOSE_PART #诊断部位
from public.web_upload_public import DIAGNOSE_RESULT #诊断结果
import os
import time
import datetime
from django.conf import settings
from django.db.models import Q
from public.web_upload_public import slide_make_jpg #给切片生成缩略图的接口


#获取小切片缩略图的前缀
BMP_BEFORE = 'http://gastritis.thearay.net/color/'
class PublicPaginator(Paginator):

    def __init__(self, object_list, current_page=1,per_page=5, orphans=0,
                 allow_empty_first_page=True):
        super().__init__(object_list,per_page,orphans,allow_empty_first_page)
        self.object_list = object_list #数据集
        self._check_object_list_is_ordered()
        self.per_page = int(per_page) #每页的数据量
        self.orphans = int(orphans)
        self.allow_empty_first_page = allow_empty_first_page
        self.current_page = 1 if current_page==None else int(current_page) #要获取那一页的数据
    @property
    def result(self):
        #根据页数拿到结果集
        page_data = self.get_page(self.current_page)
        #拿到最终的数据集
        res = page_data.object_list
        try:
            #all 或 filter结尾的查询数据集转成列表
            res = serializers.serialize("python", res)
        except Exception as e:
            #values结尾的查询数据集转成列表
            res = list(res)

        #当前页是否有下一页，上一页
        has_next = 0
        has_prev = 0
        #有下一页：当前页面大于等于1，当前页*页面大小 < 总数量
        if self.current_page>=1 and self.current_page*self.per_page < self.count:
            has_next =1
        #有上一页：当前页大于1，且总数据量要大于页面大小
        if self.current_page>1 and self.count>self.per_page: #有上一页，页数大于1，page_size小于总数据量
            has_prev =1
        #获取的数据的页数
        current_page = self.current_page if self.current_page<=self.num_pages else self.num_pages
        dic ={
            'data':res, #当前页的数据
            'current_page':current_page, #当前页数
            'all_counts':self.count, #总数据量
            'page_size':self.per_page, #每页数据量
            'all_page':self.num_pages, #总页数
            'has_next':has_next, #是否有下一页
            'has_prev':has_prev, #是否有上一页
            'code':200,#状态码
        }
        return dic


class SlidePaginator(Paginator):
    '''
    专门给切片展示使用的分页器：
    1、传入object_list=查询数据集、current_page=搜索页面、per_page=页面大小
    2、按照需求，新增需要跨表或连表查询的数据
    3、返回的是python的dict
    '''
    def __init__(self, object_list, current_page=1,per_page=5, orphans=0,
                 allow_empty_first_page=True):
        super().__init__(object_list,per_page,orphans,allow_empty_first_page)
        self.object_list = object_list #数据集
        self._check_object_list_is_ordered()
        self.per_page = int(per_page) #每页的数据量
        self.orphans = int(orphans)
        self.allow_empty_first_page = allow_empty_first_page
        self.current_page = 1 if current_page==None else int(current_page) #要获取那一页的数据
    def result(self,current_user_id):
        dic = {
            'data': [],  # 当前页的数据
            'current_page': 0,  # 当前页数
            'all_counts': 0,  # 总数据量
            'page_size': 0,  # 每页数据量
            'all_page': 0,  # 总页数
            'has_next': 0,  # 是否有下一页
            'has_prev': 0  # 是否有上一页
        }
        #查询数据集为空时，直接返回空字典
        if not len(self.object_list):
            return dic

        #根据页数拿到结果集
        page_data = self.get_page(self.current_page)
        #拿到最终的数据集
        slide_queryset = page_data.object_list
        data_list = []
        for item in slide_queryset:
            item_dict = model_to_dict(item)
            item_dict['mark_user'] = item.mark_user
            item_dict['is_scope'] = item.is_scope
            #1、如果小切片的状态是已经标注，其父切片状态也是已标注
            child_slide = TSlide.objects.filter(father_slide_id=item.pk,status=1)
            if child_slide and item.status==0:
                #print('其子已经标注了')
                item_dict['status']=1
                item.status = 1
                print(item.slide_file_name,'设置标注状态为1')
                item.save()

            # 2、查看当前用户是否收藏该切片
            is_collect = UserCollectSlide.objects.filter(tslide_id=item.slide_id,user_id=current_user_id)
            if is_collect:
                item_dict['is_collect'] = 1 #当前用户收藏了该切片
            else:
                item_dict['is_collect'] = 0 #当前用户没有收藏该切片
            
            # 3、大切片拿到小切片的智能诊断结果展示
            child_slide = TSlide.objects.filter(father_slide_id=item.pk)
            child_lis ={}
            for slide in child_slide:
                '2023-03-19：子切片的智能诊断状态必须是已经完成的状态'
                if slide.is_diagnostic !=1:
                    continue
                diaginose_result = TSlideImage.objects.filter(part__isnull=False,slide_id=slide.pk)
                if len(diaginose_result)==4:
                    for result in diaginose_result:
                        #把诊断结果写到里面
                        child_lis[result.part]=DIAGNOSE_RESULT.get(result.result)
                    break #把第一个小切片的诊断结果
            item_dict['diagnose_result'] = child_lis
            '3.2、2023-03-13新增：web上传的是小切片，但没有父切片，所有智能诊断结果是拿自己的智能诊断结果,不能拿诊断状态是未处理的'
            if item.is_small_slide==1 and item.is_diagnostic:
                child_lis = {}
                diaginose_result = TSlideImage.objects.filter(part__isnull=False, slide_id=item.pk)
                for result in diaginose_result:
                    # 把切片智能结果拿到了
                    child_lis[result.part] = DIAGNOSE_RESULT.get(result.result)
                item_dict['diagnose_result'] = child_lis
                #缩略图地址重新修改：
                #dir_apth = os.path.dirname(item.slide_path).split(settings.SLIDE_SAVE_ROOT,1)[-1]
                #bmp_path = os.path.join(BMP_BEFORE,dir_apth,'preview.bmp')
                #item_dict['bmp_path'] = bmp_path
            '2023-03-20 bmp,小切片的缩略图'
            if item.is_small_slide:
                # 缩略图地址重新修改：
                dir_apth = os.path.dirname(item.slide_path).split(settings.SLIDE_SAVE_ROOT, 1)[-1]
                bmp_path = os.path.join(BMP_BEFORE, dir_apth, 'preview.bmp')
                item_dict['bmp_path'] = bmp_path
            '3.3、2023-03-13新增，通过小切片的诊断状态，计算中、完成、未处理 优先'
            child_slide_diagnose = child_slide.order_by('-is_diagnostic').first()
            if child_slide_diagnose:
                #大切片展示的是小切片的智能诊断状态
                item_dict['is_diagnostic']=child_slide_diagnose.is_diagnostic

            #4、拿到该切片的子切片的数量
            child_slide_counts = child_slide.count()
            item_dict['child_counts'] = child_slide_counts
            
            # 5.1、是否进行就版本的AI标注了, 被AI用户打上标注信息的【数据下载】
            #has_old_ai = 0
            #for child in child_slide:
            #    if TSlideLabel.objects.filter(creator_id=32,slide_file_name=child.slide_file_name):
            #        has_old_ai=1
            #        break
            #item_dict['has_old_ai'] = has_old_ai
            # 5.2、是否有固定框数据[数据下载]
            #has_scop_data=0
            #for child in child_slide:
            #    if TSlideLabel.objects.filter(slide_file_name=child.slide_file_name,is_scope=1):
            #        has_scop_data =1
            #        break
            #item_dict['has_scop_data']=has_scop_data
            #5.3、是否有标注信息 [数据下载]
            #has_lables_data = 0
            #for child in child_slide:
            #    if TSlideLabel.objects.filter(slide_file_name=child.slide_file_name):
            #        has_lables_data = 1
            #        break
            #item_dict['has_labels_data']=has_lables_data
            
            #5、智能诊断结果的是小切片的智能诊断，优先展示计算中[在小切片请求智能诊断时，把父切片诊断状态=2，当gpu返回智能诊断结果时，把父切片诊断状态=1]，无需下面的代码了
            # 智能诊断状态,2计算中，1已完成，0未诊断，按照这个顺序优先, 刚好按照降序排序，可以拿到第一个小切片的诊断状态
            #diaginose_status = child_slide.order_by('-is_diagnostic').first().is_diagnostic if child_slide  else None
            #item_dict['diaginose_status']=diaginose_status
            
            #6、获取文件的大小，MB单位
            try:
                file_size = os.stat(item.slide_path).st_size
                item_dict['file_size'] = f'{file_size//1024**2}M'
            except Exception as e:
                item_dict['file_size'] = '未知'
                #raise ValueError(str(e))
    
            #7、判断大切片1的子切片是否有数据，数据下载标识显示
            has_data = 1 if child_slide.filter(has_data=1) else 0 
            item_dict['has_data'] = has_data
            
            #8、扫描时间
            try:
                scanning_time = time.strftime('%Y/%m/%d %H:%M:%S',item.scanning_time)
            except Exception as e:
                scanning_time = datetime.datetime.strftime(item.create_time, "%Y/%m/%d %H:%M:%S") if item.create_time else None
            item_dict['scanning_time'] = scanning_time

            #9、对切片的路径进行切割，得到url，请求GPU时需要使用到
            try:
                url = item.slide_path.split(settings.SLIDE_SAVE_ROOT, 1)[-1]
                item_dict['url'] = url
            except Exception as e:
                item_dict['url'] = None
            #11、智能诊断状态，1已完成，2计算中，null未处理
            time_now = datetime.datetime.now()
            if item.is_diagnostic==2 and item.diagnose_time:
                if time_now>item.diagnose_time:
                    child_slide_diagnose_complete = child_slide.filter(~Q(is_diagnostic=2)).order_by('-is_diagnostic').first()
                    if child_slide_diagnose_complete:
                        item.is_diagnostic=child_slide_diagnose_complete.is_diagnostic
                        item.save()
                        item_dict['is_diagnostic'] = child_slide_diagnose_complete.is_diagnostic
                        print('最后一次小切片的诊断时间超过8小时，就判定其大切片的智能诊断已经完成')
            '2023-03-19: web上传的是小切片，智能诊断结果是计算中，但是时间超过8小时还在计算中的话'
            if item.is_small_slide==1 and item.is_diagnostic==2 and item.diagnose_time:
                #是小切片，诊断是计算中，有最后一次诊断时间
                if time_now>item.diagnose_time:
                    #诊断时间超过8小时了,将诊断状态设置成None
                    item.is_diagnostic=None
                    item.save()
                    item_dict['is_diagnostic']=None
                    #删除切片生成的对应的数据库记录
                    slide_imgs = TSlideImage.objects.filter(slide_id=item.pk, part__isnull=False)
                    #删除切片生成的对应的图片
                    for slide_img in slide_imgs:
                        # 删除上次的图片
                        delete_path = os.path.join(settings.BASE_DIR, slide_img.path)
                        print(f'删除上次智能诊生成的图片：{delete_path}')
                        if os.path.exists(delete_path):
                            os.remove(delete_path)
                        else:
                            print('data/obtain_fourinfor 要删除的智能诊断的图片不存在')
                    slide_imgs.delete()
            '2023-03-19: 过滤条件是已完成，但是还是出现了未完成的数据,其子切片都被当作未处理执行了，但父切片诊断状态还是1'
            child_count = TSlide.objects.filter(father_slide_id=item.pk,is_diagnostic__isnull=False).count()
            if not child_count and item.is_diagnostic:
                #如果其所有子切片都是未处理状态，就更新其诊断状态=None
                item.is_diagnostic=None
                item.save()
                print(f'{item.slide_file_name},所有子切片诊断=None，将其也设置成None')
            '2023-03-20: 是小切片，且诊断结果为已经完成，但是在数据库记录中没有诊断结果'
            if item.is_small_slide and item.is_diagnostic==1:
                slide_imgs = TSlideImage.objects.filter(slide_id=item.pk, part__isnull=False)
                if not slide_imgs:
                    #查询不到智能诊断结果
                    item.is_diagnostic=None
                    item.save()
                    print('小切片，诊断状态是已经完成，但是搜索不到智能诊断的四个结果')

            #最后、把每条数据追加到列表中
            data_list.append(item_dict) 

        #当前页是否有下一页，上一页
        has_next = 0
        has_prev = 0
        # 有下一页：当前页面大于等于1，当前页*页面大小 < 总数量
        if self.current_page >= 1 and self.current_page * self.per_page < self.count:
            has_next = 1
        # 有上一页：当前页大于1，且总数据量要大于页面大小
        if self.current_page > 1 and self.count > self.per_page:  # 有上一页，页数大于1，page_size小于总数据量
            has_prev = 1
        #获取的数据的页数
        current_page = self.current_page if self.current_page<=self.num_pages else self.num_pages
        dic['data']=data_list#当前页的数据
        dic['current_page']=current_page #当前页数
        dic['all_counts'] = self.count #总数据量
        dic['page_size'] = self.per_page #每页数据量
        dic['all_page'] = self.num_pages #总页数
        dic['has_next'] = has_next #是否有下一页
        dic['has_prev'] = has_prev #是否有上一页
        print(self.per_page,'size')
        print(self.num_pages,'all_page')
        return dic


class ChildSlidePaginator(Paginator):
    def __init__(self, object_list, current_page=1,per_page=5, orphans=0,
                 allow_empty_first_page=True):
        super().__init__(object_list,per_page,orphans,allow_empty_first_page)
        self.object_list = object_list #数据集
        self._check_object_list_is_ordered()
        self.per_page = int(per_page) #每页的数据量
        self.orphans = int(orphans)
        self.allow_empty_first_page = allow_empty_first_page
        self.current_page = 1 if current_page==None else int(current_page) #要获取那一页的数据
    def result(self,current_user_id):
        dic = {
            'data': [],  # 当前页的数据
            'current_page': 0,  # 当前页数
            'all_counts': 0,  # 总数据量
            'page_size': 0,  # 每页数据量
            'all_page': 0,  # 总页数
            'has_next': 0,  # 是否有下一页
            'has_prev': 0  # 是否有上一页
        }
        #查询数据集为空时，直接返回空字典
        if not len(self.object_list):
            return dic

        #根据页数拿到结果集
        page_data = self.get_page(self.current_page)
        #拿到最终的数据集
        slide_queryset = page_data.object_list
        data_list = []
        for item in slide_queryset:
            item_dict = model_to_dict(item)
            item_dict['mark_user'] = item.mark_user
            item_dict['is_scope'] = item.is_scope

            # 2、查看当前用户是否收藏该切片
            is_collect = UserCollectSlide.objects.filter(tslide_id=item.slide_id,user_id=current_user_id)
            if is_collect:
                item_dict['is_collect'] = 1 #当前用户收藏了该切片
            else:
                item_dict['is_collect'] = 0 #当前用户没有收藏该切片

            # 3、大切片拿到小切片的智能诊断结果展示
            diaginose_result = TSlideImage.objects.filter(part__isnull=False,slide_id=item.pk)
            child_lis = {}
            if item.is_diagnostic:
                for result in diaginose_result:
                    #把最后一个小切片的诊断结果写到里面，给大切片片展示
                    child_lis[result.part]=DIAGNOSE_RESULT.get(result.result)
                item_dict['diagnose_result'] = child_lis

            #6、获取文件的大小，MB单位
            try:
                file_size = os.stat(item.slide_path).st_size
                item_dict['file_size'] = f'{file_size//1024**2}M'
            except Exception as e:
                item_dict['file_size'] = '未知'
                raise ValueError(str(e))

            #8、扫描时间
            try:
                scanning_time = time.strftime('%Y/%m/%d %H:%M:%S',item.scanning_time)
            except Exception as e:
                scanning_time = datetime.datetime.strftime(item.create_time, "%Y/%m/%d %H:%M:%S") if item.create_time else None
            item_dict['scanning_time'] = scanning_time

            #9、对切片的路径进行切割，得到url，请求GPU时需要使用到
            try:
                url = item.slide_path.split(settings.SLIDE_SAVE_ROOT, 1)[-1]
                item_dict['url'] = url
            except Exception as e:
                item_dict['url'] = None

            #10、判断当前小切片是否有AI标注数据,AI账户的id是32
            #slide_labels = TSlideLabel.objects.filter(slide_file_name=item.slide_file_name,creator=32).first()
            #item_dict['has_ai_labels'] = 0
            #if slide_labels:
            #    #说明有AI的标注数据，要显示出这个按钮来，但是不能对按钮进行任何操
            #    item_dict['has_ai_labels'] = 1

            #11、是否有固定框数据,is_scope=1
            #slide_labels = TSlideLabel.objects.filter(slide_file_name=item.slide_file_name,is_scope=1).first()
            #item_dict['has_fixeds']=0
            #if slide_labels:
            #    item_dict['has_fixeds'] = 1
            #12.1 当小切片没有缩略图时，会去请求生成缩略图
            try:
                jpg_path = item.slide_path.replace('.tiff', '_thum.jpg')
                if not os.path.exists(jpg_path):
                    slide_make_jpg(item.slide_path)
            except Exception as e :
                #给小切片生成缩略图失败
                print(f'{e}')
            #12、小切片的缩略图地址
            try:
                bmp_path = item.slide_path.replace('.tiff','_thum.jpg').split(settings.SLIDE_SAVE_ROOT)[-1]
                bmp_path = BMP_BEFORE +bmp_path
            except:
                bmp_path = ''
            item_dict['bmp_path']=bmp_path
            
            
            #13、智能诊断状态，当最后一次智能诊断时间+8，小于当前时间时，就将该切片生成的诊断结果都删除掉，且诊断结果置空
            time_now = datetime.datetime.now() #小切片数据
            if item.is_diagnostic == 2 and item.diagnose_time:
                if time_now > item.diagnose_time:
                    #智能诊断时间超过8小时了，直接将诊断结果回退
                    #13.1、删除对应的数据库记录
                    slide_imgs = TSlideImage.objects.filter(slide_id=item.pk,part__isnull=False)
                    # 13.2、删除对应的图片
                    for slide_img in slide_imgs:
                        # 删除上次的图片
                        delete_path = os.path.join(settings.BASE_DIR, slide_img.path)
                        print(f'删除上次智能诊生成的图片：{delete_path}')
                        if os.path.exists(delete_path):
                            os.remove(delete_path)
                        else:
                            print('data/obtain_fourinfor 要删除的智能诊断的图片不存在')
                    slide_imgs.delete()
                    #13.3、将切片的智能诊断状态改为未处理
                    item.is_diagnostic = None
                    item.save()


            #最后，将所有数据都写到列表中去
            data_list.append(item_dict)

        #当前页是否有下一页，上一页
        has_next = 0
        has_prev = 0
        #有下一页：当前页面大于等于1，当前页*页面大小 < 总数量
        if self.current_page>=1 and self.current_page*self.per_page < self.count:
            has_next =1
        #有上一页：当前页大于1，且总数据量要大于页面大小
        if self.current_page>1 and self.count>self.per_page: #有上一页，页数大于1，page_size小于总数据量
            has_prev =1
        #获取的数据的页数
        current_page = self.current_page if self.current_page<=self.num_pages else self.num_pages
        dic['data']=data_list#当前页的数据
        dic['current_page']=current_page #当前页数
        dic['all_counts'] = self.count #总数据量
        dic['page_size'] = self.per_page #每页数据量
        dic['all_page'] = self.num_pages #总页数
        dic['has_next'] = has_next #是否有下一页
        dic['has_prev'] = has_prev #是否有上一页
        return dic

class CollectSlidePaginator(Paginator):
    '''
    专门给用户收藏的切片：大切片和小切片都在里面
    1、传入object_list=查询数据集、current_page=搜索页面、per_page=页面大小
    2、按照需求，新增需要跨表或连表查询的数据
    3、返回的是python的dict
    '''
    def __init__(self, object_list, current_page=1,per_page=5, orphans=0,
                 allow_empty_first_page=True):
        super().__init__(object_list,per_page,orphans,allow_empty_first_page)
        self.object_list = object_list #数据集
        self._check_object_list_is_ordered()
        self.per_page = int(per_page) #每页的数据量
        self.orphans = int(orphans)
        self.allow_empty_first_page = allow_empty_first_page
        self.current_page = 1 if current_page==None else int(current_page) #要获取那一页的数据
    def result(self):
        dic = {
            'data': [],  # 当前页的数据
            'current_page': 0,  # 当前页数
            'all_counts': 0,  # 总数据量
            'page_size': 0,  # 每页数据量
            'all_page': 0,  # 总页数
            'has_next': 0,  # 是否有下一页
            'has_prev': 0  # 是否有上一页
        }
        #查询数据集为空时，直接返回空字典
        if not len(self.object_list):
            return dic

        #根据页数拿到结果集
        page_data = self.get_page(self.current_page)
        #拿到最终的数据集
        slide_queryset = page_data.object_list
        #print(slide_queryset,'分页器中拿到的数据')
        data_list = []
        for item in slide_queryset:
            item_dict = model_to_dict(item)
            item_dict['mark_user'] = item.mark_user
            item_dict['is_scope'] = item.is_scope
            if item.father_slide_id == 0:
                '一、当前切片是大切片时'
                # 1.1、如果小切片的状态是已经标注，其父切片状态也是已标注
                child_slide = TSlide.objects.filter(father_slide_id=item.pk, status=1)
                if child_slide:
                    #print('其子已经标注了')
                    item_dict['status'] = 1
                # 1.2、大切片拿到小切片的智能诊断结果展示
                child_slide = TSlide.objects.filter(father_slide_id=item.pk)
                child_lis = {}
                for slide in child_slide:
                    diaginose_result = TSlideImage.objects.filter(part__isnull=False, slide_id=slide.pk)
                    if len(diaginose_result) == 4:
                        for result in diaginose_result:
                            # 把最后一个小切片的诊断结果写到里面，给大切片片展示
                            child_lis[result.part] = DIAGNOSE_RESULT.get(result.result)
                        break  # 拿到第一个进行智能诊断的小切片的结果
                item_dict['diagnose_result'] = child_lis
                '1.2-2、2023-03-13新增：web上传的是小切片，但没有父切片，所有智能诊断结果是拿自己的智能诊断结果'
                if item.is_small_slide == 1:
                    child_lis = {}
                    diaginose_result = TSlideImage.objects.filter(part__isnull=False, slide_id=item.pk)
                    for result in diaginose_result:
                        # 把切片智能结果拿到了
                        child_lis[result.part] = DIAGNOSE_RESULT.get(result.result)
                    item_dict['diagnose_result'] = child_lis
                    #缩略图地址重新修改：
                    dir_apth = os.path.dirname(item.slide_path).split(settings.SLIDE_SAVE_ROOT,1)[-1]
                    bmp_path = os.path.join(BMP_BEFORE,dir_apth,'preview.bmp')
                    item_dict['bmp_path'] = bmp_path
                '3.3、2023-03-13新增，通过小切片的诊断状态，计算中、完成、未处理 优先'
                child_slide_diagnose = child_slide.order_by('-is_diagnostic').first()
                if child_slide_diagnose:
                    #大切片展示的是小切片的智能诊断状态
                    item_dict['is_diagnostic']=child_slide_diagnose.is_diagnostic

                # 1.3、拿到该切片的子切片的数量
                child_slide_counts = child_slide.count()
                item_dict['child_counts'] = child_slide_counts
                # 1.4、判断大切片1的子切片是否有数据，数据下载标识显示
                has_data = 1 if child_slide.filter(has_data=1) else 0
                item_dict['has_data'] = has_data
                #1.5、两种类型数据是否可下载，AI，固定框，标注数据 【未想好】
            else:
                '二、当前切片是小切片时[说用户不会收藏小切片了，所以这段不会被执行到了]'
                #2.1、切片标注状态，表中就有此字段，无需额外操作
                # item_dict['status'] = item.status
                #2.2、智能诊断结果
                child_lis = []
                diaginose_result = TSlideImage.objects.filter(part__isnull=False, slide_id=item.pk)
                for result in diaginose_result:
                    # 把最后一个小切片的诊断结果写到里面，给大切片片展示
                    child_lis.append({'key': result.part, 'value': DIAGNOSE_RESULT.get(result.result)})
                item_dict['diagnose_result'] = child_lis
                #2.3、has_data,该字段在表中就有，无需额外操作
                #2.4、两种类型数据是否可下载，AI，固定框，标注数据 【未想好】
                #12、小切片的缩略图地址
                try:
                    bmp_path = item.slide_path.replace('.tiff','_thum.jpg').split(settings.SLIDE_SAVE_ROOT)[-1]
                    bmp_path = BMP_BEFORE +bmp_path
                except:
                    bmp_path = ''
                item_dict['bmp_path']=bmp_path

            '三、大切片小切片都需要的字段'
            # 3.1、查看当前用户是否收藏该切片
            #is_collect = UserCollectSlide.objects.filter(tslide_id=item.slide_id,user_id=current_user_id)
            #if is_collect:
            #    item_dict['is_collect'] = 1 #当前用户收藏了该切片
            #else:
            #    item_dict['is_collect'] = 0 #当前用户没有收藏该切片

            #3.2、获取文件的大小，MB单位
            try:
                file_size = os.stat(item.slide_path).st_size
                item_dict['file_size'] = f'{file_size//1024**2}M'
            except Exception as e:
                item_dict['file_size'] = '未知'
                raise ValueError(str(e))

            #3.3、扫描时间
            try:
                scanning_time = time.strftime('%Y/%m/%d %H:%M:%S',item.scanning_time)
            except Exception as e:
                scanning_time = datetime.datetime.strftime(item.create_time, "%Y/%m/%d %H:%M:%S") if item.create_time else None
            item_dict['scanning_time'] = scanning_time
            #print(item.create_time)
            #3.4、对切片的路径进行切割，得到url，请求GPU时需要使用到
            try:
                url = item.slide_path.split(settings.SLIDE_SAVE_ROOT, 1)[-1]
                item_dict['url'] = url
            except Exception as e:
                item_dict['url'] = None

            '四、数据放到列表中'
            data_list.append(item_dict)

        #当前页是否有下一页，上一页
        has_next = 0
        has_prev = 0
        #有下一页：当前页面大于等于1，当前页*页面大小 < 总数量
        if self.current_page>=1 and self.current_page*self.per_page < self.count:
            has_next =1
        #有上一页：当前页大于1，且总数据量要大于页面大小
        if self.current_page>1 and self.count>self.per_page: #有上一页，页数大于1，page_size小于总数据量
            has_prev =1
        #获取的数据的页数
        current_page = self.current_page if self.current_page<=self.num_pages else self.num_pages
        dic['data']=data_list#当前页的数据
        dic['current_page']=current_page #当前页数
        dic['all_counts'] = self.count #总数据量
        dic['page_size'] = self.per_page #每页数据量
        dic['all_page'] = self.num_pages #总页数
        dic['has_next'] = has_next #是否有下一页
        dic['has_prev'] = has_prev #是否有上一页
        return dic



