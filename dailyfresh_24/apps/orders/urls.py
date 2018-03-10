from django.conf.urls import url
from orders import views


urlpatterns = [

    # 订单确认 http://127.0.0.1:8000/orders/place(需要的sku_id和count存放在request请求体中)
    url(r'^place$', views.PlaceOrderView.as_view(), name='place'),

    # 订单提交
    url(r'^commit$', views.CommitOrderView.as_view(), name='commit'),

    # 全部订单
    url(r'^(?P<page>\d+)$', views.UserOrderView.as_view(), name='info'),

    # 支付宝支付
    url(r'^pay$', views.PayView.as_view(), name='pay'),

    # 订单状态
    url(r'^checkpay$', views.CheckPayView.as_view(), name='checkpay'),

    # 评论页
    url(r'^comment/(?P<order_id>\d+)$', views.CommentView.as_view(), name='comment')
]