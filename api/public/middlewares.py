from django.utils.deprecation import MiddlewareMixin
import json
from public.global_common import *

class disporeRequest(MiddlewareMixin):
    def process_request(self, request):
        if request.method == "POST":
            try:
                if not request.FILES and request.body.strip != '':
                    _mutable = request.POST._mutable
                    request.POST._mutable = True
                    request.POST.update(json.loads(request.body))
                    request.POST._mutable = _mutable
            except Exception as e:
                print(e)
                sderror(e)
        elif request.method == "GET":
            pass
        else:
            return build_err_json('try post again.')



