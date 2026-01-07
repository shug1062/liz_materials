"""Web scraping utilities for fetching material prices from suppliers"""
import requests
from bs4 import BeautifulSoup
from typing import Optional, Dict
import re
import urllib3

# Disable SSL warnings when verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Constants
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
REQUEST_TIMEOUT = 10
VAT_RATE = 1.2


def scrape_cooksongold_price(url: str) -> Optional[Dict[str, float]]:
    """
    Scrape fixed price from Cooksongold product page for items sold as single units or packs.
    
    This function looks for prices displayed on the page in common formats like:
    - "£3.32" (with VAT)
    - "£2.77 exc. VAT" (excluding VAT)
    
    Args:
        url: The Cooksongold product page URL
    
    Returns:
        Dict with 'inc_vat' and 'exc_vat' prices, or None if scraping fails
        
    Example:
        >>> scrape_cooksongold_price("https://www.cooksongold.com/...")
        {'inc_vat': 3.32, 'exc_vat': 2.77}
    """
    try:
        headers = {'User-Agent': USER_AGENT}
        
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, verify=False)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        price_inc_vat = None
        price_exc_vat = None
        
        # Find all text containing £ symbol
        price_elements = soup.find_all(string=re.compile(r'£\d+\.\d+'))
        
        for element in price_elements:
            text = element.strip()
            
            # Extract price with VAT (usually just "£X.XX")
            if 'exc' not in text.lower() and price_inc_vat is None:
                match = re.search(r'£(\d+\.\d+)', text)
                if match:
                    price_inc_vat = float(match.group(1))
            
            # Extract price excluding VAT
            if 'exc' in text.lower() and 'vat' in text.lower():
                match = re.search(r'£(\d+\.\d+)', text)
                if match:
                    price_exc_vat = float(match.group(1))
        
        # If we found at least the inc VAT price, return it
        if price_inc_vat is not None:
            return {
                'inc_vat': price_inc_vat,
                'exc_vat': price_exc_vat if price_exc_vat else price_inc_vat / VAT_RATE
            }
        
        return None
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None
    except Exception as e:
        print(f"Error parsing price from {url}: {e}")
        return None


def scrape_cooksongold_per_gram_price(url: str) -> Optional[Dict[str, float]]:
    """
    Scrape per-gram pricing from Cooksongold product pages using structured meta tags.
    
    This function reads the meta tag: <meta itemprop="price" content="4072.910 per kg"/>
    This is the most accurate and consistent source for weight-based pricing.
    
    Handles both formats:
    - "per kg" (e.g., £2,889.44 per kg) - automatically converts to per gram
    - "per g" (e.g., £4.16 per g) - uses value directly
    
    Works for:
    - Sheet silver
    - Wire (round, D-shape, etc.)
    - Bezel strips
    - Tube
    - Any other weight-based precious metal products
    
    Args:
        url: The Cooksongold product page URL
    
    Returns:
        Dict with 'inc_vat' (price per gram) and 'exc_vat' prices, or None if scraping fails
        
    Example:
        >>> scrape_cooksongold_per_gram_price("https://www.cooksongold.com/.../Sheet/...")
        {'inc_vat': 2.8894, 'exc_vat': 2.4078}
    """
    try:
        headers = {'User-Agent': USER_AGENT}
        
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, verify=False)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for meta tag with price per kg or per g
        meta_price = soup.find('meta', {'itemprop': 'price'})
        if meta_price and 'content' in meta_price.attrs:
            content = str(meta_price['content'])
            
            # Check for "per kg" format first (needs conversion)
            match = re.search(r'([\d,]+\.?\d*)\s*per\s*kg', content, re.IGNORECASE)
            if match:
                price_str = match.group(1).replace(',', '')
                price_per_kg = float(price_str)
                price_per_gram = price_per_kg / 1000
                return {
                    'inc_vat': price_per_gram,
                    'exc_vat': price_per_gram / VAT_RATE
                }
            
            # Check for "per g" format (already in grams)
            # (?!\w) negative lookahead ensures we don't match "per gram"
            match = re.search(r'([\d,]+\.?\d*)\s*per\s*g(?!\w)', content, re.IGNORECASE)
            if match:
                price_str = match.group(1).replace(',', '')
                price_per_gram = float(price_str)
                return {
                    'inc_vat': price_per_gram,
                    'exc_vat': price_per_gram / VAT_RATE
                }
        
        # If no meta tag found, return None
        print(f"Warning: No price meta tag found for URL: {url}")
        return None
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None
    except Exception as e:
        print(f"Error parsing per-gram price from {url}: {e}")
        return None


def get_material_price_from_url(url: str, use_vat: bool = True, pricing_type: str = "fixed") -> Optional[float]:
    """
    Get material price from supplier URL.
    
    This is the main entry point for price scraping. It routes to the appropriate
    scraper function based on the pricing type.
    
    Args:
        url: The supplier product page URL
        use_vat: If True, return price including VAT, otherwise excluding VAT
        pricing_type: Pricing model to use:
            - 'fixed': Standard per-item or per-pack pricing
            - 'per_kg': Weight-based pricing (returns price per gram)
    
    Returns:
        Price as float, or None if scraping fails
        - For 'fixed': price per item/pack
        - For 'per_kg': price per gram (always in grams, never kg)
        
    Example:
        >>> # Fixed price item
        >>> get_material_price_from_url(url, use_vat=True, pricing_type='fixed')
        3.32
        
        >>> # Weight-based item (returns price per gram)
        >>> get_material_price_from_url(url, use_vat=True, pricing_type='per_kg')
        2.8894
    """
    if 'cooksongold.com' in url:
        if pricing_type == 'per_kg':  # Note: Despite name, always returns per GRAM
            prices = scrape_cooksongold_per_gram_price(url)
        else:
            prices = scrape_cooksongold_price(url)
            
        if prices:
            return prices['inc_vat'] if use_vat else prices['exc_vat']
    
    return None
