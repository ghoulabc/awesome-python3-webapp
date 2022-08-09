L = [{'name':'jkw'},{'gender':'male'}]
json ={}

def m(x):
    global json
    json[list(x.keys())[0]]=list(x.values())[0]
    return

(list(map(m,L)))

print(json)