import queue
import time
from urllib.parse import parse_qsl, urljoin
from scrapy.selector import Selector
from playwright.sync_api import sync_playwright
from playwright._impl._api_types import TimeoutError,Error
from rich.console import Console
import random
import json
from openpyxl import Workbook
from openpyxl.styles.fonts import Font
import string
import threading
import argparse


class Cars():
    def __init__(self,url):
        self.base = url
        self.not_required = ['seller','body style','seller type','drivetrain']
        self.current_listings = queue.Queue()
        self.newcars = set()
        self.con = Console()
        self.once = True
        self.counter = 0
        self.page_count = 1
        self.offset = 0
        
    def handle_newroute(self,route,request):
        newurl = request.url.replace("limit=12","limit=100")
        route.continue_(url=newurl)
    # extracting urls for current listings
    def new_cars(self,url):
        resp = []
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=True,proxy={
            "server":"http://p.webshare.io:80",
            "username":"hjdkysch-rotate",
            "password":"iwfapn45qbcm"
        })
        page = browser.new_page()
        try:                
            page.on("response",lambda response: resp.append(response) if "/v2/autos/auctions?limit" in response.url else None)
            page.route("**/v2/autos/auctions?limit*",self.handle_newroute)
            page.goto(url)
            page.check(".paginator")
        except Exception as e:
            if "checkbox" in str(e):
                # self.con.print_exception()
                resp = resp[0]
                data = resp.json()
                count = data.get("count")
                self.total = data.get("total")
                for i in range(count):
                    key = data['auctions'][i].get("id")
                    value = data['auctions'][i].get("title").replace(" ","-")
                    car = f"https://carsandbids.com/auctions/{key}/{value}" 
                    self.current_listings.put(car)
                self.con.print(f"Total urls >>[bold] {self.total}")
                browser.close()
                p.stop()
            elif "timeouterror" in str(e).lower():
                browser.close()
                p.stop()
                self.new_cars(url)
            else:
                browser.close()
                p.stop()
                self.new_cars(url)
        else:
            browser.close()
            p.stop()
            print("retrying")
            self.new_cars(url)


    # parsing each car page
    def get_page(self,lock,url):
        data = {}
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=True,proxy={
            "server":"http://p.webshare.io:80",
            "username":"hjdkysch-rotate",
            "password":"iwfapn45qbcm"
        })
        page = browser.new_page()
        try:
            page.goto(url)
            page.check(".quick-facts")
        except Exception as e:     
            if "checkbox" in str(e).lower():
                resp = page.content()
                sel = Selector(text=resp)
                year = sel.xpath("//div[@class='auction-title']/h1/text()").get()[:4]
                raw_title = sel.xpath("//div[@class='auction-title']/h1/text()").get()
                raw_subtitle = sel.xpath("//div[@class='d-md-flex justify-content-between flex-wrap']/h2/text()").get()
                if sel.xpath("//div[@class='d-md-flex justify-content-between flex-wrap']//h2/span").get():
                    no_reserver = "True"
                else:
                    no_reserver = "False"
                source = url
                price = sel.xpath("//span[@class='value']/span[@class='bid-value']/text()").get()
                main_image = sel.xpath("//div[@class='preload-wrap main loaded']/img/@src").get()
                images = ",".join(sel.xpath("//div[@class='preload-wrap  loaded']/img/@src").getall())
                if "kilometers" in sel.xpath("//div[@class='detail-wrapper']").get().lower():
                    kilometers = "True"
                else:
                    kilometers = "False"
                dt_tags = sel.xpath("//div[@class='quick-facts']//dt")
                dd_tags = sel.xpath("//div[@class='quick-facts']//dd")
                for dt,dd in zip(dt_tags,dd_tags):
                    if dd.xpath(".//a"):
                        with lock:
                            not_required = self.not_required
                        if not dt.xpath(".//text()").get().lower() in not_required:
                            data[dt.xpath(".//text()").get()] = dd.xpath(".//a/text()").get()
                    else:
                        if not dt.xpath(".//text()").get().lower() in not_required:
                            if dt.xpath(".//text()").get() == "Mileage":
                                raw_miles = dd.xpath(".//text()").get()
                                if "TMU" in raw_miles:
                                    tmu = "True"
                                else:
                                    tmu = "False"
                                Mileage = ''
                                miles_characters = list(dd.xpath(".//text()").get())
                                for c in miles_characters:
                                    if c.isdigit():
                                        Mileage +=c
                                data["Mileage"] = Mileage
                            else:
                                data[dt.xpath(".//text()").get()] = dd.xpath(".//text()").get()
                data['Year'] = year
                data['URL'] = source
                data["Raw_Title"] = raw_title
                data["Raw_Subtitle"] = raw_subtitle
                data["Raw_Mileage"] = raw_miles
                data["Price"] = price
                data["Source"] = url
                data["TMU"] = tmu
                data["No_Reserve"] = no_reserver
                data["Kilometers"] = kilometers
                data["Main-Image"] = main_image
                data["Images"] = images
                self.save_to_excel(data,lock)
                browser.close()
                p.stop()
            elif "timeouterror" in str(e).lower():
                browser.close()
                p.stop()
                self.get_page(lock,url)
            else:
                browser.close()
                p.stop()
                self.get_page(lock,url)
        else:
            browser.close()
            self.get_page(lock,url)

    def handle_pastroute(self,route,request):
        newurl = request.url.replace("limit=50&status=closed&",f"limit=100&status=closed&offset={self.offset}&")
        self.offset+=50
        route.continue_(url=newurl)
    # extracting urls for past listings
    def past_cars(self,url):
        resp = []
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=True,proxy={
            "server":"http://p.webshare.io:80",
            "username":"hjdkysch-rotate",
            "password":"iwfapn45qbcm"
        })
        page = browser.new_page()
        try:
            page.on("response",lambda response: resp.append(response) if "/v2/autos/auctions?limit" in response.url else None)
            page.route("**/v2/autos/auctions?limit*",self.handle_pastroute)
            page.goto(url)
            page.check(".paginator")
        except Exception as e:
            if "checkbox" in str(e):
                resp = resp[0]
                data = resp.json()
                count = data.get("count")
                self.total = data.get("total")
                for i in range(count):
                    key = data['auctions'][i].get("id")
                    value = data['auctions'][i].get("title").replace(" ","-")
                    car = f"https://carsandbids.com/auctions/{key}/{value}" 
                    self.current_listings.put(car)
                self.con.print(f"Total urls >>[bold] {self.total}")
                browser.close()
                p.stop()
            elif "timeouterror" in str(e).lower():
                browser.close()
                p.stop()
                self.past_cars(url)
            else:
                browser.close()
                p.stop()
                self.past_cars(url)
        else:
            browser.close()
            p.stop()
            self.past_cars(url)
    

    def save_to_excel(self,data,lock):
        with lock:
            if self.once:
                self.once = False
                self.wb = Workbook()
                self.wb.active.title = "Cars"
                self.Cars = self.wb.active
                keys = list(data.keys())
                values = list(data.values())
                self.Cars.append(keys)
                self.Cars.append(values)
                letters = list(string.ascii_uppercase)[:len(keys)]
                for letter in letters:
                    self.Cars[f"{letter}1"].font = Font(bold=True)
            else:
                values = list(data.values())
                self.Cars.append(values)

    # start threads for current listings
    def run_new(self,lock,t_val,load=True):
        if load:
            self.new_cars("https://carsandbids.com/")
        threads = []
        qsize = self.current_listings.qsize()
        while not self.current_listings.empty():
            self.counter+=1
            url = self.current_listings.get()
            t = threading.Thread(target=self.get_page,args=(lock,url))
            t.daemon = True
            threads.append(t)
            t.start()
            if self.counter%t_val == 0:
                break
        for t in threads:
            t.join()
        self.con.print(f"[bold green]Processed Items [cyan]{self.counter}:[bold green] Remaining Items [cyan]{self.current_listings.qsize()}")
        if self.current_listings.empty():
            self.wb.save("Cars.xlsx")
            self.con.print("[+] File Saved")
        else:
            self.run_new(lock,t_val,False)
    
    # start threads for past listings
    def run_past(self,lock,t_val,load=True):
        if load:
            self.past_cars("https://carsandbids.com/past-auctions/")
        threads = []
        qsize = self.current_listings.qsize()
        while not self.current_listings.empty():
            self.counter+=1
            url = self.current_listings.get()
            t = threading.Thread(target=self.get_page,args=(lock,url))
            t.daemon = True
            threads.append(t)
            t.start()
            if self.counter%t_val == 0:
                break
        for t in threads:
            t.join()
        self.con.print(f"[bold green]Processed Items [cyan]{self.counter}:[bold green] Remaining Items [cyan]{self.total-self.counter}")
        if self.current_listings.empty() and self.counter >= self.total:
            self.wb.save("Cars.xlsx")
            self.con.print("[+] File Saved")
        else:
            if self.counter==100:
                self.run_past(lock,t_val,True)
            else:
                self.run_past(lock,t_val,False)
    def argss(self):
        args = argparse.ArgumentParser()
        args.add_argument('-m','--mode',dest='mode',help="give 'new' for current listings\n'past' for old listings")
        args.add_argument('-t','--threads',type=int,dest='threads',help="number of threads, default 10")
        values = args.parse_args()
        value = vars(values)
        return value

import logging
logging.basicConfig(level=logging.ERROR)
lock = threading.Lock()
c = Cars("https://carsandbids.com")
args = c.argss()
t_val = args.get("threads")
if t_val == None:
    t_val = 10
if args.get("mode") == "past":
    c.con.print(f"[bold ][+] Staring crawler for past listings..")
    c.run_past(lock,t_val)
else:
    c.con.print(f"[bold][+] Staring crawler for current listings..")
    c.run_new(lock,t_val)
