from django.contrib import admin
from goods.models import GoodsCategory, Goods, IndexPromotionBanner
from celery_tasks.tasks import generate_static_index_html
from django.core.cache import cache

# Register your models here.


class BaseAdmin(admin.ModelAdmin):

    def save_model(self, request, obj, form, change):
        """保存数据/更改数据时使用的"""

        # 执行父类的保存逻辑
        obj.save()

        # 触发生成静态主页的异步任务
        generate_static_index_html.delay()

        # 手动的删除缓存
        cache.delete('index_page_data')

    def delete_model(self, request, obj):
        """删除数据时使用的"""

        # 执行父类的保存逻辑
        obj.delete()

        # 触发生成静态主页的异步任务
        generate_static_index_html.delay()

        # 手动的删除缓存
        cache.delete('index_page_data')


class IndexPromotionBannerAdmin(BaseAdmin):
    """IndexPromotionBanner模型的管理类"""
    pass


class GoodsCategoryAdmin(BaseAdmin):
    pass


class GoodsAdmin(BaseAdmin):
    pass

admin.site.register(GoodsCategory, GoodsCategoryAdmin)

admin.site.register(Goods, GoodsAdmin)

admin.site.register(IndexPromotionBanner, IndexPromotionBannerAdmin)