import logging; logging.basicConfig(level=logging.INFO)
import asyncio, os, json, time
from datetime import datetime
from jinja2 import Environment,FileSystemLoader
from aiohttp import web
from coroweb import add_routes,add_static


# 和装饰器一样，如果要给中间件传参，就要增加一层返回函数，application中传入中间件
async def logger_factory(app, handler):
    async def logger(request):
        logging.info('Request: %s %s' % (request.method, request.path))
        return await handler(request)
    return logger

async def response_factory(app, handler):
    async def response(request):
        #在响应函数返回视图后进行格式化
        r = await handler(request)
        if isinstance(r,web.StreamResponse):
            return r
        if isinstance(r,bytes):
            resp = web.Response(body=r)
            resp.content_type = 'application/octet-stream'
            return resp
        if isinstance(r,str):
            resp = web.Response(body=r.encode('utf-8'))
            resp.content_type = 'text/html;charset=utf-8'
            return resp
        if isinstance(r,dict):
            template =r.get('__template__')
            if template is None:
                resp = web.Response(body=json.dumps(r,ensure_ascii=False,default=lambda x:x.__dict__).encode('utf-8'))
                resp.content_type = 'application/json;charset=utf-8'
                return resp
            else:
                resp = web.Response(body=app['__templating__'].get_template(template).render(**r).encode('utf-8'))
                resp.content_type = 'text/html;charset=utf-8'
                return resp
        if isinstance(r,int) and r >= 100 and r < 600 :
            return web.Response(r)
        if isinstance(r,tuple) and len(r) == 2:
            t,m = r
            if isinstance(t,int) and t >= 100 and t < 600:
                return web.Response(r,str(m))
        #default:
        resp = web.Response(body=str(r).encode('utf-8'))
        resp.content_type = 'text/plain;charset=utf-8'
        return resp
    return response


#创建webapp对象,添加中间件日志工厂，和响应工厂
#响应工厂用于格式化请求
async def init(loop):
    #中间件参考 https://docs.aiohttp.org/en/stable/web_advanced.html#aiohttp-web-middlewares
    #中间件在调用响应函数时被调用，它既可以在响应函数返回结果之前运行也可以之后拦截结果并加以处理并返回处理后的结果
    app = web.Application(loop=loop, middlewares=[logger_factory,response_factory])
    #init_jinja2(app,filters=dict(datetime=datetime_filter))
    #监听分发url
    add_routes(app,'handlers')
    #add_static(app)
    srv = await loop.create_server(app.make_handler(),'127.0.0.1',9000)
    #执行wepapp，设定域名、ip、端口
    logging.info('server started at http://127.0.0.1:9000')
    return srv

loop = asyncio.get_event_loop()
loop.run_until_complete(init(loop))
loop.run_forever()
