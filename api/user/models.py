from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from dataCtrl.models import *


class TAccount(models.Model):
    account_id = models.AutoField(primary_key=True)
    account_name = models.CharField(max_length=50, blank=True, null=True, verbose_name="用户名", unique=True)
    account_pwd = models.CharField(max_length=50,  blank=True, null=True, verbose_name="密码")
    real_name = models.CharField(max_length=30, blank=True, null=True, verbose_name="真实姓名")
    is_delete = models.IntegerField(blank=True, null=True)
    phone = models.CharField(max_length=255, blank=True, null=True, verbose_name="电话")
    user_id = models.CharField(max_length=255, blank=True, null=True)
    is_super = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = 't_account'
        verbose_name = '用户'  # 在admin站点中显示名称
        verbose_name_plural = verbose_name  # 显示复数

