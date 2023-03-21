from django.shortcuts import render

# Create your views here.
from django.http import HttpResponse
from dataCtrl.models import TSlideLabel, TSlide
from public import global_common as gcm
import datetime
import simplejson

enumLabelType = {
    'pen': 1,
    'circle': 2,
    'rectangle': 3,
    'brokenLine': 4,
    'line': 5
}

def get_slide_label_data(request):
    if request.method == 'POST':
        slide_file_name = request.POST.get('slide_file_name')
        slide_info = TSlide.objects.get(slide_file_name=slide_file_name)
        label_list = TSlideLabel.objects.get(slide_file_name=slide_file_name)

        real_width = slide_info.get('real_width')
        if not real_width:
            return gcm.failed('此切片文件缺少real_width数据')

        create_time = slide_info.get('create_time')
        rlt = {
            'id': slide_info['slide_id'],
            'width': real_width,
            'height': slide_info.get('real_height'),
            'file_name': slide_file_name,
            'date_captured': datetime.datetime.strftime(create_time, '%Y-%m-%d %H:%M:%S') if create_time else '',
            'annotations': []
        }

        for label in label_list:
            label_info = label.get('label_info')
            if not label_info: continue

            labelObj = simplejson.loads(label_info)
            baseX = labelObj.get('x') * real_width
            baseY = labelObj.get('y') * real_width

            path = labelObj.get('data').get('path')

            realpath = []
            for p in path:
                realpath.append([p['x'] + baseX, p['y'] + baseY])

            labelType = labelObj.get('type')
            rlt.get('annotations').append({
                'id': label.get('slide_label_id'),
                'category_id': enumLabelType.get(labelType),
                'segmentation': realpath
            })

        sss = simplejson.dumps(rlt)
        return gcm.download(sss, "%s.json" % slide_file_name)