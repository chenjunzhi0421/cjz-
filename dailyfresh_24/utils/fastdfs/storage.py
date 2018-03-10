from django.core.files.storage import Storage
from fdfs_client.client import Fdfs_client
from django.conf import settings


class FastDFSStorage(Storage):
    """实现Django上传静态文件到fdfs， 提供给运维使用的"""
    def __init__(self, client_conf=None, server_ip=None):
        """初始化"""
        if client_conf is None:
            client_conf = settings.CLIENT_CONF
        self.client_conf = client_conf

        if server_ip is None:
            server_ip = ''
        self.server_ip = settings.SERVER_IP

    def _open(self, name, mode='rb'):
        """打开文件时使用的，此处不是打开文件，而是存储文件到fdfs"""
        pass

    def _save(self, name, content):
        """存储文件时用的：name 表示要上传文件名字， content表示File类型的对象，通过实例方法read（）可以读取文件内容"""

        # 创建client对象
        client = Fdfs_client(self.client_conf)

        # 获取上传文件的内容
        file_data = content.read()

        # 调用上传的方法，通过文件内容上传，接收上传后的返回值
        try:
            ret = client.upload_appender_by_buffer(file_data)
        except Exception as e:
            print(e)  # 方便自己调试
            raise   # 捕获到什么异常，就抛出什么异常
        # 判断是否上传成功
        if ret.get('Status') == 'Upload successed.':
            # 上传成功， 读取file_id,完成存储到mysql
            file_id = ret.get('Remote file_id')
            # 如果运维当前在操作GoodsCategory模型类，那么我们的Storage会自动的把返回值file_id,存储到GoodsCategory模型类
            return file_id
        else:
            # 上传失败
            raise Exception('上传失败')

    def exists(self, name):
        """判断文件是否存储在系统当中，如果文件返回True，否则返回False"""
        return False  # 告诉django文件不存在，就可以继续执行_save()

    def url(self, name):
        """可以返回要下载的文件的全路径，提供给用户下载时使用"""
        # name就是要下载的文件的名字，将来会把从数据库中查询出来的file_id传入到url方法中
        return self.server_ip + name