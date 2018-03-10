from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.views.generic import View
from django.core.urlresolvers import reverse
import re
from users.models import User, Address
from django import db
from django.conf import settings
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from celery_tasks.tasks import send_active_email
from itsdangerous import SignatureExpired
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django_redis import get_redis_connection
from goods.models import GoodsSKU
from utils.views import LoginRequiredMixin
import json


# Create your views here.

class UserInfoView(LoginRequiredMixin, View):
    """个人信息"""
    def get(self, request):
        """查询基本信息和最近浏览，并且渲染模板"""

        # 查询基本信息 ： 用户名， 联系方式， 地址
        # 获取user
        user = request.user
        try:
            address = user.address_set.latest('create_time')
        except Address.DoesNotExist:
            address = None

        # 查询最近浏览
        redis_conn = get_redis_connection('default')
        # 调用对应的方法，查询出redis列表中保持sku_id
        sku_ids = redis_conn.lrange('history_%s' % user.id, 0, 4)
        # 遍历sku_id
        # 定义临时容器
        sku_list = []
        for sku_id in sku_ids:
            # 查询出sku_id对应的GoodsSKU
            sku = GoodsSKU.objects.get(id=sku_id)
            sku_list.append(sku)

        # 构造上下文
        context = {
            'address':address,
            'sku_list':sku_list
        }

        # 渲染模板
        return render(request, 'user_center_info.html', context)


class AddressView(LoginRequiredMixin, View):
    """收货地址"""

    def get(self, request):
        """提供收货地址页面，查询地址信息，并且渲染"""
        """方案一
        if not request.user.is_authenticated():
            return redirect(reverse('users:login'))
        else:
            return render(request, 'user_center_site.html')
        """
        # 获取登陆的用户
        user = request.user

        # 查询登陆用户的地址信息 查询用户最近创建的地址，取最新的地址
        # address = Address.objects.filter(user=user)[-1]   # 顺序
        # address = Address.objects.filter(user=user).order_by('-create_time')[0]  # 逆序
        # address = user.address_set.order_by('-create_time')[0]
        try:
            address = user.address_set.latest('create_time')
        except Address.DoesNotExist:
            address = None
        # 构造上下文
        context = {
            # 'user': user,
            'address': address
        }

        # 渲染模板
        return render(request, 'user_center_site.html', context)

    def post(self, request):
        """编辑地址"""

        # 接收编辑的地址参数
        recv_name = request.POST.get('recv_name')
        addr = request.POST.get('addr')
        zip_code = request.POST.get('zip_code')
        recv_mobile = request.POST.get('recv_mobile')

        # 校验地址参数 说明开发还需要校验数据是否真实
        if all([recv_name, addr, zip_code, recv_mobile]):
            # 保存地址参数
            Address.objects.create(
                user = request.user,
                receive_name = recv_name,
                receive_mobile = recv_mobile,
                detail_addr = addr,
                zip_code = zip_code
            )

        # 响应结果
        return redirect(reverse('users:address'))


class LogoutView(View):
    """退出登陆"""
    def get(self, request):
        """处理退出登陆逻辑:确定清空谁的状态保持信息"""
        logout(request)
        # return redirect(reverse("users:login"))
        return redirect(reverse('goods:index'))


class LoginView(View):
    """登陆"""
    def get(self, request):
        """提供登陆页面"""
        return render(request, 'login.html')

    def post(self, request):
        """处理登陆逻辑"""
        # 接收登陆请求的参数
        user_name = request.POST.get('user_name')
        pwd = request.POST.get('pwd')
        # 校验登陆请求参数
        if not all([user_name, pwd]):
            return redirect(reverse('users:login'))
        # 判读用户是否存在
        user = authenticate(username=user_name, password=pwd)
        if user is None:
            """提示用户：用户名或密码错误"""
            return render(request, 'login.html', {'errmsg':'用户名或密码错误'})
        # 判读用户是否市激活用户

        if user.is_active == False:
            return render(request, 'login.html', {'errmsg':'请激活'})

        # 登入该用户
        # 提示，如果调用login方法，没有指定session的引擎，那么默认存储在django_session表中
        # 提示：如果指定了session的引擎，那么就按照引擎的指引进行session数据的存储，需要搭配django-redis使用

        login(request, user)

        # 实现记住用户名/多少天免登陆
        # 如果用户勾选了记住用户码，就把状态保持10天，否则，保持0
        remembered = request.POST.get('remembered')
        if remembered != "on":
            request.session.set_expiry(0)  # 状态保持0秒
        else:
            request.session.set_expiry(60*60*24*10) # 状态保持10天

        # 在界面跳转之前，将cookie中的购物车信息合并到redis中
        # 查询cookie中购物车信息
        cart_json = request.COOKIES.get('cart')
        if cart_json is not None:
            cart_dict_cookie = json.loads(cart_json)
        else:
            cart_dict_cookie = {}

        # 查询redis中的购物车信息
        redis_conn = get_redis_connection('default')
        cart_dict_redis = redis_conn.hgetall('cart_%s' % user.id)

        # 遍历cart_dict_cookie，取出其中的sku_id和count信息，存储到redis中国
        for sku_id, count in cart_dict_cookie.items():
            # sku_id是字符串，count是int类型
            sku_id = sku_id.encode()  # 将sku_id转bytes类型
            if sku_id in cart_dict_redis:
                orgin_count = cart_dict_redis[sku_id]
                count += int(orgin_count)

            # 保存合并数据到cart_dict_redis中
            cart_dict_redis[sku_id] = count

        if cart_dict_redis:
            redis_conn.hmset('cart_%s' % user.id, cart_dict_redis)

        # 在界面跳转以前，需要判断用户登陆以后需要跳转的页面
        # 如果有next就跳转到next指向的地方，否则跳转到主页
        next = request.GET.get('next')
        if next is None:
            # 跳转到主页
            response =  redirect(reverse('goods:index'))
        else:
            # 跳转到next指向的页面
            if next == '/orders/place':
                response = redirect(reverse('cart:info'))
            else:
                response = redirect(next)

        # 删除cookie
        response.delete_cookie('cart')

        return response


class ActiveView(View):
    """邮件激活"""
    def get(self, request, token):
        """处理邮件激活逻辑"""
        # 获取封装了user_id的字典 创建序列化器
        serializer = Serializer(settings.SECRET_KEY, 3600)
        # 解出原始字典
        try:
            result = serializer.loads(token)
        except SignatureExpired:
            return HttpResponse('激活链接已过期')
        # 获取user_id
        user_id = result.get('confirm')
        # 查询user
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return HttpResponse('用户不存在')
        # 重置激活状态码为True
        user.is_active = True
        user.save()
        # 响应结果
        return redirect(reverse('users:login'))


class RegisterView(View):
    """类视图，注册页面：提供注册页面和注册逻辑"""

    def get(self, request):
        """提供注册页面"""
        return render(request, 'register.html')

    def post(self, request):
        """处理注册逻辑，存储注册信息"""
        # 接收用户注册的参数
        user_name = request.POST.get('user_name')
        pwd = request.POST.get('pwd')
        email = request.POST.get('email')
        allow = request.POST.get('allow')

        # 校验用户注册的参数: all()只要有一个数据为空，那么就返回假，只有全部为真，才返回真
        if not all([user_name, pwd, email]):
            # 公司中，根据开发文档实现需求
            return redirect(reverse('users:register'))
        # 判断邮箱格式
        if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return render(request, 'register.html', {'errmsg':'邮箱格式错误'})

        # 判断是否勾选了协议
        if allow != 'on':
            return render(request, 'register.html', {'errmsg': '请勾选用户协议'})

        # 保存用户注册的参数
        try:
            user = User.objects.create_user(user_name, email, pwd)
        except db.IntegrityError:
            return render(request, 'register.html', {'errmsg': '用户已存在'})

        # 重置激活状态：需要使用邮件激活
        user.is_active = False

        # 注意：需要重新保存以下
        user.save()

        # 生成token
        token = user.generate_active_token()

        # 发送激活邮件，不能够阻塞HttpResponse -->异步发送
        # send_active_email(email, user_name, token) # 错误写法，不会粗放异步的send_active_email
        # 正确的写法
        send_active_email.delay(email, user_name, token)


        # from django.core.mail import send_mail
        #
        # subject = "天天生鲜用户激活"  # 标题
        # body = ""   # 文本邮件框
        # sender = settings.EMAIL_FORM   # 发件人
        # receive = [email]   # 收件人
        # html_body = '<h1>尊敬的用户 %s ,感谢您注册天天生鲜！</h1>'\
        #             '<br/><p>请点击此链接激活您的账号<a href="http://127.0.0.1:8000/users/active/%s">'\
        #             'http://127.0.0.1:8000/users/active/%s</a></p>' % (user_name, token, token)
        # send_mail(subject, body, sender, receive, html_message=html_body)


        return redirect(reverse('goods:index'))




# 函数视图
# def register(request):
#     """注册"""
#     if request.method == 'GET':
#         """提供注册页面"""
#         return render(request, 'register.html')
#
#     if request.method == 'POST':
#         """处理注册逻辑，存储注册信息"""
#         return HttpResponse('这里是处理注册的逻辑')