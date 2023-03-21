import argparse
import requests
import simplejson
import xml.dom.minidom as minidom
import pymysql.cursors
import random
import datetime
import os

def get_args():
    parser = argparse.ArgumentParser(description='xml2data')
    parser.add_argument('-dir_path', '--dir_path', type=str, help='name of dir', required=True)
    return parser.parse_args()

def xml2data(xmlname, dir_path):
    connection = pymysql.connect(host='localhost', port=3306, user='root', passwd='123456', db='slide_mark',
                                 charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
    cursor = connection.cursor()
    url = 'http://127.0.0.1:8813/getFilesByNames/'
    # url = 'http://192.168.3.109:8803/getFilesByNames/'
    filename = xmlname.replace(".xml", ".tiff")

    result = requests.post(url, data={"filterFileNames": filename}, timeout=50)
    tem_rlt = simplejson.loads(result.content)
    path = tem_rlt[filename][0]["path"]
    slide_url = tem_rlt[filename][0]["url"]

    url = "http://127.0.0.1:8814/" + "GetImageObj/?fileName=http://127.0.0.1:7100/" + slide_url
    req = requests.get(url, timeout=5)
    slideData = simplejson.loads(req.content)
    height = slideData.get('maxHeight')
    width = slideData.get('maxWidth')
    maxZoom = slideData.get('maxZoom')
    distance = slideData.get('distance')

    sql = "select * from t_slide where slide_file_name = '{}'".format(filename)
    cursor.execute(sql)
    results = cursor.fetchone()
    dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not results:
        sql = "insert into t_slide(slide_file_name, real_width, real_height, status, create_time) " \
              "values('{}', {}, {}, {}, '{}')".format(filename, width, height, 0, dt)
        cursor.execute(sql)
        connection.commit()
        sql = "select * from t_slide where slide_file_name = '{}'".format(filename)
        cursor.execute(sql)
        results = cursor.fetchone()

    slide_id = results.get('slide_id')

    xml = minidom.parse(os.path.join(dir_path, xmlname))
    root = xml.documentElement
    annos = root.getElementsByTagName('Annotation')

    for i in range(len(annos)):
        color = annos[i].getAttribute('Color')
        coordinates = annos[i].getElementsByTagName('Coordinates')[0].getElementsByTagName('Coordinate')
        x_list = []
        y_list = []
        for each_coord in coordinates:
            X = each_coord.getAttribute('X')
            Y = each_coord.getAttribute('Y')
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
        data = {
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
            "data": data,
            "x": x,
            "y": y,
            "width": coord_width,
            "height": coord_height,
            "realZoom": maxZoom,
        }
        label_info = simplejson.dumps(rlt)
        sql = "insert into t_slide_label(slide_id,label_info,slide_file_name,creator,create_time,update_time)" \
              " values ({},'{}','{}', 45,'{}','{}')".format(slide_id, label_info, filename,
                                                             dt, dt)
        cursor.execute(sql)
        connection.commit()
    connection.close()
    print(xmlname +" done")


if __name__ == '__main__':
    args = get_args()
    for filename in os.listdir(args.dir_path):
        xml2data(filename, args.dir_path)