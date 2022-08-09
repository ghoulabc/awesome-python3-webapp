import logging;logging.basicConfig(level=logging.INFO)
import asyncio, os, json, time
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from aiohttp import web
from coroweb import add_routes, add_static
from orm import create_pool
from config import configs
from handlers import cookie2user, COOKIE_NAME


# 对jinja2进行设置，并加载模板
# 参考 https://jinja.palletsprojects.com/en/3.1.x/templates/
def init_jinja2(app, **kw):
    logging.info('init jinja2...')
    options = dict(
        autoescape=kw.get('autoescape', True),
        block_start_string=kw.get('block_start_string', '{%'),
        block_end_string=kw.get('block_end_string', '%}'),
        variable_start_string=kw.get('variable_start_string', '{{'),
        variable_end_string=kw.get('variable_end_string', '}}'),
        auto_reload=kw.get('auto_reload', True)
    )
    path = kw.get('path', None)
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
    logging.info('set jinja2 template path: %s' % path)
    env = Environment(loader=FileSystemLoader(path), **options)
    filters = kw.get('filters', None)
    if filters is not None:
        for name, f in filters.items():
            env.filters[name] = f
    app['__templating__'] = env


def datetime_filter(t):
    delta = int(time.time() - t)
    if delta < 60:
        return u'1分钟前'
    if delta < 3600:
        return u'%s分钟前' % (delta // 60)
    if delta < 86400:
        return u'%s小时前' % (delta // 3600)
    if delta < 604800:
        return u'%s天前' % (delta // 86400)
    dt = datetime.fromtimestamp(t)
    return u'%s年%s月%s日' % (dt.year, dt.month, dt.day)


# 和装饰器一样，如果要给中间件传参，就要增加一层返回函数，application中传入中间件
async def logger_factory(app, handler):
    async def logger(request):
        logging.info('Request: %s %s' % (request.method, request.path))
        return await handler(request)

    return logger


async def response_factory(app, handler):
    async def response(request):
        # 在响应函数返回视图后根据响应的数据类型进行格式化和渲染
        r = await handler(request)
        if isinstance(r, web.StreamResponse):
            return r
        if isinstance(r, bytes):
            resp = web.Response(body=r)
            resp.content_type = 'application/octet-stream'
            return resp
        if isinstance(r, str):
            resp = web.Response(body=r.encode('utf-8'))
            resp.content_type = 'text/html;charset=utf-8'
            return resp
        if isinstance(r, dict):
            template = r.get('__template__')
            if template is None:
                resp = web.Response(
                    body=json.dumps(r, ensure_ascii=False, default=lambda x: x.__dict__).encode('utf-8'))
                resp.content_type = 'application/json;charset=utf-8'
                return resp
            # 将handler返回的参数写入jinja2加载的模板并响应，所有response的user信息都是在这里加载的
            else:
                r['__user__'] = request.__user__
                resp = web.Response(body=app['__templating__'].get_template(template).render(**r).encode('utf-8'))
                resp.content_type = 'text/html;charset=utf-8'
                return resp
        if isinstance(r, int) and r >= 100 and r < 600:
            return web.Response(body=r)
        if isinstance(r, tuple) and len(r) == 2:
            t, m = r
            if isinstance(t, int) and t >= 100 and t < 600:
                return web.Response(body=(t, str(m)))
        # default:
        resp = web.Response(body=str(r).encode('utf-8'))
        resp.content_type = 'text/plain;charset=utf-8'
        return resp

    return response


# request格式整形
async def data_factory(app, handler):
    async def parse_data(request):
        if request.method == 'POST':
            if request.content_type.startswith('application/json'):
                request.__data__ = await request.json()
                logging.info('request json: %s' % str(request.__data__))
            elif request.content_type.startswith('application/x-www-form-urlencoded'):
                request.__data__ = await request.post()
                logging.info('request form: %s' % str(request.__data__))
        return (await handler(request))

    return parse_data

# 从request中解析cookie获取用户信息，提交给后续handler
# 若无用户信息则跳转登录界面
async def auth_factory(app, handler):
    async def auth(request):
        logging.info('check user: %s %s' % (request.method, request.path))
        request.__user__ = None
        cookie_str = request.cookies.get(COOKIE_NAME)
        if cookie_str:
            user = await cookie2user(cookie_str)
            if user:
                logging.info('set current user: %s' % user.email)
                request.__user__ = user
        # 如果是在管理url发来的request，验证是否为管理员
        # 不是则重定向至一般登陆界面
        if request.path.startswith('/manage/') and (request.__user__ is None or not request.__user__.admin):
            return web.HTTPFound('/signin')
        return (await handler(request))
    return auth


# 创建webapp对象,添加中间件日志工厂，和响应工厂
# 响应工厂用于格式化请求
async def init(loop):
    await create_pool(loop, host=configs.db.host, port=configs.db.port, user=configs.db.user,
                      password=configs.db.password, db=configs.db.db)
    # 中间件参考 https://docs.aiohttp.org/en/stable/web_advanced.html#aiohttp-web-middlewares
    # 中间件在调用响应函数时被调用，它既可以在响应函数返回结果之前运行也可以之后拦截结果并加以处理并返回处理后的结果
    app = web.Application(loop=loop, middlewares=[logger_factory, response_factory, data_factory, auth_factory])
    init_jinja2(app, filters=dict(datetime=datetime_filter))
    # 监听分发url
    add_routes(app, 'handlers')
    # 添加静态定制css和js交互
    add_static(app)
    srv = await loop.create_server(app.make_handler(), '127.0.0.1', 9000)
    # 执行wepapp，设定域名、ip、端口
    logging.info('server started at http://127.0.0.1:9000')
    return srv


loop = asyncio.get_event_loop()
loop.run_until_complete(init(loop))
loop.run_forever()
