"""Rules-first brand extraction from a public HTML site."""
from __future__ import annotations
import re, urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin

COLOR=re.compile(r"#(?:[0-9a-fA-F]{3,4}){1,2}\b"); FONT=re.compile(r"font-family\s*:\s*([^;}]+)",re.I)
class P(HTMLParser):
 def __init__(self): super().__init__(); self.css=[]; self.img=[]; self.icon=[]; self.theme=""
 def handle_starttag(self,t,a):
  d={k:(v or "") for k,v in a}
  if t=="link":
   rel=d.get("rel","").lower(); h=d.get("href","");
   if "stylesheet" in rel and h:self.css.append(h)
   if "icon" in rel and h:self.icon.append(h)
  if t=="meta" and d.get("name","").lower()=="theme-color":self.theme=d.get("content","")
  if t=="img":self.img.append((d.get("src","") ,d.get("alt","")+" "+d.get("class","")))
def fetch(url):
 req=urllib.request.Request(url,headers={"User-Agent":"PostMeet-Brand/1.0"}); return urllib.request.urlopen(req,timeout=25).read().decode("utf-8","replace")
def extract(site_url:str)->dict:
 text=fetch(site_url); p=P(); p.feed(text); blobs=[text]
 for h in p.css[:8]:
  try: blobs.append(fetch(urljoin(site_url,h)))
  except Exception: pass
 colors=[]
 for b in blobs: colors.extend(COLOR.findall(b))
 primary=p.theme or (colors[0] if colors else ""); unique=[]
 for c in colors:
  if c.lower() not in {x.lower() for x in unique} and c.lower() not in {"#fff","#ffffff","#000","#000000"}: unique.append(c)
 if not primary and unique: primary=unique[0]
 fonts=[]
 for b in blobs:
  fonts += [m.group(1).strip().split(",")[0].strip(" '\"") for m in FONT.finditer(b)]
 logo=""
 for src,hint in p.img:
  if re.search(r"logo|brand|site-title|navbar-brand",src+" "+hint,re.I): logo=urljoin(site_url,src); break
 return {"source_site":site_url,"primary":primary,"secondary":unique[1] if len(unique)>1 else "","accent":unique[2] if len(unique)>2 else "","font_body":fonts[0] if fonts else "","font_display":fonts[1] if len(fonts)>1 else (fonts[0] if fonts else ""),"logo_url":logo,"icons":[urljoin(site_url,x) for x in p.icon[:5]],"method":"rules-css-html"}
