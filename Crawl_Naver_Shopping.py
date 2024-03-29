import requests
from requests.adapters import HTTPAdapter, Retry
import os
import re
from collections import defaultdict
from datetime import datetime
from copy import deepcopy
import pytz
import random
import pickle

import pandas as pd
import numpy as np
import time

from lxml import etree
import urllib3

from tqdm import tqdm
from user_agent import generate_user_agent, generate_navigator

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# overseaTp = "1" : 해외
class Crawl_Naver_Shopping():
    def __init__(self, list_type:str = "전체", verify = True):
        self.verify = verify

        if list_type == "전체":
            self.productSet = "total"
        elif list_type == "가격비교":
            self.productSet = "model"


        self.headers = {
            'authority': 'search.shopping.naver.com',
            'method': 'GET',
            'logic': 'PART',
            "sbth" : 'a3dc4411455cb04d54463960fc7f7406e1e0acc1949f74e0010cbc1de82e77d6407ab302ab68d51773e8f0b643e88d5e'
        }

        self.rs = requests.Session()
        retries = Retry(total = 5,
                        backoff_factor = 0.1,
                        status_forcelist=[ 500, 502, 503, 504 ])
        self.rs.mount('http://', HTTPAdapter(max_retries=retries))     

    def create_params(self, idx:int, page_size:int, **kwargs):
        """
        request.get에 들어갈 parameter들을 생성하는 method.
        필수적인 parameter들 (idx, page_size)만 명시적으로 표시함.
        
        1) category로 수집하는 경우 (get_product_infos_in_category)
          : cat_id가 **kwargs에 포함되어야 함.

        2) query로 수집하는 경우 (get_product_infos_from_query)
          : query가 **kwargs에 포함되어야 함.

        Args:
            idx: 페이지 번호
            page_size: 한 페이지 내에서 보여주는 데이터 건수
            **kwargs: 기타 다른 parameter

        Returns:
            params: parameters

        Raises:
            
        """
        params = {"sort" : "rel", # date
                  "pagingIndex" : idx,
                  "pagingSize" : page_size,
                  "viewType" : "list",
                  "productSet" : self.productSet
                  }
        params = dict(params, **kwargs)
        
        return params


    def create_headers(self, url: str) -> dict:
        """
        request.get에 들어갈 headers를 생성하는 method.
        fake_user_agent를 생성하여 ip 차단을 우회한다.

        Args:
            url: 수집 url

        Returns:
            headers: 헤더

        Raises:
            
        """         
        headers = deepcopy(self.headers)
        fake_user_agent = generate_user_agent(os=('mac', 'linux'), device_type='desktop')
        headers["User-Agent"] = fake_user_agent
        headers["Referer"] = url

        return headers
        

    def get_max_page(self, collect_num:int, page_size:int = 80) -> tuple[int]:
        """
        수집해야하는 데이터 건수(collect_num)를 page_size로 나누어 
        수집해야하는 페이지의 수 (max_page)와 마지막 page에서의 데이터 건수(remainder)를 산출하는 method.

        Args:
            collect_num: 수집 데이터 건수
            page_size: 한 페이지 내에서 보여주는 데이터 건수

        Returns:
            max_page: 수집해야하는 페이지의 수
            remainder: 마지막 page에서의 데이터 건수

        Raises:
            
        """    
        max_page = min(int(np.ceil(collect_num / page_size)), 100)
        remainder = int(collect_num % page_size)

        return max_page, remainder

    
    def merge_dict(self, org_dict:dict, new_dict:dict, type:str = "full") -> dict:
        """
        dict(list) 형태의 두 개의 dictionary들을 key에 맞춰 각 value값 (list)를 extend 하는 method.

        모든 key를 다 활용할지 (full), org_dict에 있는 key만 활용할지 (left), new_dict에 있는 key만 활용할지(right)에 따라
        type이 구분된다.

        Args:
            org_dict: 기존 dictionary
            new_dict: 추가하는 dictionary
            type: ["full", "left", "right"]

        Returns:
            merged_dict: 결합된 dictionary

        Raises:
            
        """           
        merged_dict = org_dict
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
        """
        dictionary에 있는 item들을 concat하여 string으로 반환하는 method.

        key 간에는 ' | '로 연결하고, 각 key내의 value(list)는 ', '로 연결한다.

        e.g.) 
        input : {"크기" : ["240 x 140 x 150"], "색상": ["빨강", "노랑", "검정", "화이트"]}
        output : "크기 : 240 x 140 x 150 | 색상 : 빨강, 노랑, 검정, 화이트"

        Args:
            input_dict: concat 대상 dictionary

        Returns:
            string

        Raises:
            
        """            
        temp = []
        for k, v in input_dict.items():
            v = [str(x) for x in v]
            temp.append(f"{k} : {', '.join(v)}")
        return " | ".join(temp)


    def create_productAttr(self, attr_val:list, char_val:list) -> dict:
        """
        제품 속성 Key와 Value 리스트를 기반으로 제품 속성값 string을 만드는 method.

        e.g.) 
        input : attr_val = ["크기", "색상"], char_val = [["240 x 140 x 150"], ["빨강", "노랑", "검정", "화이트"]]
        "크기 : 240 x 140 x 150 | 색상 : 빨강, 노랑, 검정, 화이트"

        Args:
            attr_val: 제품 속성 Key 리스트
            char_val: 제품 속성 Value 리스트

        Returns:
            string

        Raises:
            
        """   
        product_attr_dict = defaultdict(list)
        for attr, char in zip(attr_val, char_val):     
            product_attr_dict[attr].append(char)

        return self.concat_dict(product_attr_dict)


    def save_images(self, img_urls:list, img_names:list, img_dir:str = "./image/"):
        """
        image를 저장하는 method.

        Args:
            img_urls: 이미지 url 리스트 
            img_names: 저장할 이미지 파일명 리스트
            img_dir: 저장 경로

        Returns:

        Raises:
            
        """           
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
                img_rq = requests.get(img_url, verify = False)
                with open(f"{img_dir}/{img_name}", "wb") as f:
                    f.write(img_rq.content)
            except Exception as e: 
                error_list.append(img_name)
                print(e)
                print(f"Image Save Error : {img_name}")


    def extract_product_infos(self, rq_json:dict, start_date:str = None, collect_num:int = None, image_save:bool = True, img_dir:str = "./image/") -> dict:
        """
        request 결과 json으로 부터 product info를 dictionary 형태로 반환하는 method.

        overSeaTp: 
            0: 국내
            1: 해외
        
        saleTp:
            0: 일반
            1: ??
            2: 렌탈

        Args:
            rq_json: request 결과
            collect_num: 수집해야하는 제품의 개수
            image_save: 제품 이미지 저장 여부
            img_dir: 제품 이미지 저장 경로

        Returns:
            products_dict: 제품 정보 dictionary

        Raises:
            
        """ 
        today = datetime.now(pytz.timezone("Asia/Seoul")).strftime("%y.%m.%d")

        products_dict = defaultdict(list)
        products = rq_json["shoppingResult"]["products"]
        continue_flag = True

        if collect_num is None:
            collect_num = len(products)


        
        for i, product in enumerate(products):
            # 수집해야하는 제품 개수를 초과하는 경우는 iteration 종료
            if i == collect_num:
                break

            if start_date is not None:
                if len(product["lnchYm"]) == 8:
                    if product["lnchYm"] < start_date:
                        continue_flag = False
                        break


            collect_cols = ["rank", "id", "scoreInfo", "productName", "overseaTp", "saleTp",
                            "category1Id", "category2Id", "category3Id", "category4Id",
                            "category1Name", "category2Name", "category3Name", "category4Name",
                            "maker", "makerNo", "brand", "brandNo", "price", "priceUnit", "lnchYm", 
                            "lowMallList",
                            "attributeValue", "characterValue", "crUrl", "imageUrl"]

            for col in collect_cols:
                products_dict[col].append(product[col])


            # 이미지명
            try: 
                products_dict["imageName"].append(product["imageUrl"].split("/")[-1])
            except:
                print(product["imageUrl"])

            attr_val = re.sub(r"_[A-Z]{1}","",product["attributeValue"]).split("|")
            char_val = product["characterValue"].split("|")
            attr_char = self.create_productAttr(attr_val, char_val)

            if product.get("lowMallList") is not None:
                price_list = [int(mall_info.get("price")) for mall_info in product["lowMallList"]]
                attr_char += " | " + f"가격 : {min(price_list):,} ~ {max(price_list):,} ({today} 기준)"
                products_dict["price_list"].append(price_list)
            else:
                products_dict["price_list"].append(None)
            
            products_dict["productAttr"].append(attr_char)
            


            
            try:
                # 모든 값의 길이가 동일한 지 check
                value_length = [len(v) for k, v in products_dict.items()]
                if (sum(value_length) / len(value_length)) != value_length[0]:
                    raise
            except:
                print("속성의 길이가 다릅니다.")
                for k, v in products_dict.items():
                    print(f"key : {k}, length : {len(v)}")

            if image_save:
                self.save_images(img_urls=product["imageUrl"], 
                                 img_names=product["imageUrl"].split("/")[-1],
                                 img_dir = img_dir)
        
        return products_dict, continue_flag




    def get_product_infos_in_category(self, cat_ids:list, start_date:str = None, cat_levels:list = None, collect_num:int = None, image_save:bool = False) -> dict:
        """
        카테고리 내의 제품 정보를 수집하는 method.

        Args:
            cat_ids: 카테고리 id 리스트
            cat_levels: 카테고리 level 리스트
            collect_num: 수집하고자 하는 데이터 건수
                         None -> 전체 수집
            image_save: 제품 이미지 수집 여부

        Returns:
            total_product_infos: 제품 정보 데이터 dict

        Raises:
            
        """          
        if isinstance(cat_ids, list) == False:
            cat_ids = [cat_ids]
        base_url = "https://search.shopping.naver.com/api/search/category"
        total_product_infos = defaultdict(list)

        today = datetime.now(pytz.timezone("Asia/Seoul")).strftime("%Y%m%d")
        if os.path.exists(f"./pickle/{today}") == False:
            os.makedirs(f"./pickle/{today}")

        sort = "rel"
        if (start_date is not None):
            sort = "date"

        for i, cat_id in enumerate(cat_ids):
            time.sleep(5)
            print(i, end =  ", ")
            if cat_levels is None:
                print(cat_id)
            else:
                print(cat_levels[i])

            if cat_levels[i].split(">")[2] == "":
                temp_cat_levels_list = cat_levels[i].split(">")
                temp_cat_levels_list[2] = temp_cat_levels_list[1]
                # print(temp_cat_levels_list)
                temp_cat_levels = ">".join(temp_cat_levels_list)
            else:
                temp_cat_levels = cat_levels[i]

            # request의 parameter로 넣기 위한 params와 header를 생성
            initial_params = self.create_params(idx=1, page_size=40, cat_id=cat_id, sort = sort)
            initial_headers = self.create_headers(url = base_url)

            initial_rq = requests.get(base_url, params = initial_params, headers = initial_headers, verify = False)
            self.initial_rq = initial_rq
            try:
                initial_rq_json = initial_rq.json()
            except:
                print(initial_rq.text)
                continue

            # 전체 검색 결과 건수 산출
            self.initial_rq_json = initial_rq_json
            self.initial_rq_url = initial_rq.url
            total_num = initial_rq_json["shoppingResult"]["total"]
            
            if collect_num is None:
                temp_collect_num = total_num
            else:
                temp_collect_num = min(collect_num, total_num)

            # 수집해야하는 page 수 (max_page)와 마지막 페이지에서 수집해야하는 데이터 건수 추출(remainder)
            max_page, remainder = self.get_max_page(collect_num = temp_collect_num, page_size = 80)
            
            for pg in tqdm(range(1, max_page+1)):
                time.sleep(0.5)

                # request의 parameter로 넣기 위한 params와 header를 생성
                params = self.create_params(idx=pg, page_size=80, cat_id=cat_id, sort = sort)
                headers = self.create_headers(url = base_url)
                rq = self.rs.get(base_url, params = params, headers = headers, verify = False)
                rq_json = rq.json()

                if pg < max_page:
                    collect_num_in_page = None

                else:
                    collect_num_in_page = remainder

                try:
                    products_infos, continue_flag = self.extract_product_infos(rq_json = rq_json, 
                                                                               collect_num = collect_num_in_page, 
                                                                               image_save = image_save, 
                                                                               img_dir = f"./images/{cat_id}/", 
                                                                               start_date = start_date)
                    products_infos["searchCategoryId"] = [cat_id for x in range(len(products_infos["id"]))]
                    # products_infos["searchCategoryName"] = [" > ".join(cat_levels[i]) for x in range(len(products_infos["id"]))]
                except Exception as e:
                    print(e)
                    print(rq.url)
                    continue

                total_product_infos = self.merge_dict(total_product_infos, products_infos)

                if continue_flag == False:
                    break

                with open(f"./pickle/{today}/{cat_id}_{pg}.pkl", "wb") as f:
                    pickle.dump(products_infos, f)

        
        return total_product_infos


    def get_product_infos_from_query(self, queries, collect_num = None, image_save:bool = False, temp_product_ids = None) -> dict:
        """
        query(검색어)를 보내서 제품 정보를 수집하는 method.

        Args:
            queries: 검색어 리스트
            collect_num: 수집하고자 하는 데이터 건수
                         None -> 전체 수집
            image_save: 제품 이미지 수집 여부

        Returns:
            total_product_infos: 제품 정보 데이터 dict

        Raises:
            
        """          
        if isinstance(queries, list) == False:
            queries = [queries]

        if temp_product_ids is None:
            temp_product_ids = []

        base_url = "https://search.shopping.naver.com/api/search/all"
        total_product_infos = defaultdict(list)

        for i, query in enumerate(queries):
            print(f"{i+1} : {query}")
            time.sleep(random.random()*1.5)
            # request의 parameter로 넣기 위한 params와 header를 생성
            initial_params = self.create_params(idx=1, page_size=40, query=query)
            initial_headers = self.create_headers(url = base_url)

            initial_rq = self.rs.get(base_url, params = initial_params, headers = initial_headers, verify = False)
            self.query = query
            self.initial_rq = initial_rq

            initial_rq_json = initial_rq.json()

            # 전체 검색 결과 건수 산출
            total_num = initial_rq_json["shoppingResult"]["total"]

            if collect_num is None:
                temp_collect_num = total_num
            else:
                temp_collect_num = min(collect_num, total_num)

            # 수집해야하는 page 수 (max_page)와 마지막 페이지에서 수집해야하는 데이터 건수 추출(remainder)
            max_page, remainder = self.get_max_page(collect_num = temp_collect_num, page_size = 80)

            for pg in tqdm(range(1, max_page+1)):
                # request의 parameter로 넣기 위한 params와 header를 생성
                params = self.create_params(idx=pg, page_size=80, query=query)
                headers = self.create_headers(url = base_url)

                rq = requests.get(base_url, params = params, headers = headers, verify = False)
                rq_json = rq.json()

                if pg < max_page:
                    collect_num_in_page = None

                else:
                    collect_num_in_page = remainder

                try:
                    products_infos, _ = self.extract_product_infos(rq_json = rq_json, 
                                                                   collect_num = collect_num_in_page, 
                                                                   image_save = image_save, 
                                                                   img_dir = f"./images/{query}/")

                    products_infos["query"] = [query for _ in range(len(products_infos["id"]))]

                    products_infos["temp_product_id"] = [temp_product_ids[i] for _ in range(len(products_infos["id"]))]
                except Exception as e:
                    print(e)
                    print(rq.url)
                    continue

                total_product_infos = self.merge_dict(total_product_infos, products_infos)
        
        return total_product_infos
    

if __name__ == "__main__":
    category_df = pd.read_excel("수집_대상_카테고리.xlsx")
    category_df["cat_levels"] = category_df["category1"].fillna("") + ">" +  category_df["category2"].fillna("") + ">" + category_df["category3"].fillna("") + ">" + category_df["category4"].fillna("")
    crawl = Crawl_Naver_Shopping(list_type="가격비교")
    crawl_result = crawl.get_product_infos_in_category(cat_ids = category_df["category_id"].to_list(), cat_levels = category_df["cat_levels"].to_list())