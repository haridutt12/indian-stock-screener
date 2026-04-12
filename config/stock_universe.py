"""
Stock universe definitions for Indian markets.
Tickers use yfinance format: <SYMBOL>.NS for NSE.
"""

# Nifty 50 constituents (as of 2025)
NIFTY_50 = {
    "RELIANCE": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "HDFCBANK": "HDFCBANK.NS",
    "BHARTIARTL": "BHARTIARTL.NS",
    "ICICIBANK": "ICICIBANK.NS",
    "INFOSYS": "INFY.NS",
    "SBIN": "SBIN.NS",
    "HINDUNILVR": "HINDUNILVR.NS",
    "ITC": "ITC.NS",
    "LT": "LT.NS",
    "KOTAKBANK": "KOTAKBANK.NS",
    "AXISBANK": "AXISBANK.NS",
    "BAJFINANCE": "BAJFINANCE.NS",
    "ASIANPAINT": "ASIANPAINT.NS",
    "MARUTI": "MARUTI.NS",
    "TITAN": "TITAN.NS",
    "SUNPHARMA": "SUNPHARMA.NS",
    "ULTRACEMCO": "ULTRACEMCO.NS",
    "WIPRO": "WIPRO.NS",
    "NESTLEIND": "NESTLEIND.NS",
    "POWERGRID": "POWERGRID.NS",
    "NTPC": "NTPC.NS",
    "ONGC": "ONGC.NS",
    "M&M": "M&M.NS",
    "BAJAJFINSV": "BAJAJFINSV.NS",
    "HCLTECH": "HCLTECH.NS",
    "ADANIENT": "ADANIENT.NS",
    "ADANIPORTS": "ADANIPORTS.NS",
    "TATAMOTORS": "TATAMOTORS.NS",
    "TATASTEEL": "TATASTEEL.NS",
    "HINDALCO": "HINDALCO.NS",
    "JSWSTEEL": "JSWSTEEL.NS",
    "COALINDIA": "COALINDIA.NS",
    "BPCL": "BPCL.NS",
    "DRREDDY": "DRREDDY.NS",
    "CIPLA": "CIPLA.NS",
    "DIVISLAB": "DIVISLAB.NS",
    "APOLLOHOSP": "APOLLOHOSP.NS",
    "BRITANNIA": "BRITANNIA.NS",
    "EICHERMOT": "EICHERMOT.NS",
    "HEROMOTOCO": "HEROMOTOCO.NS",
    "BAJAJ-AUTO": "BAJAJ-AUTO.NS",
    "TECHM": "TECHM.NS",
    "INDUSINDBK": "INDUSINDBK.NS",
    "GRASIM": "GRASIM.NS",
    "SHREECEM": "SHREECEM.NS",
    "TATACONSUM": "TATACONSUM.NS",
    "SBILIFE": "SBILIFE.NS",
    "HDFCLIFE": "HDFCLIFE.NS",
    "LTF": "LTF.NS",
}

# Additional Nifty Next 50 / midcap stocks to form ~Nifty 200 universe
NIFTY_NEXT_50 = {
    "PIDILITIND": "PIDILITIND.NS",
    "SIEMENS": "SIEMENS.NS",
    "ABB": "ABB.NS",
    "HAL": "HAL.NS",
    "BEL": "BEL.NS",
    "IRCTC": "IRCTC.NS",
    "DMART": "DMART.NS",
    "NYKAA": "NYKAA.NS",
    "ZOMATO": "ZOMATO.NS",
    "PAYTM": "PAYTM.NS",
    "MUTHOOTFIN": "MUTHOOTFIN.NS",
    "CHOLAFIN": "CHOLAFIN.NS",
    "BANKBARODA": "BANKBARODA.NS",
    "CANBK": "CANBK.NS",
    "PNB": "PNB.NS",
    "IDBI": "IDBI.NS",
    "FEDERALBNK": "FEDERALBNK.NS",
    "IDFCFIRSTB": "IDFCFIRSTB.NS",
    "BANDHANBNK": "BANDHANBNK.NS",
    "AUBANK": "AUBANK.NS",
    "TATAPOWER": "TATAPOWER.NS",
    "ADANIGREEN": "ADANIGREEN.NS",
    "ADANITRANS": "ADANITRANS.NS",
    "TORNTPOWER": "TORNTPOWER.NS",
    "CESC": "CESC.NS",
    "AUROPHARMA": "AUROPHARMA.NS",
    "LUPIN": "LUPIN.NS",
    "BIOCON": "BIOCON.NS",
    "ALKEM": "ALKEM.NS",
    "TORNTPHARM": "TORNTPHARM.NS",
    "ABBOTINDIA": "ABBOTINDIA.NS",
    "PERSISTENT": "PERSISTENT.NS",
    "LTIM": "LTIM.NS",
    "MPHASIS": "MPHASIS.NS",
    "COFORGE": "COFORGE.NS",
    "OFSS": "OFSS.NS",
    "KPITTECH": "KPITTECH.NS",
    "ZEEL": "ZEEL.NS",
    "PVRINOX": "PVRINOX.NS",
    "INDIGO": "INDIGO.NS",
    "INTERGLOBE": "INTERGLOBE.NS",
    "VBL": "VBL.NS",
    "DABUR": "DABUR.NS",
    "MARICO": "MARICO.NS",
    "GODREJCP": "GODREJCP.NS",
    "COLPAL": "COLPAL.NS",
    "EMAMILTD": "EMAMILTD.NS",
    "BERGEPAINT": "BERGEPAINT.NS",
    "KANSAINER": "KANSAINER.NS",
    "HAVELLS": "HAVELLS.NS",
}

# Combined Nifty 200 universe
NIFTY_200 = {**NIFTY_50, **NIFTY_NEXT_50}

# Sector mappings (stock -> sector)
SECTOR_MAP = {
    # IT
    "TCS": "IT", "INFOSYS": "IT", "WIPRO": "IT", "HCLTECH": "IT",
    "TECHM": "IT", "PERSISTENT": "IT", "LTIM": "IT", "MPHASIS": "IT",
    "COFORGE": "IT", "OFSS": "IT", "KPITTECH": "IT",
    # Banking & Finance
    "HDFCBANK": "Banking", "ICICIBANK": "Banking", "SBIN": "Banking",
    "KOTAKBANK": "Banking", "AXISBANK": "Banking", "INDUSINDBK": "Banking",
    "BANKBARODA": "Banking", "CANBK": "Banking", "PNB": "Banking",
    "FEDERALBNK": "Banking", "IDFCFIRSTB": "Banking", "BANDHANBNK": "Banking",
    "AUBANK": "Banking", "IDBI": "Banking",
    "BAJFINANCE": "Finance", "BAJAJFINSV": "Finance", "MUTHOOTFIN": "Finance",
    "CHOLAFIN": "Finance", "LTF": "Finance", "SBILIFE": "Finance",
    "HDFCLIFE": "Finance",
    # Oil & Gas
    "RELIANCE": "Oil & Gas", "ONGC": "Oil & Gas", "BPCL": "Oil & Gas",
    # Auto
    "MARUTI": "Auto", "TATAMOTORS": "Auto", "M&M": "Auto",
    "BAJAJ-AUTO": "Auto", "HEROMOTOCO": "Auto", "EICHERMOT": "Auto",
    # Pharma
    "SUNPHARMA": "Pharma", "DRREDDY": "Pharma", "CIPLA": "Pharma",
    "DIVISLAB": "Pharma", "AUROPHARMA": "Pharma", "LUPIN": "Pharma",
    "BIOCON": "Pharma", "ALKEM": "Pharma", "TORNTPHARM": "Pharma",
    "ABBOTINDIA": "Pharma",
    # FMCG
    "HINDUNILVR": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG", "DABUR": "FMCG", "MARICO": "FMCG",
    "GODREJCP": "FMCG", "COLPAL": "FMCG", "EMAMILTD": "FMCG", "VBL": "FMCG",
    # Metal
    "TATASTEEL": "Metal", "HINDALCO": "Metal", "JSWSTEEL": "Metal",
    "COALINDIA": "Metal",
    # Infra & Capital Goods
    "LT": "Infra", "SIEMENS": "Infra", "ABB": "Infra", "HAL": "Infra",
    "BEL": "Infra", "POWERGRID": "Infra", "NTPC": "Infra",
    "TATAPOWER": "Energy", "ADANIGREEN": "Energy", "ADANITRANS": "Energy",
    "TORNTPOWER": "Energy", "CESC": "Energy",
    # Cement
    "ULTRACEMCO": "Cement", "SHREECEM": "Cement", "GRASIM": "Cement",
    # Consumer
    "TITAN": "Consumer", "ASIANPAINT": "Consumer", "PIDILITIND": "Consumer",
    "BERGEPAINT": "Consumer", "KANSAINER": "Consumer", "HAVELLS": "Consumer",
    "DMART": "Consumer", "APOLLOHOSP": "Healthcare",
    # New-age tech
    "ZOMATO": "New-age Tech", "NYKAA": "New-age Tech", "PAYTM": "New-age Tech",
    "IRCTC": "New-age Tech",
    # Conglomerate
    "ADANIENT": "Conglomerate", "ADANIPORTS": "Ports",
    "TATACONSUM": "FMCG",
}

# Sector -> list of stock symbols
def get_sector_stocks(sector: str, universe: dict = None) -> list[str]:
    if universe is None:
        universe = NIFTY_200
    return [sym for sym in universe if SECTOR_MAP.get(sym) == sector]

def get_all_sectors() -> list[str]:
    return sorted(set(SECTOR_MAP.values()))

def get_yf_tickers(symbols: list[str], universe: dict = None) -> list[str]:
    """Convert symbol list to yfinance ticker format."""
    if universe is None:
        universe = NIFTY_200
    return [universe[s] for s in symbols if s in universe]

def get_universe_tickers(universe: dict = None) -> list[str]:
    """Get all yfinance tickers for a universe."""
    if universe is None:
        universe = NIFTY_200
    return list(universe.values())
