# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timedelta
from typing import Tuple

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# 備援匯率（yfinance 完全失敗時使用，並觸發 ERR-005 警告）
FALLBACK_RATES: dict[str, float] = {
    "JPY": 0.212,
    "USD": 31.5,
    "KRW": 0.024,
    "EUR": 33.8,
    "GBP": 39.5,
    "HKD": 4.03,
    "SGD": 23.2,
    "CNY": 4.35,
}


class FinanceUtils:
    """
    財務資料整合管線。
    負責：從 yfinance 抓取指定日期的歷史匯率；失敗時自動切換備援估算值。
    """

    @staticmethod
    def get_historical_exchange_rate(
        currency_from: str,
        currency_to: str,
        target_date: str,
    ) -> Tuple[float, bool]:
        """
        查詢 currency_from → currency_to 在 target_date 當日的收盤匯率。

        :param currency_from: 來源幣別 (e.g. 'JPY')
        :param currency_to:   目標幣別 (e.g. 'TWD')
        :param target_date:   消費日期字串 'YYYY-MM-DD'
        :return: (匯率浮點數, 是否為備援值)
        """
        currency_from = currency_from.strip().upper()
        currency_to   = currency_to.strip().upper()

        if currency_from == currency_to:
            return 1.0, False

        ticker = f"{currency_from}{currency_to}=X"
        logger.info(f"Fetching exchange rate for {ticker} on {target_date}...")

        try:
            date_obj  = datetime.strptime(target_date, "%Y-%m-%d")
            start_str = date_obj.strftime("%Y-%m-%d")
            end_str   = (date_obj + timedelta(days=7)).strftime("%Y-%m-%d")

            data = yf.download(ticker, start=start_str, end=end_str, progress=False, auto_adjust=True)

            if data.empty:
                logger.warning(
                    f"No data for {ticker} around {target_date}. "
                    "Trying most recent 5 days..."
                )
                data = yf.download(ticker, period="5d", progress=False, auto_adjust=True)

            if data.empty:
                raise ValueError(f"yfinance returned empty DataFrame for {ticker}")

            # Handle both single-index and multi-index columns
            close = data["Close"]
            if isinstance(close, pd.DataFrame):
                rate_val = float(close.iloc[0, 0])
            else:
                rate_val = float(close.iloc[0])

            if pd.isna(rate_val) or rate_val <= 0:
                raise ValueError(f"Invalid rate value: {rate_val}")

            logger.info(f"Exchange rate fetched: 1 {currency_from} = {rate_val:.6f} {currency_to}")
            return rate_val, False

        except Exception as e:
            logger.error(f"yfinance error for {ticker}: {e}")

            # ERR-005: Fallback to hardcoded estimate
            fallback = FALLBACK_RATES.get(currency_from)
            if fallback is not None:
                logger.warning(
                    f"ERR-005: Using hardcoded fallback rate for {currency_from}: {fallback}"
                )
                return fallback, True

            # Unknown currency: return 1.0 as last resort
            logger.warning(
                f"ERR-005: No fallback rate available for {currency_from}. Returning 1.0."
            )
            return 1.0, True


if __name__ == "__main__":
    rate, is_fb = FinanceUtils.get_historical_exchange_rate("JPY", "TWD", "2024-03-15")
    print(f"Rate: {rate:.4f}  |  Fallback: {is_fb}")
