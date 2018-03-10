from django.shortcuts import render, redirect
from django.views.generic import View
from goods.models import GoodsCategory, Goods, GoodsSKU, IndexPromotionBanner, IndexGoodsBanner, IndexCategoryGoodsBanner
from django.core.cache import cache
from django_redis import get_redis_connection
from django.core.urlresolvers import reverse
from django.core.paginator import Paginator, EmptyPage
import json

# Create your views here.

class BaseCartView(View):
    """查询登陆和未登陆时购物车信息"""

    def get_cart_num(self, request):

        cart_num = 0

        # 如果是登陆用户，读取购物车数据
        if request.user.is_authenticated():
            # 创建链接到redis的对象
            redis_conn = get_redis_connection('default')

            # 调用hgetall()方法，读取所有的购物车数据
            user_id = request.user.id
            cart_dict = redis_conn.hgetall('cart_%s' % user_id)

            # 遍历数量，累加求和
            for val in cart_dict.values():
                cart_num += int(val)

        else:
            # cookie中存储的是json字符串
            cart_json = request.COOKIES.get('cart')
            if cart_json is not None:
                cart_dict = json.loads(cart_json)
            else:
                cart_dict = {}

            # 遍历cart_dict,取出count，求和
            for val in cart_dict.values():
                cart_num += int(val)  # val 是int类型

        return cart_num


class ListView(BaseCartView):
    """列表页"""
    def get(self, request, category_id, page_num):
        """查询数据，渲染模板，实现分页和排序"""

        # 获取排序的规则
        sort = request.GET.get('sort', 'default')

        # 查询用户要看的商品的分类，category_id对应的

        try:
            category = GoodsCategory.objects.get(id=category_id)
        except GoodsCategory.DoesNotExist:
            return redirect(reverse('goods:index'))

        # 查询所有的商品分类
        categorys = GoodsCategory.objects.all()

        # 查询新品推荐
        new_skus = GoodsSKU.objects.filter(category=category).order_by('-create_time')[:2]

        # 查询category_id 对应 的sku信息, 并且排序
        if sort == 'price':
            skus = GoodsSKU.objects.filter(category=category).order_by('price')
        elif sort == 'hot':
            skus = GoodsSKU.objects.filter(category=category).order_by('-sales')
        else:
            skus = GoodsSKU.objects.filter(category=category)
            sort = 'default'

        # 查询购物车信息
        cart_num = self.get_cart_num(request)

        # 如果是登陆用户，读取购物车数据
        if request.user.is_authenticated():
            # 创建链接到redis的对象
            redis_conn = get_redis_connection('default')

            # 调用hgetall()方法，读取所有的购物车数据
            user_id = request.user.id

        # 查询分页数据
        # paginator = [GoodsSKU,GoodsSKU,GoodsSKU,GoodsSKU,GoodsSKU,...]
        paginator = Paginator(skus, 2)
        # 获取用户要看的那一页
        page_num = int(page_num)
        try:
            page_skus = paginator.page(page_num)
        except EmptyPage:
            page_skus = paginator.page(1)

        # 获取页码列表
        page_list = paginator.page_range

        # 构造上下文
        context = {
            'category':category,
            'categorys':categorys,
            'new_skus':new_skus,
            'page_skus':page_skus,
            'page_list':page_list,
            'sort':sort,
            'cart_num':cart_num
        }

        # 渲染模板
        return render(request, 'list.html', context)


class DetailView(BaseCartView):
    """详情页面"""
    def get(self, request, sku_id):
        """查询详情页面数据，渲染模板"""

        # 查询商品SKU信息
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return redirect(reverse('goods:index'))

        # 查询商品分类信息:6大分类
        categorys = GoodsCategory.objects.all()

        # 查询商品详情介绍信息
        # 查询商品评价信息，从订单中获取评论信息
        sku_orders = sku.ordergoods_set.all().order_by('-create_time')[:30]
        if sku_orders:
            for sku_order in sku_orders:
                sku_order.ctime = sku_order.create_time.strftime('%Y-%m-%d %H-%M-%S')
                sku_order.username = sku_order.order.user.username
        else:
            sku_orders = []

        # 查询最新推荐商品信息: 从数据库中获取最新发布的两件商品
        new_skus = GoodsSKU.objects.filter(category=sku.category).order_by('-create_time')[:2]

        # 查询其他规格商品信息
        other_skus = sku.goods.goodssku_set.exclude(id=sku.id)

        # 查询购物车信息
        cart_num = self.get_cart_num(request)

        # 如果是登陆用户，读取购物车数据
        if request.user.is_authenticated():
            # 创建链接到redis的对象
            redis_conn = get_redis_connection('default')

            # 调用hgetall()方法，读取所有的购物车数据
            user_id = request.user.id

            # 删除重复的sku_id
            redis_conn.lrem('history_%s' % user_id, 0, sku_id)

            # 记录浏览信息
            redis_conn.lpush('history_%s' % user_id, sku_id)

            # 最多保存5条记录
            redis_conn.ltrim('history_%s' % user_id, 0, 4)

        # 构造上下文
        context = {
            'sku':sku,
            'categorys':categorys,
            'sku_orders':sku_orders,
            'new_skus':new_skus,
            'other_skus':other_skus,
            'cart_num':cart_num
        }

        # 更新context
        # context.update(cart_num=cart_num)

        # 渲染模板
        return render(request, 'detail.html', context)


class IndexView(BaseCartView):
    """主页"""
    def get(self, request):
        """查询主页商品数据，渲染模板"""

        # 读取缓存的数据
        context = cache.get('index_page_data')
        if context is None:
            print('没有缓存，查询数据')

            # 查询用户user信息
            # 查询商品分类信息
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

            # 构造上下文
            context = {
                'categorys':categorys,
                'goods_banners':goods_banners,
                'promotionbanners':promotionbanners,
            }

            # 缓存上下文，缓存的key  要缓存的数据  过期的时间：秒数
            cache.set('index_page_data', context, 3600)

        # 查询购物车信息
        cart_num = self.get_cart_num(request)

        # 更新context
        context.update(cart_num=cart_num)

        # 渲染模板
        return render(request, 'index.html', context)
