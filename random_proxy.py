import requests
from lxml import etree
import random

def random_proxy():
    
    proxy_url = "https://www.us-proxy.org/"

    rq = requests.get(proxy_url)

    dom = etree.HTML(rq.text)

    proxy_server_list = []
    for i, x in enumerate(dom.findall(".//table[@class='table table-striped table-bordered']/tbody/tr")):
        ip = x.findall(".//td")[0].text
        port = x.findall(".//td")[1].text
        server = f"{ip}:{port}"
        proxy_server_list.append(server)

    return proxy_server_list