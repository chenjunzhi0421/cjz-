from celery import Celery
from django.core.mail import send_mail
from django.conf import settings
from goods.models import GoodsCategory, Goods, GoodsSKU, IndexPromotionBanner, IndexGoodsBanner, IndexCategoryGoodsBanner
from django.template import loader
import os

# 创建celery客户端 或者叫做celery对象
# 参数1： 指定任务所在的路径，从包名开始
# 参数2"： 指定任务队列（borker）， 可以作为任务队列的有多种，此处以redis数据库为例
celery_app = Celery('celery_tasks.tasks', broker='redis://127.0.0.1:6379/4')

# 生产任务
@celery_app.task
def send_active_email(to_email, user_name, token):
    """封装发送邮件的任务"""
    subject = "天天生鲜用户激活"  # 标题
    body = ""  # 文本邮件框
    sender = settings.EMAIL_FORM  # 发件人
    receive = [to_email]  # 收件人
    html_body = '<h1>尊敬的用户 %s ,感谢您注册天天生鲜！</h1>' \
                '<br/><p>请点击此链接激活您的账号<a href="http://127.0.0.1:8000/users/active/%s">' \
                'http://127.0.0.1:8000/users/active/%s</a></p>' % (user_name, token, token)
    send_mail(subject, body, sender, receive, html_message=html_body)


@celery_app.task
def generate_static_index_html():
    """异步生成静态主页"""
    categorys = GoodsCategory.objects.all()

    # 查询图片轮播信息 需求：根据index从小到大排序
    goods_banners = IndexGoodsBanner.objects.all().order_by('index')

    # 查询商品活动信息
    promotionbanners = IndexPromotionBanner.objects.all().order_by('index')

    # 查询主页分类列表信息
    for category in categorys:
        title_banners = IndexCategoryGoodsBanner.objects.filter(category=category, display_type=0)
        category.title_banners = title_banners

        image_banners = IndexCategoryGoodsBanner.objects.filter(category=category, display_type=1)
        category.image_banners = image_banners
    # 查询购物车信息
    cart_num = 70

    # 构造上下文
    context = {
        'categorys': categorys,
        'goods_banners': goods_banners,
        'promotionbanners': promotionbanners,
        'cart_num': cart_num
    }

    # 获取模板
    template = loader.get_template('static_index.html')

    # 上下文渲染模板，得到模板数据
    html_data = template.render(context)

    # 获取静态文件保存路径
    file_path = os.path.join(settings.STATICFILES_DIRS[0], 'index.html')

    # 存储到静态文件夹
    with open(file_path, 'w') as file:
        file.write(html_data)


