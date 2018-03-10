from django.conf.urls import url
from goods import views


urlpatterns = [
    # 主页 http://127.0.0.1:8000/index
    url(r'^index$', views.IndexView.as_view(), name='index'),

    # 商品详情页面
    url(r'^detail/(?P<sku_id>\d+)$', views.DetailView.as_view(), name='detail'),

    # 列表页 http://127.0.0.1:8000/list/category_id/page_num?sort='default'
    url(r'^list/(?P<category_id>\d+)/(?P<page_num>\d+)$', views.ListView.as_view(), name='list')
]