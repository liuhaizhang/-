from django.shortcuts import render
from django.http import JsonResponse
from public import global_common as gcm
import hashlib
from .models import TAccount
import simplejson
from django.views.decorators.http import require_http_methods
from django.forms.models import model_to_dict


# Create your views here.


def login(request):
    if request.method == 'POST':
        account_name = request.POST.get('account_name')
        account_pwd = request.POST.get('account_pwd')

        if not account_pwd or not account_name:
            return gcm.failed('请输入用户密码')

        account_pwd = hashlib.md5(account_pwd.encode("latin1")).hexdigest()
        try:
            account = TAccount.objects.get(account_name=account_name, account_pwd=account_pwd, is_delete=0)
        except Exception as e:
            return gcm.failed('用户名或者密码错误')

        token_obj = {
            'account_id': account.account_id
        }
        token_json_str = simplejson.dumps(token_obj)
        account = model_to_dict(account)
        account['token'] = gcm.getToken(token_json_str)

        return gcm.data(account)


def add(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        account_name = request.POST.get('account_name')
        account_pwd = request.POST.get('account_pwd')
        real_name = request.POST.get('real_name')
        phone = request.POST.get('phone')

        if not user_id:
            return gcm.failed("请输入用户ID")
        account = TAccount.objects.filter(user_id=user_id, is_delete=0)
        if account:
            return gcm.failed("用户id已存在，请确认")

        if not account_name:
            return gcm.failed('请输入用户名')
        account = TAccount.objects.filter(account_name=account_name, is_delete=0)
        if account:
            return gcm.failed("用户名已存在，请重新输入")

        if not account_pwd:
            return gcm.failed('请输入密码')
        if not real_name:
            return gcm.failed('请输入真实姓名')

        account_pwd = hashlib.md5(account_pwd.encode("latin1")).hexdigest()
        account = TAccount.objects.create(account_name=account_name, account_pwd=account_pwd, real_name=real_name,
                                          phone=phone, user_id=user_id, is_delete=0, is_super=0)

        if not account:
            return gcm.failed("注册失败，请重试")

        return gcm.success("注册成功")


@gcm.check_api_token()
def update(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        account_name = request.POST.get('account_name')
        real_name = request.POST.get('real_name')
        account_pwd = request.POST.get('account_pwd')
        phone = request.POST.get('phone')

        if not user_id:
            return gcm.failed('请输入用户id')

        accounts = TAccount.objects.filter(user_id=user_id, is_delete=0)
        if not accounts:
            return gcm.failed('用户不存在')
        account = accounts[0]

        if not account_name:
            return gcm.failed('请输入用户名')
        account_by_name = TAccount.objects.filter(account_name=account_name, is_delete=0)
        if account_by_name and account_by_name[0].user_id != user_id: return gcm.failed('用户名已存在')

        if not real_name:
            return gcm.failed('请输入真实姓名')

        if not account_pwd:
            return gcm.failed('请输入密码')
        account_pwd = hashlib.md5(account_pwd.encode("latin1")).hexdigest()

        account.account_name = account_name
        account.account_pwd = account_pwd
        account.real_name = real_name
        account.phone = phone
        account.save()

        return gcm.data("修改成功")


@gcm.check_api_token()
def delete(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        if not user_id:
            return gcm.failed('请输入用户id')
        accounts = TAccount.objects.filter(user_id=user_id, is_delete=0)
        if not accounts:
            return gcm.failed('用户不存在')

        account = accounts[0]
        account.is_delete = 1
        account.save()
        return gcm.success('删除成功')


@gcm.check_api_token()
def delete_ids(request):
    if request.method == 'POST':
        ids = request.POST.getlist('ids[]')
        TAccount.objects.filter(user_id__in=ids, is_delete=0).update(is_delete=1)
        return gcm.success('删除成功')
