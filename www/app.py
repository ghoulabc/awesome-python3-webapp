# !/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import asyncio, os, json, time
from datetime import datetime
from aiohttp import web

logging.basicConfig(level=logging.INFO)


# webapp三大组件模组、视图、控制MVC
# 视图组件+控制组件
def index(request):
    # 增加了参数以在谷歌显示
    return web.Response(body=b'<h1>Awesome</h1>', content_type='text/html', headers={'content_type': 'text/html'})


# url分发器
def setup_routes(app):
    # 对域名和函数进行链接
    app.router.add_get('/', index)
    # 打印备注
    logging.info('server started at http://127.0.0.1:8080...')


# 创建webapp对象
app = web.Application()
setup_routes(app)
# 执行wepapp，设定域名、ip、端口
web.run_app(app, host='127.0.0.1', port=8080)
