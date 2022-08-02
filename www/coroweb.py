import functools,asyncio,os,inspect,logging

from urllib import parse

from aiohttp import web



# 创建http方法通常使用的get和post的装饰器，用来给响应这两个方法的url函数补全url
def get(path):
    '''Define decorator @get('/path')'''
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args,**kw):
            return func(*args,**kw)
        wrapper.__method__ = 'GET'
        wrapper.__route__ = path
        return wrapper
    return decorator


def post(path):
    '''Define decorator @post('/path/)'''
    def decorator(func):
        functools.wraps(func)
        def wrapper(*args,**kw):
            return func(*args,**kw)
        wrapper.__method__ = 'POST'
        wrapper.__path__ = 'path'
        return wrapper
    return decorator

#从fn中获取无默认值的命名关键字参数
def get_required_kw_args(fn):
    args = []
    params = inspect.signature(fn).parameters
    for name,param in params.items():
        if param.kind ==inspect.Parameter.KEYWORD_ONLY and param.default == inspect.Parameter.empty:
            args.append(name)
    return tuple(args)

#从fn中获取命名关键字参数
def get_named_kw_args(fn):
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind ==inspect.Parameter.KEYWORD_ONLY:
            args.append(name)
            return tuple(args)

#判断fn是否有命名关键字参数
def has_named_kw_args(fn):
    params = inspect.signature(fn).parameters
    for name,param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            return True

# 判断fn是否有关键字参数
def has_var_kw_arg(fn):
    params = inspect.signature(fn).parameters
    for name,param in params.items():
        if param.kind ==inspect.Parameter.VAR_KEYWORD:
            return True

#对于非get类的request，如果没有找到request参数，报错
def has_request_arg(fn):
    sig = inspect.signature(fn)
    params= sig.parameters
    found = False
    for name,param in params.items():
        if name =='request':
            found = True
            continue
        if found and (param.kind != inspect.Parameter.VAR_POSITIONAL
                      and param.kind != inspect.Parameter.KEYWORD_ONLY
                      and param.kind != inspect.Parameter.VAR_KEYWORD):
            raise ValueError('request parameter must be the last named parameter in function:%s%s' % (fn.__name__,str(sig)))
    return found


#handler对象，用于集约式定义handler行为
# 参考https://docs.aiohttp.org/en/stable/web_quickstart.html#organizing-handlers-in-classes
class RequestHandler(object):
    # 初始化响应函数对象，传入参数函数名
    def __init__(self,app,fn):
        self._app = app
        self._func = fn
        self._has_request_arg = has_request_arg(fn)
        self._has_var_kw_arg = has_var_kw_arg(fn)
        self._has_named_kw_args = has_named_kw_args(fn)
        self._named_kw_args = get_named_kw_args(fn)
        self._required_kw_args = get_required_kw_args(fn)

    # 将实例定制为可调用函数，并集中解析请求信息，将解析结果传给响应函数
    # 响应函数根据传入信息生成视图，发送响应
    async def __call__(self,request):
        kw = None
        #如果响应函数接受了关键字参数，命名关键字参数，和有默认值的命名关键字参数，判断是get方法还是post方法
        #根据方法加工参数，并传入fn
        if self._has_var_kw_arg or self._has_named_kw_args or self._required_kw_args:
            if request.method == 'POST':
                if not request.content.type:
                    return web.HTTPBadRequest(body='Missing Content_type.')
                ct = request.content_type.lower()
                if ct.startswith('application/json'):
                    params = await request.json()
                    if not isinstance(params,dict):
                        return web.HTTPBadRequest(body='JSON body must be object.')
                    kw = params
                elif ct.startswith('application/x-www-form-urlencoded') or ct.startswith('multipart/form-data'):
                    params = await request.post()
                    kw = dict(**params)
                else:
                    return web.HTTPBadRequest(body='Unsupported Content-Type: %s.' % request.content.type)
            if request.method == 'GET':
                qs = request.query_string
                if qs:
                    kw = dict()
                    for k,v in parse.parse_qs(qs,True).items():
                        kw[k] = v[0]
        if kw is None:
            kw = dict(**request.match_info)
        else:
            if not self._has_var_kw_arg and self._named_kw_args:
                # remove all unamed kw:
                copy = dict()
                for name in self._named_kw_args:
                    if name in kw:
                        copy[name] = kw[name]
                kw = copy
            # check named arg:
            for k,v in request.match_info.items():
                if k in kw:
                    logging.warning('Duplicate arg name in named arg and kw args: %s' % k)
                kw[k] = v
        if self._has_request_arg:
            kw['request'] = request
        # check required kw:
        if self._required_kw_args:
            for name in self._required_kw_args:
                if not name in kw:
                    return web.HTTPBadRequest(body='Missing argument: %s' % name)
        logging.info('call with args: %s' % str(kw))
        try:
            r = await  self._func(**kw)
            return r
        except APIError as e:
            return dict(error=e.error,data=e.data,message=e.message)


# 定义子调度函数，检查响应函数后建立响应函数对象
def add_route(app,fn):
    method  = getattr(fn,'__method__',None)
    path =getattr(fn,'__route__',None)
    if path is None or method is None:
        raise ValueError('@get or @post not defined in %s' % str(fn))
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        fn =asyncio.coroutine(fn)
    logging.info('add route %s %s => %s(%s)' % (method ,path,fn.__name__,
                                                ', '.join(inspect.signature(fn).parameters.keys())))
    app.router.add_route(method,path,RequestHandler(app,fn))


#总调度函数，取request
def add_routes(app,module_name):
    n = module_name.rfind('.')
    if n ==(-1):
        #导入分配模组
        mod = __import__(module_name,globals(),locals())
    else:
        name = module_name[n+1:]
        mod = getattr(__import__(module_name[:n],globals(),locals(),[name]),name)
    for attr in dir(mod):
        if attr.startswith('_'):
            continue
        #获取模组中的方法
        fn = getattr(mod,attr)
        if callable(fn):
            method =getattr(fn,'__method__',None)
            path = getattr(fn,'__route__',None)
            #如果是响应函数，转入子调度函数
            if method and path:
                add_route(app,fn)


# 添加静态文件 如css
# https://docs.aiohttp.org/en/stable/web_advanced.html#static-file-handling
def add_static(app):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),'static')
    app.route1.add_static('/static/',path)
    logging.info('add static %s=>%s' % ('/static/',path))