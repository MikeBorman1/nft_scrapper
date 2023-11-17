from urllib.parse import urlparse, urlunparse, urljoin
from datetime import timedelta, datetime
import requests
from bs4 import BeautifulSoup
import cloudscraper
import justext
import re
from fastapi import FastAPI
from htmldate import find_date
from requests_html import HTMLSession
from typing import Optional
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import threading
import concurrent.futures 
from queue import Queue


load_dotenv()


class KeywordsInput(BaseModel):
    keywords: Optional[str]

MAX_THREADS = 15

global_results = []
results_lock = threading.Lock()

skip_url = ["https://www.coindesk.com/newsletters/the-protocol/", "https://news.google.com/publications/"]

keywords = [
    'learn', 'index', 'indices', '/price/', 'subscribe', 'terms of service', 
    'terms and conditions', 'author', 'contact', 'learn', 'about-us', 'contact-us', 
    'about', 'advertise', 'marketplaces', 'deals', 'disclosure', 'privacy policy', 
    'contact', '@', '#', "$", 'discord', 'sale', 'guides', 'collectibles', 'category', 
    'tiktok', 'learn', 'guide', 'privacy', 'visit', 'cryptocurrency-prices', 'cookie-policy',
    'crypto', 'policies', 'policy', 'twitter', 'facebook', 'instagram', 'linkedin', 
    'reddit', 'medium', 'youtube', 'twitch', 'telegram', 'github', 'discord', 't.me', 
    'sar.asp', 'terms-and-conditions', 'sponsors',
]

def is_valid_url(url):
    regex = r'^http[s]?://(?:[a-zA-Z]|[0-9]|[._-]|\~|\?|\:|=|%|&|/|(|)){1,256}\.[a-zA-Z]{1,256}\b([-a-zA-Z0-9@:%_\+.~#?&//=]{0,256}\.[a-z]{1,256})?\b(:[0-9]{1,4})?'
    match = re.match(regex, url)
    return bool(match)

def validate_and_fix_url(url, parent_domain):
    
    
    # Check if the URL starts with 'https://'
    if url is None:
        return None, None

    # Check if the URL starts with 'https://'
    if not url.startswith('https://'):
        url = 'https://' + parent_domain + url

    # Parse the URL
    parsed_url = urlparse(url)

    # If the URL is missing a scheme, add the scheme 'https'
    if not parsed_url.scheme:
        url = 'https://' + url
    
    if not is_valid_url(url):
        return None, None
    # Send a GET request to the URL and check the response status code
    if any(keyword in url.lower() for keyword in keywords):
            return None, None
    
    
    
    resp = requests.get(url)
    if resp.status_code == 200:
        return (url, resp)
    else:
        return (None, None)
    

def get_article_content(response):
    try:
        # Handle HTTP errors
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
    response = scraper.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).content
    soup = BeautifulSoup(response, 'html.parser')
    for script in soup(["script", "style"]):
        script.decompose()
    
    # get all links and associated text
    links = soup.find_all('a')
    
    potential_articles = []
    processed_urls = set()
    
    
    for link in links:
        link_url = link.get('href')
        if any(skipable_url in link_url for skipable_url in skip_url):
            continue
        if link_url in processed_urls:
            continue 
        if link is None:
            continue
        
        try:
            (link_url, article_resp) = validate_and_fix_url(link_url, parent_domain)
        except Exception as e:
            # Log the error and continue to the next iteration of the loop
            print(f'Error processing URL: {link_url}, {e}')
            continue

        if link_url is None:
            continue
        
        link_text = link.get_text()
        link_text = link_text.replace('\n', '').replace('\t', '').replace('\r', '')
        
        if len(link_text) <= 10:
            continue
        # Checks if any of the keywords are present in the URL or link text
        

        processed_urls.add(link_url)
        # print(link_url)
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
                    continue
                print(link_url)
                # print(link_url,html_date_datetime.date())
                # potential_articles.append({"url": link_url, "title": link_text, "description": article_content})
                potential_articles.append({"url": link_url, "title": link_text, "description": article_content, "date": html_date })
            
        else:
            continue       
            
    return potential_articles

def get_info_threaded(url_list):
    final_list = []
    for url in url_list:
        potential_list = get_info_from_url(url)
        if potential_list:
            final_list.extend(potential_list)
    # final_list = get_info_from_url(test_url)
    return final_list

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
            # print(lines)
            
        #     # Extract title
            title = lines[0].strip()
            
            # Extract URL link
            url_link = lines[1].strip()
            article_resp = requests.get(url_link, stream=True)
            article_content = get_article_content(article_resp)
            if article_content is None:
                article_content = ""
            if "403 Client Error" in article_content:
                article_content = ""
        #     # Extract date
            date_str = lines[3]
            date = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %Z').date()
            # print(type(date))
            if date >= twenty_four_hours_ago.date():
                res_list.append({"url": url_link, "title": title, "description": article_content,"date": date_str})

    return res_list  

app = FastAPI()

@app.get("/articles")
async def get_content():
    
    # global_list = get_info_threaded(url_list=url_list)
    # temp = {"items": global_list}
    # return temp
    
    url_list = os.getenv("URL_LIST").split(',')

    with results_lock:
        
        if not global_results:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future_to_url = {executor.submit(get_info_from_url, url): url for url in url_list}
                for future in concurrent.futures.as_completed(future_to_url):
                    url = future_to_url[future]
                    try:
                        result = future.result()
                        global_results.extend(result)  # Extend global_results with the contents of result
                    except Exception as e:
                        print(f"Error processing {url}: {e}")

        # Return a copy of global_results and clear it after retrieval
        results_copy = global_results.copy()
        global_results.clear()
        return {"items":results_copy}


@app.post("/google-articles")
async def get_articles(keywords_input: KeywordsInput):
    keywords = keywords_input.keywords
    
    if keywords is None:
        keywords = "nft"
    
    results = get_google_articles(keywords)
    return {"items": results}
    
