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
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, ElementNotInteractableException, ElementClickInterceptedException, StaleElementReferenceException


class Collect_Category_Ids():
    def __init__(self, driver_loc):
        # driver_loc = "../webdriver/chromedriver_97"
        options = webdriver.ChromeOptions()
        self.driver = webdriver.Chrome(executable_path=driver_loc, options = options)

        self.driver.get("https://shopping.naver.com/home/p/index.naver")

    def click_more_category(self):
        # 카테고리 더보기 클릭
        category_layer_open_yn = self.driver.find_elements(By.XPATH, ".//div[contains(@class, '_gnb_layer_wrap_1a4UN')]")
        if len(category_layer_open_yn) == 0:
            self.driver.find_element(By.XPATH, ".//button[@class='_gnb_category_2wDT4 N=a:SNB.category']").click()
        else:
            print("Category Wrap is already opened")
        time.sleep(2)


    def click_main_category_button(self, category:str):    
        # 대분류 카테고리 버튼 
        main_category_elems = self.driver.find_elements(By.XPATH, ".//div[contains(@class,'_categoryLayer_main_category_2A7mb')]//li[@class='_categoryLayer_list_34UME']")
        main_category_names = [re.sub("\n|(선택됨)","",x.text) for x in main_category_elems]

        main_category_buttons = {name : elem for name, elem in zip(main_category_names, main_category_elems)}

        # 카테고리 클릭
        main_category_buttons[category].click()
        time.sleep(2)


    def check_category_more_button(self):
        category_more_button = self.driver.find_elements(By.XPATH, ".//div[@class='filter_finder_tit__2VCKd' and @data-nclick='N=a:rcc*A.cat.fold']")
        if len(category_more_button) != 0:
            category_more_button[0].click()
        time.sleep(2)

        
    def extract_catId(self):
        if (r"catId=([\d]{8})", self.driver.current_url) is None:
            time.sleep(1)
        try:
            catId = re.search(r"catId=([\d]{8})", self.driver.current_url).group(1)
        except Exception as e:
            print(e)
            print(f"url : {self.driver.current_url}")
            catId = self.driver.current_url

        return catId

    def extract_category_levels(self):
        category_infos = self.driver.find_elements(By.XPATH, ".//div[@class='resultSummary_category_info__1jq2r']/a")
        return [x.text for x in category_infos]

    def extract_filter_list(self):
        category_filter_panel = self.driver.find_element(By.XPATH, ".//div[contains(@class,'filter_finder_col__3ttPW')]")
        filters = category_filter_panel.find_elements(By.XPATH, "div[@class='filter_finder_row__1rXWv']//ul[@class='filter_finder_list__16XU5']/li/a")
        filter_names = [x.text for x in filters]
        return filter_names, filters
    
    def check_next_level(self, prev_filters):
        filter_names, _ = self.extract_filter_list()

        # 기존과 filter들이 동일하면 다음 level의 filter가 없다고 판단
        if prev_filters == filter_names:
            return False
        else:
            return True

    def get_category_ids(self):
        category_levels = []
        catIds = []
        urls = []
        filter_names, filters = self.extract_filter_list()
        for i in range(len(filters)):
        # for i in range(2):
            filters[i].click()
            org_url = self.driver.current_url
            urls.append(org_url)
            print(filter_names[i])
            print(org_url)
            time.sleep(1.5)
            # category_levels = extract_category_levels()
            # catId = extract_catId()
            category_level = self.extract_category_levels()
            category_levels.append(category_level)
            
            try:
                catId = self.extract_catId()
            except Exception as e:
                self.driver.find_element(By.XPATH, ".//li[@class='filter_active__7ne8N']").click()
                filters[i].click()
                catId = self.extract_catId()

            catIds.append(catId)

            no_result = self.driver.find_elements(By.XPATH, ".//div[@class='noResult_no_result__1ad0P']")
            if len(no_result) > 0:
                self.driver.back()
                time.sleep(1.5)
                filter_names, filters = self.extract_filter_list()
                continue

            if self.check_next_level(prev_filters=filter_names):
                print("세부 카테고리 있음")
                temp_category_levels, temp_catIds, temp_urls = self.get_category_ids()
                category_levels.extend(temp_category_levels)
                catIds.extend(temp_catIds)
                urls.extend(temp_urls)
                # print(temp_category_levels)
                # print(temp_catIds)
                self.driver.get(org_url)
                time.sleep(1.5)
                filter_names, filters = self.extract_filter_list()


        return category_levels, catIds, urls

    
    def get(self, categories):
        category_levels = []
        catIds = []
        urls = []
        if isinstance(categories, list) == False:
            categories = [categories]

        for category in categories:
            # self.driver.get("https://shopping.naver.com/home/p/index.naver")
            # self.click_more_category()
            # self.click_main_category_button(category)
            # self.check_category_more_button()

            self.driver.get("https://search.shopping.naver.com/search/category?catId=50000003")

            temp_category_levels, temp_catIds, temp_urls = self.get_category_ids()
            category_levels.append(temp_category_levels)
            catIds.append(temp_catIds)
            urls.append(temp_urls)
        
        return category_levels, catIds, urls
