import requests 
import os
import re
from collections import defaultdict
from copy import deepcopy
import pickle

import pandas as pd
import numpy as np
import time

from bs4 import BeautifulSoup
from tqdm import tqdm
from user_agent import generate_user_agent, generate_navigator


# overseaTp = "1" : 해외
class Crawl_Naver_Shopping():
    def __init__(self, list_type:str = "전체"):
        if list_type == "전체":
            self.frm = "NVSHTTL"
        elif list_type == "가격비교":
            self.frm = "NVSHMDL"

        self.proxies = {
            "http": "socks5://127.0.0.1:9050",
            "https": "socks5://127.0.0.1:9050"
        }

    def create_params(self, idx:int, page_size:int, cat_id:str):
        params = {"sort" : "rel",
                  "pagingIndex" : idx,
                  "pagingSize" : page_size,
                  "viewType" : "list",
                  "productSet" : "model",
                  "catId" : cat_id,
                  "deliveryFee" : "",
                  "deliveryTypeValue" : "",
                  "frm" : self.frm,
                  "iq" : "",    
                  "eq" : "",
                  "xq" : ""}
        
        return params


    def get_max_page(self, collect_num:int, page_size:int = 80):
    
        max_page = min(int(np.ceil(collect_num / page_size)), 100)
        remainder = int(collect_num % page_size)

        return max_page, remainder

    
    def merge_dict(self, org_dict:dict, new_dict:dict, type:str = "full"):
        merged_dict = deepcopy(org_dict)
        if type == "full":
            keys = pd.unique(list(org_dict.keys()) + list(new_dict.keys()))
        elif type == "left":
            keys = list(org_dict.keys())
        elif type == "right":
            keys = list(new_dict.keys())


        for key in keys:
            if isinstance(new_dict[key], list):
                merged_dict[key].extend(new_dict[key])
            else:
                merged_dict[key].append(new_dict[key])
        
        return merged_dict

    def concat_dict(self, input_dict:dict) -> str:
        temp = []
        for k, v in input_dict.items():
            v = [str(x) for x in v]
            temp.append(f"{k} : {', '.join(v)}")
        return " | ".join(temp)


    def create_productAttr(self, attr_val, char_val):
        product_attr_dict = defaultdict(list)
        for attr, char in zip(attr_val, char_val):     
            product_attr_dict[attr].append(char)

        return self.concat_dict(product_attr_dict)


    def save_images(self, img_urls, img_names, img_dir = "./image/"):
        if isinstance(img_urls, list) == False:
            img_urls = [img_urls]
        if isinstance(img_names, list) == False:
            img_names = [img_names]
        
        if img_dir is None:
            img_dir = f"./image/"
        
        if not os.path.exists(img_dir):
            os.makedirs(img_dir)

        error_list = []
        for img_url, img_name in zip(img_urls, img_names):
            # image 저장
            try:
                img_rq = requests.get(img_url, verify = True)
                with open(f"{img_dir}/{img_name}", "wb") as f:
                    f.write(img_rq.content)
            except: 
                error_list.append(img_name)
                print(img_name)


    def extract_product_infos(self, rq_json:dict, collect_num:int = None, image_save:bool = True, img_dir:str = "./image/") -> dict:
    
        products_dict = defaultdict(list)
        products = rq_json["shoppingResult"]["products"]

        if collect_num is None:
            collect_num = len(products)

        for i, product in enumerate(products):
            if i == collect_num:
                break

            collect_cols = ["rank", "id", "scoreInfo", "productName", "overseaTp", "saleTp",
                            "category1Id", "category2Id", "category3Id", "category4Id",
                            "category1Name", "category2Name", "category3Name", "category4Name",
                            "maker", "makerNo", "brand", "brandNo", "price", "priceUnit", "lnchYm", 
                            "attributeValue", "characterValue", "crUrl", "imageUrl"]

            for col in collect_cols:
                products_dict[col].append(product[col])

            try: 
                products_dict["imageName"].append(product["imageUrl"].split("/")[-1])
            except:
                print(product["imageUrl"])
                
            

            attr_val = re.sub(r"_[A-Z]{1}","",product["attributeValue"]).split("|")
            char_val = product["characterValue"].split("|")
            attr_char = self.create_productAttr(attr_val, char_val)
            products_dict["productAttr"].append(attr_char)

            if image_save:
                self.save_images(img_urls=product["imageUrl"], 
                            img_names=product["imageUrl"].split("/")[-1],
                            img_dir = img_dir)
        
        return products_dict


    def get_product_infos_in_category(self, cat_ids:list, cat_levels:list, collect_num:int = None, image_save:bool = False):
        if isinstance(cat_ids, list) == False:
            cat_ids = [cat_ids]
        base_url = "https://search.shopping.naver.com/api/search/category"
        total_product_infos = defaultdict(list)

        for cat_id, cat_level in zip(cat_ids, cat_levels):
            # time.sleep(5)
            print(cat_level)
            initial_params = self.create_params(idx=1, page_size=40, cat_id=cat_id)

            fake_user_agent = generate_user_agent(os=('mac', 'linux'), device_type='desktop')
            initial_rq = requests.get(base_url, params = initial_params, headers = {"User-Agent": fake_user_agent})

            initial_rq_json = initial_rq.json()

            total_num = initial_rq_json["shoppingResult"]["total"]
            
            if collect_num is None:
                temp_collect_num = total_num
            else:
                temp_collect_num = min(collect_num, total_num)

            max_page, remainder = self.get_max_page(collect_num = temp_collect_num, page_size = 80)
            for pg in tqdm(range(1, max_page+1)):
                # time.sleep(1)
                params = self.create_params(idx=pg, page_size=80, cat_id=cat_id)
                fake_user_agent = generate_user_agent(os=('mac', 'linux'), device_type='desktop')
                rq = requests.get(base_url, params = params, headers = {"User-Agent": fake_user_agent})
                rq_json = rq.json()

                if pg < max_page:
                    collect_num_in_page = None

                else:
                    collect_num_in_page = remainder

                try:
                    products_infos = self.extract_product_infos(rq_json, collect_num_in_page, image_save = image_save, img_dir = f"./images/{cat_id}/")
                    products_infos["searchCategoryId"] = [cat_id for x in range(len(products_infos["id"]))]
                    products_infos["searchCategoryName"] = [" > ".join(cat_level) for x in range(len(products_infos["id"]))]
                except:
                    print(rq.url)
                    continue
                with open(f"crawl_pkl/{cat_id}_{pg}.pkl", "wb") as f:
                    pickle.dump(products_infos, f)
                total_product_infos = self.merge_dict(total_product_infos, products_infos)
        
        return total_product_infos