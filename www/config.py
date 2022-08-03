import config_default

# config.py
configs = config_default.configs

#自定义字典类型，用来给字典类型提供动态加载属性功能
class Dict(dict):
    def __init__(self,names=(),values=(),**kw):
        super().__init__(**kw)
        for k,v in zip(names,values):
            self[k] = v

    def __getattr__(self,key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Dict' object has no attribute '%s'" % key)

    def __setattr__(self,key,value):
        self[key] = value

# 设置合并规则，用override的数据覆写default，overrider没有的部分沿用default
def merge(defaults,override):
    r = {}
    for k,v in defaults.items():
        if k in override:
            if isinstance(v,dict):
                r[k] = merge(v,override[k])
            else:
                r[k] = override[k]
        else:
            r[k] = v
    return r

# 建立类型转换函数，用于把configs及其内部嵌套的字典都转换为自定义字典类型
def toDict(d):
    D=Dict()
    for k,v in d.items():
        D[k] = toDict(v) if isinstance(v,dict) else v
    return D


try:
    import config_override
    configs = merge(configs, config_override.configs)
except ImportError:
    pass


configs = toDict(configs)