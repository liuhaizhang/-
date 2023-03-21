import hashlib

from django.shortcuts import render

# Create your views here.
from django.http import HttpResponse, StreamingHttpResponse
from public import global_common as gcm
from .models import TSlideLabel, TSlide, TSlideImage, TSlideDiagnose ,SlideDiagnoseModel,UserCollectSlide
from user.models import TAccount
from django.forms.models import model_to_dict
from django.core import serializers
from public.my_aggregate import GroupConcat
from MySQLdb import escape_string, escape
import datetime
from django.conf import settings
import requests
import simplejson
from public import common_util
import os
from public.kmeans import color
import openslide
import numpy
import cv2
import uuid
from django.db.models import Count
import base64
#2022/12/06新增
from django.views import View
from django.http import JsonResponse
import json
#2023-02-14新增
import time
from public import get_imagesize
#2023-02-17新增
from django.core.cache import cache
#2023-03-01新增：从public/web_upload_public.py导入web_upload_file视图需要的函数
from public.web_upload_public import save_file #保存文件
from public.web_upload_public import imge_hight_weight #换取图片宽度和高度
from public.web_upload_public import go_to_diaginose #等待文件切割完成，循环调用data/importXml
from public.web_upload_public import GoToDiaginose #等待文件切割完成，循环调用/data/importXmlNew的类
from public.web_upload_public import send_to_import_xml_new #请求本地智能诊断接口
from public.web_upload_public import web_small_diagnose #给web上传的小切片进行智能诊断
from public.web_upload_public import write_diagnose_in_file #将切片的智能诊断进度写到文件中
#2023-03-02新增：自定义分页器s
from public.paginator import PublicPaginator
from public.paginator import SlidePaginator
from public.paginator import ChildSlidePaginator
from public.paginator import CollectSlidePaginator
#2023-03-02: 给CBV加装饰器
from django.utils.decorators import method_decorator
import math
#2023-03-06:Q对象，或非运算
from django.db.models import Q
#2023-03-07:压缩文件夹的类
from public.folder_to_zip import ZipUtilities
from public.common_util import create_dir_path #创建多级目录，权限是777
from public.web_upload_public import DIAGNOSE_PART #诊断部位
from public.web_upload_public import DIAGNOSE_RESULT #诊断结果

'''测试django的cache功能'''
@gcm.check_api_token()
def save_msg_to_cache(request):
    name = request.GET.get('name')
    user_id = request.req_accountInfo.get('account_id')
    dic = {'name':name,'age':12,'sex':'男'}
    cache.set(f'name.tiff-{user_id}',json.dumps(dic))
    cache.set('number',1)
    number = cache.get('number')
    print(number,type(number))
    print(user_id)
    return JsonResponse({'name':name,'code':200,'msg':'将数据存储到数据库中的'})
@gcm.check_api_token()
def get_msg_from_cache(request):
    user_id = request.req_accountInfo.get('account_id')
    key = f'name.tiff-{user_id}'
    dic = cache.get(key)
    dic = json.loads(dic)
    return JsonResponse({'dic':dic,'code':200,'msg':'从cache中获取到的数据','key':key})
#开给前端测试文件上传功能
def test_upload_file(request):
    if request.method=='POST':
        file_list = request.FILES.getlist("file")
        auto_cut = request.POST.get('is_cut')  # 自动切割，yes=是，no=否，检测到为大文件时，自动切割成小文件，若大文件不切割则无法进行下一步的智能诊断
        handle_name = request.POST.get('handle_name')  # 文件名重名情况：cover=直接覆盖，skip=跳过该文件夹，rename=重命名
        diagnosis = request.POST.get('diagnosis')  # 是否进行智能诊断，all=全部，no=否，x=随机x个文件进行智能诊断
        return JsonResponse({'msg':'成功'})
    else:
        return JsonResponse({"msg":'该请求无法使用'},status=405)

'2023-03-19: 上传的是小切片，但是没有将其的is_small_slide 设置程1'
def set_is_small_slide(request):
    slide_filename = request.POST.get('slide_filename')
    slide = TSlide.objects.filter(slide_file_name=slide_filename,is_small_slide=0,father_slide_id=0,is_delete=0).first()
    file_size = os.stat(slide.slide_path).st_size//1024**2
    if file_size<=100:
        slide.is_small_slide=1
        slide.save()
    return JsonResponse({'code':200,'filename':slide.slide_file_name,'is_small':slide.is_small_slide})

'2023-03-16：历史小切片，可能没有缩略图，给这些小切片添加上缩略图'
def small_slide_make_jpg(request):
    '给小tiff文件生成缩略图'
    #小切片的目录地址：/home/thearay/DataSet/web-upload/46-userID/2023-03-11/1-TestB202061994/output_1
    dir_path = request.POST.get('dir_path')
    if not os.path.exists(dir_path):
        return JsonResponse({'code':400,'msg':'目录不存在'})
    if 'output_' not in dir_path:
        return JsonResponse({'code':400,'msg':'不是小切片的目录路径'})
    small_files = os.listdir(dir_path) #拿到目录下所有文件的名字
    complete_list = []
    for filename in small_files:
        #filename就是文件名了
        if '.tiff' not in filename:
            continue    
        slide_path = os.path.join(dir_path, filename)
        tiff_to_bmp_url = 'http://192.168.3.103:4900/createpreview'
        nfs_path = "/mnt"
        str_path = nfs_path + slide_path.split('DataSet')[-1]
        data = {"path": str_path,'is_small':'yes'}
        r = requests.post(tiff_to_bmp_url, data=data)
        ret_data = r.json()
        complete_list.append(filename)
    return JsonResponse({'code':200,'files':complete_list})

'2023-03-16：手动将切片的智能诊断状态由计算中改为已经完成'
@gcm.check_api_token()
def make_diagnose_complete(request):
    if request.method == 'POST':
        make_complete = request.POST.get('make_complete')
        if make_complete == 'yes':
            #将所有智能诊断状态是计算中，改为已完成
            counts = TSlide.objects.filter(is_diagnostic=2).update(is_diagnostic=1)
            return JsonResponse({'code':200,'counts':counts})
        else:
            return JsonResponse({'code':403,'msg':'参数不对'})
    else:
        return JsonResponse({'code':405,'msg':'非法请求'},status=405)

'2023-03-15： 浏览器上点击某个小切片进行智能诊断，同一个小切片名5分钟内只能进行一次智能诊断'
@gcm.check_api_token()
def import_xml_small(request):
    '''
    2023-03-09：新版本智能诊断系统，GPU的接口改变了，浏览器对小切片进行智能诊断时，使用这个功能
    '''
    if request.method == 'POST':
        filename = request.POST.get('filename')#小切片名
        url = request.POST.get("url")#文件相对于/home/thearay/Dataset的相对路径
        path = request.POST.get('path') #文件的绝对路径
        t_slide = TSlide.objects.filter(slide_file_name=filename,slide_path__isnull=False)
        # 进行智能诊断小切片的父切片名【web上传文件过程中选择了智能诊断时需要这个】
        father_filename = request.POST.get('father_filename')
        '2023-03-15：小切片智能诊断前，将cache缓存删除掉'
        user_id = request.req_accountInfo.get('account_id')  # 当前用户id
        key = f'{filename}-{user_id}-chrome'  # 从cache中获取智能诊断进度
        try:
            cache.delete(key)
        except Exception as e:
            #小切片进行智能诊断前先把之前在cache中同名的key删除掉
            pass
        if not t_slide:
            return JsonResponse({'code':400,'msg':f"当前{filename}不存在"})
            detail_url = settings.IMAGEPARSER_URL + 'GetImageObj/?fileName=' + "http://127.0.0.1:7100/" + url
            r = requests.get(detail_url, timeout=5)
            slide_data = simplejson.loads(r.content)
            real_width = slide_data.get('maxWidth')
            real_height = slide_data.get('maxHeight')
            t_slide = TSlide(slide_file_name=filename, slide_path=path, real_width=real_width,
                               real_height=real_height, status=0)
            t_slide.save()
        else:
            t_slide = t_slide[0]
        if not t_slide.slide_path:
            return JsonResponse({'code':400,'msg':f'{filename} 切片的路径不存在'})
        #t_slide.is_diagnostic = 0
        t_slide.is_diagnostic = 2 #这个字段0或null时，就是未处理,1是智能诊断完成，2是智能诊断计算中
        t_slide.diagnose_time = datetime.datetime.now()+datetime.timedelta(hours=8)
        #更新最后一次智能诊断时间+8小时，如果当前时间大于切片最后一次诊断时间，就将计算中改为已完成
        t_slide.save()
        # 找到进行智能诊断小切片的父切片（不能进行智能诊断，但需要过滤子切片的诊断状态），把父切片的智能诊断状态也改成2
        TSlide.objects.filter(slide_id=t_slide.father_slide_id).update(is_diagnostic=2,diagnose_time=datetime.datetime.now()+datetime.timedelta(hours=8))

        #2023-02-28注释：GPU服务器修改智能诊断接口，旧路由=Diagnose改为新路由=Diagnosetest
        # down_url = "http://192.168.3.103:5001/Diagnose"
        down_url = "http://192.168.3.103:5001/Diagnosetest"
        # nfs_path = "/app/store/"
        nfs_path = "/mnt/"
        '2023-02-28新增，请求给GPU时，携带上token和小切片的父切片名字，在obtain_fourinfor请求中会使用到'
        url = t_slide.slide_path.split(settings.SLIDE_SAVE_ROOT,1)[-1] #将path 切割 'DataSet/',取后面部分
        token = request.req_token
        data = {"path": nfs_path + url,'token':token,'father_filename':father_filename}
        res = requests.post(down_url, data=data)
        print("request.done")
        return gcm.data("正在智能诊断中，请稍后查看")

'2023-03-14 : web上传切片时，需要进行切割预览操作【web_upload_file视图没有使用整个接口】'
@gcm.check_api_token()
def auto_preview_webupload(request):
    filename = request.POST.get('filename')
    tslide = TSlide.objects.filter(slide_file_name=filename).first()
    if tslide:
        path = tslide.slide_path  # 切片的数量
        dir_path = os.path.dirname(path).split(settings.SLIDE_SAVE_ROOT)[-1]
        bmp_path = os.path.join('/mnt', dir_path, 'preview.bmp')  # 构建缩略图的路径
        auto_url = 'http://192.168.3.103:4900/autocut'
        auto_result = requests.post(auto_url, data={"path": bmp_path})
        labels = json.loads(auto_result.content)["location"]
        sliename = path.split('/')[-1]
        root_path = path.replace(sliename, "")
        out_path = os.path.join(root_path)
        bmp_path = os.path.join(root_path, "preview.bmp")
        color(bmp_path, out_path, labels)
        print(filename,'切割预览=',labels)
        return JsonResponse({'labels':labels})
    else:
        return JsonResponse({'labels':[]})


#2023-03-07 打印时，要请求这个接口，记录打印次数
def report_print_count(request):
    if request.method=='GET':
        slide_diagnose_id = request.GET.get('slide_diagnose_id')
        tsd = TSlideDiagnose.objects.filter(pk=slide_diagnose_id).first()
        if not tsd:
            return JsonResponse({'code':400,'msg':'不存在的诊断报告'})
        count = tsd.print_count+1
        tsd.print_count=count
        tsd.save()
        return JsonResponse({'code':200,'msg':'操作成功'})
    else:
        return JsonResponse({'code':403,'msg':'暂不支持post请求'})

#2023-03-08只执行一次，将历史数据中，执行过智能诊断操作的所有切片打上标记
def slide_has_old_ai(request):
    #想把所有has_old_ai=1设置成0
    TSlide.objects.filter(has_old_ai=1).update(has_old_ai=0)
    
    #用户id=32，这个是旧智能诊断使用的用户id，用户名=AI
    slide_filename_list = TSlideLabel.objects.filter(creator_id=32).values_list('slide_file_name',flat=True)
    slide_filename_list = list(set(slide_filename_list))
    #return JsonResponse({'list':slide_filename_list,'old_len':len(has_old_slide)})
    #遍历所有
    for slide_filename in slide_filename_list:
        #查询切片
        slide = TSlide.objects.filter(slide_file_name=slide_filename).first()
        if slide.father_slide_id==0:
            slide.has_old_ai=1
        else:
            #把父切片，的has_old_ai=1
            TSlide.objects.filter(pk=slide.father_slide_id).update(has_old_ai=1)
            slide.has_old_ai =1
        slide.save()
    return JsonResponse({'lis':slide_filename_list,'len':len(slide_filename)})

#2023-03-07 将/home/thearay/DataSet文件夹中未记录到数据库的切片数据都写到数据库中【已经将胃镜中的切片记录到数据库中了】
def folder_tiff_to_mysql(request):
    return JsonResponse({'msg':'接口暂时不再开放'})
    data = request.POST
    father_slide_name = data.get('slide_name')
    father_slide_path = data.get('slide_path','000kkk000')
    father_slide = TSlide.objects.filter(slide_file_name=father_slide_name).first()
    childs = data.get('child',[])
    if not os.path.exists(father_slide_path):
        error_dic = {'slide_name': father_slide_name, 'slide_path': father_slide_path, 'child': childs}
        error_str = json.dumps(error_dic)
        with open('./error.txt','w+') as fp:
            fp.write(error_str+'\n')
        return JsonResponse({'code':400,'slide_name':father_slide_name},status=400)
    #return JsonResponse({'code':200})

    '一、大切片的操作'
    if not father_slide:
        #大切片没有记录在数据库时，要先记录到数据库中
        #获取图片的宽度和高度
        hw_dic = imge_hight_weight(father_slide_path)
        width = hw_dic.get('width')
        height = hw_dic.get('height')
        #大切片没有记录到数据库中
        father_slide = TSlide.objects.create(slide_file_name=father_slide_name,slide_path=father_slide_path,status=0,real_width=width,real_height=height)
        father_slide = TSlide.objects.filter(slide_file_name=father_slide_name).first()
    else:
        #当大切片数据库记录中的切片路径为null时，更新路径和宽度高度
        if not father_slide.slide_path:
            hw_dic = imge_hight_weight(father_slide_path)
            width = hw_dic.get('width')
            height = hw_dic.get('height')
            father_slide.slide_path = father_slide_path
            father_slide.real_width = width
            father_slide.real_height = height
            father_slide.save()

    '二、小切片的操作'
    for dic in childs:
        child_filename = dic.get('slide_name') #小切片名
        child_path = dic.get('path') #小切片路径
        child_slide = TSlide.objects.filter(slide_file_name=child_filename).first()
        if child_slide:
            #1、记录存在时，更新父切片id、路径
            child_slide.father_slide_id = father_slide.pk
            if not child_slide.slide_path:
                #小切片的路径不存在时，重新写上，并更新宽度和高度
                hw_dic = imge_hight_weight(father_slide_path)
                width = hw_dic.get('width')
                height = hw_dic.get('height')
                child_slide.slide_path = child_path
                child_slide.real_width=width
                child_slide.real_height=height
            child_slide.save()
        else:
            #2、将小切片记录到数据库中
            hw_dic = imge_hight_weight(father_slide_path)
            width = hw_dic.get('width')
            height = hw_dic.get('height')
            TSlide.objects.create(slide_file_name=child_filename,slide_path=child_path,status=0,real_width=width,real_height=height,father_slide_id=father_slide.pk)
    return JsonResponse({'code':200,'msg':'操作成功'})


#2023-03-07 获取小切片智能诊断的图片
def slide_diagnose_imge(request):
    slide_id = request.GET.get('slide_id','0')
    if not slide_id.isdigit():
        return JsonResponse({'code':400,'msg':'携带的参数有问题'})
    slide = TSlide.objects.filter(pk=slide_id,is_delete=False).first()
    if not slide:
        return JsonResponse({'code':400,'msg':'不存在的切片'})
    '1、拿到切片的AI诊断的四个信息'
    imge_obj = TSlideImage.objects.filter(slide_id=slide_id,part__isnull=False).values('slide_image_id','slide_id','path','part','result').order_by('part')
    lis = list(imge_obj)
    for dic in lis:
        dic['part']=DIAGNOSE_PART.get(dic['part'])
        dic['result']=DIAGNOSE_RESULT.get(dic['result'])
    '2、拿到医生诊断的四个信息'
    tslide_diagnose = TSlideDiagnose.objects.filter(slide_id=slide_id).order_by('-pk').first()
    lis2 =[]
    if tslide_diagnose:
        #从数据库中拿到[{"part":1,"result":1},{"part":2,"result":1},{"part":3,"result":2},{"part":4,"result":0}]
        four_diagnose_list = tslide_diagnose.four_part_result
        four_diagnose_list = json.loads(four_diagnose_list)
        for dic in four_diagnose_list:
            #转成中文信息
            lis2.append({
                'part':DIAGNOSE_PART.get(dic.get('part')),
                'result':DIAGNOSE_RESULT.get(dic.get('result'))
            })
    return JsonResponse({'code':200,'ai':lis,'doctor':lis2})

#2023-03-07 大切片下载所有小切片的固定框信息：将所有小切片生成_fixed.xml 文件打包成zip下载
@gcm.check_api_token()
def father_slide_fixed(request):
    if request.method == 'POST':
        father_slide_id = request.POST.get('slide_id','0')
    else:
        father_slide_id = request.GET.get('slide_id','0')
    if not father_slide_id.isdigit():
        return JsonResponse({'code':400,'msg':'携带的参数有问题'})
    father_slide_id = int(father_slide_id)
    father_slide = TSlide.objects.filter(pk=father_slide_id,is_delete=False,father_slide_id=0).first()
    if not father_slide:
        return JsonResponse({'code':400,'msg':'切片不存在'})
    '1、在的大切片的目录下创建all_fixed 目录，该目录是用来存放所有子切片的固定框文件'
    try:
        father_path = os.path.join(os.path.dirname(father_slide.slide_path),'all_fixed')
    except Exception as e:
        return JsonResponse({'code':400,'msg':'当前切片没有记录路径，无法操作'})
    #1.2、创建all_fixed目录
    create_dir_path(father_path)

    '2、拿到所有子切片，给子切片的固定框生成xml文件,文件保存在父切片的all_fixed 目录下，【实时生成的】'
    chile_slides = TSlide.objects.filter(father_slide_id=father_slide_id,is_delete=False)
    #print(chile_slides)
    #return JsonResponse({'code':1000})

    has_fixed_count = 0
    for slide in chile_slides:
        #2.1、如果小切片没有固定框数据，就跳回继续
        fixed_obj = TSlideLabel.objects.filter(slide_id=slide.pk,is_scope=True)
        if not fixed_obj:
            has_fixed_count+=1
            continue
        #2.2、有固定框时，将固定框数据生成文件，保存到all_fixed文件夹中
        slide_name = slide.slide_file_name
        slide_path = slide.slide_path
        file = common_util.create_fixed_rectangle_xml_file(slide_name, slide_path)
        stream = file.getvalue()
        filename = slide_name.replace(".tiff", "_fixed.xml")
        filename_path = os.path.join(father_path,filename)
        with open(filename_path,'w') as fp:
            fp.write(stream)
        print(slide_name)
    '3、返回zip文件夹给用户使用'
    if has_fixed_count == len(chile_slides):
        #2.1、所有小切片都没有标注信息，无法生成xml文件
        return JsonResponse({'code':400,'msg':'所有小切片都没有固定框信息，请先在小切片下打上固定框'})
    else:
        #2.1、将大切片文件目录下的 all_fixed目录转成zip，给用户下载
        #文件名，不带文件后缀
        father_name = father_slide.slide_file_name.split('.')[0]
        #要进行压缩的文件夹 /xx/all_fixed文件夹
        utilities = ZipUtilities()
        utilities.toZip(father_path,father_name)
        response = StreamingHttpResponse(utilities.zip_file, content_type='application/zip')
        response['Content-Disposition'] = f'attachment;filename="{father_name}-fixed.zip"'  # 展示的zip名
        return response

#2023-03-06 大切片下载标注数据信息：将小切片的所有xml文件打包成zip下载
@gcm.check_api_token()
def father_slide_xml(request):
    if request.method == 'POST':
        father_id = request.POST.get('slide_id',0)
    else:
        father_id = request.GET.get('slide_id',0)
    #搜索大切片的数据库记录
    father_slide = TSlide.objects.filter(slide_id=int(father_id),father_slide_id=0,is_delete=False).first()
    print(father_slide) 
    if father_slide:
        '一、拿到所有的子切片，循环生成xml文件，文件存放父切片所在目录的all_xml目录下'
        child_slides = TSlide.objects.filter(father_slide_id=father_slide.pk)
        hs_no_labels_child = 0 #没有标注信息的小切片数量
        #临时存放压缩文件
        for child in child_slides:
            #小切片文件的路径
            file_path = child.slide_path
            #http://127.0.0.1:7100/web-upload-12-uid/xxx-xxx-xx/xxx.tiff
            slide_url = os.path.join(settings.MAKE_JSON_URL, child.slide_path.split(settings.SLIDE_SAVE_ROOT)[-1])
            # 检查文件是否存在
            # 1、获取切片信息
            url = settings.IMAGEPARSER_URL + 'GetImageObj/?fileName=' + slide_url
            r = requests.get(url, timeout=5)
            slide_data = simplejson.loads(r.content)
            max_zoom = slide_data.get('maxZoom')
            # 2、先查看切片是否有标注信息，没有的就不能进行
            slide_labels = TSlideLabel.objects.filter(slide_id=child.pk).filter(~Q(creator=32))
            if not slide_labels:
                hs_no_labels_child+=1
                continue
            # 3、读取数据库中小切片的标注信息，该文件与小切片的路径一样
            common_util.father_slide_create_json_file(child.pk, child.slide_path, max_zoom)
            # 4、依赖上面生成的.json文件，生成.xml文件
            common_util.father_slide_create_xml_file(child.slide_path,is_father=True)
            #小切片上说明有数据可以下载了
            TSlide.objects.filter(slide_id=child.pk).update(has_data=1)
            #对应的大切片也是有数据下载的了
            father_slide.has_data=1
            father_slide.save()
        '二、返回生成的所有xml文件，以zip格式'
        if hs_no_labels_child == len(child_slides):
            return JsonResponse({'code':400,'msg':'所有小切片都没有标注信息，无法下载'})
        else:
            #2.1、将大切片文件目录下的 all_xml目录转成zip，给用户下载
            #文件名，不带文件后缀
            father_name = father_slide.slide_file_name.split('.')[0]
            #要进行压缩的文件夹 /xx/all_xml文件夹
            father_xml_path = os.path.join(os.path.dirname(father_slide.slide_path),'all_xml')
            utilities = ZipUtilities()
            utilities.toZip(father_xml_path,father_name)
            response = StreamingHttpResponse(utilities.zip_file, content_type='application/zip')
            response['Content-Disposition'] = f'attachment;filename="{father_name}-labels.zip"'  # 展示的zip名
            return response
    else:
        return JsonResponse({'code':400,'msg':'当前切片不存在数据库中'})

#2023-03-06 小切片的固定框数据下载
#@gcm.check_api_token()
def child_slide_fixed(request):
    if request.method == 'GET':
        #slide_path = request.GET.get('slide_path')
        slide_name = request.GET.get('slide_name')
        #if not slide_path:
        #    return JsonResponse({'code':400,'msg':'请携带上对应的小切片路径'})
        if not slide_name:
            return JsonResponse({'code':400,'msg':'请携带上对应的小切片文件名'})
        #不需要前端传递slide_path
        tslide = TSlide.objects.filter(slide_file_name=slide_name, slide_path__isnull=False, is_delete=False).first()
        if not tslide:
            return JsonResponse({'code':400,'msg':'找不到符合的切片'})
        slide_path = tslide.slide_path

        dir_path = os.path.dirname(slide_path)
        # 检查文件夹是否存在
        if not os.path.exists(dir_path):
            return JsonResponse({'code':400,'msg':'文件夹不存在:%s' % dir_path})
        slide_info = TSlide.objects.filter(slide_file_name=slide_name).first()
        if not slide_info:
            return JsonResponse({'code':400,'msg':'该切片不存在数据库中'})
        label_list = TSlideLabel.objects.filter(slide_id=slide_info.slide_id, is_scope=1)
        #检测当前切片是否有固定框
        if not label_list:
            return JsonResponse({'code':400,'msg':'切片下没有固定框'})
        file = common_util.create_fixed_rectangle_xml_file(slide_name, slide_path)
        stream = file.getvalue()
        filename = slide_name.replace(".tiff", "_fixed.xml")
        return gcm.download(stream, filename)
    else:
        return JsonResponse({'code':400,'msg':'请使用get请求'})


#2023-03-04 查询大切片的所有小切片的数据
@gcm.check_api_token()
def search_slide_childs(request):
    father_slide_id = request.POST.get('slide_id')
    page = request.POST.get('page','1')
    page_size = request.POST.get('page_size','10')
    user_id = request.req_accountInfo.get('account_id')  # 拿到当前登录的用户id
    if page.isdigit:
        page = int(page)
    if page_size.isdigit:
        page_size = int(page_size)
    if not TSlide.objects.filter(pk = father_slide_id):
        return JsonResponse({'code':404,'msg':'当前切片不存在'})

    #拿到大切片的所有小切片的数据
    slide_childs = TSlide.objects.filter(father_slide_id=father_slide_id,is_delete=False,slide_path__isnull=False).order_by('slide_file_name')
    #print(slide_childs,len(slide_childs))
    # 实例化分页器
    paginitor = ChildSlidePaginator(slide_childs, current_page=page, per_page=page_size)
    # 拿到分页数据
    res = paginitor.result(user_id)
    return JsonResponse(res)

#2023-03-06 小切片的xml文件生成和下载
@gcm.check_api_token()
def child_slide_jsonData(request):
    '''
    该功能：下载小切片的xml数据,要先生成xml文件再下载,保证下载的数据是实时的
    '''
    if request.method=='GET':
        return JsonResponse({'code':400,'msg':'不支持get请求'})

    slide_id = request.POST.get('slide_id')

    slide_url = request.POST.get('slide_url')
    print(slide_id,type(slide_id))
    slide = TSlide.objects.filter(slide_id=int(slide_id), slide_path__isnull=False, is_delete=False).first()
    if not slide:
        return JsonResponse({'code':400,'msg':'该小切片不存在'})
    if not slide_url:
        if not slide.slide_path:
            return JsonResponse({'code':400,'msg':'小切片的路径不存在，可能切片已经被销毁了'})
        else:
            #slide_path = /home/thearay/DataSet/web-upload/13-userID/2023-03-03/TestB202104700/output_1/TestB202104700_1_1.tiff
            #slide_url = http://127.0.0.1:7100/web-upload/13-userID/2023-03-03/TestB202104700/output_1/TestB202104700_1_1.tiff
            slide_url = os.path.join(settings.MAKE_JSON_URL,slide.slide_path.split(settings.SLIDE_SAVE_ROOT)[-1])
            print(slide_url)
    #return JsonResponse({'code':200})
    dir_path = os.path.dirname(slide.slide_path) #xml文件存放路径
    xml_filename =  os.path.basename(slide.slide_path).replace('.tiff','.xml')#xml文件名
    xml_path = os.path.join(dir_path,'xml',xml_filename )#xml文件绝对路径
    # 检查文件是否存在
    # 1、获取切片信息
    url = settings.IMAGEPARSER_URL + 'GetImageObj/?fileName=' + slide_url
    r = requests.get(url, timeout=5)
    slide_data = simplejson.loads(r.content)
    max_zoom = slide_data.get('maxZoom')
    #2、先查看切片是否有标注信息，没有的就不能进行
    slide_labels = TSlideLabel.objects.filter(slide_id=slide_id).filter(~Q(creator=32))
    if not slide_labels:
        return JsonResponse({'code':400,'msg':'当前小切片还没有进行标注操作，无法生成标注数据'})
    #3、读取数据库中小切片的标注信息，写到data.json文件，该文件与小切片的路径一样
    common_util.father_slide_create_json_file(slide_id, slide.slide_path, max_zoom)
    #4、依赖上面生成的data.json文件，生成.xml文件
    common_util.father_slide_create_xml_file(slide.slide_path)
    slide = TSlide.objects.get(slide_id=slide_id)
    slide.has_data = 1
    slide.save()

    #5、xml文件存在时，就下载
    file = open(xml_path, 'rb')
    xml_filename = xml_path.rsplit('/')[-1]
    response = FileResponse(file)
    response['Content-Type'] = 'application/octet-stream'
    response['Content-Disposition'] = f'attachment;filename="{xml_filename}"'
    return response


#2023-03-04, 点击大切片下的智能诊断按钮，选择对应的子切片进行智能诊断
@gcm.check_api_token()
def send_importXmlNew(request):
    if request.method == "GET":
        return JsonResponse({'code':405,'msg':'请使用POST请求'},status=405)
    number = request.POST.get('number','none')
    is_random = request.POST.get('is_random')
    slide_id = request.POST.get('slide_id') #父切片id
    slide = TSlide.objects.filter(pk=int(slide_id),father_slide_id=0).first()
    child_slides = TSlide.objects.filter(father_slide_id=int(slide_id),is_delete=False) #拿到所有子切片
    url = 'http://127.0.0.1:8084/data/importXmlNew'
    token = request.req_token
    user_id = request.req_accountInfo.get('account_id') #当前用户id
    print(slide_id,type(slide_id),'浏览器进行大切片智能诊断',f'小切片数{len(child_slides)}')
    if not slide:
        return JsonResponse({'code':404,'msg':'当前切片不存在数据库中'})
    if not child_slides:
        return JsonResponse({'code':400,'msg':'没有小切片，先进行切割后再操作'})
    '2023-03-19: 先将浏览器点击大切片智能诊断产生的cache删除掉'
    for the_child in child_slides:
        key = f'{the_child.slide_file_name}-{user_id}-chrome-big'
        try:
            cache.delete(key)
            print(f'浏览器点击大切片智能诊断，先删除的cache,{key}')
        except Exception as e:
            pass

    #return JsonResponse({'code':200,'msg':'正在诊断中'})
    if type(number) !=str:
        number = str(number)
    if number.isdigit():
        '1、对指定数量的小切片进行智能诊断'
        number = int(number)
        number = int(math.fabs(number))
        if is_random in [1,'1']:#是否随机，按未进行智能诊断的优先
            if number>=child_slides.count():#输入的诊断数量大于子切片数，全部诊断
                for child in child_slides:
                    path = child.slide_path #切片的路径
                    filename=child.slide_file_name #切片的文件名
                    send_to_import_xml_new(path=path,filename=filename,url=url,token=token)
            else:
                #未进行智能诊断小切片
                no_diagnose_childs = child_slides.filter(is_diagnostic__isnull=True)
                #完成过智能诊断的小切片
                diagnose_childs = child_slides.filter(is_diagnostic=1)
                for child in no_diagnose_childs[:number]:#优先对未诊断的切片进行诊断，还有空位就对进行过智能诊断的小切片操作
                    path = child.slide_path  # 切片的路径
                    filename = child.slide_file_name  # 切片的文件名
                    send_to_import_xml_new(path=path, filename=filename, url=url, token=token)
                if no_diagnose_childs.count() < number:
                    #在未诊断的数量不够时，会对已诊断进行再次诊断
                    for child in diagnose_childs[:number-no_diagnose_childs.count()]:
                        path = child.slide_path  # 切片的路径
                        filename = child.slide_file_name  # 切片的文件名
                        send_to_import_xml_new(path=path, filename=filename, url=url, token=token)
        else:#不是随机，就不是按未切片的优先智能诊断了，直接按顺序诊断
            for child in child_slides[:number]:
                path = child.slide_path  # 切片的路径
                filename = child.slide_file_name  # 切片的文件名
                send_to_import_xml_new(path=path, filename=filename, url=url, token=token)

    elif number == 'all':
        for child in child_slides:
            path = child.slide_path  # 切片的路径
            filename = child.slide_file_name  # 切片的文件名
            send_to_import_xml_new(path=path, filename=filename, url=url, token=token)

    else:
        return JsonResponse({'code':404,'msg':'请携带上要进行智能诊断数量'})
    return JsonResponse({'code':200,'msg':'正在诊断中'})

#2023-03-03,新版本首页搜索功能
@gcm.check_api_token()
def index_search(request):
    status = request.POST.get('status') #切片状态，1已标记，0未标记，2已检测
    slide_name = request.POST.get('slideName') #搜索的切片名
    page = request.POST.get('page','1') #当前页
    page_size = request.POST.get('pageSize','10')#每页大小
    is_diaginose = request.POST.get('diaginose') #搜索智能诊断状态，0未处理，1是已完成，2是计算中（前端不传递2 优先展示）（再时间降序）
    user_id = request.req_accountInfo.get('account_id') #拿到当前登录的用户id
    if type(page) == str:
        if page.isdigit():
            page = int(page)
        else:
            page =1
    if type(page_size) == str:
        if page_size.isdigit():
            page_size = int(page_size)
        else:
            page_size =10    
    print('当前页=',page,'页面大小=',page_size)
    print(slide_name)
    #搜索所有未删除的大切片
    all_slides = TSlide.objects.filter(is_delete=False,slide_path__isnull=False)
    #过滤切片状态
    if status in [0,'0','1',1,'2',2]:
        #切片的状态：0是未标记，1是已标记，2是已检验
        all_slides =all_slides.filter(status=int(status))
    #过滤智能诊断:已完成和未处理
    if is_diaginose in [1,'1']:#过滤已经完成诊断
        #如果前端选择过滤的是已完成：返回 已完成和计算中 的数据
        all_slides  = all_slides.filter(is_diagnostic__in=[1,2])
    if is_diaginose in [0,'0']:#过滤未处理
        all_slides = all_slides.filter(is_diagnostic__isnull=True)
    #过滤切片名：
    if slide_name:
        #搜索的是小切片时,搜索的结果一定是属于同一个父切片的
        if slide_name.count('_') >=1:
            #print('进入小切片了')
            child_slides = all_slides.filter(slide_file_name__contains=slide_name,father_slide_id__gt=0)
            '2023-03-20新增，优化搜索小切片名时找不到父亲切片'
            father_slides = all_slides.filter(slide_file_name__contains=slide_name,father_slide_id=0).order_by('-slide_id')
            if child_slides:
                #print('搜索小切片')
                father_id = child_slides.values_list('father_slide_id')
                #返回的结果一定只有一个数据，小切片名=f'{大切片名}_1_2.tiff' , 大切片名在数据库是唯一的【最终返回的还是大切片】 
                all_slides = all_slides.filter(slide_id__in=father_id,father_slide_id=0).filter(~Q(slide_path__contains='output_')).order_by('-slide_id')
                '2023-03-20新增，优化搜索小切片时找不到父亲切片'
                all_slides = all_slides | father_slides
            else:
                all_slides = father_slides.order_by('-slide_id')
        else:
            #搜索的文件名不是大切片,最终返回给前端的数据都是大切片文件，所以在最后需要过滤没有父切片的的切片
            #【最终返回的还是大切片】
            all_slides = all_slides.filter(slide_file_name__contains=slide_name,father_slide_id=0).filter(~Q(slide_path__contains='output_')).order_by('-slide_id')
    else:
        #【最终返回的还是大切片】
        all_slides =all_slides.filter(father_slide_id=0).filter(~Q(slide_path__contains='output_')).order_by('-slide_id')
    #实例化分页器
    paginitor = SlidePaginator(all_slides,current_page=page,per_page=page_size)
    #拿到分页数据
    res = paginitor.result(user_id)
    return  JsonResponse(res)

#2023-03-02用户收藏切片的操作
@gcm.check_api_token()
def user_slides(request):
    if request.method=='GET':
        # 当前用户的id
        user_id = request.req_accountInfo.get('account_id')
        page = request.GET.get('page', '1')
        page_size = request.GET.get('page_size', '10')
        if not page.isdigit():
            page =1
        else:
            page=int(page)
        if not page_size.isdigit():
            page_size=10
        else:
            page_size = int(page_size)
        slide_id_list = UserCollectSlide.objects.filter(user_id=user_id).values_list('tslide_id', flat=True)
        slide_id_list = list(slide_id_list)
        slide = TSlide.objects.filter(slide_id__in=slide_id_list,is_delete=False) #拿到用户收藏的所有切片
        
        page = CollectSlidePaginator(slide, current_page=page, per_page=page_size)
        dic = page.result()
        return JsonResponse(dic)
    elif request.method=='POST':
        user_id = request.req_accountInfo.get('account_id')
        slide_id = request.POST.get('slide_id')  # 操作切片的id
        print(slide_id)

        operate = request.POST.get('operate', None)  # 1是收藏该切片，0是取消收藏该切片
        if not slide_id:
            return JsonResponse({'code': 400, 'msg': '没有携带切片id'})
        if operate == None:
            return JsonResponse({'code': 400, 'msg': '没有携带操作类型'})
        tslide = TSlide.objects.filter(pk=slide_id,father_slide_id=0,is_delete=False)
        if not tslide:
            return JsonResponse({'code':400,'msg':'不存在的切片，或该切片是小切片'})
        #查询收藏记录
        user_collect_slide = UserCollectSlide.objects.filter(user_id=user_id, tslide_id=int(slide_id))
        if operate in ['0', 0]:
            user_collect_slide.delete()
            return JsonResponse({'code': 200, 'msg': '取消收藏成功'})
        elif operate in [1,'1']:
            #用户
            if user_collect_slide:
                #如果当前用户对切片已经有收藏记录了，就不操作
                return JsonResponse({'code':200,'msg':'收藏已存在'})
            else:
                #记录前，判断是否存在该切片
                tslide = TSlide.objects.filter(slide_id=slide_id).first()
                if tslide:
                    UserCollectSlide.objects.create(user_id=user_id, tslide_id=slide_id)
                    return JsonResponse({'code': 200, 'msg': '确定收藏成功'})
                else:
                    return JsonResponse({'code':400,'msg':'当前切片id不存在'})
        else:
            return JsonResponse({'code':400,'msg':'参数有问题'})
    else:
        return JsonResponse({'code':405},status=405)


'''2023-02-14新增功能-文件上传->文件处理->文件切割->智能诊断'''
@gcm.check_api_token()
def web_upload_file(request):
    '''
            功能：
                1、保存前端上传的tiff文件
                2、处理tiff文件重命名问题
                3、生成tiff文件的缩略图 (gpu服务器)
                4、将tiff文件进行分割（请求内部的切割接口）
                5、对分割后的小文件进行智能诊断 （请求内部的智能诊断接口）
            :param request:
            :return:
            {
            'code':200,
            'success_list':[], #上传成功的文件
            'failed_list':[{'filename':,'error':'失败的原因'}], #上传失败的文件
            }
    '''
    print(time.strftime("%Y-%m-%d %H:%M:%S"),'最开始时间')
    file_list = request.FILES.getlist("file")
    auto_cut = request.POST.get('is_cut')  # 自动切割，yes=是，no=否，检测到为大文件时，自动切割成小文件，若大文件不切割则无法进行下一步的智能诊断
    handle_name = request.POST.get('handle_name')  # 文件名重名情况：cover=直接覆盖，skip=跳过该文件夹，rename=重命名
    diagnosis = request.POST.get('diagnosis')  # 是否进行智能诊断，all=全部，no=否，x=随机x个文件进行智能诊断
    user_id = request.req_accountInfo.get('account_id') #拿到当前用户id，用来拼接
    # 转成数值类型
    token = request.req_token  #拿到token
    if not file_list:
        return JsonResponse({'code': 400, 'msg': '请上传文件'})
    if handle_name not in ['skip','rename','cover']:
        return JsonResponse({'code':400,'msg':'重名处理参数：skip、rename和cover'})

    print('1、上传的文件列表 ', file_list)
    str_time = time.strftime('%Y-%m-%d')

    # 文件保存失败的列表
    faile_list = []
    # 文件保存成功的列表
    success_list = []
    for file in file_list:
        '每次处理文件前：将上次同名的上传文件名，对应的切割进度和诊断进度cache清除'
        delete_diagionesis_key = f'{file.name}-{user_id}-diagnosis' #智能诊断进度
        delete_cut_key = f'{file.name}-{user_id}-cut'#文件切割进度
        delete_lis = [delete_diagionesis_key,delete_cut_key]
        for delete_key in delete_lis:
            try:
                cache.delete(delete_key)
            except:
                pass        

        '一、重名处理,生成文件存放的路径和文件名'
        # filename 后面可能存放重命名的文件名,old_name是文件上传时的原始文件名
        filename = file.name
        old_name = file.name
        print(file.size, file, filename)
        # 只处理tiff文件
        if 'tiff' not in filename or 'tif' not in filename:
            faile_list.append({'filename': filename, 'error': '文件格式不是tiff，无法处理'})
            continue

        # 构造文件存放的目录(创建数据库记录或修改记录，slide_path=os.path.join(path,filename))
        path = os.path.join(settings.SLIDE_PATH, 'web-upload',f'{user_id}-userID', str_time, filename.split('.')[0])#2023-03-03 路径格式
        # 切片的文件名在数据库表中是唯一的
        tslide = TSlide.objects.filter(slide_file_name=filename) #2023-03-03, 去掉first()
        # 切片名记录在数据库中了，就要处理重名问题
        if handle_name.strip() == 'cover':
            '''
            1.1、直接覆盖： 修改文件存放的路径
            拿到已经在数据库中的切片文件存储的路径，文件覆盖写这个路径
            '''
            if tslide:
                #2023-03-03 选择覆盖时且文件重名了，要重新设置上传文件的存放路径,
                delete_tslide = TSlide.objects.filter(slide_file_name=f'{filename[0]}=={filename[1:]}') #已经重名过的，且重新设置了文件名的
                cover_count = len(delete_tslide)+len(tslide)
                path = os.path.join(settings.SLIDE_PATH, 'web-upload', f'{user_id}-userID', str_time,f"{filename.split('.')[0]}-{cover_count}")
            else:
                pass
                print(filename,'cover,在数据库不存在，继续执行，保存文件，生成缩略图等操作')
                # 当文件名没有在数据库中记录过时，且选择是覆盖时，无需更改path
        elif handle_name.strip() == 'skip':
            '''
            1.2、文件名在数据库中已经存在了，就跳过该文件，不操作该文件
            '''
            if tslide:
                #该文件名在数据库中有记录了，且重名操作选择跳过，循环到下一个文件
                faile_list.append({'filename': filename, 'error': '重命名选择跳过，就没有存储该文件了'})
                continue
            else:
                pass
                print(filename,'skip,在数据库不存在，继续执行，保存文件，生成缩略图等操作')
        elif handle_name.strip() == 'rename':
            '''
            1.3、重命名文件名，handle_name = 3：修改文件名
            '''
            if tslide:
                co = 0
                while True:
                    name_list = filename.split('.')
                    new_filename = name_list[0] + f'R{co}' + '.' + name_list[-1]
                    tslide = TSlide.objects.filter(slide_file_name=new_filename).first()
                    if not tslide:
                        # 当新的文件名在数据库中查询不到时，退出循环，给我们重命名完成
                        filename = new_filename
                        print('需要重新命名的名字 ', filename)
                        break
                    co+=1
                # 2023-03-03 2023-03-03 文件名重新命名，文件夹也要重新改变
                path = os.path.join(settings.SLIDE_PATH, 'web-upload', f'{user_id}-userID', str_time, filename.split('.')[0])
            else:
                # 当前文件没有记录在数据库中时，无需修改上传时的文件名，文件的存放路径也无需修改
                pass
                print(filename,'skip,在数据库不存在，继续执行，保存文件，生成缩略图等操作')
        else:
            return JsonResponse({'code': 400, 'msg': 'handle_name参数有问题'})

        '二、将上传的文件保存起来，记录到数据库中'
        ret = save_file(path=path, file=file, filename=filename)
        if ret.get('code'):
            #文件保存成功的处理
            filename_path = ret.get('file_path')
            dic = imge_hight_weight(filename_path)
            '2.1、获取图片的宽度和高度'
            if dic.get('code'):
                width = dic.get('width')
                height = dic.get('height')
            else:
                print('拿不到文件的真实宽度和高度')
                width = -1
                height = -1
            '2.2、记录到数据库中'
            if handle_name == 'rename':
                # 重命名时，需要新建数据库记录，保存上传的文件情况
                try:
                    TSlide.objects.create(slide_path=filename_path, slide_file_name=ret.get('filename'),
                                                 status=0, real_width=width, real_height=height)
                except Exception as e:
                    faile_list.append({'filename': old_name, 'error': f'rename:创建数据库记录失败：{str(e)}'})
                    continue
            elif handle_name == 'cover':
                # 重名解决方法，cover=覆盖原来, 
                if tslide:
                    #文件名有重名情况，需要先源数据库记录设置好
                    #1、设置源切片的is_delete=True
                    ts = tslide.first()
                    ts.is_delete = True #设置删除了
                    ts.slide_file_name = ts.slide_file_name[0]+'=='+ts.slide_file_name[1:]  #给文件名构建新文件
                    ts.save()
                    #1.2、标记大切片的收藏 is_delete=True
                    collect_slides = UserCollectSlide.objects.filter(tslide_id=ts.pk)
                    for collect in collect_slides:
                        collect.is_delete = True
                        collect.save()
                    #2、子切片中设置，is_delete=True：
                    childs = TSlide.objects.filter(father_slide_id=ts.pk)
                    for child in childs:
                        child.is_delete=True
                        child.slide_file_name = child.slide_file_name[0]+'=='+child.slide_file_name[1:]
                        child.save()
                        #2.1、标记所有小切片的收藏状态为删除状态
                        collect_slides = UserCollectSlide.objects.filter(tslide_id=child.pk)
                        for collect in collect_slides:
                            collect.is_delete = True
                            collect.save()
                    #3、给新文件创建数据库记录
                    try:
                        TSlide.objects.create(slide_file_name=filename,
                                                    slide_path=os.path.join(path, filename), status=0,
                                                    real_height=height, real_width=width)
                    except Exception as e:
                        faile_list.append({'filename':filename,'error':'cover,为该文件创建的数据库记录失败'})
                        #数据库记录失败，无需进行生成缩略图，切割文件、智能诊断了
                        continue
                else:
                    # 上传的文件名在数据库中没有记录时，需要新建数据库记录，不再修改原来的数据库记录
                    try:
                        TSlide.objects.create(slide_file_name=filename,
                                                    slide_path=os.path.join(path, filename), status=0,
                                                    real_height=height, real_width=width)
                    except Exception as e:
                        faile_list.append({'filename':filename,'error':'cover,为该文件创建的数据库记录失败'})
                        #数据库记录失败，无需进行生成缩略图，切割文件、智能诊断了
                        continue

            elif handle_name=='skip':
                # 重名问题，选择skip
                if not tslide :
                    #当文件名在数据库中不存在时，不过是skip、rename还是cover都要保存文件，记录到数据库中
                    try:
                        TSlide.objects.create(slide_file_name=filename, slide_path=os.path.join(path, filename),
                                          status=0,real_height=height, real_width=width)
                    except Exception as e:
                        faile_list.append({'filename':filename,'error':'skip: 为文件创建数据库记录失败'})
                        #数据库记录失败，无需进行下面的操作了
                        continue
        else:
            #文件保存失败了
            error = ret.get('error')
            faile_list.append({'filename': old_name, 'error': '该文件存储到服务器中失败了,没有记录到数据库、生成缩略图，切割文件' })
            #tiff没有存储成功，无需下面的操作 ，直接去处理下一个文件了
            continue
        print(time.strftime('%Y-%m-%d %H:%M:%S'),'存储一个tiff文件的时间')
        '三、给上传的tiff文件生成缩略图'
        slide_path = os.path.join(path, filename)
        tiff_to_bmp_url = 'http://192.168.3.103:4900/createpreview'
        nfs_path = "/mnt"
        str_path = nfs_path+slide_path.split('DataSet')[-1]
        data = {"path": str_path}
        try:
            r = requests.post(tiff_to_bmp_url, data=data)
            ret_data = r.json()
            #print(ret_data,'生成缩略图请求的响应')
            #print(r.content,'生成缩略图请求的响应')
        except Exception as e:
            faile_list.append({'filename': old_name, 'error': '该tiff文件没有生成缩略图,无法进入到切割文件环节'})
            '2023-03-14:生成缩略图失败，需要删除保存的文件和对应的数据库记录，不然会有垃圾数据'
            tslide = TSlide.objects.filter(slide_file_name=filename).first()
            bmp_file_path = os.path.join(os.path.dirname(tslide.slide_path),'preview.bmp')
            if not os.path.exists(bmp_file_path):
                dir_path = os.path.dirname(bmp_file_path)
                remove_dir(dir_path) #删除保存的文件夹
                TSlide.objects.filter(slide_file_name=filename).delete() #
            continue
        '三-1、查询缩略图是否生成成功'
        bmp_success = False
        for i in range(5):
            check_bmp_url = 'http://192.168.3.103:4900/checkpreview'
            check_nfs_path =  "/mnt"+slide_path.split('DataSet')[-1]
            param = {'tiff_path': check_nfs_path}
            res = requests.get(check_bmp_url,params=param)
            ret_dic = res.json()
            if ret_dic.get('code',0)==200 and ret_dic.get('boolean'):
                bmp_success = True
                break
            time.sleep(2)
        if bmp_success:
            #生成缩略图成功，可以进行下一步的切割
            print('缩略图生成成功了')
        else:
            #四次请求均拿不到缩略图生成成功的，
            faile_list.append({'filename':old_name,'error':'该切片生成缩略图失败无法进行下一步切割操作'})
            '2023-03-14:生成缩略图失败，需要删除保存的文件和对应的数据库记录，不然会有垃圾数据'
            tslide = TSlide.objects.filter(slide_file_name=filename).first()
            bmp_file_path = os.path.join(os.path.dirname(tslide.slide_path),'preview.bmp')
            if not os.path.exists(bmp_file_path):
                dir_path = os.path.dirname(bmp_file_path)
                remove_dir(dir_path) #删除保存的文件夹
                TSlide.objects.filter(slide_file_name=filename).delete() #
            continue
        

        #文件保存到服务器中了，返回的实际存储到服务器中的文件名
        #continue
        '四、文件自动切割'
        print('4、进入切割预览')
        if auto_cut=='yes':
            '4.1、切割预览，生成对应的切割块: 该请求就在这个系统里面'
            user_id = request.req_accountInfo.get('account_id') #拿到当前用户id，用来拼接
            cache_name = f'{old_name}-{user_id}-cut'#切割文件情况，记录到cache中，这个是key
            pre_url = 'http://127.0.0.1:8084/data/autoPreview'
            #如果是手动切割 data/runPreview路由时，需要再加上参数：'centers':12,'patch':80,'ioc':0.5
            pre_data = {'token':token,'filename':filename}
            try:
                pre_return = requests.post(url=pre_url,data=pre_data)
                labels = pre_return.json().get('data').get('labels')
                if len(labels) <=1:
                    faile_list.append({'filename': old_name, 'warning': '该切片是小切片，切割预览没有报错'})
                    '4.1.1、上传的是小切片，且要进行智能诊断【2023-03-13】'
                    # 使用一个标识，表明是上传的小切片
                    TSlide.objects.filter(slide_file_name=ret.get('filename')).update(is_small_slide=1)
                    if diagnosis !='no':
                        #对该上传的切片进行智能诊断
                        print('小切片进行切割预览成功，进行智能诊断')
                        web_small_diagnose(filename=filename,old_name=old_name,user_id=user_id,token=token)
                    continue#处理洗一个文件
                # print(pre_return.json(), 'json格式的数据')
                # print(pre_return.content, '字符串格式的数据')
                if type(labels)==list:
                    labels = json.dumps(labels)
                print('大切片切割预览成功')
            except Exception as e:
                faile_list.append({'filename':old_name,'error':'该文件在自动切割预览时出错了'})
                print('切片在切割预览时报错')
                #'4.1.2、修改之前记录好的数据库记录,标识上是小切片但是是由web上传的文件【2023-03-13】'
                # 使用一个标识，表明是上传的小切片
                #TSlide.objects.filter( slide_file_name=ret.get('filename')).update(is_small_slide = 1)
                #if diagnosis != 'no':
                #    print('自动切割报错，对小切片进行智能诊断')
                #    #将上传的小切片进行智能诊断
                #    web_small_diagnose(filename=filename,old_name=old_name,user_id=user_id,token=token)
                
                continue
            
            #continue
            '4.2、生成切割文件，记录到数据库中'
            cut_url = 'http://127.0.0.1:8084/data/cutImageView'
            cut_data = {
                'token':token,
                'labels':labels, # labels列表必须转成字符串，不然application/x-www-form-urlencoded处理有问题 
                'filename':filename,
                'real_width':width ,
                'real_height':height,
                'cache_name':cache_name,#文件切割情况，记录到cache中，这个是key
            }
            headers = {
                'content-type':'application/x-www-form-urlencoded; charset=UTF-8',
                'token':token
            }
            print('-------开始切割--------')
            try:
                print(time.strftime('%Y-%m-%d %H:%M:%S'),' 真正切割的开始时间')
                cut_returen = requests.post(url=cut_url,data=cut_data,headers=headers)
                #print(cut_returen.content,'字符串格式数据')
                #print(cut_returen.json(),'json格式数据')
                print('文件切割结束',cut_returen.status_code,'状态码')
            except Exception as e:
                faile_list.append({'filename':old_name,'error':'文件在正式切割文件报错了'})
                #正式对文件进行切割时报错了，就不再往下进行了
                continue

            #如果正式切割时，是异步的，立即就往下一步操作，那就很难实现下面的智能诊断
            print(time.strftime('Y-%m-%d %H:%M:%S'),' 真正切割的结束时间')
            print('-----切割结束-------')
            '4.3、需要告诉前端，该切片选择了自动切割文件，需要展示切割进度'
            is_cut_key = f'{old_name}-{user_id}-is-cut'
            cache.set(is_cut_key, 'yes')

            '五、智能诊断:只有进行了文件切割才能进行智能诊断'
            # 让前端知道切片是否进行智能诊断，这个是key
            is_diagnose_key = f'{old_name}-{user_id}-is-diagnose'
            if diagnosis=='all':
                #将切割后的所有小文件进行智能诊断
                #go_to_diaginose(cut_cache_key=cache_name,numbel=diagnosis,token=token,user_id=user_id,
                #                old_filename=old_name)
                goto=GoToDiaginose(cut_cache_key=cache_name,numbel=diagnosis,token=token,user_id=user_id,old_filename=old_name)
                goto.start()
                #将是进行智能诊断放到cache中
                cache.set(is_diagnose_key,'yes')
                print(diagnosis,'对所有的小文件进行智能诊断结束')
            elif diagnosis == 'no':
                #切割后的小文件不进行智能诊断
                pass
            else:
                try:
                    diagnosis = int(diagnosis)
                    #智能诊断的个数

                except Exception as e:
                    diagnosis = 2
                print(diagnosis, '个小文件进行智能诊断')
                #go_to_diaginose(cut_cache_key=cache_name,numbel=diagnosis,token=token,user_id=user_id,
                #                old_filename=old_name)
                goto=GoToDiaginose(cut_cache_key=cache_name,numbel=diagnosis,token=token,user_id=user_id,old_filename=old_name)
                goto.start()
                #将是进行智能诊断放到cache中
                cache.set(is_diagnose_key,'yes')
                print('一个大文件诊断结束')
        else:
            #不选择自动切割
            '四-1、上传的是小切片，没有选择自动切割，但选择了智能诊断[需要对小切片进行智能诊断]'
            '请求切割预览：判断是否是小切片'
            pre_url = 'http://127.0.0.1:8084/data/autoPreview'
            # 如果是手动切割 data/runPreview路由时，需要再加上参数：'centers':12,'patch':80,'ioc':0.5
            pre_data = {'token': token, 'filename': filename}
            is_small = False
            try:
                pre_return = requests.post(url=pre_url, data=pre_data)
                labels = pre_return.json().get('data').get('labels')
                if len(labels) <= 1:
                    print('切割预览是小切片')
                    is_small = True
                    faile_list.append({'warning':f'{old_name}切片是小切片，切割预览没有报错','filename':old_name})
            except Exception as e:
                print(str(e),'切割预览报错了')
                faile_list.append({'error': f'{old_name}切片自动切割预览时报错了', 'filename': old_name})
                #is_small = True
                continue 
            '根据切割预览知道上传的切片是否是小切片'
            if is_small:
                # 上传的是小切片，需要根据用户选择，对切片进行智能诊断
                #更新web上传的切片是个小切片，
                TSlide.objects.filter(slide_file_name=ret.get('filename')).update(is_small_slide=1)
                if diagnosis !='no':
                    #对小切片进行智能诊断
                    print('上传小切片，没有自动切割，进行智能诊断')
                    web_small_diagnose(filename=filename, old_name=old_name, user_id=user_id, token=token)
                else:
                    #上传的是小切片，也没有选择智能诊断,就无需操作，进行下一个文件操作
                    pass
            else:
                #上传的是小切片，不管用户是否选择智能诊断，都不会有任何操作了
                pass
        #文件成功后
        success_list.append(filename)
    return JsonResponse(data={'code':200,'failed':faile_list,'success':success_list})

@gcm.check_api_token()
def web_upload_file_progress(request):
    '''
    功能：传递文件名过来，返回文件的处理情况。
    1、文件切割的处理进度
    2、小文件进行智能诊断的处理进度
    '''
    file_type = request.POST.get('type') #要查看的文件情况
    user_id = request.req_accountInfo.get('account_id') #拿到当前用户的id
    file_name = request.POST.get('filename')

    show = 'no'
    if file_type =='cut':#文件切割进度情况
        '如果选择自动切割，给一个字段给前端，说明要展示切割进度条'
        is_cut_key = f'{file_name}-{user_id}-is-cut'
        is_show = cache.get(is_cut_key)
        if is_show:
            show = 'yes'

        key = f'{file_name}-{user_id}-cut'
        dic = cache.get(key)
        print(dic,type(dic),'cut情况')
        try:
            dic = json.loads(dic)
            #切割进度数据不仅仅前端要用到，智能诊断需要里面的切割文件名数据,不能清除掉
        except Exception as e:
            return JsonResponse({'code':400,'msg':'cut没有查询到数据','show':show})
    elif file_type =='diagnosis':#智能诊断进度情况
        '给前端一个信号，说明要展示智能诊断进度条'
        is_diagnose_key = f'{file_name}-{user_id}-is-diagnose'
        is_show = cache.get(is_diagnose_key)
        if is_show:
            show ='yes'

        key = f'{file_name}-{user_id}-diagnosis'
        dic = cache.get(key)
        try:
            dic = json.loads(dic)
        except Exception as e:
            return JsonResponse({'code': 400, 'msg': 'diagnosis没有查询到数据','show':show})
    else:
        return JsonResponse({'code':400,'msg':'请携带上type参数数据','show':show})
    
    return JsonResponse({'code':200,'data':dic,'msg':'','show':show})

@gcm.check_api_token()
def save_new_diagnostic_result(request):
    '''
    2023-2-28: 新增接口，智能诊断接口改版，一个切片进行智能诊断后，只会生成4张图和对应的结果【GPU返回结果到这个接口】
    GPU的诊断结果会返回到这个接口来，这里是处理诊断结果的数据    
    '''
    img = request.FILES.get('file')  # 智能诊断生成的图片,拿到的文件名，cam_切片文件名，每次拿到的文件名都不一样
    filename = request.POST.get('tiff')  # 进行智能诊断的切片文件
    part = request.POST.get('type')  # 1萎缩性，2肠上皮化生，3活动性，4炎症
    result = request.POST.get('class')  # 0无，1轻度，2中度，3重度
    father_filename = request.POST.get('father_filename') #进行智能诊断切片的父切片名
    #print(request.POST,'拿到的数据')
    #print(img,'拿到的图片')
    if not img:
        return JsonResponse({'code': 404, 'msg': '没有图片'})
    if not filename:
        return JsonResponse({'code': 404, 'msg': '没有携带文件名'})
    if not part:
        return JsonResponse({'code': 404, 'msg': '没有诊断部分'})
    if not result:
        return JsonResponse({'code': 404, 'msg': '没有诊断结果'})
    '1、将本次智能诊断生成的part类型图片存到upload/hear_map路径中'
    name = str(uuid.uuid4()) + '.jpg'  # 给图片设置名字
    #print(2)
    path = 'upload/heat_map/' + name  # 图片保存的位置
    with open(path, 'wb+') as fp:
        fp.write(img.read())
    #print(f'本次智能诊断保存的图片：{path}')

    '2、将上次智能诊断该part类型的图片删除，将上次智能诊断数据库记录删除掉'
    t_slide = TSlide.objects.filter(slide_file_name=filename).first()
    old_img = TSlideImage.objects.filter(slide=t_slide, part=part)

    for o in old_img:
        # 删除上次的图片
        delete_path = os.path.join(settings.BASE_DIR, o.path)
        #print(f'上次智能诊断删除的图片：{delete_path}')
        if os.path.exists(delete_path):
            os.remove(delete_path)
        else:
            print('data/obtain_fourinfor 要删除的智能诊断的图片不存在')
    old_img.delete()

    '3、将本次智能诊断的结果，写到数据库中'
    image_data = TSlideImage(slide=t_slide, path=path, part=part, result=result)  # 新建数据库记录
    image_data.save()
    #print(img.name)
    '4、浏览器请求的本次智能诊断是否结束了'
    user_id = request.req_accountInfo.get('account_id')#当前用户id

    #浏览器点击小切片智能诊断，使用的cache的key
    key = f'{filename}-{user_id}-chrome' #将当前切片的智能诊断进度写到cache中

    '2023-03-19：当是浏览器点击大切片的智能诊断，选择小切片进行智能诊断时，重新设置key，标识是浏览器点击大切片的智能诊断'
    if father_filename == 'delete':
        #因为浏览器对大切片的智能诊断，无需展示进度，需要完成时将cache删除，需要在开始诊断前将cache删除掉
        key  = f'{filename}-{user_id}-chrome-big'
        print(key,'浏览器点击大切片智能诊断')
    
    '2023-03-19: 当web上传大切片且要进行智能诊断时，重新设置key'
    if '.tiff' in father_filename:
        key = f'{filename}-{user_id}-is-web-diagnose-small'    

    #拿到cache缓存
    cache_dic = cache.get(key)
    if not cache_dic:
        dic = {'all':4,'has':1,'complete':0}
        cache.set(key,json.dumps(dic))
        print(f'{filename}={dic["has"]}智能诊断结果之一记录到数据库中了')
    else:
        '4.1、记录单个切片的智能诊断的进程'
        dic = json.loads(cache_dic)
        dic['has']+=1
        print(f'{filename}={dic["has"]}智能诊断结果之一记录到数据库中了')
        '2023-03-19: 将智能诊断进度写到文件中'
        log_path = os.path.join(settings.BASE_DIR,'logs','diagnose-process.txt')
        write_diagnose_in_file(father=father_filename,slide=filename,count=dic.get('has'),log_path=log_path)
        if dic['has']%4==0:
            dic['complete']=1
            #对于这个切片来说，已经完成智能诊断阶段
            t_slide.is_diagnostic=1
            t_slide.save()
            #找到其父切片(大切片不能直接智能诊断，却要展示子切片的诊断结果，所以才有这个)，把父切片的智能诊断状态也改成1
            TSlide.objects.filter(slide_id=t_slide.father_slide_id).update(is_diagnostic=1)
            '4.2、浏览器点击大切片的智能诊断时，大切片会在father_filename=delete'
            if father_filename == 'delete':
                print('浏览器对大切片智能诊断，其中',filename,'切片诊断完成')
                cache.delete(key)
                #因为浏览器点击大切片的智能诊断时，不需要展示进度，就无需将大切片的进度写到cache中,无需进行步骤我5.1和5.2
                #清除小切片的cache
                return gcm.success()
            
            '4.3、浏览器点击小切片的智能诊断时，完成时，在cache添加father_filename=can-delete, 前端在请求进度数据时，当拿到complete=1时就将cache删除掉'
            if not father_filename:#浏览器小切片智能诊断，不会携带father_filename字段
                print(filename,'浏览器对单个切片进行智能诊断结束')
                dic['father_filename'] = 'can-delete' #当前端拿到的cache说明诊断已经结束，就可以把cache删除掉 
        '4.4、将单个智能诊断进度更新回cache中'
        cache.set(key, json.dumps(dic))
        #'4.3、如果只是浏览器选择单个切片进行智能诊断，前端获取到结果后就可以直接删除cache了'
        #if not father_filename and dic['complete']==1:
        #        #当是浏览器请求单个小切片智能诊断完成后，就从cache中移除数据
        #        cache.delete(key)


        '''5.1、web上传文件时，选择了智能诊断，存放诊断的进度, 计算次数的情况,总数=12，完成数=9，可能此时已经完成了（多线程存在的问题），需要下面的来确定是否已经完成了
        '''
        diagnoise_cache_key = f'{father_filename}-{user_id}-diagnosis'
        diagnoise_dic = cache.get(diagnoise_cache_key)
        if diagnoise_dic:
            diagnoise_dic = json.loads(diagnoise_dic)
            diagnoise_dic['finiship_counts']+=1 #一个文件会生成四种数据，这个是完成的数据量
            diagnoise_dic = json.dumps(diagnoise_dic)
            cache.set(diagnoise_cache_key,diagnoise_dic)
    #print(dic,'写到cache中的数据','cache中的key=',key)
    #print(father_filename,'父切片名')
    '''
    diagnoise_dic = {
        'all_files':None, #要进行智能诊断的总切片数量
        'finiship_files':0, #完成智能诊断的切片数量
        'complete':0 #是否已经完成智能诊断
    }
    '''
    #单个切割是否诊断完成
    '''5.2、对web上传时的多个文件的智能诊断进度的书写到cache中'''
    try:
        cache_dic = cache.get(key)
        cache_dic = json.loads(cache_dic)
    except Exception as e:
        cache_dic=None
    if cache_dic and cache_dic['complete']==1 and ('.tiff' in father_filename):
        diagnoise_cache_key = f'{father_filename}-{user_id}-diagnosis'
        diagnoise_dic = cache.get(diagnoise_cache_key)
        if diagnoise_dic: #如果cache中有大文件的小文件智能诊断的进度数据
            diagnoise_dic = json.loads(diagnoise_dic)
            diagnoise_dic['finiship_files']+=1
            '2023-03-19: web上传的单个小切片已经完成智能诊断了，将对应的cache删除掉'
            try:
                cache.delete(key)
                print(f'web上传文件进行的智能诊断，单个切片完成诊断，将key={key}删除')
            except:
                pass
            if diagnoise_dic.get('all_files')==diagnoise_dic.get('finiship_files'):
                #如果所有文件诊断结束了，修改complete=1
                diagnoise_dic['complete']=1
                #将finiship_counts=all_counts ,让完成次数等于总次数
                diagnoise_dic['finiship_counts'] = diagnoise_dic['all_counts'] 
            diagnoise_dic = json.dumps(diagnoise_dic)
            cache.set(diagnoise_cache_key,diagnoise_dic)
            print(diagnoise_dic,'大文件切割的小文件诊断进度')
    return gcm.success()

@gcm.check_api_token()
def get_diagnoise_chrome(request):
    '''
    2023-2-28：浏览器端获取单个切片的智能诊断进度
    从cache中拿到的切片进度
    dic = {
        'all':4,#总图片生成
        'has':1, #完成图片
        'complete':0
    }
    '''
    user_id = request.req_accountInfo.get('account_id')#当前用户id
    filename = request.GET.get('filename')#进行智能诊断的切片名
    key = f'{filename}-{user_id}-chrome' #从cache中获取智能诊断进度
    print(key,'cache中的key')
    dic = cache.get(key)
    if dic:
        dic = json.loads(dic)
    else:
        dic = {
            'all':4,
            'has':0,
            'complete':0
        }
    '2、前端拿到浏览器请求的单个智能诊断结束了，要把cache删除掉'
    if dic.get('father_filename','none')=='can-delete' and dic.get('complete'):
        #当是浏览器点击单个切片智能诊断时，且已经完成诊断了，前端拿到数据后，就把cache删除掉
        print('删除掉key=',key)
        cache.delete(key)
    return JsonResponse({'data': dic, 'code': 200})

'2023-2-14,新增web文件上传，自动切割，智能诊断结束'

'''2023/1/8新增功能：切片名字和诊断结果'''
def slide_diagnose_result(request):
    if request.method == 'GET':
        is_all = request.GET.get('is_all')
        if is_all:
            with open('upload/all_result.txt','w+') as fp:
                slide_results = SlideDiagnoseModel.objects.all()
                for slide_result in slide_results:
                    dic = {'id':slide_result.pk,'slide_name':slide_result.slide_name,'diagnose_result':slide_result.diagnose_result}
                    str_dic = f'id={slide_result.pk}  ,slide_name={slide_result.slide_name}'
                    fp.write(str_dic+'\n'+'\n')
            return JsonResponse({'code':200,'msg':'文件下载成功'})
        #传递切片的名字,同一个切片名字，只有一条记录
        slide_name = request.GET.get('slide')
        if not slide_name:
            return JsonResponse(data={'code':401,'msg':'请携带上切片名字'})
        else:
            #查询数据库
            slide_result = SlideDiagnoseModel.objects.filter(slide_name=slide_name).first()
            if slide_result:
                #把模型直接转成字典格式
                dic = model_to_dict(slide_result)
                return JsonResponse(data={'code':200,'data':dic},)
            else:
                return JsonResponse(data={'code':404,'data':{},'msg':'无此记录'})
    elif request.method == 'POST':
        #新建切片名字和诊断结果的记录,同一个切片名字只有一条记录
        slide_name = request.POST.get('slide')
        diagnose_result = request.POST.get('diagnose')
        if not slide_name:
            return JsonResponse(data={'code':401,'msg':'没有携带上切片文件名'})
        if not diagnose_result:
            return JsonResponse(data={'code':401,'msg':'没有携带上诊断结果'})
        if len(diagnose_result) > 512:
            return JsonResponse(data={'code':405,'msg':'诊断结果描述，字符数不能超过512'})
        slide_result = SlideDiagnoseModel.objects.filter(slide_name=slide_name).first()
        if slide_result:
            #当前的切片文件名字存在记录了
            slide_result.diagnose_result = diagnose_result
            slide_result.save()
            return JsonResponse(data={'code':200,'msg':'操作成功（修改）'})
        else:
            #当前切片文件不存在记录时
            slide=SlideDiagnoseModel()
            slide.diagnose_result=diagnose_result
            slide.slide_name=slide_name
            slide.save()
            return JsonResponse(data={'code':200,'msg':'操作成功（新增）'})
    else:
        return JsonResponse(data={'code':403,'msg':'错误的请求方式'})


'''2022/12/6新增的功能'''
class DiagnoseNeedDataView(View):
    def get(self,request):
        '''
        功能：返回诊断报告中，病理分析中，选项的第一个参数
        :param request:
        :return:
        PART_OF_SELECTION={
                1:['DQ','窦前'],2:['DX','窦小'],3:['DD','窦大'],4:['DH','窦后'],5:['DT','窦体'],
                6:['WT','胃体'],7:['WX','胃小'],8:['WD','胃窦'],9:['WD','胃底'],10:['WJ','胃角'],
                11:['TX','体小'], 12:['TD','体大'],13:['BM','贲门'],14:['BMX','贲门下'],15:['YMQQ','幽门前区'],
            }
        SLIDE_TYPE={1:'CT/活检'}
        '''
        #获取诊断位置选项
        dic = settings.PART_OF_SELECTION
        data_list=[]
        for key,values_list in dic.items():
            d = {'id':key,'value':values_list[1]}
            data_list.append(d)
        #获取影像选择
        image_type= settings.SLIDE_TYPE
        slide_type_list=[]
        for k,value in image_type.items():
            slide_type_list.append({'id':k,'value':value})

        #诊断结果的程度
        diagnose_level = settings.DIAGNOSE_LEVEL
        level_list=[]
        for k,v in diagnose_level.items():
            level_list.append({'id':k,'value':v})
        #2023-03-7新增：诊断部位
        diagnose_part = []
        for k,v in DIAGNOSE_PART.items():
            diagnose_part.append({'id':k,'value':v})

        #2023-03-07新增：诊断部位结果
        diagnose_result=[]
        for k,v in DIAGNOSE_RESULT.items():
            diagnose_result.append({'id':k,'value':v})

        #2023-03-07科室
        department_list=[]
        for k,v in settings.DEPARTMENT.items():
            department_list.append({'id':k,'value':v})
        #2023-03-08 医院
        hospital = settings.HOSPITAL

        return JsonResponse(data={
            'code':200,
            'part_list':data_list,
            'slide_types':slide_type_list,
            'level':level_list,
            'diagnose_part':diagnose_part,
            'diagnose_result':diagnose_result,
            'department_list':department_list,
            'hospital':hospital, #2023-03-08
        })


'''2022/12/06新增：搜索诊断部分返回符合条件的选项'''

def search_part(request):
    '''
    功能：前端搜索下面的部位，返回对应符合搜索的结果的列表, 搜d或D ，返回所有带D的选项
    PART_OF_SELECTION={
    1:['DQ','窦前'],2:['DX','窦小'],3:['DD','窦大'],4:['DH','窦后'],
    5:['DT','窦体'],6:['WT','胃体'],7:['WX','胃小'],8:['WD','胃窦'],
    9:['WD','胃底'],10:['WJ','胃角'],11:['TX','体小'],12:['TD','体大'],
    13:['BM','贲门'],14:['BMX','贲门下'],15:['YMQQ','幽门前区'],
}
    :param request:
    :return:
             [{'id':1,'value':'窦前'},{},...]
    '''
    if request.method == 'GET':
        part = request.GET.get('part')#part 可以是大小写字母，中文，等
        if not part:
            return JsonResponse(data={'code':404,'error':'没有携带搜索的关键字'})
        #将字符串转成大写
        part = part.strip().upper()
        part_dic = settings.PART_OF_SELECTION
        ret_list=[]
        #过滤符合搜索关键字的所有选项
        for k,v in part_dic.items():
            for i in v:
                if part in i:
                    ret_list.append({'id':k,'value':v[1]})
        return JsonResponse(data={'cdoe':200,'data':ret_list})
    else:
        return JsonResponse(data={'code':200,'error':'当前请求无功能'})


@gcm.check_api_token()
def update_slide_label(request):
    if request.method == 'POST':
        account_id = request.req_accountInfo.get('account_id')

        slide_label_id = request.POST.get('slide_label_id')
        label_info = request.POST.get('label_info')
        slide_file_name = request.POST.get('slide_file_name')
        real_width = request.POST.get('real_width')
        real_height = request.POST.get('real_height')
        print(slide_label_id,'标注的id')

        account = TAccount.objects.get(account_id=account_id)

        label_info_dict = simplejson.loads(label_info)
        if label_info_dict.get('type') == 'fixedRectangle':
            is_scope = 1
        else:
            is_scope = 0

        if slide_label_id:
            slide_label = TSlideLabel.objects.get(slide_label_id=slide_label_id)
            slide_label.label_info = label_info
            slide_label.save()
        else:
            if not slide_file_name:
                return gcm.failed('缺少切片名称')

            slide_objs = TSlide.objects.filter(slide_file_name=slide_file_name)
            if not slide_objs:
                slide = TSlide.objects.create(slide_file_name=slide_file_name, real_width=real_width,
                                              real_height=real_height, status=1)
            else:
                slide = slide_objs[0]
                slide.status = 1
                slide.save()
                '2023-03-15 找到小切片的父切片，把它的status也设置成1,浏览器展示切片的标注状态时'
                fatherslide_id = slide.father_slide_id
                TSlide.objects.filter(pk=fatherslide_id,is_delete=False).update(status=1)
                print(fatherslide_id,'父切片的id')
            slide_label = TSlideLabel.objects.create(label_info=label_info, slide_id=slide.slide_id,
                                                     slide_file_name=slide_file_name, creator=account, is_scope=is_scope)

        return gcm.data(slide_label.slide_label_id)

def update_slide_label_title(request):
    if request.method == 'POST':
        slide_label_id = request.POST.get('slide_label_id')
        label_title = request.POST.get('label_title')
        label_desc = request.POST.get('label_desc')

        slide_label = TSlideLabel.objects.get(slide_label_id=slide_label_id)
        slide_label.label_title = label_title
        slide_label.label_desc = label_desc
        slide_label.save()

        return gcm.success()

def list_slide_label(request):
    if request.method == "POST":
        slide_file_name = request.POST.get('slide_file_name')
        print(slide_file_name)
        slide_label = TSlideLabel.objects.filter(slide_file_name=slide_file_name).exclude(creator__account_id=32).values("slide_label_id",
                    "label_title", "label_desc", "label_info", "creator__real_name")
        if slide_label:
            slide_label = list(slide_label)
        else:
            slide_label = []
        print(slide_label)
        return gcm.data(slide_label)


def list_slide_label_type(request):
    if request.method == 'POST':
        #return JsonResponse({'code':100})
        slide_file_name = request.POST.get('slide_file_name')
        page = request.POST.get('page')
        type = request.POST.get('type')
        slide_label = TSlideLabel.objects.filter(slide_file_name=slide_file_name, creator__account_id=32,
                    type=type).values("slide_label_id", "label_title", "label_desc", "label_info", "creator__real_name")
        count = slide_label.count()
        print(count,'请求智能诊断打上的标签')
        size = 1000
        if slide_label:
            start = (page - 1) * size
            end = page * size - 1
            if end > count:
                end = count
            slide_label = list(slide_label[start:end])
        else:
            slide_label = []
            start = 0
            end = 0

        return gcm.data({"data": slide_label, "count": count, "start": start, "end": end})


def del_slide_label(request):
    if request.method == "POST":
        slide_label_id = request.POST.get('slide_label_id')
        label_info = TSlideLabel.objects.get(slide_label_id=slide_label_id)
        slide_id = label_info.slide_id
        slide_file_name = label_info.slide_file_name

        label_info.delete()
        label_list = TSlideLabel.objects.filter(slide_file_name=slide_file_name)
        if not label_list:
            TSlide.objects.get(slide_id=slide_id).delete()
        return gcm.success()


def check_is_mark(request):
    if request.method == 'POST':
        file_name_list = request.POST.get('fileNameList')
        label_data = TSlide.objects.filter(tslidelabel__slide_file_name__in=file_name_list).distinct()
        print(label_data)
        rlt = {}
        for item in label_data:
            slide_file_name = item.slide_file_name
            item_dict = model_to_dict(item)
            item_dict['mark_user'] = item.mark_user
            item_dict['is_scope'] = item.is_scope
            rlt[slide_file_name] = item_dict

        return gcm.data(rlt)


@gcm.check_api_token()
def update_slide_confirm(request):
    if request.method == 'POST':
        account_id = request.req_accountInfo.get('account_id')
        account = TAccount.objects.get(account_id=account_id)

        slide_id = request.POST.get('slide_id')
        print('lhz ',type(slide_id),slide_id)
        if type(slide_id)==TSlide:
            print('当前slide_id是对象，不是id值')
        slide_path = request.POST.get('slide_path')
        slide_url = request.POST.get('slide_url')

        slide = TSlide.objects.get(slide_id=slide_id)
        slide.status = 2
        slide.confirm_time = datetime.datetime.now()
        slide.confirm_account = account
        slide.has_data = 1
        slide.save()

        # 获取切片信息
        url = settings.IMAGEPARSER_URL + 'GetImageObj/?fileName=' + slide_url
        r = requests.get(url, timeout=5)
        slide_data = simplejson.loads(r.content)
        max_zoom = slide_data.get('maxZoom')

        #生成数据文件
        #2023-02-16修改：之前传递的是slide，一直报错，后面改为slide.slide_id
        common_util.create_json_file(slide.slide_id, slide_path, max_zoom)

        return gcm.success()


def list_slide(request):
    if request.method == 'POST':
        status = request.POST.get('status')
        slide_name = request.POST.get('slideName')
        page_index = int(request.POST.get('pageIndex'))
        page_size = int(request.POST.get('pageSize'))
        sort = request.POST.get('sort') if request.POST.get('sort') == 'asc' else 'desc'
        sort_type = request.POST.get('sortType')
        if status == '1' or status == '2' or status == '0':
            '''
            status=0，过滤未标注
            status=1，过滤已经标注
            status=2，过滤已经检测
            '''
            if slide_name:
                slide_list = TSlide.objects.filter(status=int(status), slide_file_name__contains=slide_name)
            else:
                slide_list = TSlide.objects.filter(status=int(status))


            if not slide_list: return gcm.data({'count': 0, 'list': []})

            filter_file_names = ','.join([x.slide_file_name for x in slide_list])
            url = 'http://127.0.0.1:8813/getFilesByNames/'
            result = requests.post(url, data={"filterFileNames": filter_file_names}, timeout=50)
            tem_rlt = simplejson.loads(result.content)
            #print(tem_rlt,'响应回来的数据')
            all_data = []
            for slide_file_name in tem_rlt:
                all_data += tem_rlt[slide_file_name]

            if sort_type == "slide_time":
                for i in range(len(all_data) - 1):
                    ex_flag = False
                    for j in range(len(all_data) - i - 1):
                        dj = datetime.datetime.strptime(all_data[j]["scantime"], "%Y/%m/%d %H:%M:%S")
                        dj2 = datetime.datetime.strptime(all_data[j + 1]["scantime"], "%Y/%m/%d %H:%M:%S")
                        if dj > dj2:
                            all_data[j], all_data[j + 1] = all_data[j + 1], all_data[j]
                            ex_flag = True
                    if not ex_flag:
                        break
            else:
                all_data = sorted(all_data, key=lambda data: data["name"])
            if sort == "desc":
                all_data.reverse()

            return gcm.data({
                'count': len(all_data),
                'list': all_data[page_index * page_size:page_size + page_index * page_size]
            })

        else:  # 全部
            # 查询全部数据
            if slide_name:
                url = 'http://127.0.0.1:8813/getFilesByNames/'
                result = requests.post(url, data={"filterFileNames": slide_name}, timeout=50)
                tem_rlt = simplejson.loads(result.content)

                all_data = []
                for slide_file_name in tem_rlt:
                    all_data += tem_rlt[slide_file_name]

                if sort_type == "slide_time":
                    for i in range(len(all_data) - 1):
                        ex_flag = False
                        for j in range(len(all_data) - i - 1):
                            dj = datetime.datetime.strptime(all_data[j]["scantime"], "%Y/%m/%d %H:%M:%S")
                            dj2 = datetime.datetime.strptime(all_data[j + 1]["scantime"], "%Y/%m/%d %H:%M:%S")
                            if dj > dj2:
                                all_data[j], all_data[j + 1] = all_data[j + 1], all_data[j]
                                ex_flag = True
                        if not ex_flag:
                            break
                else:
                    all_data = sorted(all_data, key=lambda data: data["name"])
                if sort == "desc":
                    all_data.reverse()

                return gcm.data({
                    'count': len(all_data),
                    'list': all_data[page_index * page_size:page_size + page_index * page_size]
                })
            else:
                url = 'http://127.0.0.1:8813/getFilesByDays/?pageindex=%s&pagesize=%s&stdate=%s&end=%s' % (
                    page_index, page_size, '2000-01-01'
                    , datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d')
                )
                result = requests.post(url, timeout=50)
                tem_rlt = simplejson.loads(result.content)
                all_data = tem_rlt['ret_data']['list']
                count = tem_rlt['ret_data']['count']

                return gcm.data({
                    'count': count,
                    'list': all_data
                })


def save_json_data(request):
    if request.method == 'POST':
        slide_path = request.POST.get('slide_path')
        slide_id = request.POST.get('slide_id')
        slide_url = request.POST.get('slide_url')

        # 获取切片信息
        url = settings.IMAGEPARSER_URL + 'GetImageObj/?fileName=' + slide_url
        r = requests.get(url, timeout=5)
        slide_data = simplejson.loads(r.content)
        max_zoom = slide_data.get('maxZoom')

        common_util.create_json_file(slide_id, slide_path, max_zoom)
        common_util.create_xml_file(slide_path)
        slide = TSlide.objects.get(slide_id=slide_id)
        slide.has_data = 1
        slide.save()
        return gcm.success()


from django.http import FileResponse
def get_data_json(request):
    if request.method == 'POST':
        slide_path = request.POST.get('slide_path')
        if not slide_path: return gcm.failed('切片路径为空')

        dir_path = os.path.dirname(slide_path)
        filename = os.path.basename(slide_path).replace(".tiff", '.xml')
        data_file_path = os.path.join(dir_path, filename)

        # 检查文件是否存在
        if not os.path.exists(data_file_path):
            return gcm.failed('数据文件不存在:%s' % data_file_path)
        '''原先的文件下载的方法'''
        #f = open(data_file_path, 'rb')
        #stream = f.read()
        #f.close()

        ##一直都是注释的 slideFileName = os.path.split(slide_path)[-1]
        #return gcm.download(stream, filename)

        '''2022/12/09 修改为 '''
        file = open(data_file_path,'rb')
        response = FileResponse(file)
        response['Content-Type'] = 'application/octet-stream'
        response['Content-Disposition'] = f'attachment;filename="{filename}"'
        print(response,'11111111111')
        return response

    elif request.method=='GET':
        slide_path = request.GET.get('slide_path')
        if not slide_path: return gcm.failed('切片路径为空')

        dir_path = os.path.dirname(slide_path)
        filename = os.path.basename(slide_path).replace(".tiff", '.xml')
        data_file_path = os.path.join(dir_path, filename)

        # 检查文件是否存在
        if not os.path.exists(data_file_path):
            return gcm.failed('数据文件不存在:%s' % data_file_path)
        f = open(data_file_path, 'rb')
        stream = f.read()
        f.close()

        #一直都是注释的情况 slideFileName = os.path.split(slide_path)[-1]
        return gcm.download(stream, filename)

def get_fixed_rectangle_xml(request):
    if request.method == 'GET':
        slide_path = request.GET.get('slide_path')
        slide_name = request.GET.get('slide_name')

        file = common_util.create_fixed_rectangle_xml_file(slide_name, slide_path)
        stream = file.getvalue()
        filename = slide_name.replace(".tiff", "_fixed.xml")
        return gcm.download(stream, filename)


def get_md5(request):
    if request.method == 'POST':
        s = request.POST.get('s')
        return gcm.data(hashlib.md5(s).hexdigest())


@gcm.check_api_token()
def run_preview(request):
    if request.method == 'POST':
        centers = request.POST.get('centers')
        patch = request.POST.get('patch')
        iou = request.POST.get('iou')
        filename = request.POST.get('filename')
        labels, path = common_util.previewImage(filename, centers, patch, iou)
        sliename = path.split('/')[-1]
        root_path = path.replace(sliename, "")
        out_path = os.path.join(root_path)
        bmp_path = os.path.join(root_path, "preview.bmp")
        color(bmp_path, out_path, labels)
        data = {
            "out_path": out_path,
            "labels": labels
        }
        return gcm.data(data)

@gcm.check_api_token()
def auto_preview(request):
    if request.method == 'POST':
        filename = request.POST.get('filename')
        url = 'http://127.0.0.1:8813/getFilesByNames/'
        result = requests.post(url, data={"filterFileNames": filename}, timeout=50)
        tem_rlt = simplejson.loads(result.content)
        print(tem_rlt)
        path = tem_rlt[filename][0]["path"]
        path_list = path.split("/")
        bmp_path = "/mnt/" + "/".join(path.split("/")[4:-1]) + "/preview.bmp"

        auto_url = 'http://192.168.3.103:4900/autocut'
        auto_result = requests.post(auto_url, data={"path": bmp_path})
        #print(auto_result,'自动切割返回的数据')
        labels = simplejson.loads(auto_result.content)["location"]
        sliename = path.split('/')[-1]
        root_path = path.replace(sliename, "")
        out_path = os.path.join(root_path)
        bmp_path = os.path.join(root_path, "preview.bmp")
        color(bmp_path, out_path, labels)

        data = {
            "out_path": out_path,
            "labels": labels
        }
        return gcm.data(data)

@gcm.check_api_token()
def cut_image_view(request):
    if request.method == 'POST':
        labels = request.POST.get('labels')
        filename = request.POST.get('filename')
        real_width = request.POST.get('real_width')
        real_height = request.POST.get('real_height')
        '2023-02-16新增'
        #print(type(labels),'数据类型',labels)
        if not labels:
            return JsonResponse({'code':400,'msg':'没有传递labels数据'})
        if not filename:
            return JsonResponse({'code':400,'msg':'没有传递filename数据'})
        if type(labels)==str:
            try:
                labels = json.loads(labels)
            except Exception as e:
                return JsonResponse({'code':400,'msg':'切割预览的数据不能转成列表'})
            '2023-02-16新增结束'
        print(labels,type(labels),'cut_image中拿到的切割数据')
        #return JsonResponse({'code':200})
        slide_obj = TSlide.objects.filter(slide_file_name=filename)
       
        if not slide_obj:
            slide_obj = TSlide(slide_file_name=filename, real_width=real_width, real_height=real_height, status=0,
                               cut_count=0)
            slide_obj.save()
            slide_id = slide_obj.slide_id
        else:
            slide_obj = slide_obj[0]
            slide_id = slide_obj.slide_id
        old_count = slide_obj.cut_count
        if old_count:
            count = old_count + 1
        else:
            count = 0 + 1
        slide_obj.cut_count = count

        slide_obj.save()

        url = 'http://127.0.0.1:8813/getFilesByNames/'
        result = requests.post(url, data={"filterFileNames": filename}, timeout=50)
        tem_rlt = simplejson.loads(result.content)
        path = tem_rlt[filename][0]["path"]

        slide_obj.slide_path = path
        slide_obj.save()

        slide_name = path.split('/')[-1]
        root_path = path.replace(slide_name, "")
        old_out_path = os.path.join(root_path, "output" + str(old_count))
        if os.path.exists(old_out_path):
            common_util.del_file(old_out_path)
        out_path = os.path.join(root_path, "output_" + str(count))
        bmp_path = os.path.join(root_path, "preview.bmp")
        '''2023-02-21 (新增参数cache_name)【web_upload_file视图使用】
            cache_name，cache的key，以要进行切割的大文件+userID作为key。切割文件不在这里，是在cutImageThread方法中实现，要把cache_name传递进去'''
        cache_name = request.POST.get('cache_name',None)

        cut_img = common_util.cutImageThread(path, bmp_path, out_path, labels, root_path, str(count),
                                            slide_id,cache_name=cache_name)
        cut_img.start()
        return gcm.success()

def batch_cut(request):
    filename = request.POST.get('filename')
    url = 'http://127.0.0.1:8813/getFilesByNames/'
    result = requests.post(url, data={"filterFileNames": filename}, timeout=50)
    tem_rlt = simplejson.loads(result.content)
    path = tem_rlt[filename][0]["path"]
    slide_url = tem_rlt[filename][0]["url"]
    bmp_path = "/mnt/" + "/".join(path.split("/")[4:-1]) + "/preview.bmp"

    detail_url = settings.IMAGEPARSER_URL + 'GetImageObj/?fileName=' + "http://127.0.0.1:7100/" + slide_url
    r = requests.get(detail_url, timeout=5)
    slideData = simplejson.loads(r.content)
    real_width = slideData.get('maxWidth')
    real_height = slideData.get('maxHeight')

    auto_url = 'http://192.168.3.103:4900/autocut'
    auto_result = requests.post(auto_url, data={"path": bmp_path})
    labels = simplejson.loads(auto_result.content)["location"]

    slide_obj = TSlide.objects.filter(slide_file_name=filename)
    count = 1
    if not slide_obj:
        slide_obj = TSlide(slide_file_name=filename, slide_path=path, real_width=real_width, real_height=real_height, status=0)
    else:
        slide_obj = slide_obj[0]

    slide_obj.cut_count = count
    slide_obj.save()

    slide_id = slide_obj.slide_id

    slide_name = path.split('/')[-1]
    root_path = path.replace(slide_name, "")
    out_path = os.path.join(root_path, "output_" + str(count))
    bmp_path = os.path.join(root_path, "preview.bmp")
    cut_img = common_util.cutImageThread(path, bmp_path, out_path, labels, root_path, str(count), slide_id)
    cut_img.start()

    return gcm.success()

@gcm.check_api_token()
def get_thumb(request):
    if request.method == 'POST':
        filename = request.POST.get('filename')
        url = 'http://127.0.0.1:8813/getFilesByNames/'
        result = requests.post(url, data={"filterFileNames": filename}, timeout=50)
        tem_rlt = simplejson.loads(result.content)
        path = tem_rlt[filename][0]["path"]

        slide_url = path.replace('/home/thearay/DataSet', "")
        url = settings.IMAGEPARSER_URL + 'GetImageObj/?fileName=http://127.0.0.1:7100' + slide_url
        r = requests.get(url, timeout=5)
        slide_data = simplejson.loads(r.content)
        max_zoom = slide_data.get('maxZoom')

        slide_name = path.split('/')[-1]
        root_path = path.replace(slide_name, "")
        thumb_path = os.path.join(root_path, slide_name.replace(".tiff", "_color.jpg"))

        slide = openslide.OpenSlide(path)
        slide_thumbnail = slide.get_thumbnail((1920, 1080))
        thumb_array = numpy.array(slide_thumbnail)
        slide_w, slide_h = slide.dimensions
        img_h, img_w = thumb_array.shape[:2]
        downsample = min(int(slide_h / img_h), int(slide_w / img_w))
        print(slide_w, slide_h)

        label_list = TSlideLabel.objects.filter(slide_file_name=filename)
        for label in label_list:
            label_info = label.get('label_info')
            if not label_info: continue

            labelObj = simplejson.loads(label_info)
            baseX = labelObj.get('x') * slide_w
            baseY = labelObj.get('y') * slide_w

            if 'data' not in labelObj: continue
            path = labelObj.get('data').get('path')
            realZoom = labelObj.get('realZoom')
            color = labelObj.get('color').encode('gbk')
            color = common_util.change_color(color)

            realpath = []
            if not path: continue
            for p in path:
                realpath.append([p['x'] * max_zoom / realZoom + baseX, p['y'] * max_zoom / realZoom + baseY])
            realpath = numpy.array(realpath) / downsample
            realpath = numpy.array(realpath, dtype=numpy.int)
            color = (color[2], color[1], color[0])
            img = cv2.polylines(thumb_array, [realpath], True, color, 2)
        cv2.imwrite(thumb_path, img)
        return gcm.data(thumb_path.replace("/home/thearay/DataSet/", ""))

@gcm.check_api_token()
def import_xml(request):
    '''2023-3-1注释，旧版请求智能诊断的接口{后续不再使用这个接口了，使用下面的import_xml_new}'''
    if request.method == 'POST':
        filename = request.POST.get('filename')
        url = request.POST.get("url")
        path = request.POST.get('path')
        t_slide = TSlide.objects.filter(slide_file_name=filename)
        # 进行智能诊断小切片的父切片名【web上传文件过程中选择了智能诊断时需要这个】
        father_filename = request.POST.get('father_filename')
        if not t_slide:
            detail_url = settings.IMAGEPARSER_URL + 'GetImageObj/?fileName=' + "http://127.0.0.1:7100/" + url
            r = requests.get(detail_url, timeout=5)
            slide_data = simplejson.loads(r.content)
            real_width = slide_data.get('maxWidth')
            real_height = slide_data.get('maxHeight')
            t_slide = TSlide(slide_file_name=filename, slide_path=path, real_width=real_width,
                               real_height=real_height, status=0)
            t_slide.save()
        else:
            t_slide = t_slide[0]
        #t_slide.is_diagnostic = 0
        t_slide.is_diagnostic = 2 #这个字段0或null时，就是未处理,1是智能诊断完成，2是智能诊断计算中 
        t_slide.save()
        down_url = "http://192.168.3.103:5001/Diagnose"
        #down_url = "http://192.168.3.103:5001/Diagnosetest"
        # nfs_path = "/app/store/"
        nfs_path = "/mnt/"
        '2023-02-28新增，请求给GPU时，携带上token和小切片的父切片名字，在obtain_fourinfor请求中会使用到'
        token = request.req_token
        data = {"path": nfs_path + url,'token':token,'father_filename':father_filename}
        res = requests.post(down_url, data=data)
        print("request.done")
        return gcm.data("正在标注，请稍后查看")

@gcm.check_api_token()
def import_xml_new(request):
    '''2023-3-1注释，新版请求智能诊断的接口'''
    if request.method == 'POST':
        filename = request.POST.get('filename')#小切片名
        url = request.POST.get("url")#文件相对于/home/thearay/Dataset的相对路径[前端可以不要传递，通过数据库拿]
        path = request.POST.get('path') #文件的绝对路径 【前端可以不用传递通过数据库拿】
        t_slide = TSlide.objects.filter(slide_file_name=filename)
        # 进行智能诊断小切片的父切片名【web上传文件过程中选择了智能诊断时需要这个,在作为cache的key的一部分】
        father_filename = request.POST.get('father_filename')
        print(filename,'进行智能诊断的小切片')
        #print(request.POST)
        #return gcm.data('在测试中')
        if not t_slide:
            #进行智能诊断的小切片一定在数据库中
            return JsonResponse({'code':400,'msg':f'数据库无{filename}切片'})
            detail_url = settings.IMAGEPARSER_URL + 'GetImageObj/?fileName=' + "http://127.0.0.1:7100/" + url
            r = requests.get(detail_url, timeout=5)
            slide_data = simplejson.loads(r.content)
            real_width = slide_data.get('maxWidth')
            real_height = slide_data.get('maxHeight')
            t_slide = TSlide(slide_file_name=filename, slide_path=path, real_width=real_width,
                               real_height=real_height, status=0)
            t_slide.save()
        else:
            t_slide = t_slide[0]
        if not t_slide.slide_path:
            return JsonResponse({'code':400,'msg':f'{filename} 切片的路径不存在'})
        #t_slide.is_diagnostic = 0
        t_slide.is_diagnostic = 2 #这个字段0或null时，就是未处理,1是智能诊断完成，2是智能诊断计算中 
        t_slide.diagnose_time = datetime.datetime.now()+datetime.timedelta(hours=8)  # 更新最后一次智能诊断时间
        # 更新最后一次智能诊断时间+8个小时，如果当前时间大于最后一次诊断时间，就将计算中的切片转成已经完成
        t_slide.save()
        # 找到进行智能诊断小切片的父切片（不能进行智能诊断，但需要过滤子切片的诊断状态），把父切片的智能诊断状态也改成2
        TSlide.objects.filter(slide_id=t_slide.father_slide_id).update(is_diagnostic=2,diagnose_time=datetime.datetime.now()+datetime.timedelta(hours=8))

        #2023-02-28注释：GPU服务器修改智能诊断接口，旧路由=Diagnose改为新路由=Diagnosetest
        # down_url = "http://192.168.3.103:5001/Diagnose"
        down_url = "http://192.168.3.103:5001/Diagnosetest"
        # nfs_path = "/app/store/"
        nfs_path = "/mnt/"
        '2023-02-28新增，请求给GPU时，携带上token和小切片的父切片名字，在obtain_fourinfor请求中会使用到'
        url = t_slide.slide_path.split(settings.SLIDE_SAVE_ROOT,1)[-1] #将path 切割 'DataSet/',取后面部分
        token = request.req_token
        data = {"path": nfs_path + url,'token':token,'father_filename':father_filename}
        res = requests.post(down_url, data=data)
        print("request.done")
        return gcm.data("正在标注，请稍后查看")

@gcm.check_api_token()
def download_slide(request):
    if request.method == 'GET':
        filename = request.GET.get('filename')
        url = 'http://127.0.0.1:8813/getFilesByNames/'
        result = requests.post(url, data={"filterFileNames": filename}, timeout=50)
        tem_rlt = simplejson.loads(result.content)
        path = tem_rlt[filename][0]["path"]
        if not os.path.exists(path):
            return gcm.failed("文件不存在")
        if os.path.getsize(path) > 1024 * 1024 * 100:
            return gcm.failed("文件大于100M，不提供下载")
        file = open(path, 'rb')
        response = StreamingHttpResponse(file)
        response['Content-Type'] = 'application/octet-stream'
        response['Content-Disposition'] = 'attachment;filename=' + filename
        return response


def all_save_json_data(request):
    filename = request.POST.get('filename')

    # 获取切片信息
    all_url = 'http://127.0.0.1:8813/getFilesByNames/'
    all_result = requests.post(all_url, data={"filterFileNames": filename}, timeout=50)
    tem_rlt = simplejson.loads(all_result.content)

    slide = TSlide.objects.get(slide_file_name=filename)
    slide_id = slide.slide_id

    slide_url = tem_rlt[filename][0]["url"]
    slide_path = tem_rlt[filename][0]["path"]
    url = settings.IMAGEPARSER_URL + 'GetImageObj/?fileName=http://127.0.0.1:7100/' + slide_url
    r = requests.get(url, timeout=5)
    slideData = simplejson.loads(r.content)
    maxZoom = slideData.get('maxZoom')

    common_util.create_json_file(slide_id, slide_path, maxZoom)
    common_util.createXmlFile(slide_path)
    slide.has_data = 1
    slide.save()
    return gcm.success()


def obtain(request):
    data = simplejson.loads(request.body.decode())
    str_name = ['contour', 'cell', 'gland_contour']
    filename = data["filename"]
    level = data["CSPHS"]["level"]
    ratio = data["CSPHS"]["ratio"]
    atropy = data["atropy"]["class"]
    t_slide = TSlide.objects.filter(slide_file_name=filename)[0]
    t_slide.level = level
    t_slide.ratio = ratio
    t_slide.atrophy = atropy
    t_slide.save()
    common_util.json2data(filename, data)
    return gcm.success()


def obtain_image(request):
    img = request.FILES.get('file')
    tiff_name = request.POST.get('name')
    img_type = request.POST.get('type')
    if img_type == "twogland":
        i = 1
    else:
        i = 2
    name = str(uuid.uuid4()) + '.jpg'
    path = 'upload/heat_map/' + name
    with open(path, 'wb+') as f:
        f.write(img.read())
    t_slide = TSlide.objects.filter(slide_file_name=tiff_name)[0]
    old_img = TSlideImage.objects.filter(slide=t_slide, type=i)
    if old_img:
        for o in old_img:
            os.remove(os.path.join('/home/thearay/gastritis/slideapi-copy/api', o.path))
    old_img.delete()
    image_data = TSlideImage(slide=t_slide, path=path, type=i)
    image_data.save()
    return gcm.success()


def get_diagnostic(request):
    file_name = request.GET.get('name')
    slide = TSlide.objects.filter(slide_file_name=file_name)
    data = 0
    if slide:
        if slide[0].is_diagnostic == 1:
            data = 1
    return gcm.data(data)


def get_image_url(request):
    file_name = request.GET.get('name')
    img_list = TSlideImage.objects.filter(slide__slide_file_name=file_name)
    data = []
    for i in img_list:
        data.append(model_to_dict(i))
    return gcm.data({"data": data})


def get_label_data(request):
    file_name = request.GET.get('name')
    labels = TSlideLabel.objects.filter(slide_file_name=file_name).values('type').annotate(count=Count('type'))\
        .values('type', 'count')
    data = []
    for l in labels:
        data.append(l)
    return gcm.data({"data": data})


def save_image(request):
    slide_file_name = request.POST.get('path')#http://127.0.0.1:7100/切片的相对路径
    note = request.POST.get('screenshot_text')#截图名
    num = 0
    #print(request.POST.dict())
    print(type(request.POST.dict()))#类型是<class 'dict'>
    for k in request.POST.dict():
        if k.find("data") != -1:
            num += 1
    data = ""
    for i in range(num):
        key = 'data' + str(i)
        if request.POST.get(key):
            data += request.POST.get(key)
    name = data[0:data.find(',')+1]
    img_code = data[data.find(',')+1:]
    img_data = base64.b64decode(img_code)
    _, ext = name.split("/")
    e, _ = ext.split(";")
    new_name = str(uuid.uuid4()) + "." + e
    path = 'upload/screenshots/' + new_name
    with open(path, 'wb') as f:
        f.write(img_data)
    slide_file_name = slide_file_name.split("/")[-1]
    slide = TSlide.objects.filter(slide_file_name=slide_file_name)[0]
    t_image = TSlideImage(slide=slide, path=path, type=3, note=note)
    t_image.save()
    return gcm.data({"message": "保存成功", "t_image_id": t_image.slide_image_id, "path": path})


def get_image(request):
    slide_file_name = request.POST.get('path')
    type = request.POST.get('type')
    slide_file_name = slide_file_name.split("/")[-1]
    slide = TSlide.objects.filter(slide_file_name=slide_file_name)[0]
    t_image = TSlideImage.objects.filter(slide=slide, type=type)
    data = []
    for t in t_image:
        data.append(model_to_dict(t))
    return gcm.data({"data": data})


def delete_image(request):
    image_id = request.POST.get('imageId')
    image = TSlideImage.objects.filter(slide_image_id=image_id, type=3).first()
    print(image.path,'删除的图片路径')
    os.remove(image.path)
    image.delete()
    return gcm.data({"message": "保存成功"})


def save_diagnose(request):
    rise = request.POST.get('rise')
    name = request.POST.get('name')
    gender = request.POST.get('gender')
    age = request.POST.get('age')
    number = request.POST.get('number')
    department = request.POST.get('department')
    hospital = request.POST.get('hospital')
    part = request.POST.get('part')
    content = request.POST.get('content')
    diagnose = request.POST.get('diagnose')
    doctor = request.POST.get('doctor')
    selectNode = request.POST.get('selectNode')
    filename = request.POST.get('filename')
    selectNode = selectNode.split(",")
    #前端没有传递医院时，使用默认的医院
    if not hospital:
        hospital = settings.HOSPITAL
    '''2022/12/06新增，影像类型，整体诊断结果，部分位置诊断结果'''
    slide_type = request.POST.get('slide_type') #影像类型={1:'CT/活检'},前端传递的是中文
    if not slide_type:
        return JsonResponse(data={'code':400,'error':'没有提交影像类型'})
    #2022、12、08新增
    for k,v in settings.SLIDE_TYPE.items():
        if slide_type==v:
            #将中文转成数字
            slide_type=k
            break

    entirety_result = request.POST.get('all_result') #病理诊断，整体诊断结果，医生写什么，就存什么，不再给医生选择
    if not entirety_result:
        return JsonResponse(data={'code':400,'error':'没有提交整体诊断结果'})

    part_result = request.POST.get('part_result') # 病理诊断，部分位置的诊断情况[{'id':1,'part':胃体,'level':医生手写结果,'note':'无需特殊情况'}]
    if not part_result:
        return JsonResponse(data={'code':400,'error':'没有提交部分诊断结果'})
    if type(part_result) ==str:
        part_result = json.loads(part_result)
    if type(part_result) !=str: #最终存储到数据库是json字符串
        part_result = json.dumps(part_result)
    '2022/12/06结束'
    
    '''2023-03-08新增: 显著可见、四个诊断结果[{'part':1,'result':2}]、详解   ，看public/web_upload_public.py 下DIAGNOSE_PART和DIAGNOSE_RESULT两个字典'''
    #1、显著可见
    clearly_visible = request.POST.get('clearly_visible')
    #2、四个方向诊断结果
    four_result = request.POST.get('four_result')
    #3、详解
    detail_content = request.POST.get('detail_content')
    if not four_result:
        return JsonResponse(data={'code':400,'error':'没有携带上四个方向诊断结果'})
    if len(four_result)<4:
        return JsonResponse(data={'code':400,'error':f'缺少{4-len(four_result)} 个方向的诊断结果'})
    four_result = json.dumps(four_result)
    '2023-03-08新增结束'

    #通过切片文件，找到切片记录
    t_slide = TSlide.objects.filter(slide_file_name=filename)[0]
    #新增诊断报告
    t_diagnose = TSlideDiagnose(rise=rise, name=name, gender=gender, age=age, number=number, department=department,
                              hospital=hospital, part=part, content=content, diagnose=diagnose, doctor=doctor)

    '''2022/12/06 新增：将新增加的三个字段写到数据库表中'''
    t_diagnose.slide_type = slide_type
    t_diagnose.check_entirety_result=entirety_result
    t_diagnose.check_part_result = part_result
    '2022/12/06结束'

    '''2023-03-08 新增：将新增加的三个字段写到数据库中'''
    t_diagnose.clearly_visible=clearly_visible #显著可见
    t_diagnose.four_part_result = four_result #[{'part':1,'result':2}] 四个记录
    t_diagnose.detailed_explanation = detail_content #详解
    '20230-03-08结束'

    #保存到数据库中
    t_diagnose.save()
    t_diagnose.slide = t_slide
    t_diagnose.save()
    #将切片的截图记录起来
    for s in selectNode:
        image = TSlideImage.objects.get(slide_image_id=s)
        t_diagnose.image.add(image)

    return gcm.data({"message": "保存成功"})


def get_diagnose(request):
    filename = request.POST.get('filename')
    if not filename:
        return JsonResponse(data={'code':404,'msg':'请携带上切片文件名'})
    t_slide = TSlide.objects.get(slide_file_name__contains=filename)
    t_diagnoses = TSlideDiagnose.objects.filter(slide=t_slide).order_by('-slide_diagnose_id') #2023-03-08取最新的诊断结果
    if t_diagnoses:
        t_diagnose = t_diagnoses[0]
        '''2022、12、06新增：送检时间=切片记录的comfire_time+8个小时, 切片号=切片文件.split('.')[0],'''
        slide_file = t_diagnose.slide.slide_file_name#切片的文件名
        slide_number = slide_file.split('.')[0]
        slide_time = t_diagnose.slide.create_time #切片的检验时间
        slide_time = (slide_time+datetime.timedelta(hours=8)).strftime('%Y-%m-%d')#系统时间是utc，转成东八区
        data = model_to_dict(t_diagnose)

        '''2022、12、06新增：三个字段数据的展示'''
        data['slide_number']=slide_number #切片号
        data['slide_time']=slide_time #送检时间
        data['slide_type']=settings.SLIDE_TYPE.get(data['slide_type'])#影像类型：CT/活检
        data['check_entirety_result']=data['check_entirety_result']#整体诊断结果：无/轻度/中度/重度
        if type(data['check_part_result']) == str:#各部分诊断情况[{},{}]
            data['check_part_result']=json.loads(data['check_part_result'])
        #print(data['check_part_result'],type(data['check_part_result']))
        #print(data)
        dic = data['check_part_result']
        for d in dic:
            print(d,type(d))
        images = t_diagnose.image.all()
        image = []
        for i in images:
            d = {"path": i.path}
            image.append(d)
        data["image"] = image
        #time = (t_diagnose.create_time + datetime.timedelta(hours=8)).strftime("%Y-%y-%m %H:%M")
        #time = (t_diagnose.create_time + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
        time = t_diagnose.create_time.strftime('%Y-%m-%d %H:%M:%S') #时间不用再加8小时了
        data["time"] = time
        
        '''2023-03-08 新增、打印次数、显著可见、详解、四个方向的诊断情况[{'part':'1','result':2}] 通过public/web_upload_puvlic/ part=DIAGNOSE_PART,level=DIAGNOSE_PART '''
        four_dic = data['four_part_result']
        if data['four_part_result']:  # 各部分诊断情况[{'part':'1','result':2}]
            #print(four_dic,type(four_dic))
            try:
                four_part_list = json.loads(data['four_part_result']) #转成python数据格式
                print(four_part_list,type(four_part_list),len(four_part_list))
                lis_dic = []
                for dic in four_part_list:
                    print(dic,type(dic))
                    result=DIAGNOSE_RESULT.get(int(dic.get('result'))) #拿到诊断结果中文=萎缩性
                    part = DIAGNOSE_PART.get(int(dic.get('part'))) #拿到诊断部位中文=无(-)
                    str_and = result.split('(')[0]+part+'('+ result.split('(',1)[-1] #无萎缩性(-)
                    lis_dic.append(str_and)
                data['four_part_result']=lis_dic
            except Exception as e:
                
                pass
        else:
            data['four_part_result']=[]
        '2023-03-08 结束'

    else:
        data = {}
    return gcm.data({"data": data})


'2022、12、06，新增：测试将数据转成json字符串存到数据库，再拿出来'
def test(request):
    if request.method=='POST':
        lis = request.POST.get('lis')
        # lsi =[{"id":1,"part":"胃体","level":"轻度","note":"无"},{"id":2,"part":"窦后","level":"中度","note":"无"}]
        if type(lis) == str:
            lis = json.loads(lis)
        if type(lis) != str:
            lis = json.dumps(lis)
        t_diagonse = TSlideDiagnose.objects.filter(pk=17)[0]
        t_diagonse.check_part_result=lis
        t_diagonse.save()
        return JsonResponse(data={'code':200})
    elif request.method == 'GET':
        t_diagonse = TSlideDiagnose.objects.filter(pk=17)[0]
        t_diagonse = model_to_dict(t_diagonse)
        part_list = t_diagonse.get('check_part_result')
        print(type(part_list),part_list)
        if type(part_list) == str:
            part_list=json.loads(part_list)
        print(type(part_list), part_list)
        if type(part_list) != str:
            for i in part_list:
                print(i,type(i))
        return JsonResponse(data={'code':200})

