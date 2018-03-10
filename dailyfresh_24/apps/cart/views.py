from django.shortcuts import render, redirect
from django.views.generic import View
from django.http import JsonResponse
from goods.models import GoodsSKU
from django_redis import get_redis_connection
import json
# Create your views here.

class DeleteCartView(View):
    """删除购物车记录：一次删除一个"""
    def post(self, request):

        # 接收参数：sku_id
        sku_id = request.POST.get('sku_id')

        # 校验参数： not 判断是否为空
        if not sku_id:
            return JsonResponse({'code': 1, 'message': '用户不存在'})

        # 判断sku_id是否合法
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'code': 2, 'message': '删除的商品不存在'})

        # 判断用户是否登陆
        if request.user.is_authenticated():
            # 如果是登陆用户，删除redis中的购物车信息
            redis_conn = get_redis_connection('default')
            user_id = request.user.id
            redis_conn.hdel('cart_%s' % user_id, sku_id)

        else:
            # 如果是未登录用户，删除cookie中的购物车信息
            cart_json = request.COOKIES.get('cart')
            if cart_json is not None:
                cart_dict = json.loads(cart_json)

                del cart_dict[sku_id]

                new_cart_json = json.dumps(cart_dict)

                response = JsonResponse({'code':0, 'message':'删除成功'})
                response.set_cookie('cart', new_cart_json)

                return response

        return JsonResponse({'code': 0, 'message': '删除成功'})


class UpdateCartView(View):
    """更新购物车信息"""
    def post(self, request):
        """+ - 手动输入"""

        # 获取参数信息： sku_id, count
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # 校验参数
        if not all([sku_id, count]):
            return JsonResponse({'code':1, 'message':'缺少参数'})

        # 判断商品是否存在
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'code': 2, 'message': '商品不存在'})

        # 判断count是否是整数
        try:
            count = int(count)
        except Exception:
            return JsonResponse({'code': 3, 'message': '商品数量错误'})

        # 判断库存
        if count > sku.stock:
            return JsonResponse({'code': 4, 'message': '库存不足'})

        # 判断用户是否登陆
        if request.user.is_authenticated():
            # 如果用户登陆，将修改的购物车数据存储到redis中
            redis_conn = get_redis_connection('default')
            user_id = request.user.id
            redis_conn.hset('cart_%s' % user_id, sku_id, count)
            return JsonResponse({'code': 0, 'message': '更新购物车成功'})

        else:
            # 如果用户未登录，将修改的购物车数据存储到cookie中
            cart_json = request.COOKIES.get('cart')
            if cart_json is not None:
                cart_dict = json.loads(cart_json)
            else:
                cart_dict = {}

            cart_dict[sku_id] = count

            new_cart_json = json.dumps(cart_dict)

            # 更新cookie中的购物车信息
            response = JsonResponse({'code': 0, 'message': '更新购物车成功'})
            response.set_cookie('cart', new_cart_json)

            return response


class CartInfoView(View):
    """购物车信息"""
    def get(self, request):
        """查询登陆和未登录时购物车信息，并且渲染"""
        if request.user.is_authenticated():
            # 用户已登陆，查询redis中购物车信息
            redis_conn = get_redis_connection('default')
            user_id = request.user.id

            # cart_dict如果字典是通过redis_conn.hgetall得到的，那么字典的key和value信息是bytes类型
            cart_dict = redis_conn.hgetall('cart_%s' % user_id)

        else:
            # 用户未登陆时，要查询cookie中的数据
            cart_json = request.COOKIES.get('cart')

            # 如果cart_dict通过cookie中得到，那么key是字符串类型，count是int类型
            if cart_json is not None:
                cart_dict = json.loads(cart_json)
            else:
                cart_dict = {}

        # 定义临时变量
        skus = []
        total_count = 0   # 记录件数
        total_sku_amount = 0  # 记录总金额
        # 运费默认为10元

        for sku_id, count in cart_dict.items():
            try:
                sku = GoodsSKU.objects.get(id=sku_id)
            except GoodsSKU.DoesNotExist:
                continue  # 有异常跳过，展示没有异常的数据

            # 统一count的数据类型为int类型
            count = int(count)

            # 小计
            amount = count * sku.price

            # 给sku对象添加属性，存储count和amount
            sku.count = count
            sku.amount = amount

            skus.append(sku)

            # 总金额和总件数
            total_sku_amount += amount
            total_count += count

        # 构造上下文
        context = {
            'skus':skus,
            'total_sku_amount':total_sku_amount,
            'total_count':total_count
        }

        # 渲染模板
        return render(request, 'cart.html', context)


class AddCartView(View):
    """添加到购物车"""

    def post(self, request):
        """接收购物车参数，校验参数，保存参数"""

        # 判断用户是否登陆
        # if not request.user.is_authenticated():
        #     return JsonResponse({'code': 1, 'message': '用户未登陆'})

        # 接收购物车参数：user_id, sku_id, count
        # user_id = request.user.id
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # 校验参数
        if not all([sku_id, count]):
            return JsonResponse({'code': 2, 'message': '缺少参数'})

        # 判断sku_id是否合法
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'code': 3, 'message': '商品不存在'})

        # 判断count是否合法
        try:
            count = int(count)
        except Exception:
            return JsonResponse({'code': 4, 'message': '商品数量错误'})

        # 判断库存是否超出
        if count > sku.stock:
            return JsonResponse({'code': 5, 'message': '库存不足'})

        if request.user.is_authenticated():

            # 获取user_id
            user_id = request.user.id

            # 保存购物车数据到redis
            redis_conn = get_redis_connection('default')

            # 需要查询要保存的购物车的商品数据是否存在
            orgin_count = redis_conn.hget('cart_%s' % user_id, sku_id)
            if orgin_count is not None:
                count += int(orgin_count)

            # 再次判断库存是否超出
            if count > sku.stock:
                return JsonResponse({'code': 5, 'message': '库存不足'})

            redis_conn.hset('cart_%s' % user_id, sku_id, count)

            # 查询购物车中的商品数量，响应给前端
            cart_num = 0
            cart_dict = redis_conn.hgetall('cart_%s' % user_id)
            for val in cart_dict.values():
                cart_num += int(val)

            # 响应结果
            return JsonResponse({'code': 0, 'message': '添加购物车成功', 'cart_num':cart_num})

        else:
            # 用户未登陆，保存购物车数据到cookie中
            # 读取cookie中的购物车数据
            cart_json = request.COOKIES.get('cart')
            if cart_json is not None:
                # 把cart_json转成字典
                cart_dict = json.loads(cart_json)
            else:
                cart_dict = {}

            # 判断要存储的商品信息，是否已经存在
            if sku_id in cart_dict:
                orgin_count = cart_dict[sku_id]
                count += orgin_count

            # 再次判断库存是否超出
            if count > sku.stock:
                return JsonResponse({'code': 5, 'message': '库存不足'})

            cart_dict[sku_id] = count

            # 在写入cookie之前，将cart_dict转出json字符串
            new_cart_json = json.dumps(cart_dict)

            # 为了方便前端展示最新的购物车数量
            cart_num = 0
            for val in cart_dict.values():
                cart_num += val

            # 创建response
            response = JsonResponse({'code':0, 'message':'添加购物车成功', 'cart_num': cart_num})

            # 写入cookie
            response.set_cookie('cart', new_cart_json)

            return response
