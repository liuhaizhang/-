import io
import random
import threading

from public.my_error import MyError
import os
from dataCtrl.models import TSlide, TSlideLabel, TAccount, TSlideImage
import datetime
import simplejson
from public import my_enum
from xml.dom.minidom import Document
import requests
from public.preview import get_labels
from django.conf import settings
import openslide as opsl
import cv2
import numpy as np
from .cut_xml import isvaild, cut_xml
from public.cut_img import cut
import uuid
#2023-02-21新增
from django.core.cache import cache
import json
from django.db.models import Q 

cell_type = {
    "#92d050": "goblet",
    "#ffc000": "neutrophil",
    "#7030a0": "plasmacyte",
    "#002060": "lymphocyte",
    "#ffff00": "three",
    "#00b050": "three",
    "#ff0000": "three",
    "#00b0f0": "glands"
}

#2023-03-06：创建文件夹，
def create_dir_path(path):
    if not os.path.exists(path):  # 目录是否存在
        oldmask = os.umask(000)
        os.makedirs(path, mode=0o777)  # 递归创建目录
        os.umask(oldmask)

#2023-03-06，修改labels信息生成的.json文件的路径和文件名
def father_slide_create_json_file(slide_id, slide_path, max_zoom):
    if not slide_path:
        #拿到的是切片文件的绝对路径
        raise MyError('切片路径为空')

    dir_path = os.path.dirname(slide_path)

    if not os.path.exists(dir_path):
        #dir_path是切片文件的目录绝对路径
        raise MyError('文件夹不存在:%s' % dir_path)
    print(slide_id,'拿到的切片id')
    print(slide_path,'拿到的切片路径')
    #2023-02-06新增，确定检验数据
    #try:
    #    slide_id = slide_id.pk
    #except Exception as e:
    #    print(str(e),__file__)

    slide = TSlide.objects.get(slide_id=slide_id)
    #2023-03-06过滤掉是AI打的标注信息,AI在TAccount中是id是32，该用户得先创建了
    label_list = TSlideLabel.objects.filter(slide_id=slide_id).filter(~Q(creator=32))

    if not label_list:
        raise MyError('切片下没有标注')

    real_width = slide.real_width
    if not real_width:
        raise MyError('此切片文件缺少real_width数据')


    # 记录slide_path
    slide.slide_path = slide_path
    slide.save()

    create_time = slide.create_time
    rlt = {
        'id': slide.slide_id,
        'width': real_width,
        'height': slide.real_height,
        'file_name': slide.slide_file_name,
        'data_captured': datetime.datetime.strftime(create_time, '%Y-%m-%d %H:%M:%S') if create_time else '',
        'annotations': []
    }

    for label in label_list:
        label_info = label.label_info
        if not label_info: continue

        label_obj = simplejson.loads(label_info)
        baseX = label_obj.get('x') * real_width
        baseY = label_obj.get('y') * real_width
        color = label_obj.get('color')
        type = label_obj.get('type')

        if type == 'pen':
            if 'data' not in label_obj:
                continue
            path = label_obj.get('data').get('path')
            real_zoom = label_obj.get('realZoom')

            realpath = []
            if not path: continue
            for p in path:
                realpath.append([p['x'] * max_zoom / real_zoom + baseX, p['y'] * max_zoom / real_zoom + baseY])

        elif type == 'circle':

            r = label_obj.get('width') * real_width / 2
            a = baseX + r
            b = baseY + r

            realpath = []
            realpath2 = []
            realpath.append([baseX, b])
            realpath2.append([a + r, b])
            for i in [0.25 / 8, 0.5 / 8, 0.75 / 8, 1.0 / 8, 2.0 / 8, 3.0 / 8, 4.0 / 8, 5.0 / 8, 6.0 / 8, 7.0 / 8,
                      7.25 / 8, 7.5 / 8, 7.75 / 8]:
                x1 = baseX + i * 2 * r
                y1 = (r ** 2 - (x1 - a) ** 2) ** 0.5 + b
                y2 = b - (r ** 2 - (x1 - a) ** 2) ** 0.5

                realpath.append([x1, y1])
                realpath2.insert(1, [x1, y2])
            realpath.extend(realpath2)
        elif type == 'rectangle':
            x1 = baseX
            y1 = baseY
            x2 = baseX + label_obj.get('width') * real_width
            y2 = baseY + label_obj.get('height') * real_width
            realpath = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]

        else:
            continue

        rlt.get('annotations').append({
            'id': label.slide_label_id,
            'category_id': my_enum.enumLabelType.get(type),
            'color': color,
            'creator': label.creator.real_name,
            'segmentation': realpath
        })

    sss = simplejson.dumps(rlt).encode()
    print('写入文件')

    # 2023-03-6、之前小切片的生成都是data.json文件，改为切片文件名+'.json'
    slide_labels_filename = os.path.basename(slide_path).replace('.tiff','.json')
    # 写入文件,这个数据都保存到切片同目录下json文件夹下
    data_file_path = os.path.join(dir_path, 'json',slide_labels_filename)
    #如果json目录不存在就创建该目录
    create_dir_path(os.path.dirname(data_file_path))
    if os.path.exists(data_file_path):
        os.remove(data_file_path)

    f = open(data_file_path, 'wb')
    f.write(sss)
    f.close()

#2023-03-06，修改使用father_slide_create_json_file 的json文件生成xml文件的路径和文件名
def father_slide_create_xml_file(slide_path,is_father=False):
    '''依赖于create_json_file生成的data.json数据'''
    dir_path = os.path.dirname(slide_path)
    #拼接出json文件名
    slide_labels_filename = os.path.basename(slide_path).replace('.tiff','.json')
    #拿到切片对应的.json文件，生成对应的xml文件
    dataFilePath = os.path.join(dir_path, "json",slide_labels_filename)
    if not os.path.exists(dataFilePath):
        raise MyError('切片下没有标注')
    f = open(dataFilePath, 'r')
    labels = simplejson.load(f)

    category_set = set()
    cmap = ["#00AA00", "#FFFF33", "#FF0000", "#0000CC", "#FF00FF", "#BB5500", "#007799"]

    color_set = set()
    # 颜色对照PartOfGroup
    color2group = {
        "#ffff00": "_1",  # 黄色
        "#00b050": "_2",  # 绿色
        "#ff0000": "_3",  # 红色
        '#c00000': "_4",  # 暗红色
        '#ffc000': "_5",  # 琥珀色
        '#92d050': "_6",  # 黄绿色
        '#00b0f0': "_7",  # 深天蓝
        '#0070c0': "_8",  # 品蓝
        '#002060': "_9",  # 蓝宝石色
        '#7030a0': "_10",  # 紫色
    }
    doc = Document()
    '''
    <ASAP_Annotations>
    '''
    ASAP_Annotations = doc.createElement('ASAP_Annotations')
    doc.appendChild(ASAP_Annotations)
    '''
    <Annotations>
    '''
    Annotations = doc.createElement('Annotations')

    for each_anno in labels['annotations']:
        anno = doc.createElement('Annotation')
        anno.setAttribute('Name', str(each_anno['id']))
        anno.setAttribute('Type', "Polygon")
        if str(each_anno['color']) in color2group:
            part_group = color2group[str(each_anno['color'])]
        else:
            part_group = "_11"
        anno.setAttribute('PartOfGroup', part_group)
        category_set.add(each_anno['category_id'])
        anno.setAttribute('Color', str(each_anno['color']))
        anno.setAttribute('creator', str(each_anno['creator']))
        color_set.add(str(each_anno['color']))
        Annotations.appendChild(anno)
        coords = doc.createElement('Coordinates')
        anno.appendChild(coords)
        for id, each_coord in enumerate(each_anno['segmentation']):
            coord = doc.createElement('Coordinate')
            coord.setAttribute('Order', str(id))
            coord.setAttribute('X', str(each_coord[0]))
            coord.setAttribute('Y', str(each_coord[1]))
            coords.appendChild(coord)
    ASAP_Annotations.appendChild(Annotations)
    '''
    <AnnotationGroups>
    '''
    AnnotationGroups = doc.createElement('AnnotationGroups')

    for each_group in color_set:
        anno_group = doc.createElement('Group')
        if str(each_anno['color']) in color2group:
            part_group = color2group[str(each_anno['color'])]
        else:
            part_group = "_11"
        anno_group.setAttribute('Name', part_group)
        anno_group.setAttribute('PartOfGroup', "None")
        anno_group.setAttribute('Color', each_group)
        attr = doc.createElement('Attributes')
        anno_group.appendChild(attr)
        AnnotationGroups.appendChild(anno_group)
    ASAP_Annotations.appendChild(AnnotationGroups)

    filename = os.path.basename(slide_path).replace(".tiff", '.xml')
    xml_file_path = os.path.join(dir_path,'xml',filename)
    #小切片请求时，xml文件存放路径=/home/thearay/DataSet/web-upload/13-userID/2023-03-03/TestB202104700/output_1/xml
    if is_father:
        #大切片请求时，xml存放路径=/home/thearay/DataSet/web-upload/13-userID/2023-03-03/TestB202104700/all_xml
        xml_file_path = os.path.join(os.path.dirname(dir_path),'all_xml',filename)
    # 如果xml目录不存在就创建该目录
    create_dir_path(os.path.dirname(xml_file_path))
    if os.path.exists(xml_file_path):
        os.remove(xml_file_path)
    with open(xml_file_path, 'w') as f:
        doc.writexml(f, indent='\t', newl='\n', addindent='\t', encoding='utf-8')
    f.close()


def create_json_file(slide_id, slide_path, max_zoom):
    if not slide_path:
        #拿到的是切片文件的绝对路径
        raise MyError('切片路径为空')

    dir_path = os.path.dirname(slide_path)

    if not os.path.exists(dir_path):
        #dir_path是切片文件的目录绝对路径
        raise MyError('文件夹不存在:%s' % dir_path)
    #2023-02-06新增，确定检验数据
    #try:
    #    slide_id = slide_id.pk
    #except Exception as e:
    #    print(str(e),__file__)

    slide = TSlide.objects.get(slide_id=slide_id)
    #2023-03-06过滤掉是AI打的标注信息,不对AI的标注生成.json 文件，也不能生成.xml文件
    label_list = TSlideLabel.objects.filter(slide_id=slide_id).filter(~Q(creator=32))
    print(len(label_list),'标签数')
    print(slide_path,'操作的文件')

    if not label_list:
        
        raise MyError('切片下没有标注')

    real_width = slide.real_width
    if not real_width:
        raise MyError('此切片文件缺少real_width数据')

    # 记录slide_path
    slide.slide_path = slide_path
    slide.save()

    create_time = slide.create_time
    rlt = {
        'id': slide.slide_id,
        'width': real_width,
        'height': slide.real_height,
        'file_name': slide.slide_file_name,
        'data_captured': datetime.datetime.strftime(create_time, '%Y-%m-%d %H:%M:%S') if create_time else '',
        'annotations': []
    }

    for label in label_list:
        label_info = label.label_info
        if not label_info: continue

        label_obj = simplejson.loads(label_info)
        baseX = label_obj.get('x') * real_width
        baseY = label_obj.get('y') * real_width
        color = label_obj.get('color')
        type = label_obj.get('type')

        if type == 'pen':
            if 'data' not in label_obj:
                continue
            path = label_obj.get('data').get('path')
            real_zoom = label_obj.get('realZoom')

            realpath = []
            if not path: continue
            for p in path:
                realpath.append([p['x'] * max_zoom / real_zoom + baseX, p['y'] * max_zoom / real_zoom + baseY])

        elif type == 'circle':

            r = label_obj.get('width') * real_width / 2
            a = baseX + r
            b = baseY + r

            realpath = []
            realpath2 = []
            realpath.append([baseX, b])
            realpath2.append([a + r, b])
            for i in [0.25 / 8, 0.5 / 8, 0.75 / 8, 1.0 / 8, 2.0 / 8, 3.0 / 8, 4.0 / 8, 5.0 / 8, 6.0 / 8, 7.0 / 8,
                      7.25 / 8, 7.5 / 8, 7.75 / 8]:
                x1 = baseX + i * 2 * r
                y1 = (r ** 2 - (x1 - a) ** 2) ** 0.5 + b
                y2 = b - (r ** 2 - (x1 - a) ** 2) ** 0.5

                realpath.append([x1, y1])
                realpath2.insert(1, [x1, y2])
            realpath.extend(realpath2)
        elif type == 'rectangle':
            x1 = baseX
            y1 = baseY
            x2 = baseX + label_obj.get('width') * real_width
            y2 = baseY + label_obj.get('height') * real_width
            realpath = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]

        else:
            continue

        rlt.get('annotations').append({
            'id': label.slide_label_id,
            'category_id': my_enum.enumLabelType.get(type),
            'color': color,
            'creator': label.creator.real_name,
            'segmentation': realpath
        })

    sss = simplejson.dumps(rlt).encode()
    #print(sss,'写入文件的数据')
    # 写入文件
    data_file_path = os.path.join(dir_path, 'data.json')
    if os.path.exists(data_file_path):
        os.remove(data_file_path)

    f = open(data_file_path, 'wb')
    f.write(sss)
    f.close()


def create_xml_file(slide_path):
    dir_path = os.path.dirname(slide_path)
    dataFilePath = os.path.join(dir_path, "data.json")
    if not os.path.exists(dataFilePath):
        raise MyError('切片下没有标注')
    f = open(dataFilePath, 'r')
    labels = simplejson.load(f)

    category_set = set()
    cmap = ["#00AA00", "#FFFF33", "#FF0000", "#0000CC", "#FF00FF", "#BB5500", "#007799"]

    color_set = set()
    # 颜色对照PartOfGroup
    color2group = {
        "#ffff00": "_1",  # 黄色
        "#00b050": "_2",  # 绿色
        "#ff0000": "_3",  # 红色
        '#c00000': "_4",  # 暗红色
        '#ffc000': "_5",  # 琥珀色
        '#92d050': "_6",  # 黄绿色
        '#00b0f0': "_7",  # 深天蓝
        '#0070c0': "_8",  # 品蓝
        '#002060': "_9",  # 蓝宝石色
        '#7030a0': "_10",  # 紫色
    }
    doc = Document()
    '''
    <ASAP_Annotations>
    '''
    ASAP_Annotations = doc.createElement('ASAP_Annotations')
    doc.appendChild(ASAP_Annotations)
    '''
    <Annotations>
    '''
    Annotations = doc.createElement('Annotations')

    for each_anno in labels['annotations']:
        anno = doc.createElement('Annotation')
        anno.setAttribute('Name', str(each_anno['id']))
        anno.setAttribute('Type', "Polygon")
        if str(each_anno['color']) in color2group:
            part_group = color2group[str(each_anno['color'])]
        else:
            part_group = "_11"
        anno.setAttribute('PartOfGroup', part_group)
        category_set.add(each_anno['category_id'])
        anno.setAttribute('Color', str(each_anno['color']))
        anno.setAttribute('creator', str(each_anno['creator']))
        color_set.add(str(each_anno['color']))
        Annotations.appendChild(anno)
        coords = doc.createElement('Coordinates')
        anno.appendChild(coords)
        for id, each_coord in enumerate(each_anno['segmentation']):
            coord = doc.createElement('Coordinate')
            coord.setAttribute('Order', str(id))
            coord.setAttribute('X', str(each_coord[0]))
            coord.setAttribute('Y', str(each_coord[1]))
            coords.appendChild(coord)
    ASAP_Annotations.appendChild(Annotations)
    '''
    <AnnotationGroups>
    '''
    AnnotationGroups = doc.createElement('AnnotationGroups')

    for each_group in color_set:
        anno_group = doc.createElement('Group')
        if str(each_anno['color']) in color2group:
            part_group = color2group[str(each_anno['color'])]
        else:
            part_group = "_11"
        anno_group.setAttribute('Name', part_group)
        anno_group.setAttribute('PartOfGroup', "None")
        anno_group.setAttribute('Color', each_group)
        attr = doc.createElement('Attributes')
        anno_group.appendChild(attr)
        AnnotationGroups.appendChild(anno_group)
    ASAP_Annotations.appendChild(AnnotationGroups)

    filename = os.path.basename(slide_path).replace(".tiff", '.xml')
    xml_file_path = os.path.join(dir_path, filename)
    if os.path.exists(xml_file_path):
        os.remove(xml_file_path)
    with open(xml_file_path, 'w') as f:
        doc.writexml(f, indent='\t', newl='\n', addindent='\t', encoding='utf-8')
    f.close()

def previewImage(filename, centers, patch, iou):
    url = 'http://127.0.0.1:8813/getFilesByNames/'
    # url = 'http://192.168.3.109/getFilesByNames/'
    result = requests.post(url, data={"filterFileNames": filename}, timeout=50)
    tem_rlt = simplejson.loads(result.content)
    path = tem_rlt[filename][0]["path"]
    labels = get_labels(path, None, centers, patch, iou)
    return labels, path


class cutImageThread(threading.Thread):
    def __init__(self, tiff_path, bmp_path, output, labels, root_path, count, slide_id,cache_name=None):
        threading.Thread.__init__(self)
        self.tiff_path = tiff_path
        self.bmp_path = bmp_path
        self.output = output
        self.labels = labels
        self.root_path = root_path
        self.count = count
        self.slide_id = slide_id
        self.cache_name =cache_name #2023-02-21新增cache_name参数,将文件切割情况保存到cache中，这个是key

    def run(self):
        '''2023-02-21(新增cache参数)-各种需要的参数'''
        all_cut_number = len(self.labels)#总切割文件数
        has_cut_number = 0 #已经切割文件数
        dic = {'all_cut_number':all_cut_number,'has_cut_number':has_cut_number,'complete':0,'cut_file':[]} #complete切割是否完成

        #每循环一次，就生成一张切割文件和对应的缩略图
        for label in self.labels:
            l = ",".join('%s' % i for i in label)
            tiff_path = str(self.tiff_path)
            bmp_path = str(self.bmp_path)
            output = str(self.output)
            number = str(self.labels.index(label)+1)
            # command = settings.python_env_path + os.path.dirname(__file__) + "/cut_img.py " + \
            #           "-tiff_path=\"" + tiff_path + "\" -bmp_path=\"" + bmp_path + "\" -o=\"" + output + \
            #           "\" -label=\"" + l + "\" -count=" + str(self.count) + " -number=" + number
            # os.system(command)
            #生成切割文件，生成缩略图
            cut_file_dic = cut(tiff_path, bmp_path, output, label, str(self.count), number)
            save_cut_slide_label(self.slide_id, self.tiff_path, self.bmp_path, label, self.count, number, output)
            xml_path = os.path.join(self.root_path, 'data.xml')
            if os.path.exists(xml_path):
                cut_xml(label, xml_path, self.tiff_path, self.bmp_path, self.count, number, output)

            '''2023-02-21(新增cache参数)--将大tiff文件切割情况写到cache中'''
            if self.cache_name: #是web_uplaod_file视图发起的请求才会传递cache_name
                has_cut_number += 1 #文件切割完成加1
                dic['has_cut_number']=has_cut_number #切割好的文件数量
                cut_file_name = cut_file_dic.get('filename')#切割后，小文件的文件名
                dic['cut_file'].append(cut_file_name) #切割好的文件名
                if all_cut_number == has_cut_number:
                    dic['complete']=1
                print(cache.get(self.cache_name),'缓存到cache中的数据')
                print(self.cache_name,'cache的key')
                cache.set(self.cache_name,json.dumps(dic))
                print(f'文件切割完成次数，{has_cut_number}；总切割数量={all_cut_number}')
                '''(新增cache参数结束)'''
            print('切割文件返回的数据',cut_file_dic)
            '''2023-2-27新增：tiff文件进行切割时，切割的小文件也记录到数据库中'''
            from public import get_imagesize
            cut_file_path = cut_file_dic.get('path') #切割的小文件存放位置
            print(cut_file_path,'小切割文件存放位置')
            cut_file_name = cut_file_dic.get('filename') #切割的小文件的文件名，在切割时就已经保证文件名是唯一的了。
            width,height = get_imagesize.get(cut_file_path)#获取切割完成的小文件的宽度和高度
            father_id = self.slide_id #小切片的父切片的id
            print(father_id,'父切割文件的id')
            TSlide.objects.create(slide_path=cut_file_path, slide_file_name=cut_file_name,
                                  status=0, real_width=width, real_height=height,father_slide_id=father_id)
        saveCutImageJson(tiff_path, output, self.labels, self.count)
        print("cut done")
        # cut(self.tiff_path, self.bmp_path, self.output, label)


class ImportXmlThread(threading.Thread):
    def __init__(self, filename, url, path):
        threading.Thread.__init__(self)
        self.filename = filename
        self.url = url
        self.path = path

    def run(self):
        down_url = "http://192.168.3.103:5001/Diagnose"
        # nfs_path = "/app/store/"
        nfs_path = "/mnt/"
        data = {"path": nfs_path + self.url}
        res = requests.post(down_url, data=data)
        # data = simplejson.loads(res.text)
        # atrophy = data["atropy"]
        # contour = data["contour"]
        # s = str(data)
        # f = open('dict.txt', 'w')
        # f.writelines(s)
        # f.close()
        # TSlideLabel.objects.filter(creator=32, slide_file_name=self.filename)
        # json2data(self.filename, data)
        # slide_obj = TSlide.objects.get(slide_file_name=self.filename)
        # slide_obj.atrophy = atrophy["class"]
        # slide_obj.save()
        print("request.done")


def save_cut_slide_label(slide_id, tiff_path, bmp_path, label, count, number, out_path):
    slide_info = TSlide.objects.get(slide_id=slide_id)
    label_list = TSlideLabel.objects.filter(slide_id=slide_id)
    if not label_list:
        return True

    real_width = slide_info.real_width
    if not real_width:
        return True
    slide = opsl.OpenSlide(tiff_path)  # W,H
    img = cv2.imread(bmp_path)  # H, W
    slide_w, slide_h = slide.dimensions
    img_h, img_w = img.shape[:2]
    downsample = min(int(slide_h / img_h), int(slide_w / img_w))
    coords = downsample * np.array(label)
    x1, y1, x2, y2 = coords
    height = abs(x2 - x1)
    width = abs(y2 - y1)
    coords = np.array([coords[1], coords[0],
                       coords[3], coords[2]])

    slide_name = tiff_path.split('/')[-1].replace('.tiff', '')
    slide_file_name = slide_name + '_' + count + '_' + number + '.tiff'

    slides = TSlide.objects.filter(slide_file_name=slide_file_name)
    if not slides:
        slide = TSlide.objects.create(slide_file_name=slide_file_name, real_width=width, real_height=height, status=0)
    else:
        slide = slides[0]

    slide_url = tiff_path.replace("/home/thearay/DataSet", "")
    url = settings.IMAGEPARSER_URL + 'GetImageObj/?fileName=http://127.0.0.1:7100' + slide_url
    r = requests.get(url, timeout=5)
    slide_data = simplejson.loads(r.content)
    max_zoom = slide_data.get('maxZoom')

    for l in label_list:
        label_info = l.label_info
        if not label_info: continue
        label_obj = simplejson.loads(label_info)
        baseX = label_obj.get('x') * real_width
        baseY = label_obj.get('y') * real_width
        color = label_obj.get('color')
        type = label_obj.get('type')

        cut_slide_url = os.path.join(out_path, slide_file_name).replace("/home/thearay/DataSet", "")
        cut_url = settings.IMAGEPARSER_URL + 'GetImageObj/?fileName=http://127.0.0.1:7100' + cut_slide_url
        cut_r = requests.get(cut_url, timeout=5)
        cut_slideData = simplejson.loads(cut_r.content)
        cut_maxZoom = cut_slideData.get('maxZoom')
        rlt = {}

        if type == "pen":
            if 'data' not in label_obj: continue
            path = label_obj.get('data').get('path')
            realZoom = label_obj.get('realZoom')

            realpath = []
            if not path: continue
            for p in path:
                realpath.append([p['x'] * max_zoom / realZoom + baseX, p['y'] * max_zoom / realZoom + baseY])

            realpath = np.array(realpath)
            if isvaild(coords, realpath):
                realpath -= coords[:2]
                cut_baseX = baseX - coords[0]
                cut_baseY = baseY - coords[1]
                x = cut_baseX / width
                y = cut_baseY / width
                cut_width = label_obj.get('width') * real_width / width
                cut_height = label_obj.get('height') * real_width / width

                real = realZoom * cut_maxZoom / max_zoom
                data = {
                    "path": path,
                    "minX": label_obj.get('data').get('minX'),
                    "minY": label_obj.get('data').get('minY'),
                    "maxX": label_obj.get('data').get('maxX'),
                    "maxY": label_obj.get('data').get('maxY'),
                }
                rlt = {
                    "spriteId": "sprite" + str(random.random())[2:],
                    "type": type,
                    "color": color,
                    "x": x,
                    "y": y,
                    "width": cut_width,
                    "height": cut_height,
                    "data": data,
                    "realZoom": real
                }

        elif type == "fixedRectangle":
            x1 = baseX
            y1 = baseY
            x2 = baseX + label_obj.get('width') * real_width
            y2 = baseY + label_obj.get('height') * real_width
            if not (x1 > coords[0] and y1 > coords[1] and x2 < coords[2] and y2 < coords[3]):
                continue
            cut_x = (baseX - coords[0]) / width
            cut_y = (baseY - coords[1]) / width
            cut_width = label_obj.get('width') * real_width / width
            cut_height = label_obj.get('height') * real_width / width
            cut_real = label_obj.get('realZoom') * cut_maxZoom / max_zoom
            rlt = {
                "spriteId": "sprite" + str(random.random())[2:],
                "type": type,
                "color": color,
                "x": cut_x,
                "y": cut_y,
                "width": cut_width,
                "height": cut_height,
                "realZoom": cut_real
            }
        if not rlt:
            continue
        label_info = simplejson.dumps(rlt)
        creator = l.creator

        '''2023/1/13新增：l.is_scope=1时，需要在创建slide_label时，加上is_scope'''
        is_scope = l.is_scope
        is_type = l.type
        '''结束'''

        slide_label = TSlideLabel.objects.create(slide_id=slide.slide_id, label_info=label_info,
                                                 slide_file_name=slide_file_name, creator=creator,is_scope=is_scope,type=is_type)
        slide.status = 1
        slide.save()



def saveCutImageJson(tiff_path, output, labels, count):
    rlt = {
        "tiff_path": tiff_path,
        "count": count,
        "labels": labels,
    }

    sss = simplejson.dumps(rlt, ensure_ascii=False).encode()

    # 写入文件
    dataFilePath = os.path.join(output, 'preview.json')
    if os.path.exists(dataFilePath):
        os.remove(dataFilePath)
    f = io.open(dataFilePath, 'wb')
    f.write(sss)
    f.close()

    
def change_color(value):
    if isinstance(value, tuple):
        string = '#'
        for i in value:
            string += str(hex(i))[-2:].replace('x', '0').upper()
        return string
    elif isinstance(value, str):
        a1 = int(value[1:3], 16)
        a2 = int(value[3:5], 16)
        a3 = int(value[5:7], 16)
        tup = (a1, a2, a3)
        return tup


def json2data(filename, data):
    url = 'http://127.0.0.1:8813/getFilesByNames/'
    result = requests.post(url, data={"filterFileNames": filename}, timeout=50)
    tem_rlt = simplejson.loads(result.content)
    img_path = tem_rlt[filename][0]["path"]
    slide_url = tem_rlt[filename][0]["url"]


    url = "http://127.0.0.1:8814/" + "GetImageObj/?fileName=http://127.0.0.1:7100/" + slide_url
    req = requests.get(url, timeout=5)
    slide_data = simplejson.loads(req.content)
    height = slide_data.get('maxHeight')
    width = slide_data.get('maxWidth')
    max_zoom = slide_data.get('maxZoom')

    slide_objs = TSlide.objects.filter(slide_file_name=filename)
    if slide_objs:
        slide_obj = slide_objs[0]
    else:
        slide_obj = TSlide.objects.create(slide_file_name=filename, real_width=width, real_height=height, status=0)

    TSlideLabel.objects.filter(slide=slide_obj, creator__account_id=32).delete()

    print("import sql")
    str_name = ['contour', 'cell', 'gland_contour']
    number_x = 0
    number_y = 0
    label_list = []
    for i in str_name:
        if i in data:
            number_x += 1
            for d in data[i]:
                number_y += 1
                color = d['Color']
                c_type = cell_type[color]
                cood = d['Location']
                x_list = []
                y_list = []
                for c in cood:
                    X = c.get('X')
                    Y = c.get('Y')
                    x_list.append(float(X))
                    y_list.append(float(Y))
                baseX = min(x_list)
                baseY = min(y_list)
                maxX = max(x_list)
                maxY = max(y_list)
                x = baseX / width
                y = baseY / width
                coord_width = (maxX - baseX) / width
                coord_height = (maxY - baseY) / width
                path = []
                for n in range(len(x_list)):
                    path.append({'x': (x_list[n] - baseX),
                                 'y': (y_list[n] - baseY)})
                minX = 0
                minY = 0
                maxX = (maxX - baseX)
                maxY = (maxY - baseY)
                dataXY = {
                    "path": path,
                    "minX": minX,
                    "minY": minY,
                    "maxX": maxX,
                    "maxY": maxY,
                }
                rlt = {
                    "spriteId": "sprite" + str(random.random())[2:],
                    "type": "pen",
                    "color": color,
                    "data": dataXY,
                    "x": x,
                    "y": y,
                    "width": coord_width,
                    "height": coord_height,
                    "realZoom": max_zoom,
                }
                label_info = simplejson.dumps(rlt)

                creator = TAccount.objects.get(account_id=32)
                slide_label = TSlideLabel(slide=slide_obj, label_info=label_info,
                                                         slide_file_name=filename, creator=creator, is_scope=0, type=c_type)
                label_list.append(slide_label)
    print("parse ok")
    print(len(label_list),'要写入数据库的数据量')
    '2023-1-30（修改）：上传数据报：2006, MySQL server has gone away'
    all_len = len(label_list)
    count = 5000  # 将原始列表，分割成5000长度的列表
    number = all_len // count  # 批量写入数据库的次数
    op_count = 0 #多少条数据写到数据库中
    if number == 0:
        #循环将数据写入数据库的次数
        number = 1
    else:
        if all_len % count:
            # 取余不为0，就是不能整除，需要加1
            number += 1
    print(number, '循环操作的数据库次数')
    for i in range(number):
        if i == 0:
            op_list = label_list[:count]
        else:
            op_list = label_list[i * count:count * (i + 1)]
        op_count+=len(op_list)
        #将数据批量写入数据库中
        TSlideLabel.objects.bulk_create(op_list)
        '2023-1-30（修改结束）'
    if op_count==len(label_list):
        print('操作的数据量等于未切割时的数据量',f'数据量={op_count}')


    print("import sql done")
    cell_img = TSlideImage.objects.filter(slide=slide_obj, type=4)
    if cell_img:
        for c in cell_img:
            old_path = os.path.join('/home/thearay/gastritis/slideapi-copy/api/', c.path)
            if os.path.exists(old_path):
                os.remove(old_path)
    cell_img.delete()
    cell_center = data["cell_center"]
    cell_key = ["goblet", "yancell", "neutrophil"]
    slide = opsl.OpenSlide(img_path)
    base_path = "upload/center/"
    img_list = []
    for i in cell_key:
        if i not in cell_center:
            continue
        c = cell_center[i]
        for n in c:
            center = (int(float(n['X'])), int(float(n['Y'])))
            image = slide.read_region(center, 0, (200, 200))
            name = str(uuid.uuid4()) + '.png'
            thum_path = base_path + name
            image.save(thum_path)
            note = str(float(n['X'])/width) + "," + str(float(n['Y'])/width)
            img_model = TSlideImage(slide=slide_obj, path=thum_path, type=4, note=note)
            img_list.append(img_model)

    TSlideImage.objects.bulk_create(img_list)

    slide_obj.is_diagnostic = 1
    slide_obj.save()
    # print(number_x, number_y)
    print("import.done")

def create_fixed_rectangle_xml_file(slide_name, slide_path):
    if not slide_path:
        raise MyError('切片路径为空')

    dir_path = os.path.dirname(slide_path)
    # 检查文件夹是否存在
    if not os.path.exists(dir_path):
        raise MyError('文件夹不存在:%s' % dir_path)

    # 生成文件
    slide_info = TSlide.objects.get(slide_file_name=slide_name)
    label_list = TSlideLabel.objects.filter(slide_id=slide_info.slide_id, is_scope=1)

    if not label_list:
        raise MyError('切片下没有固定')

    real_width = slide_info.real_width
    if not real_width:
        raise MyError('此切片文件缺少real_width数据')

    slide_info.slide_path = slide_path
    slide_info.save()

    create_time = slide_info.create_time
    rlt = {
        'id': slide_info.slide_id,
        'width': real_width,
        'height': slide_info.real_height,
        'file_name': slide_info.slide_file_name,
        'date_captured': datetime.datetime.strftime(create_time, '%Y-%m-%d %H:%M:%S') if create_time else '',
        'annotations': []
    }

    for label in label_list:
        label_info = label.label_info
        if not label_info: continue

        label_obj = simplejson.loads(label_info)
        baseX = label_obj.get('x') * real_width
        baseY = label_obj.get('y') * real_width
        color = label_obj.get('color')
        type = label_obj.get('type')

        if type != 'fixedRectangle':
            continue

        x1 = baseX
        y1 = baseY
        x2 = baseX + label_obj.get('width') * real_width
        y2 = baseY + label_obj.get('height') * real_width
        realpath = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]

        rlt.get('annotations').append({
            'id': label.slide_label_id,
            'category_id': my_enum.enumLabelType.get(type),
            'color': color,
            'creator': label.creator,
            'segmentation': realpath
        })

    labels = rlt

    category_set = set()
    cmap = ["#00AA00", "#FFFF33", "#FF0000", "#0000CC", "#FF00FF", "#BB5500", "#007799"]

    color_set = set()
    # 颜色对照PartOfGroup
    color2group = {
        "#ffff00": "_1",  # 黄色
        "#00b050": "_2",  # 绿色
        "#ff0000": "_3",  # 红色
        '#c00000': "_4",  # 暗红色
        '#ffc000': "_5",  # 琥珀色
        '#92d050': "_6",  # 黄绿色
        '#00b0f0': "_7",  # 深天蓝
        '#0070c0': "_8",  # 品蓝
        '#002060': "_9",  # 蓝宝石色
        '#7030a0': "_10",  # 紫色
    }
    doc = Document()
    '''
    <ASAP_Annotations>
    '''
    ASAP_Annotations = doc.createElement('ASAP_Annotations')
    doc.appendChild(ASAP_Annotations)
    '''
    <Annotations>
    '''
    Annotations = doc.createElement('Annotations')

    for each_anno in labels['annotations']:
        anno = doc.createElement('Annotation')
        anno.setAttribute('Name', str(each_anno['id']))
        anno.setAttribute('Type', "Polygon")
        anno.setAttribute('PartOfGroup', color2group[str(each_anno['color'])])
        category_set.add(each_anno['category_id'])
        anno.setAttribute('Color', str(each_anno['color']))
        anno.setAttribute('creator', str(each_anno['creator']))
        color_set.add(str(each_anno['color']))
        Annotations.appendChild(anno)
        coords = doc.createElement('Coordinates')
        anno.appendChild(coords)
        for id, each_coord in enumerate(each_anno['segmentation']):
            coord = doc.createElement('Coordinate')
            coord.setAttribute('Order', str(id))
            coord.setAttribute('X', str(each_coord[0]))
            coord.setAttribute('Y', str(each_coord[1]))
            coords.appendChild(coord)
    ASAP_Annotations.appendChild(Annotations)
    '''
    <AnnotationGroups>
    '''
    AnnotationGroups = doc.createElement('AnnotationGroups')

    for each_group in color_set:
        anno_group = doc.createElement('Group')
        anno_group.setAttribute('Name', color2group[each_group])
        anno_group.setAttribute('PartOfGroup', "None")
        anno_group.setAttribute('Color', each_group)
        attr = doc.createElement('Attributes')
        anno_group.appendChild(attr)
        AnnotationGroups.appendChild(anno_group)
    ASAP_Annotations.appendChild(AnnotationGroups)
    f = io.StringIO()
    doc.writexml(f, indent='\t', newl='\n', addindent='\t', encoding='utf-8')

    return f

def del_file(path_data):
    for i in os.listdir(path_data):
        file_data = path_data + "\\" + i
        if os.path.isfile(file_data) == True:
            os.remove(file_data)
        else:
            del_file(file_data)
