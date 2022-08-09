#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Michael Liao'

' url handlers '
from aiohttp import web
import re, time, json, logging, hashlib, base64, asyncio
from config import configs
from coroweb import get, post
from apis import APIValueError, APIResourceNotFoundError,APIError,APIPermissionError,Page
from models import User, Comment, Blog, next_id
import markdown2

_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')
COOKIE_NAME = 'awesession'
_COOKIE_KEY = configs.session.secret

# 处理request附带的page参数，解析为整数
def get_page_index(page_str):
    p = 1
    try:
        p = int(page_str)
    except ValueError as e:
        pass
    if p < 1:
        p = 1
    return p

# 将sql搜索到的文章本文转化为html格式的段落文本
def text2html(text):
    lines = map(lambda s: '<p>%s</p>' % s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'), filter(lambda s: s.strip() != '', text.split('\n')))
    return ''.join(lines)


# 检查request是否是由管理员发出的
def check_admin(request):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError()



# 从用户的数据库id和生成的摘要产生时效性的识别码
def user2cookie(user,max_age):
    # 根据用户信息创建session
    expires = str(int(time.time() + max_age))
    s = '%s-%s-%s-%s' % (user.id,user.passwd,expires,_COOKIE_KEY)
    L = [user.id,expires,hashlib.sha1(s.encode('utf-8')).hexdigest()]
    s = '-'.join(L)
    return s

async def cookie2user(cookie_str):
    # 将解析接收的request拿到cookie，判断cookie的时效性和真伪
    # 并从中识别用户将用户返回为request的属性，使handler能够从中读取
    if not cookie_str:
        return None
    try:
        #判断cookie是否符合格式
        L = cookie_str.split('-')
        if len(L) !=3:
            return None
        uid,expires,sha1 = L
        # 判断cookie是否在时效内
        if int(expires) < time.time():
            return None
        user = await User.find(uid)
        # 判断cookie是否是真实的
        if user is None:
            return None
        s = '%s-%s-%s-%s' % (uid,user.passwd,expires,_COOKIE_KEY)
        # 判断cookie是否是真实的
        if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
            logging.info('invalid sha1')
            return None
        user.passwd = '******'
        return user
    except Exception as e:
        logging.exception(e)
        return None


# url为主页的request将被分配到该响应函数
@get('/')
async def index(*, page='1'):
    page_index = get_page_index(page)
    num = await Blog.findNumber('count(id)')
    page = Page(num, page_index)
    if num == 0:
        blogs = []
    else:
        blogs = await Blog.findAll(orderBy='created_at desc', limit=(page.offset, page.limit))
    return {
        '__template__': 'blogs.html',
        'page': page,
        'blogs': blogs,
    }

# 注册页面，注册按钮绑定的ajax将分配到该响应函数
@post('/api/users')
async def api_register_user(*,email,name,passwd):
    if not name or not name.strip():
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    if not passwd or not _RE_SHA1.match(passwd):
        raise APIValueError('passwd')
    users = await User.findAll('email=?',[email])
    #如果用户已存在，返回错误
    if len(users) > 0 :
        raise APIError('register:failed','email',message='Email is already in use.')
    uid = next_id()
    sha1_passwd = '%s:%s' % (uid, passwd)
    user = User(id=uid,name=name.strip(),email=email,
                passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(),
                image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
    await user.save()
    #创建session cookie，由用户分配到的id，生成的摘要生成时效性的用户识别码
    r = web.Response()
    r.set_cookie(COOKIE_NAME,user2cookie(user,86400),max_age=86400,httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user,ensure_ascii=False).encode('utf-8')
    return r


@get('/api/users')
async def api_get_users(*, page='1'):
    page_index = get_page_index(page)
    num = await User.findNumber('count(id)')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, users=())
    users = await User.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    for u in users:
        u.passwd = '******'
    return dict(page=p, users=users)


# url为注册页面的request将被引导到该响应函数
@get('/register')
async def register():
    return {
        '__template__': 'register.html'
    }


# url为登录页面的request将被引导到该响应函数
@get('/signin')
def signin():
    return{
        '__template__':'signin.html'
    }


# 登录按钮绑定的ajax将被引导到该响应函数
@post('/api/authenticate')
async def authenticate(*,email,passwd):
    # 检查post的参数是否完整
    if not email:
        raise APIValueError('email','Invalid email.')
    if not passwd:
        raise APIValueError('passwd','Invalid passwd.')
    users = await User.findAll('email=?', [email])
    # 检查用户是否存在
    if len(users) == 0:
        raise APIValueError('email','Email not exist.')
    user = users[0]
    #检查密码是否正确
    sha1 = hashlib.sha1()
    sha1.update(user.id.encode('utf-8'))
    sha1.update(b':')
    sha1.update(passwd.encode('utf-8'))
    if user.passwd != sha1.hexdigest():
        raise APIValueError('passwd','Invalid passwd')
    # 确认密码和用户名匹配后，根据当前时间建立cookie
    r = web.Response()
    r.set_cookie(COOKIE_NAME,user2cookie(user,86400),max_age=86400,httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user,ensure_ascii=False).encode('utf-8')
    return r


# 退出登录按钮绑定的ajax将被引导到该响应函数
@get('/signout')
def signout(request):
    # 找到向导url，返回向导url
    referer = request.headers.get('Referer')
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME,'_deleted_',max_age=0,httponly=True)
    logging.info('user signed out.')
    return r

@get('/manage/users')
def manage_users(*, page='1'):
    return {
        '__template__': 'manage_users.html',
        'page_index': get_page_index(page)
    }


@get('/manage/blogs/create')
def manage_create_blog():
    return {
        '__template__': 'manage_blog_edit.html',
        'id': '',
        'action': '/api/blogs'
    }

# 从提交文章按钮ajax发送的request将被引导到该响应函数
@post('/api/blogs')
async def api_create_blog(request, *, name, summary, content):
    # 检查文章三要素是否具备
    check_admin(request)
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'content cannot be empty.')
    # 根据post内容创建blog对象，并保存到数据库
    blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image, name=name.strip(), summary=summary.strip(), content=content.strip())
    await blog.save()
    return blog


# 翻页按钮ajax触发的request被引导到该响应函数
# 从根据页数计算已翻过数量，从数据库中查找下一页条目
@get('/api/blogs')
async def api_blogs(*,page='1'):
    page_index = get_page_index(page)
    # 查找文章总数
    num = await Blog.findNumber('count(id)')
    p = Page(num,page_index)
    if num == 0:
        return dict(page=p,blogs=())
    blogs = await Blog.findAll(orderBy='created_at desc', limit=(p.offset,p.limit))
    return dict(page=p,blogs=blogs)


@get('/api/blogs/{id}')
async def api_get_blog(*, id):
    blog = await Blog.find(id)
    return blog

# 从管理文章页面url发来的request由该响应函数处理
@get('/manage/blogs')
def manage_blogs(*,page='1'):
    return {
        '__template__': 'manage_blogs.html',
        'page_index': get_page_index(page)
    }


# 以文章id为url的request将被引导到该响应函数
@get('/blog/{id}')
async def get_blog(id):
    # 根据文章id获取相应文章及其评论
    blog = await Blog.find(id)
    comments = await Comment.findAll('blog_id=?',[id],orderBy='created_at')
    for c in comments:
        c.html_content = text2html(c.content)
    blog.html_content = markdown2.markdown(blog.content)
    return {
        '__template__':'blog.html',
        'blog': blog,
        'comments':comments
    }