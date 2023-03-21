from django.urls import path
from . import views
from user import views as user_views
from ratelimit.decorators import ratelimit

urlpatterns = [
    path('listSlideLabel', views.list_slide_label, name='listSlideLabel'),
    path('listSlideLabelType', views.list_slide_label_type, name='listSlideLabelType'),
    path('upsertSlideLabel', views.update_slide_label, name='updateSlideLabel'),
    path('updateSlideLabelTitle', views.update_slide_label_title, name='updateSlideLabelTitle'),
    path('delSlideLabel', views.del_slide_label, name='delSlideLabel'),
    path('checkIsMark', views.check_is_mark, name='checkIsMark'),
    path('updateSlideConfirm', views.update_slide_confirm, name='updateSlideConfirm'),
    path('listSlide', views.list_slide, name='listSlide'),
    path('saveJsonData', views.save_json_data, name='saveJsonData'),
    path('getDataJson', views.get_data_json, name='getDataJson'),
    path('getMd5', views.get_md5, name='getMd5'),
    path('runPreView', views.run_preview, name='runPreView'),
    path('cutImageView', views.cut_image_view, name='cutImageView'),
    path('importXml', views.import_xml, name='importXml'),
    path('downloadSlide', views.download_slide, name='downloadSlide'),
    path('login', user_views.login, name='loginApi'),
    path('getFixedRectangleXml', views.get_fixed_rectangle_xml, name='getFixedRectangleXml'),
    path('batchCut', views.batch_cut, name='batchCut'),
    path('autoPreview', views.auto_preview, name='autoPreview'),
    path('getThumb', views.get_thumb, name='getThumb'),
    path('allSaveJsonData', views.all_save_json_data, name='allSaveJsonData'),
    path('obtain', views.obtain, name='obtain'),
    path('obtainImage', views.obtain_image, name='obtainImage'),
    path('getDiagnostic', views.get_diagnostic, name='getDiagnostic'),
    path('getImageUrl', views.get_image_url, name='getImageUrl'),
    path('getLabelData', views.get_label_data, name='getLabelData'),
    path('saveImage', views.save_image, name='saveImage'),
    path('getImage', views.get_image, name='getImage'),
    path('deleteImage', views.delete_image, name='deleteImage'),
    path('saveDiagnose', views.save_diagnose, name='saveDiagnose'),#保存诊断报告
    path('getDiagnose', views.get_diagnose, name='getDiagnose'), #获取诊断报告

    #2022/12/06新增
    path('diagnose-need',views.DiagnoseNeedDataView.as_view()),
    path('search-part',views.search_part,name='search-part'),
    path('test-json',views.test,name='test-json'),
    #2023/1/8新增
    path('slide-diagnose',views.slide_diagnose_result,name='slide-diagnose'),
    #2023-02-14新增:文件上传，文件保存，文件切割、智能诊断
    path('web-upload-file',views.web_upload_file,name='web-upload-file'),
    #2023-02-21新增：文件处理进度
    path('file-process',views.web_upload_file_progress,name='file-process'),
    #2023-02-17新增，测试cache缓存是否可用
    path('save-cache',views.save_msg_to_cache,name='save-cache'),
    path('get-cache',views.get_msg_from_cache,name='get-cache'),
    #2023-02-28新增：新版智能诊断返回的结果
    path('obtain_fourinfor',views.save_new_diagnostic_result,name='obtain_fourinfor'),
    #2023-02-28新增：浏览器获取当个切片的智能诊断进度
    path('diagnoise-result-chrome',views.get_diagnoise_chrome,name='dianoise-result-chrome'),
    #2023-03-01新增，开放给前端进行测试
    path('test-upload-file',views.test_upload_file,name='test-upload-file'),
    #2023-03-01新版智能诊断接口,旧版本=importXml,点击小切片的智能诊断就会跳到这里
    path('importXmlNew',views.import_xml_new,name='import-xml-new'),
    #2023-03-02用户收藏切片
    path('user-slides',views.user_slides,name='user-slides'),
    #2023-03-03 首页搜索功能:就搜索功能路由 listSlide 和 checkIsMark
    path('index-search',views.index_search,name='index-search'),
    #2023-03-0 4点击大切片中的智能诊断按钮(限制浏览器对同一个大切片进行智能诊断，30分钟只能请求一次)
    path('send-importXmlNew',ratelimit(key='post:slide_id', method='POST', rate='1/30m',block=True)(views.send_importXmlNew),name='send-to-import-xml-new'),
    #2023-03-04大切片搜索小切片
    path('search-child-slides',views.search_slide_childs,name='search-child-slides'),
    #2023-03-06新增：小切片的数据文件
    path('child-slide-xml',views.child_slide_jsonData,name='chile-slide-xml'),
    #2023-03-06 ：下载小切片的固定框数据文件
    path('child-slide-fixed',views.child_slide_fixed,name = 'chile-slide-fixed'),
    #2023-03-06 : 大切片文件下载标注数据文件
    path('father-slide-xml',views.father_slide_xml,name='father-slide-xml'),
    #2023-03-07: 大切片文件下载固定框信息文件
    path('father-slide-fixed',views.father_slide_fixed,name='father-slide-fixed'),
    #2023-03-07: 拿到切片智能诊断结果和相关图片
    path('slide-diagnose-img',views.slide_diagnose_imge,name='slide-diagnose-img'),
    #2023-03-07：将DataSet中没有记录到数据库的切片都记录到数据库中
    path('folder-tiff-to-mysql',views.folder_tiff_to_mysql,name='folder-tiff-to-mysql'),
    #2023-03-08:更新诊断报告打印次数
    path('report-count',views.report_print_count,name = 'report-count'),
    #2023-03-08: 将切片进行过旧智能诊断（会给切片生成十几万条标注信息的），将有进行中此操作的切片记录起来（只执行一次，后续不再执行）
    path('slide-has-old-ai',views.slide_has_old_ai,name='slide-has-old-ai'),
    #2023-03-14:web上传文件时，进行切割预览操作，判断切片类型
    path('auto-preview-webupload',views.auto_preview_webupload,name='auto-preview-webupload'),
    #2023-03-01新版智能诊断接口，浏览器点击小切片进行智能诊断,加上请求频率限制，同一个切片文件，在30分钟内只能进行一次智能诊断
    path('importXmlSmall',ratelimit(key='post:filename', method='POST', rate='1/30m',block=True)(views.import_xml_small),name='import-xml-small'),
    #2023-03-16:手动修改数据库记录，将智能诊断状态是计算中改为已完成
    path('make-diagnose-complete',views.make_diagnose_complete,name='make-diagnose-complete'),
    #2023-03-16: 历史小切片，有些切片在生成小切片的时候，没有把小切片的缩略图生成，这个接口是给小切片生成缩略图的
    path('slide-make-jpg',views.small_slide_make_jpg,name='small-slide-jpg'),
    #2023-03-19: 上传的是小切片，但是在上传时没有将其的字段is_small_slide设置成1
    path('set_is_small',views.set_is_small_slide,name='set_is_small'),

]
