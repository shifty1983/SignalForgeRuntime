import requests

from src.common.config import get_alpha_vantage_api_key
from src.common.logger import get_logger
from src.common.rate_limiter import RateLimiter
from src.common.retry import RetryConfig, retry_call


class AlphaVantageClient:
    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or get_alpha_vantage_api_key()
        self.logger = get_logger(self.__class__.__name__)
        self.rate_limiter = RateLimiter(
            calls=5,
            period_seconds=60,
            name="alpha_vantage",
        )

        if not self.api_key:
            raise ValueError("Missing ALPHA_VANTAGE_API_KEY")

        self.retry_config = RetryConfig(
            max_attempts=3,
            initial_delay_seconds=1.0,
            max_delay_seconds=30.0,
            backoff_factor=2.0,
            jitter=True,
            exceptions=(Exception,),
        )

    def get_daily(self, symbol: str, outputsize: str = "compact") -> dict:
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol.upper(),
            "outputsize": outputsize,
            "apikey": self.api_key,
        }

        return self._request(params)

    def get_company_overview(self, symbol: str) -> dict:
        params = {
            "function": "OVERVIEW",
            "symbol": symbol.upper(),
            "apikey": self.api_key,
        }

        return self._request(params)

    def get_news_sentiment(self, symbol: str) -> dict:
        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": symbol.upper(),
            "apikey": self.api_key,
        }

        return self._request(params)

    def _request(self, params: dict) -> dict:
        return retry_call(
            self._get,
            params,
            config=self.retry_config,
            logger=self.logger,
        )

    def _get(self, params: dict) -> dict:
        self.rate_limiter.acquire(block=True)

        response = requests.get(self.BASE_URL, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()

        if "Error Message" in data:
            raise ValueError(data["Error Message"])

        if "Note" in data:
            raise ValueError(data["Note"])

        if "Information" in data:
            raise ValueError(data["Information"])

        return data
