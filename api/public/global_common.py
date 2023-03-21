from django.http import JsonResponse, HttpResponse
import simplejson
import datetime
import decimal
import time
import base64
import rsa
import os
from .logger import log

g_publicKey = None
g_privateKey = None

#token 的有效时间 默认 24小时
token_valid_time = 24*60*60*7


def sderror(e,name=''):
    log.error(str(e))
    log.error(name)


def createPublicPrivateKeyRsa():
    global g_publicKey
    global g_privateKey

    (g_publicKey, g_privateKey) = rsa.newkeys(800)
    try:
        pub = g_publicKey.save_pkcs1()
        pubfile = open('public.pem', 'wb+')
        pubfile.write(pub)

        pri = g_privateKey.save_pkcs1()
        prifile = open('private.pem', 'wb+')
        prifile.write(pri)
    except Exception as e:
        print(e)
        sderror(e)
    finally:
        pubfile.close()
        prifile.close()


def initRsa():
    '''
        寻找public.pem 和 private.pem 文件 如果不存在 就创建
        存在就加载
    '''
    global g_publicKey
    global g_privateKey

    try:
        f = None
        if os.path.isfile('public.pem') and os.path.isfile('private.pem'):
            f = open('public.pem')
            g_publicKey = rsa.PublicKey.load_pkcs1(f.read())

            f = open('private.pem')
            g_privateKey = rsa.PrivateKey.load_pkcs1(f.read())
        else:
            createPublicPrivateKeyRsa()
    except Exception as e:
        print(e)
        sderror(e)
    finally:
        if f: f.close()


initRsa()


def safe_new_datetime(d):
    kw = [d.year, d.month, d.day]
    if isinstance(d, datetime.datetime):
        kw.extend([d.hour, d.minute, d.second, d.microsecond, d.tzinfo])
    return datetime.datetime(*kw)


def safe_new_date(d):
    return datetime.date(d.year, d.month, d.day)


class DatetimeJSONEncoder(simplejson.JSONEncoder):
    """可以序列化时间的JSON"""

    DATE_FORMAT = "%Y-%m-%d"
    TIME_FORMAT = "%H:%M:%S"

    def default(self, o):
        if isinstance(o, datetime.datetime):
            d = safe_new_datetime(o)
            return d.strftime("%s %s" % (self.DATE_FORMAT, self.TIME_FORMAT))
        elif isinstance(o, datetime.date):
            d = safe_new_date(o)
            return d.strftime(self.DATE_FORMAT)
        elif isinstance(o, datetime.time):
            return o.strftime(self.TIME_FORMAT)
        elif isinstance(o, decimal.Decimal):
            return str(o)
        else:
            return super(DatetimeJSONEncoder, self).default(o)


def cross_response(response):
    response['Server'] = 'godwind_django'
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    response["Access-Control-Max-Age"] = "1000"
    response["Access-Control-Allow-Headers"] = "X-Requested-With"

    return response


def build_str_json(tmp='success'):
    rlt = {}
    rlt['resultCode'] = 0
    rlt['resultMsg'] = tmp
    response = HttpResponse(simplejson.dumps(rlt, cls=DatetimeJSONEncoder, ensure_ascii = False),
                            content_type="application/json; charset=utf-8")
    return cross_response(response)

def build_err_json(errstr, errorcode="-1"):
    rlt = {}
    rlt['resultCode'] = errorcode
    rlt['resultMsg'] = errstr

    response = HttpResponse(simplejson.dumps(rlt, cls=DatetimeJSONEncoder, ensure_ascii=False),
                            content_type="application/json; charset=utf-8")
    return cross_response(response)

def success(m='操作成功'):
    return build_str_json(m)


def failed(m='操作失败'):
    return build_err_json(m)


def runing(m='操作进行，请稍等'):
    return build_str_json(m)



def build_dict_json(rlt, msg=''):
    tmp = {}
    if 'data' not in rlt:
        tmp['data'] = rlt
    else:
        tmp = rlt

    tmp['resultCode'] = 0
    tmp['resultMsg'] = msg
    #    return cross_response(HttpResponse(json.dumps(tmp),content_type="application/json; charset=utf-8"))
    return cross_response(HttpResponse(simplejson.dumps(tmp, cls=DatetimeJSONEncoder),
                                       content_type="application/json; charset=utf-8"))


def dict_custom(rlt):
    return cross_response(HttpResponse(simplejson.dumps(rlt,cls=DatetimeJSONEncoder),content_type="text/html; charset=utf-8"))


def data(data):
    return build_dict_json({'data': data})


def dict_data_token(data,request):
    return build_dict_json({'data': data, 'update_token': request.get('update_token')})


def rsa_encode(m):
    #加密
    m = bytes(m, encoding='utf-8')
    return rsa.encrypt(m, g_publicKey)

def rsa_decode(m):
    #解密
    return rsa.decrypt(m, g_privateKey).decode()


def getToken(userId):
    '''
        根据客户端请求登录的时候上传用户名、密码
        服务器端返回 token  目前的规则是 userId+登录时间时间戳 超过24小时则无效
        如:2015_1429577483.65  userId为2015,时间戳1429577483.65
        json.dump - UnicodeDecodeError: 'utf8' codec can't decode byte 0xbf in position 0: invalid start byte
        .decode('latin-1')

        同时 记录到 t_token 表 user_id,token
    '''
    token = None
    if str(userId):
        token = str(userId) + '|' + str(time.time())
        return base64.b64encode(rsa_encode(token))
    else:
        return None


def checkToken(token, is_forever=False):
    '''
            对用户的token校验  有效时间为24小时 超过即无效
            如果验证失败 返回false 如果验证成功 返回解密后的 UserId
    '''
    try:
        if token:
            (userId, login_time) = rsa_decode(base64.b64decode(token)).split("|")
            token_interval = time.time() - float(login_time)

            if is_forever and token_interval > token_valid_time:
                return False
            else:
                update_token = getToken(userId)
                return userId, update_token
        else:
            pass
    except Exception as e:
        print(e)
        sderror(e, 'checkToken')
        return False


def check_api_token(check=True):
    from urllib import parse
    def Get_reg(func):
        def call(request, **kwargs):
            if check:
                if request.method == "POST":
                    token = request.POST.get('token', None)
                else:
                    token = request.GET.get('token', None)
                    if token:
                        token = parse.unquote(token)
                if not token:
                    token = request.META.get('HTTP_TOKEN',None)
                #print(len(token))
                #print('检测token，',token)
                if not token: return build_err_json("没有发现token参数.", 100)

                check_token_result = checkToken(token)

                if not check_token_result:
                    return build_err_json('token:%s 已失效.' % token, 100)

                user_id_token = check_token_result[0]
                update_token = check_token_result[1]
                request.req_accountInfo = simplejson.loads(user_id_token)
                request.req_token = update_token

            return func(request, **kwargs)
        call.__doc__ = func.__doc__
        return call
    return Get_reg


def download(stream, filename):
    response = HttpResponse(stream, content_type="application/octet-stream")
    response['Content-Disposition'] = 'attachment;filename="%s"' % filename
    return response
