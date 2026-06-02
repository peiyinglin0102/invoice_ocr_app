import yfinance as yf
import logging
from datetime import datetime, timedelta
import pandas as pd

logger = logging.getLogger(__name__)

class FinanceUtils:
    @staticmethod
    def get_historical_exchange_rate(currency_from: str, currency_to: str, target_date: str) -> float:
        """
        根據發票日期抓取特定的歷史匯率
        :param currency_from: 原始幣別 (如 'JPY')
        :param currency_to: 目標幣別 (如 'TWD')
        :param target_date: 'YYYY-MM-DD'
        :return: 匯率數值
        """
        if currency_from.upper() == currency_to.upper():
            return 1.0
            
        ticker = f"{currency_from.upper()}{currency_to.upper()}=X"
        logger.info(f"Fetching exchange rate for {ticker} on {target_date}...")
        
        try:
            # 轉換日期
            date_obj = datetime.strptime(target_date, "%Y-%m-%d")
            # yfinance 的儲存資料需要一個 range，所以我們結束日期設為目標的下一天
            start_date = date_obj.strftime("%Y-%m-%d")
            end_date = (date_obj + timedelta(days=5)).strftime("%Y-%m-%d") # 多抓幾天以防遇到假日
            
            data = yf.download(ticker, start=start_date, end=end_date, progress=False)
            
            if data.empty:
                logger.warning(f"No exchange rate data found for {ticker} around {target_date}. Falling back to recent rate.")
                # 若抓不到 (例如未來日期)，抓近 5 天
                data = yf.download(ticker, period="5d", progress=False)
                if data.empty:
                    raise ValueError(f"Cannot fetch any data for {ticker}")
            
            # 取第一筆有效紀錄的 Close 價格
            # yfinance 新版本回傳的常是 multi-index columns, 取得 [('Close', 'JPYTWD=X')] 或者取出第一個值
            close_prices = data['Close']
            if isinstance(close_prices, pd.DataFrame):
                rate = close_prices.iloc[0, 0]
            else:
                rate = close_prices.iloc[0]
            
            rate_val = float(rate)
            logger.info(f"Exchange rate found: 1 {currency_from} = {rate_val} {currency_to}")
            return rate_val
            
        except Exception as e:
            logger.error(f"Error fetching exchange rate: {str(e)}")
            # Fallback 預設日幣抓 0.21, 美金抓 31, 韓元 0.024 之類的 (實務上可以更精細)
            fallback_rates = {"JPY": 0.212, "USD": 31.5, "KRW": 0.024}
            if currency_from in fallback_rates:
                logger.warning(f"Using fallback hardcoded rate for {currency_from}")
                return fallback_rates[currency_from]
            return 1.0 # 失敗時預設回傳 1 以免程式崩潰

if __name__ == "__main__":
    # Test
    rate = FinanceUtils.get_historical_exchange_rate("JPY", "TWD", "2023-06-24")
    print("Test Rate:", rate)
