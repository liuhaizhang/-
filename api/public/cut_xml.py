import os
import argparse
import pyvips
import cv2
import openslide as opsl
import numpy as np
from xml.dom.minidom import Document
import xml.dom.minidom as minidom
from .np2vips import numpy2vips

def cut_xml(coords, xml_path, tiff_path, bmp_path, count, number, output_path='./'):
    '''
    :param coords: [x1, y1, x2, y2]
    :param xml_path: e.g. ./test/xml
    :return: None
    '''
    coords = np.array(coords)
    assert len(coords.shape) == 1 and coords.shape[0] == 4, 'COORDS SHAPE ERROR!'
    slide = opsl.OpenSlide(tiff_path)  # W,H
    img = cv2.imread(bmp_path)  # H, W
    slide_w, slide_h = slide.dimensions
    img_h, img_w = img.shape[:2]
    downsample = min(int(slide_h / img_h), int(slide_w / img_w))
    coords = downsample * np.array(coords)
    x1, y1, x2, y2 = coords
    slide_name = tiff_path.split('/')[-1].replace('.tiff', '')
    xml_name = slide_name + "_" + count + "_{}.xml".format(number)
    xml = minidom.parse(xml_path)
    root = xml.documentElement

    xml_info = xml_parser(root, coords)
    gen_xml(xml_info, output_path, xml_name)


def xml_parser(root, coords):  #读取解析xml
    coords = np.array([coords[1], coords[0], coords[3], coords[2]])
    annos_dict_list = []
    annos = root.getElementsByTagName('Annotation')

    for i in range(len(annos)):
        anno_dict = {}
        anno_dict['Name'] = annos[i].getAttribute('Name')
        anno_dict['Type'] = annos[i].getAttribute('Type')
        anno_dict['PartOfGroup'] = annos[i].getAttribute('PartOfGroup')
        anno_dict['Color'] = annos[i].getAttribute('Color')
        anno_dict['creator'] = annos[i].getAttribute('creator')
        labels = []
        coordinates = annos[i].getElementsByTagName('Coordinates')[0].getElementsByTagName('Coordinate') # X->W, Y->H
        for each_coord in coordinates:
            labels.append([float(each_coord.getAttribute('X')), float(each_coord.getAttribute('Y'))])

        # print(anno_dict, len(coordinates))
        labels = np.array(labels)
        if isvaild(coords, labels):
            labels -= coords[:2]
            anno_dict['labels'] = labels
            annos_dict_list.append(anno_dict)
    return annos_dict_list


def gen_xml(annos_dict_list, output_path, xml_name): #生成新的xml
    doc = Document()
    ASAP_Annotations = doc.createElement('ASAP_Annotations')
    doc.appendChild(ASAP_Annotations)
    Annotations = doc.createElement('Annotations')
    category_set = {}

    for each_anno in annos_dict_list:
        anno = doc.createElement('Annotation')
        anno.setAttribute('Name', each_anno['Name'])
        anno.setAttribute('Type', each_anno['Type'])
        anno.setAttribute('PartOfGroup', each_anno['PartOfGroup'])
        category_set[each_anno['PartOfGroup']] = each_anno['Color']
        anno.setAttribute('Color', each_anno['Color'])
        anno.setAttribute('creator', each_anno['creator'])
        Annotations.appendChild(anno)
        coords = doc.createElement('Coordinates')
        anno.appendChild(coords)

        for id, each_coord in enumerate(each_anno['labels']):
            coord = doc.createElement('Coordinate')
            coord.setAttribute('Order', str(id))
            coord.setAttribute('X', str(each_coord[0]))
            coord.setAttribute('Y', str(each_coord[1]))
            coords.appendChild(coord)
    ASAP_Annotations.appendChild(Annotations)

    AnnotationGroups = doc.createElement('AnnotationGroups')

    for each_group in category_set.keys():
        anno_group = doc.createElement('Group')
        anno_group.setAttribute('Name', str(each_group))
        anno_group.setAttribute('PartOfGroup', "None")
        anno_group.setAttribute('Color', category_set[each_group])
        attr = doc.createElement('Attributes')
        anno_group.appendChild(attr)
        AnnotationGroups.appendChild(anno_group)
    ASAP_Annotations.appendChild(AnnotationGroups)

    with open(os.path.join(output_path, xml_name), 'w') as f:
        doc.writexml(f, indent='\t', newl='\n', addindent='\t', encoding='utf-8')


def isvaild(coords, labels, threshold=0.1): #判断标记是否在切割的范围内
    '''
    :param coords: 切图的坐标
    :param labels: xml坐标
    :return:
    '''
    m = labels.shape[0]
    # print(labels)
    count = 0
    for each in labels:
        # print(each)
        if coords[0] <= each[0] <=coords[2] and coords[1]<= each[1] <= coords[3]:
            count +=1
    # print(m, count)
    return count >= int(m * threshold)


if __name__ == '__main__':
    xml_path = './data1.xml'
    tif_path = './2000527-1胃窦1_0.tiff'
    cut_xml([500, 3500, 3500, 8400], xml_path)



