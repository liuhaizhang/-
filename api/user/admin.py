from django.contrib import admin
from .models import TAccount

class TAccountAdmin(admin.ModelAdmin):
    list_display = ('account_name', 'real_name',)

admin.site.register(TAccount, TAccountAdmin)