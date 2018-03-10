from django.conf.urls import url
from apps.users import views
from django.contrib.auth.decorators import login_required

urlpatterns = [
    # http://127.0.0.1:8000/users/register/
    # url(r'^register$', views.register)

    # 类视图：
    # 注册页面-->http://127.0.0.1:8000/users/register/
    url(r'^register$', views.RegisterView.as_view(), name='register'),

    # 邮件激活
    url(r'^active/(?P<token>.+)$', views.ActiveView.as_view(), name='active'),

    # 登陆 http://127.0.0.1:8000/users/login
    url(r'^login$', views.LoginView.as_view(), name='login'),

    # 退出登陆
    url(r'^logout$', views.LogoutView.as_view(), name='logout'),

    # 收货地址方案1：
    url(r'^address$', views.AddressView.as_view(), name='address'),
    # 收货地址方案2：
    # url(r'^address$', login_required(views.AddressView.as_view()), name='address')

    # 个人信息
    url(r'^info$', views.UserInfoView.as_view(), name='info')
]