import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, urlunparse, urljoin
import datetime
import requests
from bs4 import BeautifulSoup
import cloudscraper
import justext
from fastapi import FastAPI

MAX_THREADS = 15

url_list = [
    'https://nftevening.com',
    'https://nftnow.com',
    'https://playtoearn.online',
    'https://nftnewstoday.com',
    'https://nftculture.com',
    'https://nftgators.com',
    'https://todaynftnews.com',
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
    return url

def get_article_content(url):
    try:
        response = requests.get(url)
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
    try:
        parent_domain = urlparse(url).netloc
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url).text
        soup = BeautifulSoup(response, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()
        
        # get all links and associated text
        links = soup.find_all('a')
        potential_articles = []
        processed_urls = set()
        keywords = ['learn', 'index', 'indices', '/price/', 'subscribe', 'terms of service', 'terms and conditions',
                    'privacy policy', 'contact', 'youtube.com', '#', "$", 'discord', 'sale']
        
        for link in links:
            link_url = link.get('href')
            link_url = validate_and_fix_url(link_url, parent_domain)
            if link_url in processed_urls:
                continue
            processed_urls.add(link_url)
            link_text = link.get_text()
            link_text = link_text.replace('\n', '').replace('\t', '').replace('\r', '')
            
            # Checks if any of the keywords are present in the URL or link text
            if len(link_text) > 20:
                if any(keyword in link_url.lower() or keyword in link_text.lower() for keyword in keywords):
                    continue
                
                # Get article title and content for the link
                try:
                    publication_date = soup.find('time')['datetime']
                    publication_date_str = publication_date.strftime('%Y-%m-%d')
                except:
                    publication_date_str = None
                
                # Check if the article was published within the last 24 hours
                
                now = datetime.datetime.now()
                yesterday = now - datetime.timedelta(days=1)
                
                if publication_date_str and publication_date_str < yesterday:
                    continue
                article_content = get_article_content(link_url)
                if article_content is None:
                    article_content = ""
                
                    
                potential_articles.append({"url": link_url, "title": link_text, "description": article_content})
        
        with lock:
            # print(f"Unique articles found in {url}: {len(potential_articles)}")
            global_list.extend(potential_articles)
    
    except Exception as e:
        print(f"Error processing {url}: {str(e)}")
    
    finish_event.set()

def get_info_threaded(url_list):
    num_urls = len(url_list)
    num_threads = min(num_urls, MAX_THREADS)
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        executor.map(get_info_from_url, url_list)

app = FastAPI()

@app.get("/")
async def get_content():
    global global_list
    global_list = []
    
    finish_event.clear()
    get_info_threaded(url_list=url_list)
    finish_event.wait()  # Wait for threads to finish
    
    temp = {"items": global_list}
    return temp
