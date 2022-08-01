import aiomysql
import logging


# ORM技术，把数据库表的结构体现在python对象的结构上：
# 即表名-类名
# 表行-类实例
# 表列-类属性
# 表值-类实例属性值

# 建立日志函数，用于记录sql操作
def log(sql, args=()):
    logging.info('SQL: %s' % sql)


# 用来创建sql语句的占位符，以传参
def create_args_string(num):
    L = []
    for n in range(num):
        L.append('?')
    return ', '.join(L)


# 异步编程的一个原则：一旦决定使用异步，则系统每一层都必须是异步，“开弓没有回头箭”，因此所有涉及io的操作均需声明为异步
# 建立创建链接池函数，用于根据用户输入建立连接池 参照 https://aiomysql.readthedocs.io/en/latest/pool.html
async def creat_pool(loop, **kw):
    logging.info('create database connection pool...')
    global _pool
    # 接收的输入为user、password、database其他为固定变量
    _pool = await aiomysql.create_pool(host=kw.get('host', '127.0.0.1'),
                                       port=kw.get('port', 3306),
                                       user=kw['user'],
                                       password=kw['password'],
                                       db=kw['db'],
                                       charset=kw.get('charset', 'utf8'),
                                       autocommit=kw.get('autocommit', True),
                                       maxsize=kw.get('maxsize', 10),
                                       minsize=kw.get('minsize', 1),
                                       loop=loop)


# 建立sql查询函数 参考 https://aiomysql.readthedocs.io/en/latest/examples.html
# 接收user对象的各种方法传来的sql语句和args参数，链接到连接池，生成游标执行语句，提交。
async def select(sql, args, size=None):
    # 记录查询语句和参数
    log(sql, args)
    global _pool
    # async with ... as ...与文件读写一样，用于保证一个协程对象执行完毕后关闭
    # 等价于a = await b \n f(a) \n a.close()
    # 与一般db-api类似，先建立连接再建立游标,只是多个异步声明
    async with _pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            # 用游标执行sql语句,将sql语句替换为mysql语句
            await cur.execute(sql.replace('?', '%s'), args or ())
            # 如果指定了获取数量就按指定数量获取，否则获取全部
            if size:
                rs = await cur.fetchmany(size)
            else:
                rs = await cur.fetchall()
            logging.info('rows returned: %s' % len(rs))
            # 因为是安全方法打开，这里不再添加await cur.close()
            return rs


# 因为insert、delete、update都是返回一个受影响的行数，所以用同一个函数可以概括
# 接收user对象的各种方法传来的sql语句和args参数，链接到连接池，生成游标执行语句，提交。
async def execute(sql, args):
    log(sql)
    async with _pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            try:
                await cur.execute(sql.replace('?', '%s'), args)
                affected = cur.rowcount
            except BaseException:
                raise
            return affected


class Modelmetaclass(type):
    def __new__(cls, name, bases, attrs):
        # 排除基类Model
        if name == 'Model':
            return type.__new__(cls, name, bases, attrs)
        # 参考 https://docs.python.org/zh-cn/3.9/library/stdtypes.html#dict.get
        tableName = attrs.get('__table__', None) or name
        logging.info('found model %s (table %s)' % (name, tableName))
        # 获取主键和定义域
        mapping = dict()
        fields = []
        primaryKey = None
        for k, v in attrs.items():
            if isinstance(v, Field):
                logging.info('found mapping %s==>%s' % (k, v))
                mapping[k] = v
                # 查找主键
                if v.primary_key:
                    # 判断之前是否已找到主键，若已有则唤起错误，没有则将查找到的键作为主键映射
                    if primaryKey:
                        raise RuntimeError('Duplicated primary key for field:%s' % k)
                    primaryKey = k
                # 将其他非主键的键放入定义域
                else:
                    fields.append(k)
        # 遍历过后一个表应当有了一个主键，否则唤起错误
        if not primaryKey:
            raise RuntimeError('Primary Key not found')
        # 将定义域清空，以免类属性和实例属性在getattr时冲突
        for k in mapping.keys():
            attrs.pop(k)
        # 创建类属性，包括映射和sql语句生成
        escaped_fields = list(map(lambda x: '`%s`' % x, fields))
        attrs['__mappings__'] = mapping
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primaryKey
        attrs['__fields__'] = fields
        # 将占位符、列名用`修饰起来，防止注入攻击
        # 这里设置将所有列名全部选择
        attrs['__select__'] = 'select `%s`, %s from `%s`' % (primaryKey, ', '.join(escaped_fields), tableName)
        attrs['__insert__'] = 'insert into `%s` (%s,`%s`) values (%s)' % (
            tableName, ', '.join(escaped_fields), primaryKey,
            create_args_string(len(escaped_fields) + 1))
        # 这里没懂为啥在里面不直接用map(lambda x: x.join(‘=？’),fields)
        attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (tableName, ', '.join(map(lambda x: '%s = ?' % (mapping.get(x).name or x), fields)), primaryKey)
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName, primaryKey)
        return type.__new__(cls, name, bases, attrs)


class Model(dict, metaclass=Modelmetaclass):
    # 继承字典的初始化方法
    def __init__(self, **kw):
        super().__init__(**kw)

    # 建立读写实例属性方法该方法赋予实例xxx.xxx （= xxx）的读写形式
    # 参考 https://docs.python.org/zh-cn/3.9/library/functions.html#getattr
    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % key)

    def getValue(self, key):
        return getattr(self, key, None)

    # 处理实例化时为空的实例属性，将其转换为类的相应属性的默认值
    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None:
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s : %s' % (key, str(value)))
                setattr(self, key, value)
        return value

    async def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        # 返回受影响的行数,语句设定一次只能插入一个记录，超过一行受影响则报错
        rows = await execute(self.__insert__, args, )
        if rows != 1:
            logging.warning('failed to insert record:affected rows: %s' % rows)

    # 对于find方法使用@classmethod是因为此时没有实例化对象，只能对类直接调用方法所以必须使用该装饰器，使函数可以以这个类本身为参数
    # 参考https://docs.python.org/zh-cn/3.9/library/functions.html#classmethod
    @classmethod
    async def find(cls, pk):
        # 根据主键查找行
        # 这里为什么要把pk写为列表？
        rs = await select('%s where %s=?' % (cls.__select__, cls.__primary_key__), [pk], 1)
        return cls(**rs[0])

    @classmethod
    async def findall(cls, where=None, args=None, **kw):
        # 根据条件查找所有符合条件的行
        # 首先判断有没有条件where
        sql = [cls.__select__]
        if where:
            sql.append('where')
            sql.append(where)
        if args is None:
            args = []
        orderBy = kw.get('orderBy', None)
        if orderBy:
            sql.append('order by')
            sql.append(orderBy)
        # 关于limit条款 参考https://www.sqlite.org/lang_select.html
        limit = kw.get('limit', None)
        if limit is not None:
            sql.append('limit')
            if isinstance(limit, int):
                sql.append('?')
                args.append(limit)
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append('?,?')
                args.append(limit)
            else:
                raise ValueError('Invalid limit value: %s' % str(limit))
        # join()可将列表参数返回为一个字符串
        rs = await select(' '.join(sql), args)
        # 在使用装饰器@classmethod的函数内，使用cls（）函数，返回一个本类型的实例
        return [cls(**r) for r in rs]

    # 不知道这个函数对应的是什么查询
    @classmethod
    async def findNumber(cls, selectField, where=None, args=None):
        sql = ['select %s _num_ from `%s`' % (selectField, cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where)
        rs = await select(' '.join(sql), args, 1)
        if len(rs) == 0:
            return None
        return rs[0]['_num_']


    # 程序规定只能按照主键为查找条件更新记录,且一次一条
    async def update(self,**kwargs):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = await execute(self.__update__, args)
        if rows != 1:
            logging.warning('failed to update record:affected rows: %s' % rows)

    # 程序设定为只能以主键为搜索条件删除记录且一次只删一条
    async def remove(self):
        args = [self.getValueOrDefault(self.__primary_key__)]
        rows = await execute(self.__delete__, args)
        if rows != 1:
            logging.warning('failed to remove record: affected rows: %s' % rows)


# 为定义域设置必绑属性列名，列数据类型、主键、默认值
# 并添加定制的输出格式
class Field(object):
    def __init__(self, name, column_type, primary_key, default):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default

    def __str__(self):
        return '<%s, %s:%s>' % (self.__class__.__name__, self.column_type, self.name)


# 建立定义域包括 字符串、文本、整数、浮点数、布尔值
class StringField(Field):
    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
        super().__init__(name, ddl, primary_key, default)


class BooleanField(Field):
    def __init__(self, name=None, default=False):
        super().__init__(name, 'boolean', False, default)


class IngeterField(Field):
    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'bigint', primary_key, default)


class FloatField(Field):
    def __init__(self, name=None, primary_key=False, default=0.0):
        super().__init__(name, 'real', primary_key, default)


class TextField(Field):
    def __init__(self, name=None, default=None):
        super().__init__(name, 'text', False, default)
