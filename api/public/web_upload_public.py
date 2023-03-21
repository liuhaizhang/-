import os
from public import get_imagesize
from django.core.cache import cache
import json
import time
from dataCtrl.models import *
import requests
import threading
from django.conf import settings
import shutil
import stat
import subprocess

'''
1、模型类数值对应的含义
'''

#智能诊断的部分
DIAGNOSE_PART = {
    1:'萎缩性',
    2:'肠上皮化生',
    3:'活动性',
    4:'炎症'
}

#智能诊断某个部分的结果
DIAGNOSE_RESULT={
    0:'无(-)', #表明无
    1:'轻度(+)', #表明轻度
    2:'中度(++)',#表明中度
    3:'重度(+++)'#表明重度
}


'''2、使用到的函数'''

'2023-03-19: 将完成智能诊断情况写到数据库中'
def write_diagnose_in_file(father,slide,count,log_path):
    try:
        with open(log_path,'a+') as fp:
            content = f'fathername={father}, slide={slide} ,conut={count},time={time.strftime("%Y-%m-%d %H:%M:%S")}'
            fp.write(content+'\n')
            if count%4==0:
                fp.write(f'===========》{slide}诊断结束《===========\n')
    except Exception as e:
        print('将完成的智能诊断写到文件中失败了')

'2023-03-16，给小切片生成缩略图'
def slide_make_jpg(slide_path):
    #slide_path  小切片的路径
    #修改目录权限,可以被其他人写入
    #os.chmod(os.path.dirname(slide_path),stat.S_IWOTH)
    #修改目录权限,允许其他用户读写执行
    #os.chmod(os.path.dirname(slide_path,0o777)
    #os.chmod(os.path.dirname(slide_path), 0o777)
    subprocess.run(['chmod', '777', f'{os.path.dirname(slide_path)}'])
    try:
        tiff_to_bmp_url = 'http://192.168.3.103:4900/createpreview'
        nfs_path = "/mnt"
        str_path = nfs_path + slide_path.split('DataSet')[-1]
        data = {"path": str_path, 'is_small': 'yes'}
        r = requests.post(tiff_to_bmp_url, data=data)
        ret_data = r.json()
        print(ret_data)
    except Exception as e:
        print('小切片生成缩略图失败')

'''2023-03-15:删除某个文件夹数据：web上传切片时，生成缩略图失败，没有缩略图就不能进入切割'''
def remove_dir(dir_path):
    if os.path.exists(dir_path) and os.path.isdir(dir_path):
        try:
            shutil.rmtree(dir_path)
            return True
        except Exception as e:
            return False
    else:
        return False

def send_to_import_xml_new(path,filename,token,url,father_filename='delete'):
    '''
    请求importXmlNew路由的，进行智能诊断
    '''
    data = {
        'filename': filename,
        'path': path,
        'url': path.split(settings.SLIDE_SAVE_ROOT, 1)[-1],
        'token': token,
        'father_filename':father_filename,
    }
    # 请求本地一个智能诊断接口，直接请求
    ret = requests.post(url=url, data=data)
    print('智能诊断返回状态码=',ret.status_code,'小切片名',filename)
    #由于GPU对智能诊断的处理是多线程的，所以在这里等待两秒
    time.sleep(1)

class GoToDiaginose(threading.Thread):
    '''
        后端判断文件是否完成了切割，切割完成后，才可以进行智能诊断。
        cut_cache_key: 切割文件情况的数据缓存到cache中，这个key就是cache对应的key
                    {
                    'all_cut_number': 6, #总切割数
                    'has_cut_number': 2, #已切割数
                    'complete': 0,  #0时，还没有切割完成，1时所有文件切割完成
                    'cut_file': ['TestB202035921_6_1.tiff', 'TestB202035921_6_2.tiff'] #切割后的文件名字
                    }
        numbel： 要对切割文件进行智能诊断的数量，number =all,number=数值
        token: 需要token去调用importXml路由，
        user_id: 请求发起的用户id，
        old_filename: 大tiff文件名字
        注意：智能诊断，下依赖于文件切割的
    '''
    def __init__(self,cut_cache_key,numbel,token,user_id,old_filename):
        threading.Thread.__init__(self)
        self.cut_cache_key=cut_cache_key # 切割进度的cache的key
        self.numbel = numbel #对切割好的切片进行智能诊断的数量
        self.token = token
        self.user_id = user_id #请求的用户id
        self.old_filename = old_filename #浏览器上传文件时的文件名
    def run(self) -> None:
        print('---------进入循环智能诊断----------')
        cut_cache_key = self.cut_cache_key
        numbel = self.numbel
        token = self.token
        user_id = self.user_id
        old_filename = self.old_filename
        '1、将大切片对应要进行的智能诊断数量写到cache中，要反馈出智能诊断的进度，大文件--> 切割了5个小切片，要么全部进行智能诊断，要么选择前2个进行智能诊断'
        # old_filename是浏览器上传时的文件名，后期浏览器就通过这个文件名来判断该文件的上传进度，切割进度和诊断进度
        diagnoise_cache_key = f'{old_filename}-{user_id}-diagnosis'
        diagnoise_dic = {
            'all_files': None,  # 要进行智能诊断的所有文件数量
            'finiship_files': 0,  # 完成智能诊断的文件数量
            'complete': 0,  # 所有文件是否完成了智能诊断
            #'file_list': None,  # 要进行智能诊断的文件列表
            'all_counts': None,  # 一个文件生成四个文件才是完成，总文件数x4
            'finiship_counts': 0,  # 一个文件总四次
        }

        '2、下面是cache中获取到大切片切割完成后的小切片的列表，循环这个列表请求智能诊断接口'
        # web端上传的小切片进行智能诊断，要携带上token和old_filename =要进行智能诊断的切片的父切片
        url = 'http://127.0.0.1:8084/data/importXmlNew'
        while True:
            str_dic = cache.get(cut_cache_key)  # 获取当前大tiff文件切割进度
            try:
                dic = json.loads(str_dic)
                print(dic, '切割文件夹进度数据')
            except Exception as e:
                # 此时从cache中获取到的是None时，就会报错
                time.sleep(10)
                # 只有从cache中获取到对应的数据后，才能进行下面的智能诊断请求
                continue
            '''1、拿到切割完成的文件列表，通过遍历这个列表，请求gpu服务器，进行智能诊断'''
            if numbel == 'all':
                if dic.get('complete'):
                    # 一个大的tiff文件全部切割完成了，需要去请求gpu服务器，进行智能诊断
                    file_list = dic.get('cut_file')
                    '将智能诊断情况写到缓存中'
                    #diagnoise_dic['file_list'] = file_list
                    diagnoise_dic['all_files'] = len(file_list)
                    diagnoise_dic['all_counts'] = len(file_list)*4
                    diagnoise_dic['file_list'] = file_list
                    cache.set(diagnoise_cache_key, json.dumps(diagnoise_dic))
                    print('number=all,开始进行智能诊断阶段')

                    for filename in file_list:
                        slide = TSlide.objects.filter(slide_file_name=filename).first()
                        # 请求gpu服务器，进行智能诊断
                        try:
                            path = slide.slide_path
                            data = {
                                'filename': filename,
                                'path': path,
                                'url': path.split('DataSet/',1)[-1],
                                'token': token,
                                'father_filename': old_filename
                            }
                            ret = requests.post(url=url, data=data)
                        except Exception as e:
                            print(str(e),'GoToDiaginose,all,请求importXmlNew路由报错')
                            continue

                    else:
                        # 将切割好的所有需要进行智能诊断的文件进行智能诊断了，就结束该函数
                        return

                else:
                    # 文件还没有自动切割完成
                    time.sleep(10)
                    continue
            else:
                # 要随机对切割的文件进行智能诊断处理
                try:
                    numbel = int(numbel)
                except Exception as e:
                    # 要切割的数量有问题时，就默认是2
                    numbel = 2
                # 已经切割完成的文件数量
                has_cut_number = dic.get('has_cut_number', 0)
                if has_cut_number >= numbel:
                    file_list = dic.get('cut_file')[:numbel]
                    '将智能诊断情况写到缓存中'
                    #diagnoise_dic['file_list'] = file_list
                    diagnoise_dic['all_files'] = len(file_list)
                    diagnoise_dic['all_counts'] = len(file_list)*4
                    diagnoise_dic['file_list'] = file_list
                    cache.set(diagnoise_cache_key, json.dumps(diagnoise_dic))
                    print(f'number={numbel},开始进行智能诊断阶段')
                    for filename in file_list:
                        # 请求gpu服务器，进行智能诊断

                        slide = TSlide.objects.filter(slide_file_name=filename).first()
                        # 请求gpu服务器，进行智能诊断
                        try:
                            path = slide.slide_path
                            data = {
                                'filename': filename,
                                'path': path,
                                'url': path.split('DataSet/',1)[-1],
                                'token': token,
                                'father_filename': old_filename
                            }
                            ret = requests.post(url=url, data=data)
                            print(ret.content, '智能诊断返回的结果')
                        except Exception as e:
                            print(str(e),'GoToDiaginose,请求importXmlNew路由报错')
                            continue
                    else:
                        # 将切割好的所有需要进行智能诊断的文件进行智能诊断了，就结束该函数
                        return
                else:
                    # 切割完成的数量少于要进行智能诊断的数量，等待切割数量大于要智能诊断数量
                    time.sleep(10)
                    continue

'''2023-03-13: web上传的是小切片，且要进行智能诊断'''
def web_small_diagnose(filename,old_name=None,user_id=None,token=None):
    '''
    filename: 切片存放到数据库的文件名
    old_name:切片上传时的文件名
    user_id: 当前的用户id
    token： 认证信息
    '''

    '''2023-03-13 web上传的是小切片时： 不需要展示文件切割进度，因为不能对文件进行切割'''
    '4.2.1、判断是否进行智能诊断操作'
    # 用户选择了智能诊断
    # 将用户选择对该切片进行智能诊断放到cache中，前端需要知道
    is_diagnose_key = f'{old_name}-{user_id}-is-diagnose'
    cache.set(is_diagnose_key, 'yes')
    # 对该小切片进行智能诊断操作
    '4.2.2先把切割进度设置完成，智能诊断需要先有足够的切割文件才能进行的'
    cache_name = f'{old_name}-{user_id}-cut'
    cut_dic = {
        'all_cut_number': 1,
        'has_cut_number': 1,
        'complete': 1,
        'cut_file': [f'{filename}']
    }
    # 把切割进度写到cache中，GoToDiaginose请求智能诊断的类需要这个数据
    cache.set(cache_name, json.dumps(cut_dic))
    '4.2.3、请求智能诊断'
    is_diagnose_key = f'{old_name}-{user_id}-is-diagnose'
    cache.set(is_diagnose_key, 'yes')  # 告诉前端，用户选择进行了智能诊断操作
    diagnosis = 1  # 智能诊断数量
    goto = GoToDiaginose(cut_cache_key=cache_name, numbel=1, token=token, user_id=user_id,
                         old_filename=old_name)
    goto.start()


'''2023-02-14新增功能-文件上传（小功能）: 使用到的tiff文件保存'''
def save_file(path,file,filename=None):
    '''
    :param path:  文件存放的目录，不包含文件名
    :param file:  前端上传的文件
    '''
    #1、判断目录是否存在，不存在就新建
    if not os.path.exists(path):  # 目录是否存在
        oldmask = os.umask(000)
        os.makedirs(path, mode=0o777)  # 递归创建目录
        os.umask(oldmask)
    #2、构建文件的目录
    if not filename:
        return {'code':0,'filename':filename if filename else file.name,'error':'没有传递上正确的文件名'}
    file_path = os.path.join(path,filename)
    print(file_path,'文件的保存位置')
    #3、保存文件
    try:
        with open(file_path,'wb+') as fp:
            for chunk in file.chunks():
                fp.write(chunk)
            else:
                #写文件时，中断了，文件写的不完整
                fp.close()
                return {'code': 1, 'filename': filename,'msg':'文件存储成功','file_path':file_path}
    except Exception as e:
        print(str(e),'保存文件时报错')
        return {'code':0,'filename':filename,'error':f'文件保存失败:{str(e)}'}

'''2023-02-14新增功能-文件上传（小功能）：获取tiff文件的真实宽度和高度[改为上面的多线程类了]'''
def imge_hight_weight(img_path):
    '''
    :param img_path: tiff文件的绝对路
    功能：返回tif文件的真实高度和宽度
    '''
    if os.path.exists(img_path):
        width,height = get_imagesize.get(img_path)
        return {'code':1,'width':width,'height':height}
    else:
        return {'code':1,'width':-1,'height':-1}


'''20230-02-14新增功能-文件上传->后端查看文件是否切割完成，并请求智能诊断接口【晚上写好，未更新到109】'''
def go_to_diaginose(cut_cache_key,numbel,token,user_id,old_filename):
    '''
    后端判断文件是否完成了切割，切割完成后，才可以进行智能诊断。
    cut_cache_key: 切割文件情况的数据缓存到cache中，这个key就是cache对应的key
                {
                'all_cut_number': 6, #总切割数
                'has_cut_number': 2, #已切割数
                'complete': 0,  #0时，还没有切割完成，1时所有文件切割完成
                'cut_file': ['TestB202035921_6_1.tiff', 'TestB202035921_6_2.tiff'] #切割后的文件名字
                }
    numbel： 要对切割文件进行智能诊断的数量，number =all,number=数值
    token: 需要token去调用importXml路由，
    user_id: 请求发起的用户id，
    old_filename: 大tiff文件名字
    注意：智能诊断，下依赖于文件切割的
    '''

    '1、将大切片对应要进行的智能诊断数量写到cache中，要反馈出智能诊断的进度，大文件--> 切割了5个小切片，要么全部进行智能诊断，要么选择前2个进行智能诊断'
    print('进入循环智能诊断函数')
    #old_filename是浏览器上传时的文件名，后期浏览器就通过这个文件名来判断该文件的上传进度，切割进度和诊断进度
    diagnoise_cache_key = f'{old_filename}-{user_id}-diagnosis'
    diagnoise_dic = {
        'all_files':None,
        'finiship_files':0,
        'complete':0,
        'file_list':None
    }
    # web端上传的小切片进行智能诊断，要携带上token和old_filename =要进行智能诊断的切片的父切片
    url = 'http://127.0.0.1:8000/data/importXmlNew'
    while True:
        str_dic = cache.get(cut_cache_key) #获取当前大tiff文件切割进度
        try:
            dic = json.loads(str_dic)
            print(dic,'切割文件的进度')
        except Exception as e:
            #此时从cache中获取到的是None时，就会报错
            time.sleep(3)
            #只有从cache中获取到对应的数据后，才能进行下面的智能诊断请求
            continue
        '''1、拿到切割完成的文件列表，通过遍历这个列表，请求gpu服务器，进行智能诊断'''
        if numbel == 'all':
            if dic.get('complete'):
                #一个大的tiff文件全部切割完成了，需要去请求gpu服务器，进行智能诊断
                file_list = dic.get('cut_file')
                '将智能诊断情况写到缓存中'
                diagnoise_dic['file_list']=file_list
                diagnoise_dic['all_files']=len(file_list)
                cache.set(diagnoise_cache_key,diagnoise_dic)
                print('number=all,开始进行智能诊断阶段')
                for filename in file_list:
                    slide = TSlide.objects.filter(slide_file_name=filename).first()
                    #请求gpu服务器，进行智能诊断
                    path = slide.slide_path
                    try:
                        data = {
                            'filename':filename,
                            'path':path,
                            'url':path.rsplit('DataSet/',)[-1],
                            'token':token,
                            'father_filename':old_filename
                        }
                        ret = requests.post(url=url, data=data)
                        print('')
                    except Exception as e:
                        continue

                else:
                    #将切割好的所有需要进行智能诊断的文件进行智能诊断了，就结束该函数
                    return 'ok'

            else:
                #文件还没有自动切割完成
                time.sleep(10)
                continue
        else:
            #要随机对切割的文件进行智能诊断处理
            try:
                numbel = int(numbel)
            except Exception as e:
                #要切割的数量有问题时，就默认是2
                numbel=2
            #已经切割完成的文件数量
            has_cut_number = dic.get('has_cut_number',0)
            if has_cut_number >=numbel:
                file_list = dic.get('cut_file')[:numbel]
                '将智能诊断情况写到缓存中'
                diagnoise_dic['file_list'] = file_list
                diagnoise_dic['all_files'] = len(file_list)
                cache.set(diagnoise_cache_key,diagnoise_dic)
                print(f'number={numbel},开始进行智能诊断阶段')
                for filename in file_list:
                    # 请求gpu服务器，进行智能诊断
                    slide = TSlide.objects.filter(slide_file_name=filename).first()
                    # 请求gpu服务器，进行智能诊断
                    path = slide.slide_path
                    try:
                        data = {
                            'filename': filename,
                            'path': path,
                            'url': path.rsplit('DataSet/', )[-1],
                            'token': token,
                            'father_filename': old_filename
                        }
                        ret = requests.post(url=url, data=data)
                        print(ret.content,'智能诊断返回的结果')
                    except Exception as e:
                        continue
                else:
                    #将切割好的所有需要进行智能诊断的文件进行智能诊断了，就结束该函数
                    return 'ok'
            else:
                #切割完成的数量少于要进行智能诊断的数量，等待切割数量大于要智能诊断数量
                time.sleep(10)
                continue
