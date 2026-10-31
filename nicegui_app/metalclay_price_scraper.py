"""Fetch current prices from Metal Clay Ltd website"""
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
import os
from typing import Optional, Dict
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class MetalClayPriceScraper:
    def __init__(self, cache_dir="metalclay_cache"):
        self.cache_dir = cache_dir
        self.base_url = "https://www.metalclay.co.uk"
        
        # Create cache directory if it doesn't exist
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
    
    def _get_cache_filename(self, url: str) -> str:
        """Generate a cache filename from URL"""
        # Use the product slug from the URL as the cache key
        slug = url.rstrip('/').split('/')[-1]
        return os.path.join(self.cache_dir, f"{slug}.json")
    
    def get_cached_price(self, url: str) -> Optional[Dict]:
        """Get price from cache if it's from today"""
        cache_file = self._get_cache_filename(url)
        
        if not os.path.exists(cache_file):
            return None
        
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
            
            cached_time = datetime.fromisoformat(cache_data['timestamp'])
            if cached_time.date() == datetime.now().date():
                return cache_data
            
        except Exception as e:
            print(f"⚠️ Error reading cache for {url}: {e}")
        
        return None
    
    def save_to_cache(self, url: str, price_data: Dict):
        """Save price to cache"""
        cache_file = self._get_cache_filename(url)
        try:
            with open(cache_file, 'w') as f:
                json.dump(price_data, f, indent=2)
        except Exception as e:
            print(f"⚠️ Error saving cache for {url}: {e}")
    
    def fetch_product_price(self, url: str) -> Optional[Dict]:
        """Fetch price for a specific product from Metal Clay Ltd"""
        # Try to get from cache first
        cached = self.get_cached_price(url)
        if cached:
            return cached
        
        try:
            print(f"🔍 Fetching price from {url}...")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            # Disable SSL verification to avoid certificate issues
            response = requests.get(url, headers=headers, timeout=10, verify=False)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Get product title
            title_tag = soup.find('h1')
            product_title = title_tag.get_text(strip=True) if title_tag else "Unknown Product"
            
            # Look for price patterns - inc. VAT and ex. VAT
            # Pattern: £64.95inc. VAT £54.12ex. VAT
            price_text = soup.get_text()
            
            # Try to find inc. VAT price
            inc_vat_pattern = r'£([\d,]+\.?\d*)\s*inc\.\s*VAT'
            inc_vat_match = re.search(inc_vat_pattern, price_text, re.IGNORECASE)
            
            # Try to find ex. VAT price
            ex_vat_pattern = r'£([\d,]+\.?\d*)\s*ex\.\s*VAT'
            ex_vat_match = re.search(ex_vat_pattern, price_text, re.IGNORECASE)
            
            if inc_vat_match or ex_vat_match:
                price_data = {
                    'url': url,
                    'product_title': product_title,
                    'timestamp': datetime.now().isoformat(),
                    'source': 'Metal Clay Ltd'
                }
                
                if inc_vat_match:
                    inc_vat_price_str = inc_vat_match.group(1).replace(',', '')
                    price_data['price_inc_vat'] = float(inc_vat_price_str)
                
                if ex_vat_match:
                    ex_vat_price_str = ex_vat_match.group(1).replace(',', '')
                    price_data['price_ex_vat'] = float(ex_vat_price_str)
                
                # Use ex. VAT price as the main price (for business use)
                price_data['price'] = price_data.get('price_ex_vat', price_data.get('price_inc_vat', 0))
                
                self.save_to_cache(url, price_data)
                print(f"✅ Fetched price for '{product_title}': £{price_data['price']:.2f} (ex. VAT)")
                
                return price_data
            else:
                print(f"⚠️ Could not find price on page: {url}")
                return None
                
        except Exception as e:
            print(f"⚠️ Error fetching price from {url}: {e}")
            return None
    
    def fetch_multiple_products(self, urls: list) -> Dict[str, Optional[Dict]]:
        """Fetch prices for multiple products"""
        results = {}
        for url in urls:
            results[url] = self.fetch_product_price(url)
        return results
    
    def clear_cache(self, url: Optional[str] = None):
        """Clear cache for a specific URL or all cached prices"""
        if url:
            cache_file = self._get_cache_filename(url)
            if os.path.exists(cache_file):
                os.remove(cache_file)
                print(f"✅ Cache cleared for {url}")
        else:
            # Clear all cache files
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.json'):
                    os.remove(os.path.join(self.cache_dir, filename))
            print("✅ All cache cleared")


# Example usage
if __name__ == "__main__":
    scraper = MetalClayPriceScraper()
    
    # Example product URLs
    example_urls = [
        "https://www.metalclay.co.uk/art-clay-silver-clay-20gm/",
        "https://www.metalclay.co.uk/art-clay-silver-clay-7gm/",
        "https://www.metalclay.co.uk/art-clay-silver-clay-7gm-bulk-buy-10pcs/"
    ]
    
    print("Fetching prices from Metal Clay Ltd...")
    results = scraper.fetch_multiple_products(example_urls)
    
    print("\n📊 Results:")
    for url, data in results.items():
        if data:
            print(f"\n{data['product_title']}")
            print(f"  Price (ex. VAT): £{data.get('price_ex_vat', 'N/A')}")
            print(f"  Price (inc. VAT): £{data.get('price_inc_vat', 'N/A')}")
        else:
            print(f"\n❌ Failed to fetch: {url}")
