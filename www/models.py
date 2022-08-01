#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import time, uuid
from orm import Model, StringField, BooleanField, TextField, IngeterField, FloatField


# 生成唯一的id 参考https://docs.python.org/zh-cn/3.9/library/uuid.html#module-uuid
# 该字符串含义为从当前时间取十五位整数，前缀一个0，加上uuid后缀3个0
def next_id():
    return '%015d%s000' % (int(time.time() * 1000), uuid.uuid4().hex)


# 创建user表对应的类，类属性有id/email/passwd/admin/name/image/creat_at(记录创建时间)
class User(Model):
    '''def __init__(self,**kw):
        self.id = kw.get('id',None)
        self.email = kw.get('email',None)
        self.passwd = kw.get('passwd',None)
        self.admin = kw.get('admin',None)
        self.name = kw.get('name',None)
        self.image = kw.get('image',None)
        self.created_at = kw.get('created_at',None)
        super().__init__(**kw)'''

    __table__ = 'users'

    id = StringField(primary_key=True, default=next_id, ddl='varchar(50)')
    email = StringField(ddl='varchar(50)')
    passwd = StringField(ddl='varchar(50)')
    admin = BooleanField()
    name = StringField(ddl='varchar(50)')
    image = StringField(ddl='varchar(500)')
    created_at = FloatField(default=time.time)

# 创建blog表对应的类，外键为user_id等(没有外键约束，全靠程序控制)，类属性有id/user_id/user_name/user_image/name/summary/content/created_at
class Blog(Model):
    __table__ = 'blogs'

    id = StringField(primary_key=True,default=next_id,ddl='varchar(50)')
    user_id = StringField(ddl='varchar(50)')
    user_name = StringField(ddl='varchar(50)')
    user_image = StringField(ddl='varchar(500)')
    name = StringField(ddl='varchar(50)')
    summary = StringField(ddl='varchar(200)')
    content = TextField()
    created_at = FloatField(default=time.time)
    '''    def __init__(self,**kw):
            self.id = kw.get('id',None)
            self.user_id = kw.get('user_id',None)
            self.user_name = kw.get('user_name',None)
            self.user_image = kw.get('user_image',None)
            self.name = kw.get('name',None)
            self.summary = kw.get('summary',None)
            self.content = kw.get('content',None)
            self.created_at = kw.get('created_at',None)
            super().__init__(**kw)'''


# 创建Comment表对应的类，外键为blog_id/user_id等，类属性有id/blog_id/user_id/user_name/user_image/content/created_at
class Comment(Model):
    '''def __init__(self,**kw):
        self.id = kw.get('id',None)
        self.user_id = kw.get('user_id',None)
        self.user_name = kw.get('user_name',None)
        self.user_image = kw.get('user_image',None)
        self.blog_id = kw.get('blog_id',None)
        self.content = kw.get('content',None)
        self.created_at = kw.get('created_at',None)
        super().__init__(**kw)'''

    __table__  = 'comments'
    id = StringField(primary_key=True,default=next_id,ddl='varchar(50)')
    blog_id = StringField(ddl='varchar(50)')
    user_id = StringField(ddl='varchar(50)')
    user_name = StringField(ddl='varchar(50)')
    user_image = StringField(ddl='varchar(500)')
    content = TextField()
    created_at = FloatField(default=time.time)
