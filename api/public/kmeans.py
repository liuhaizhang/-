import os
import numpy as np
import cv2
import math
from sklearn.cluster import KMeans


def OSTU(img_path):
    img = cv2.imread(img_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ret1, th1 = cv2.threshold(gray, 0, 255, cv2.THRESH_OTSU)
    mask = 255 - th1
    return mask


def kmeans(img_path, n_clusters, patch_size, threshold=0.25):
    mask = OSTU(img_path)
    #print(mask.shape)
    features = []
    h, w = mask.shape[:2]
    for i in range(h):
        for j in range(w):
            if mask[i][j] == 255:
                features.append([i, j])

    features = np.array(features)
    res = KMeans(n_clusters=n_clusters, random_state=0).fit(features)
    centers = res.cluster_centers_
    coords = []
    for each_centers in centers:
        x1 = max(int(each_centers[0] - patch_size // 2), 0)
        y1 = max(int(each_centers[1] - patch_size // 2), 0)
        x2 = min(int(each_centers[0] + patch_size // 2), h)
        y2 = min(int(each_centers[1] + patch_size // 2), w)
        coords.append([x1, y1, x2, y2])
    coords = nms(coords, threshold)
    coords = coords.astype(np.int)
    return coords.tolist()


def nms(coords, threshold=0.25):
    res = []
    cur = []
    visit = [False] * len(coords)
    for i, each in enumerate(coords):
        if not visit[i]:
            cur.append(each)
            visit[i] = True
            for j in range(i+1, len(coords)):
                if cal_iou(cur[0], coords[j]) >= threshold:
                    cur.append(coords[j])
                    visit[j] = True
            res.append(np.mean(cur, axis=0))
            cur = []
    return np.array(res)


def cal_iou(c1, c2):
    S_rec1 = (c1[2] - c1[0]) * (c1[3] - c1[1])
    S_rec2 = (c2[2] - c2[0]) * (c2[3] - c2[1])

    sum_area = S_rec1 + S_rec2

    left_line = max(c1[0], c2[0])
    right_line = min(c1[2], c2[2])
    top_line = max(c1[1], c2[1])
    bottom_line = min(c1[3], c2[3])

    if left_line >= right_line or top_line >= bottom_line:
        return 0.0
    else:
        intersect = (right_line - left_line) * (bottom_line - top_line)
        return (intersect / (sum_area - intersect)) * 1.0


def color(img_path, out_path, coords):
    img = cv2.imread(img_path)
    if not os.path.isdir(out_path):
        os.makedirs(out_path)
    for each_coord in coords:
        start = (int(each_coord[1]), int(each_coord[0]))
        end = (int(each_coord[3]), int(each_coord[2]))
        img = cv2.rectangle(img, start, end, (255, 0, 0), 3)
    cv2.imwrite(os.path.join(out_path, 'color.jpg'), img)

