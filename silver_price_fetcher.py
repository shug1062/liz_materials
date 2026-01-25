"""Fetch current silver price from Cooksongold"""
import re
import requests
import urllib3
from datetime import datetime, timedelta
import json
import os

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class SilverPriceFetcher:
    def __init__(self, cache_file="silver_price_cache.json"):
        self.cache_file = cache_file
        self.cooksongold_url = "https://www.cooksongold.com/Sheet/Sterling-Silver-Sheet-1.00mm-Fully-Annealed,-100-Recycled-Silver-prcode-CSA-100"
        
    def get_cached_price(self):
        """Get price from cache if it's from today.

        Note: This uses the local calendar day rather than a rolling 24-hour window.
        That matches the typical expectation of "refresh once per day".
        """
        if not os.path.exists(self.cache_file):
            return None
        
        try:
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)
            
            cached_time = datetime.fromisoformat(cache_data['timestamp'])
            if cached_time.date() == datetime.now().date():
                return cache_data
            
        except Exception as e:
            print(f"⚠️ Error reading cache: {e}")
        
        return None
    
    def save_to_cache(self, price_data):
        """Save price to cache"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(price_data, f)
        except Exception as e:
            print(f"⚠️ Error saving cache: {e}")
    
    def fetch_price(self):
        """Fetch current silver price from Cooksongold"""
        try:
            # Try to get from cache first
            cached = self.get_cached_price()
            if cached:
                # Silently use cached price - no need to print every time
                return cached
            
            # Only print when actually fetching
            print("🔍 Fetching fresh silver price from Cooksongold...")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            # Disable SSL verification to avoid certificate issues on macOS
            response = requests.get(self.cooksongold_url, headers=headers, timeout=10, verify=False)
            response.raise_for_status()
            
            # Look for price per kg pattern in the HTML
            # Pattern: £2,939.35 or similar
            price_pattern = r'£([\d,]+\.?\d*)\s*(?:</td>|per kg|/kg)'
            matches = re.findall(price_pattern, response.text)
            
            if matches:
                # Get the first price (usually the 1g price per kg)
                price_str = matches[0].replace(',', '')
                price = float(price_str)
                
                price_data = {
                    'price_per_kg': price,
                    'price_per_gram': price / 1000,
                    'timestamp': datetime.now().isoformat(),
                    'source': 'Cooksongold Sterling Silver 925'
                }
                
                self.save_to_cache(price_data)
                print(f"✅ Fetched silver price: £{price:.2f}/kg (£{price/1000:.3f}/g)")
                
                return price_data
            else:
                print("⚠️ Could not find price on page")
                return self._get_fallback_price()
                
        except Exception as e:
            print(f"⚠️ Error fetching silver price: {e}")
            return self._get_fallback_price()
    
    def _get_fallback_price(self):
        """Return fallback price if fetch fails"""
        # Check cache even if it's old
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)
                    print(f"⚠️ Using old cached price from {cache_data['timestamp']}")
                    cache_data['is_fallback'] = True
                    return cache_data
            except:
                pass
        
        # Don't show estimate - return None so dashboard shows "Unable to fetch"
        print("⚠️ No price available - unable to fetch and no cache exists")
        return None
    
    def get_price(self):
        """Get current silver price (cached or fresh)"""
        return self.fetch_price()


if __name__ == "__main__":
    # Test the fetcher
    fetcher = SilverPriceFetcher()
    price_info = fetcher.get_price()
    print(f"\nSilver Price Info:")
    if price_info:
        print(f"  Per kg: £{price_info['price_per_kg']:.2f}")
        print(f"  Per gram: £{price_info['price_per_gram']:.3f}")
        print(f"  Source: {price_info['source']}")
        print(f"  Last updated: {price_info['timestamp']}")
    else:
        print("  No price available")
