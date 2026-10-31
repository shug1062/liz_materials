# Silver Price Feature

## Overview
The dashboard now displays the current sterling silver (925) price per gram, automatically fetched from Cooksongold's website.

## Features

### 1. Live Silver Price Display
- Shows the current price per gram in a prominent amber card on the dashboard
- Displayed alongside the 4 main summary cards (Students, Materials, Debt, Credit)
- Price format: £X.XXX (3 decimal places for accuracy)

### 2. Automatic Caching
- Price is cached for 24 hours to minimize web requests
- Cache file: `silver_price_cache.json` (excluded from git)
- Automatically refreshes when cache expires

### 3. Manual Refresh
- **🔄 Update** button in the silver price card
- Click to force an immediate price update from Cooksongold
- Useful for getting the latest price before making purchases

### 4. Last Updated Timestamp
- Shows date when price was last fetched
- Format: DD/MM/YY
- Warning indicator (⚠️) if using fallback/old cached price

### 5. Fallback Mechanism
- If web fetch fails, uses last cached price
- If no cache exists, uses default estimate (£2.90/g)
- Always displays a price, even with network issues

## How It Works

### Price Source
The price is fetched from:
https://www.cooksongold.com/Sheet/Sterling-Silver-Sheet-1.00mm-Fully-Annealed,-100-Recycled-Silver-prcode-CSA-100

This page shows the current market price for Sterling Silver 925 sheet metal.

### Update Schedule
- **On App Start**: Checks if cache is older than 24 hours, fetches if needed
- **On Dashboard Load**: Uses cached price if available
- **Manual Update**: Click "🔄 Update" button to fetch immediately

### Cache Location
- File: `silver_price_cache.json` in the app directory
- Contains: price per kg, price per gram, timestamp, source
- Auto-expires: After 24 hours

## Usage

### Viewing the Price
1. Open the dashboard
2. See the silver price in the amber card (5th card in the top row)
3. Note the "Updated: DD/MM/YY" date

### Updating the Price
1. Click the **"🔄 Update"** button in the silver price card
2. Wait a moment while the price is fetched
3. The page will refresh with the new price
4. A notification will confirm the update

### Interpreting the Display
- **£X.XXX** - Current price per gram
- **Updated: 10/01/26** - Date of last fetch
- **⚠️** - Warning: Using cached/fallback price (network issue)

## Technical Details

### Files
- **silver_price_fetcher.py**: Handles web scraping and caching
- **pages/dashboard.py**: Displays the price on dashboard
- **silver_price_cache.json**: Cache file (not in git)

### Dependencies
- `requests`: For HTTP requests to Cooksongold
- `re`: For parsing price from HTML
- `json`: For cache file management

### Error Handling
1. **Network Error**: Uses old cached price if available
2. **Parse Error**: Falls back to default estimate
3. **Cache Read Error**: Fetches fresh price
4. **All Failures**: Shows default £2.90/g with warning

## Example Prices

Based on current market rates (January 2026):
- Per gram: £2.939 (3 decimal places)
- Per kg: £2,939.35
- Source: Sterling Silver 925, 100% Recycled

## Benefits

1. **Real-time Pricing**: Always see current market rates
2. **Purchase Planning**: Know costs before adding materials
3. **Cost Tracking**: Monitor silver price trends
4. **Offline Support**: Works even with network issues
5. **No API Key**: Direct scraping, no registration needed

## Troubleshooting

### Price Not Updating
- Check internet connection
- Verify Cooksongold website is accessible
- Try manual refresh button
- Check terminal for error messages

### Shows Warning Icon
- Network request failed
- Using old cached price
- Still accurate but may be up to 24 hours old

### Shows Default Price
- No cache available
- All fetch attempts failed
- Default: £2.90/g (reasonable estimate)

## Future Enhancements

Possible additions:
- Price history graph
- Alert when price changes significantly
- Multiple metal prices (gold, platinum)
- Price trend indicator (up/down/stable)
- Email notifications for price changes
