import threading 
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, urlunparse, urljoin
import datetime
lock = threading.Lock()
import requests 
from bs4 import BeautifulSoup

MAX_THREADS = 15

import cloudscraper
import justext



from fastapi import FastAPI


url_list = [
    'https://nftevening.com',
    'https://nftnow.com',
    'https://playtoearn.online',
    'https://nftnewstoday.com',
    'https://nftculture.com',
    'https://nftgators.com',
    'https://todaynftnews.com',
    'https://tokengamer.io',
    'https://decrypt.co/news/nft',
    'https://cointelegraph.com/tags/nft',
    'https://www.coindesk.com/tag/nft/',
    'https://www.coindesk.com/tag/nfts/',
    'https://thedefiant.io/nfts',
    'https://www.theblock.co/category/nfts-gaming-and-metaverse',
    'https://www.bitdegree.org/crypto/news/nfts',
    'https://coingape.com/category/news/nft-news/',
    'https://cryptodaily.co.uk/tag/nft',
    'https://www.thecoinrepublic.com/category/nft/',
    'https://www.bitcoininsider.org/category/nfts',
    'https://insidebitcoins.com/',
    'https://beincrypto.com/news/',
    'https://blockworks.co/',
]

global_list = []

def validate_and_fix_url(url):
    # Checks if the URL is valid
    parsed_url = urlparse(url)
    if not parsed_url.scheme:
        url = "https://" + url  
    return url


def get_article_content(url):
    response = requests.get(url)
    content = ""
    paragraphs = justext.justext(response.content, justext.get_stoplist("English"))
    for paragraph in paragraphs:
        if not paragraph.is_boilerplate:
            content += paragraph.text
    
    # print(content)
    # print("--------------------------------------------------")
    
    return content

def get_info_from_url(url):
    scraper = cloudscraper.create_scraper()
    response = scraper.get(url).text
    soup = BeautifulSoup(response, 'html.parser')
    for script in soup(["script", "style"]):
        script.decompose()

    # get all links and associated text
    links = soup.find_all('a')
    potential_articles = {}
    keywords = ['learn', 'index', 'indices', '/price/', 'subscribe', 'terms of service','terms and conditions', 'privacy policy', 'contact', 'youtube.com', '#',"$",
                'discord', 'sale'
    ]
    
    for link in links:
        link_url = link.get('href')
        link_url = validate_and_fix_url(link_url)  
        link_text = link.get_text()
        link_text = link_text.replace('\n', '').replace('\t', '').replace('\r', '')
        

        # Checks if any of the keywords are present in the URL or link text
        if len(link_text) > 20:
            if any(keyword in link_url.lower() or keyword in link_text.lower() for keyword in keywords):
                continue

            # Get article title and content for the link
            # print("-------------",link_text, "----------------")
            try:
                publication_date = soup.find('time')['datetime']
            except:
                publication_date = None

            # Check if the article was published within the last 24 hours
            now = datetime.datetime.now()
            yesterday = now - datetime.timedelta(days=1)

            if publication_date and publication_date < yesterday:
                continue
            article_content = get_article_content(link_url)
            potential_articles[link_url] = [link_text, article_content]

    with lock:
        for link_url, article_content in potential_articles.items():
            global_list.append({link_url: article_content})

                
    
    # summary = get_article_summary(text)
    # print(text)
    
    
    

def get_info_threaded(url_list):
    threads = max(len(url_list), MAX_THREADS)

    with ThreadPoolExecutor(max_workers=threads) as executor:
        executor.map(get_info_from_url, url_list)


app = FastAPI()

@app.get("/")
async def get_content():
    # print article title of global_list
    print("--------------------------------------------------")
    temp = get_info_threaded(url_list=url_list)
    global_list = []
    return temp
