"""HTML tree helpers for populating the actual SkillsBench report template."""
import html
from html.parser import HTMLParser

VOID = {'meta','link','input','br','hr','img','source','wbr'}


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def all(self, selector):
        def match(n):
            if selector.startswith('#'):return n.attrs.get('id') == selector[1:]
            if selector.startswith('.'):return selector[1:] in n.attrs.get('class','').split()
            return n.tag == selector
        found=[]
        for n in self.children:
            if isinstance(n,Node):
                if match(n):found.append(n)
                found.extend(n.all(selector))
        return found

    def one(self, selector):return self.all(selector)[0]
    def text(self, value):self.children=[html.escape(str(value))]
    def content(self, value):self.children=parse(value).children
    def render(self):
        body=''.join(x.render() if isinstance(x,Node) else x for x in self.children)
        if not self.tag:return body
        attrs=''.join(f' {k}="{html.escape(str(v),quote=True)}"' if v is not None else f' {k}' for k,v in self.attrs.items())
        return f'<{self.tag}{attrs}>'+('' if self.tag in VOID else body+f'</{self.tag}>')


class Parser(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=False);self.root=Node();self.stack=[self.root]
    def handle_starttag(self,tag,attrs):
        n=Node(tag,attrs);self.stack[-1].children.append(n)
        if tag not in VOID:self.stack.append(n)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag:self.stack=self.stack[:i];break
    def handle_data(self,data):self.stack[-1].children.append(data)
    def handle_entityref(self,name):self.handle_data('&'+name+';')
    def handle_charref(self,name):self.handle_data('&#'+name+';')
    def handle_decl(self,decl):self.handle_data('<!'+decl+'>')
    def handle_comment(self,data):self.handle_data('<!--'+data+'-->')


def parse(text):
    p=Parser();p.feed(text);return p.root


def pct(x):return f'{x:+.1f}%'
def pv(x):return f'{x:.3f}' if x >= .001 else f'{x:.2e}'
def tone(x):return '' if abs(x)<.05 else 'good' if x<0 else 'bad'


