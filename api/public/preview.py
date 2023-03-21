import os
import cv2
import openslide as opsl
import argparse
import json
from .kmeans import kmeans
from .kmeans import color


def get_args():
    parser = argparse.ArgumentParser(description='stomach / preview')
    parser.add_argument('-tiff_path', '--tiff_path', type=str, default='./dataset', help='path of tiff')
    parser.add_argument('-bmp_path', '--bmp_path', type=str, default=None, help='path of bmp')
    parser.add_argument('-c', '--centers', type=int, default=12, help='nums of centers')
    parser.add_argument('-p', '--patch', type=int, default=60, help='size of patch')
    parser.add_argument('-iou', '--iou', type=float, default=0.25, help='val of IOU')
    return parser.parse_args()


def get_labels(tiff_path, bmp_path, centers, patch, iou):
    assert os.path.isfile(tiff_path), 'TIFF PATH ERROR: {}'.format(tiff_path)
    slidename = tiff_path.split('/')[-1]
    root_path = tiff_path.replace(slidename, "")
    if bmp_path is None: #没有指定缩略图路径
        bmp_path = os.path.join(root_path, 'preview.bmp')
    assert os.path.isfile(bmp_path), 'BMP PATH ERROR: {}'.format(bmp_path)
    coords = kmeans(bmp_path, centers, patch, iou)  # (x1,y1,x2,y2)
    return coords


if __name__ == '__main__':
    args = get_args()
    labels = get_labels(args.tiff_path, args.bmp_path, args.centers, args.patch, args.iou)
    tiff_path = args.tiff_path
    slidename = tiff_path.split('/')[-1]
    root_path = tiff_path.replace(slidename, "")
    out_path = os.path.join(root_path)
    bmp_path = args.bmp_path
    if bmp_path is None: #没有指定缩略图路径
        bmp_path = os.path.join(root_path, 'preview.bmp')
    color(bmp_path, out_path, labels)
    print(labels)