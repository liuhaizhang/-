import argparse
import requests
import simplejson
from xml.dom.minidom import Document
import xml.dom.minidom as minidom
import pymysql.cursors
import random
import datetime


def get_args():
    parser = argparse.ArgumentParser(description='cut_xml2data')
    parser.add_argument('-xmlname', '--xmlname', type=str, help='name of xml', required=True)
    return parser.parse_args()


def cut_xml2data(xmlname):
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
    # url = "http://192.168.3.109:8804/" + "GetImageObj/?fileName=http://127.0.0.1:7100/" + slide_url
    req = requests.get(url, timeout=5)
    slideData = simplejson.loads(req.content)
    height = slideData.get('maxHeight')
    width = slideData.get('maxWidth')
    maxZoom = slideData.get('maxZoom')

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


    xml = minidom.parse(path.replace(".tiff", ".xml"))
    root = xml.documentElement
    annos = root.getElementsByTagName('Annotation')

    coords = []
    all_slide_file_name = None

    for i in range(len(annos)):
        slide_label_id = annos[i].getAttribute('Name')

        sql = "select * from t_slide_label where slide_label_id = {}".format(slide_label_id)
        cursor.execute(sql)
        results = cursor.fetchone()

        if not all_slide_file_name:
            all_slide_file_name = results.get('slide_file_name')

        label_info = simplejson.loads(results.get('label_info'))
        data = label_info.get('data')
        realZoom = label_info.get('realZoom')

        if not coords:
            all_slide_url = "/".join(slide_url.split("/")[:-2]) + "/" + all_slide_file_name
            all_url = "http://127.0.0.1:8814/" + "GetImageObj/?fileName=http://127.0.0.1:7100/" + all_slide_url
            # all_url = "http://192.168.3.109:8804/" + "GetImageObj/?fileName=http://127.0.0.1:7100/" + all_slide_url
            all_req = requests.get(all_url, timeout=5)
            all_slideData = simplejson.loads(all_req.content)
            global all_width
            all_width = all_slideData.get('maxWidth')
            global all_maxZoom
            all_maxZoom = slideData.get("maxZoom")

            baseX = label_info.get('x') * all_width
            baseY = label_info.get('y') * all_width
            x = data.get('path')[0].get('x') * all_maxZoom / realZoom + baseX
            y = data.get('path')[0].get('y') * all_maxZoom / realZoom + baseY
            x_0 = annos[i].getElementsByTagName('Coordinates')[0].getElementsByTagName('Coordinate')[0].getAttribute(
                'X')
            y_0 = annos[i].getElementsByTagName('Coordinates')[0].getElementsByTagName('Coordinate')[0].getAttribute(
                'Y')
            coords_x = abs(x - float(x_0))
            coords_y = abs(y - float(y_0))
            coords = [coords_x, coords_y]
            print(x, y, x_0, y_0, coords)

        baseX = label_info.get('x') * all_width
        baseY = label_info.get('y') * all_width
        x = (baseX - coords[0]) / width
        y = (baseY - coords[1]) / width
        cut_width = label_info.get('width') * all_width / width
        cut_height = label_info.get('height') * all_width / width
        real = realZoom * maxZoom / all_maxZoom

        rlt = {
            "spriteId": "sprite" + str(random.random())[2:],
            "type": label_info.get('type'),
            "color": label_info.get('color'),
            "data": data,
            "x": x,
            "y": y,
            "width": cut_width,
            "height": cut_height,
            "realZoom": real,
        }
        creator = results.get('creator')
        cut_label_info = simplejson.dumps(rlt)
        sql = "insert into t_slide_label(slide_id,label_info,slide_file_name,creator,create_time,update_time)" \
              " values ({},'{}','{}','{}','{}','{}')".format(slide_id, cut_label_info, filename, creator,
                                                   dt, dt)
        cursor.execute(sql)
        connection.commit()

    connection.close()


if __name__ == '__main__':
    args = get_args()
    cut_xml2data(args.xmlname)
