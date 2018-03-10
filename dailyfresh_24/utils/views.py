from django.contrib.auth.decorators import login_required
from functools import wraps
from django.http import JsonResponse
from django.db import transaction


# 自定义装饰器
def login_required_json(view_func):
    """验证用户是否登陆，跟JSON交互的"""
    # 恢复view_func的名字和文档

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        # 如果用户未登录。返回json数据
        if not request.user.is_authenticated():
            return JsonResponse({'code': 1, 'message': '用户未登陆'})
        else:
            # 如果用户登陆，进入到view_func中
            return view_func(request, *args, **kwargs)

    return wrapper


"""封装了判断用户是否登陆的工具类"""


class LoginRequiredMixin(object):
    """重写as_view()"""
    @classmethod
    def as_view(cls, **initkwargs):
        # 需要获取到View的as_view()执行后的结果，并且使用login_required装饰器装饰
        view = super().as_view(**initkwargs)

        return login_required(view)

# 封装自定义装饰器的拓展类
class LoginRequiredJSONMixin(object):

    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)

        return login_required_json(view)


class TransactionAtomicMiXin(object):
    """提供数据库事务功能"""

    @classmethod
    def as_view(cls, **initkwargs):
        view = super(TransactionAtomicMiXin, cls).as_view(**initkwargs)

        return transaction.atomic(view)