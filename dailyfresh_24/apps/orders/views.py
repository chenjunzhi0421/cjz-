from django.shortcuts import render, redirect
from django.views.generic import View
from utils.views import LoginRequiredMixin, LoginRequiredJSONMixin, TransactionAtomicMiXin
from django.core.urlresolvers import reverse
from goods.models import GoodsSKU
from django_redis import get_redis_connection
from users.models import Address
from django.http import JsonResponse
from orders.models import OrderGoods, OrderInfo
from django.utils import timezone
from django.db import transaction
from django.core.paginator import Paginator, EmptyPage
from alipay import AliPay
from django.conf import settings
# Create your views here.


class CommentView(LoginRequiredMixin, View):
    """评论页"""
    def get(self, request, order_id):
        """提供评论页面"""
        user = request.user
        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist:
            return redirect(reverse('order:info'))

        order.status_name = OrderInfo.ORDER_STATUS[order.status]
        order.skus = []
        order_skus = order.ordergoods_set.all()
        for order_sku in order_skus:
            sku = order_sku.sku
            sku.count = order_sku.count
            sku.amount = sku.price * sku.count
            order.skus.append(sku)

        return render(request, 'order_comment.html', {'order':order})

    def post(self, request, order_id):
        """处理评论内容"""
        user = request.user

        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist:
            return redirect(reverse('orders:info'))

        # 获取评论条数
        total_count = request.POST.get('total_count')
        total_count = int(total_count)

        for i in range(1, total_count + 1):
            sku_id = request.POST.get('sku_%d' % i)
            content = request.POST.get('content_%d' % i, '')

            try:
                order_goods = OrderGoods.objects.get(order=order, sku_id=sku_id)
            except OrderGoods.DoesNotExist:
                continue

            order_goods.comment = content
            order_goods.save()

        order.status = OrderInfo.ORDER_STATUS_ENUM['FINISHED']

        order.save()

        return redirect(reverse('orders:info', kwargs={'page':1}))


class CheckPayView(LoginRequiredJSONMixin, View):
    """对接支付宝查询的接口"""
    def get(self, request):
        """查询订单状态，保存支付宝返回的支付宝维护的订单id（trade_id），修改订单的状态为待评价"""

        # 接收订单的id
        order_id = request.GET.get('order_id')
        # 校验order_id
        if not order_id:
            return JsonResponse({'code': 2,'message': '缺少订单id'})
        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=request.user,
                                          status=OrderInfo.ORDER_STATUS_ENUM['UNPAID'],
                                          pay_method=OrderInfo.PAY_METHODS_ENUM['ALIPAY']
                                          )
        except OrderInfo.DoesNotExist:
            return JsonResponse({'code': 3, 'message':'订单不存在'})

        # 创建alipay对象
        alipay = AliPay(
            appid=settings.ALIPAY_APPID,
            app_notify_url=None,
            app_private_key_path=settings.APP_PRIVATE_KEY_PATH,
            alipay_public_key_path=settings.ALIPAY_PUBLIC_KEY_PATH,
            sign_type="RSA2",
            debug=True
        )
        while True:
            # 调用查询接口
            response = alipay.api_alipay_trade_query(order_id)

            # 读取code.trade_status,判断订单状态
            code = response.get('code')
            trade_status = response.get('trade_status')

            # 判断订单状态
            if code == '10000' and trade_status == 'TRADE_SUCCESS':
                order.trade_id = response.get('trade_no')
                order.status = OrderInfo.ORDER_STATUS_ENUM['UNCOMMENT']
                order.save()

                return JsonResponse({'code': 0,'message': '支付成功'})

            elif code == '40004' or (code == '10000' and trade_status == 'WAIT_BUYER_PAY'):
                continue

            else:
                return JsonResponse({'code': 4,'message': '支付失败'})


class PayView(LoginRequiredJSONMixin, View):
    """对接支付宝支付接口"""
    # hrxaju5993@sandbox.com
    def post(self, request):
        """接收订单id，查询订单，对接支付宝"""
        # 接收订单id
        order_id = request.POST.get('order_id')

        # 校验订单id
        if not order_id:
            return JsonResponse({'code': 2, 'message': '缺少订单id'})

        # 查询订单信息
        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=request.user,
                                          status=OrderInfo.ORDER_STATUS_ENUM['UNPAID'],
                                          pay_method=OrderInfo.PAY_METHODS_ENUM['ALIPAY'])
        except OrderInfo.DoesNotExist:
            return JsonResponse({'code': 3, 'message': '订单不存在'})

        # 创建alipay对象
        alipay = AliPay(
            appid=settings.ALIPAY_APPID,
            app_notify_url=None,
            app_private_key_path=settings.APP_PRIVATE_KEY_PATH,
            alipay_public_key_path=settings.ALIPAY_PUBLIC_KEY_PATH,
            sign_type="RSA2",
            debug=True
        )

        # 调用支付宝的支付接口
        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order_id,
            total_amount=str(order.total_amount),
            subject='天天生鲜',
            return_url=None,
            notify_url=None
        )

        # 生成打开支付宝的url
        url = settings.ALIPAY_URL + "?" + order_string

        # 响应url给ajax
        return JsonResponse({'code':0, 'message':'支付成功', 'url':url})


class UserOrderView(LoginRequiredMixin, View):
    """用户订单页面"""

    def get(self, request, page):
        """提供订单信息页面"""

        user = request.user

        # 查询所有订单数据

        orders = user.orderinfo_set.all().order_by('-create_time')

        # 遍历所有的订单
        for order in orders:

            # 给订单动态绑定：订单状态
            order.status_name = OrderInfo.ORDER_STATUS[order.status]

            # 给订单动态绑定： 支付方法
            order.pay_method_name = OrderInfo.PAY_METHODS[order.pay_method]

            order.skus = []

            # 查询订单中所有的商品
            order_skus = order.ordergoods_set.all()

            # 遍历订单中所有的商品
            for order_sku in order_skus:
                sku = order_sku.sku
                sku.count = order_sku.count
                sku.amount = sku.price * sku.count
                order.skus.append(sku)

        # 分页
        page = int(page)

        try:
            paginator = Paginator(orders, 2)
            page_orders = paginator.page(page)
        except EmptyPage:
            # 如果传入的页数不存在，就默认给第一页
            page_orders = paginator.page(1)
            page = 1

        # 页数
        page_list = paginator.page_range

        # 构造上下文
        context = {
            'orders': page_orders,
            'page': page,
            'page_list': page_list
        }

        # 渲染模板
        return render(request, 'user_center_order.html', context)


class CommitOrderView(LoginRequiredJSONMixin, TransactionAtomicMiXin, View):
    """订单提交"""
    def post(self, request):
        """接受用户提交订单的参数，保存数据到OrderInfo和OrderGoods中，渲染模板"""

        # 获取参数：user, address_id, pay_method,sku_ids,count
        user = request.user

        address_id = request.POST.get('address_id')

        pay_method = request.POST.get('pay_method')

        sku_ids = request.POST.get('sku_ids')


        # 校验参数：all([address_id, pay_method,sku_ids])
        if not all([address_id, pay_method, sku_ids]):
            return JsonResponse({'code': 2,'message': '缺少参数'})

        # 判断地址
        try:
            address = Address.objects.get(id=address_id)
        except Address.DoesNotExist:
            return JsonResponse({'code': 3,'message': '地址错误'})

        # 判断支付方式
        if pay_method not in OrderInfo.PAY_METHOD:
            return JsonResponse({'code': 4, 'message': '支付方式错误'})

        # 操作redis
        redis_conn = get_redis_connection('default')

        # 手动生成order_id
        order_id = timezone.now().strftime('%Y%m%d%H%M%S') + str(user.id)

        # 在操作数据库前创建事务保存点
        save_point = transaction.savepoint()

        try:
            # 创建OrederInfo
            order = OrderInfo.objects.create(
                order_id=order_id,
                user=user,
                address=address,
                total_amount=0,
                trans_cost=10,
                pay_method=pay_method,
            )

            # 截取出sku_ids列表
            sku_ids = sku_ids.split(',')

            # 定义临时变量
            total_count = 0
            total_sku_amount = 0

            # 遍历sku_ids
            for sku_id in sku_ids:
                # 循环取出sku，判断商品是否存在
                for i in range(3):
                    try:
                        sku = GoodsSKU.objects.get(id=sku_id)
                    except GoodsSKU.DoesNotExist:

                        # 回滚异常
                        transaction.savepoint_rollback(save_point)

                        return JsonResponse({'code': 5, 'message': '商品不存在'})

                    # 获取商品数量，判断库存(redis)
                    sku_count = redis_conn.hget('cart_%s' % user.id, sku_id)
                    sku_count = int(sku_count)

                    # 验证库存
                    if sku_count > sku.stock:

                        # 回滚异常
                        transaction.savepoint_rollback(save_point)

                        return JsonResponse({'code': 6, 'message': '库存不足'})

                    # 计算小计
                    amount = sku_count * sku.price

                    # 减少sku库存
                    # sku.stock -= sku_count

                    # 增加sku销量
                    # sku.sales += sku_count
                    # sku.save()

                    # 减少库存,增加销量
                    origin_stock = sku.stock
                    new_stock = origin_stock - sku_count
                    new_sales = sku.sales + sku_count

                    # 更新库存和销量
                    result = GoodsSKU.objects.filter(id=sku_id, stock=origin_stock).update(stock=new_stock,sales=new_sales)
                    if 0 == result and i < 2:
                        continue
                    elif 0 == result and i == 2:
                        transaction.savepoint_rollback(save_point)
                        return JsonResponse({'code': 8,'message': '下单失败'})

                    # 保存订单商品数据OrderGoods(能执行到这里说明无异常)
                    # 先创建商品订单信息
                    OrderGoods.objects.create(
                        order=order,
                        sku=sku,
                        count=sku_count,
                        price=sku.price
                    )

                    # 计算总数和总金额
                    total_count += sku_count
                    total_sku_amount += amount

                    # 下单成功，跳出循环
                    break

            # 修改订单信息里面的总数和总金额(OrderInfo)
            order.total_count = total_count
            order.total_amount = total_sku_amount + 10
            order.save()

        except Exception:
            transaction.savepoint_rollback(save_point)
            return JsonResponse({'code': 7, 'message': '下单失败'})

        # 没有异常，就手动提交
        transaction.savepoint_commit(save_point)


        # 订单生成后删除购物车(hdel)
        # for sku_id in sku_ids:
        #     redis_conn.hdel('cart_%s' % user.id, sku_id)

        redis_conn.hdel('cart_%s' % user.id, *sku_ids)

        # 响应结果
        return JsonResponse({'code': 0, 'message': '下单成功'})


class PlaceOrderView(LoginRequiredMixin, View):
    """订单确认"""
    def post(self, request):
        """购物车去结算和商品详情页面点击立即购买进入订单确认页面"""

        # 判断用户是否登陆：LoginRequiredMixin
        # 获取参数：sku_id和count
        sku_ids = request.POST.getlist('sku_ids')  # sku_ids是一健多值
        count = request.POST.get('count')

        # 校验sku_id参数：not
        if not sku_ids:
            return redirect(reverse('cart:info'))

        # 商品的数量从redis中获取
        redis_conn = get_redis_connection('default')
        user_id = request.user.id

        # 定义临时变量
        skus = []
        total_count = 0
        total_sku_amount = 0
        trans_cost = 10
        # 校验count参数：用于区分用户是从哪进入订单确认页面的
        if count is None:
            # 如果是从购物车页面过来的
            cart_dict = redis_conn.hgetall('cart_%s' % user_id)

            # 查询商品数据
            for sku_id in sku_ids:
                try:
                    sku = GoodsSKU.objects.get(id=sku_id)
                except GoodsSKU.DoesNotExist:
                    return redirect(reverse('cart:info'))

                sku_count = cart_dict[sku_id.encode()]
                sku_count = int(sku_count)

                # 计算小计
                sku_amount = sku_count * sku.price

                # 给动态的sku对象绑定count和amount
                sku.count = sku_count
                sku.amount = sku_amount

                # 记录sku信息
                skus.append(sku)

                # 累加总数量和总金额
                total_count += sku_count
                total_sku_amount += sku_amount

        else:
            # 如果是从商品详情页面请求过来的
            # 查询商品数据
            for sku_id in sku_ids:
                try:
                    sku = GoodsSKU.objects.get(id=sku_id)
                except GoodsSKU.DoesNotExist:
                    return redirect(reverse('cart:info'))

                # 商品的数量是从request中获取，并try校验
                try:
                    sku_count = int(count)
                except Exception:
                    return redirect(reverse('goods:detail', args=(sku_id,)))

                # 判断库存
                if sku_count > sku.stock:
                    return redirect(reverse('goods:detail', args=(sku_id,)))

                # 计算小计
                sku_amount = sku_count * sku.price

                sku.count = sku_count
                sku.amount = sku_amount
                skus.append(sku)

                # 累加总数量和总金额
                total_count += sku_count
                total_sku_amount += sku_amount

                # 当用户点击立即购买，进入该页面时，将商品存储到redis中
                redis_conn.hset('cart_%s' % user_id, sku_id, sku_count)

        # 计算实付款
        total_amount = trans_cost + total_sku_amount

        # 查询用户地址信息
        try:
            address = Address.objects.filter(user=request.user).latest('create_time')
        except Address.DoesNotExist:
            address = None


        # 构造上下文
        context = {
            'skus': skus,
            'total_count': total_count,
            'total_sku_amount': total_sku_amount,
            'total_amount': total_amount,
            'address': address,
            'trans_cost': trans_cost,
            'sku_ids': ','.join(sku_ids)
        }
        # 渲染模板
        return render(request, 'place_order.html', context)