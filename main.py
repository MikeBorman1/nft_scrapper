import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from datetime import timedelta, datetime
import requests
from bs4 import BeautifulSoup
import cloudscraper
import justext
import re
from fastapi import FastAPI
import time
from htmldate import find_date
from requests_html import HTMLSession
from typing import Optional
from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


class KeywordsInput(BaseModel):
    keywords: Optional[str]

MAX_THREADS = 15

url_list = os.getenv("URL_LIST").split(',')
global_list = []
lock = threading.Lock()
finish_event = threading.Event()

def validate_and_fix_url(url, parent_domain):
    # Checks if the URL is valid
    if not url.startswith('https://'):
        url = 'https://' + parent_domain + url

    # Parse the URL
    parsed_url = urlparse(url)

    # If the URL is missing a scheme, add the scheme `https`
    if not parsed_url.scheme:
        url = 'https://' + url

    # Return the fixed URL
    resp = requests.get(url)
    if resp.status_code == 200:
        
        return (url,resp)
    else:
        return (None, None)
  

def get_article_content(response):
    try:
        response.raise_for_status()  # Handle HTTP errors
        content = ""
        paragraphs = justext.justext(response.content, justext.get_stoplist("English"))
        for paragraph in paragraphs:
            if not paragraph.is_boilerplate:
                content += paragraph.text
        return content
    except Exception as e:
        # print(e)
        return str(e)

def get_info_from_url(url):
    
    parent_domain = urlparse(url).netloc
    scraper = cloudscraper.create_scraper()
    response = scraper.get(url).content
    soup = BeautifulSoup(response, 'html.parser')
    for script in soup(["script", "style"]):
        script.decompose()
    
    # get all links and associated text
    links = soup.find_all('a')
    
    potential_articles = []
    processed_urls = set()
    keywords = ['learn', 'index', 'indices', '/price/', 'subscribe', 'terms of service', 'terms and conditions',
                'privacy policy', 'contact', 'youtube.com', '#', "$", 'discord', 'sale', 'guides','collectibles','category']
    time.sleep(5)
    for link in links:
        link_url = link.get('href')
        (link_url, article_resp) = validate_and_fix_url(link_url, parent_domain)
        if link_url is None:
            continue 
        if link_url in processed_urls:
            continue
        
        link_text = link.get_text()
        link_text = link_text.replace('\n', '').replace('\t', '').replace('\r', '')
        
        # Checks if any of the keywords are present in the URL or link text
        
        if any(keyword in link_url.lower() for keyword in keywords):
            continue

        processed_urls.add(link_url)
        print(link_url)
        
        # Check if the article was published within the last 24 hours
        html_date = find_date(link_url)
        if html_date:
            
            html_date_datetime = datetime.strptime(html_date, "%Y-%m-%d")

            now = datetime.now()
            yesterday = now - timedelta(days=1)
            
            # print(link_url,html_date_datetime.date(), yesterday.date())
            # Check if the date of html_date is the same as yesterday
            if html_date_datetime.date() >= yesterday.date():
                
                article_content = get_article_content(article_resp)
                if article_content is None:
                    article_content = ""
                
                print(link_url,html_date_datetime.date())
                # potential_articles.append({"url": link_url, "title": link_text, "description": article_content})
                potential_articles.append({"url": link_url, "title": link_text, "description": article_content, "date": html_date })
            
        else:
            continue
    
    with lock:
        global_list.extend(potential_articles)
        time.sleep(1)



    finish_event.set()

def get_info_threaded(url_list):
    # final_list = []
    # print(url_list)
    # for url in url_list:
    #     potential_list = get_info_from_url(url)
    #     if potential_list:
    #         final_list.extend(potential_list)

    # return final_list
    num_threads = len(url_list)
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        executor.map(get_info_from_url, url_list)

def get_google_articles(keywords):

    base_url = f'https://news.google.com/rss/search?q={keywords}'
    s = HTMLSession()
    r = s.get(base_url)
    items = r.html.find('item')
    res_list = []

    for item in items:

        article_items = re.split(r"\n\n", item.text.strip())
        now = datetime.utcnow()
        twenty_four_hours_ago = now - timedelta(hours=24)
        # Extract information for each article
        
        # print(articles)
        for article_content in article_items:
            lines = article_content.split('\n')

            date_str = lines[3]
            date = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %Z').date()
            # print(type(date))
            if date >= twenty_four_hours_ago.date():
            
            
            # Extract title
                title = lines[0].strip()
                
                # Extract URL link
                url_link = lines[1].strip()
                article_resp = requests.get(url_link)
                article_content = get_article_content(article_resp)
                if article_content is None:
                    article_content = ""
                
            # Extract date
                res_list.append({"url": url_link, "title": title, "description": article_content,"date": date_str})

    return res_list  

app = FastAPI()

@app.get("/articles")
async def get_content():
    global global_list
    global_list = []

    finish_event.clear()
    get_info_threaded(url_list=url_list)
    finish_event.wait() 
    
    # global_list = get_info_threaded(url_list=url_list)
    
    temp = {"items": global_list}
    return temp

@app.post("/google-articles")
async def get_articles(keywords_input: KeywordsInput):
    keywords = keywords_input.keywords
    
    if keywords is None:
        keywords = "nft"
    
    results = get_google_articles(keywords)
    return {"items": results}
    
