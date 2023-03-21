import os
import cv2
import openslide as opsl
import numpy as np

from .np2vips import numpy2vips
import argparse


def get_args():
    parser = argparse.ArgumentParser(description='stomach / cut_img')
    parser.add_argument('-tiff_path', '--tiff_path', type=str, default='./dataset', help='path of tiff')
    parser.add_argument('-bmp_path', '--bmp_path', type=str, default=None, help='path of bmp')
    parser.add_argument('-o', '--output', type=str, default='./output', help='path of output')
    parser.add_argument('-label', '--label', type=str, default=None, help='coords of box', required=True)
    parser.add_argument('-count', '--count', type=str, default=None, help='count of cut', required=True)
    parser.add_argument('-number', '--number', type=str, default=None, help='number 0f list', required=True)
    return parser.parse_args()


def cut(tiff_path, bmp_path, output_path, coords, count, number):
    assert os.path.isfile(tiff_path), 'TIFF PATH ERROR: {}'.format(tiff_path)
    slide_name = tiff_path.split('/')[-1].replace('.tiff', '')
    if bmp_path is None:
        bmp_path = os.path.join(tiff_path.replace(tiff_path.split('/')[-1], ''), 'preview.bmp')
    assert os.path.isfile(bmp_path), 'BMP PATH ERROR: {}'.format(bmp_path)
    assert isinstance(coords, list), 'COORDS TYPE ERROR: {}'.format(type(coords))
    assert len(coords) == 4, 'COORDS LENGTH ERROR: {}'.format(len(coords))
    if not os.path.isdir(output_path):
        os.makedirs(output_path)
    slide = opsl.OpenSlide(tiff_path)  # W,H
    img = cv2.imread(bmp_path)  # H, W
    slide_w, slide_h = slide.dimensions
    img_h, img_w = img.shape[:2]
    downsample = min(int(slide_h / img_h), int(slide_w / img_w))
    coords = downsample * np.array(coords)
    suffix_name = str(coords[0]) + "_" + str(coords[1])
    cur_slide_name = os.path.join(output_path, slide_name+'_' + count + '_' + number + '.tiff')
    print((coords[1], coords[0]), 0, (int(coords[3] - coords[1]), int(coords[2] - coords[0])))
    cur_img = np.array(slide.read_region((int(coords[1]), int(coords[0])), 0, (int(coords[3] - coords[1]), int(coords[2] - coords[0])))
                       .convert('RGB'))
    print('Save:{}'.format(cur_slide_name))
    im = numpy2vips(cur_img)
    im.tiffsave(cur_slide_name, tile=True, compression='jpeg', bigtiff=True, pyramid=True)
    thum = os.path.join(output_path, slide_name + '_' + count + '_' + number + '_thum.jpg')
    read_level = 4
    img_slide = opsl.OpenSlide(cur_slide_name)
    thumbnail = img_slide.get_thumbnail(img_slide.level_dimensions[read_level])
    thumbnail.save(thum)

    #2023-02-21，新增，将切割保存的文件名返回给调用的多线程类，记录到cache中，后端才知道哪些是切割的文件了
    #cur_slide_name = /home/thearay/DataSet/web-upload/2023-02-20/TestB202035921/output_4/TestB202035921_4_6.tiff
    ret_filename = cur_slide_name.replace('\\','/').rsplit('/')[-1]
    return {'filename':ret_filename,'path':cur_slide_name}


if __name__ == '__main__':
    args = get_args()
    label = [int(l) for l in args.label.split(',')]
    cut(args.tiff_path, args.bmp_path, args.output, label, args.count, args.number)
