import requests
import urllib3
from requests import Response

from src.configuration.configuration import Configuration


class HomeAssistantClient:
    def __init__(self):
        options = Configuration()

        self.base_url = options.home_assistant_url()
        self.verify = options.verify_https()
        if not self.verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        token = options.home_assistant_token()
        self.headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

    def post(self, path: str, payload: dict) -> Response:
        return requests.post(self.base_url + path, json=payload, headers=self.headers, timeout=10, verify=self.verify)

    def get(self, path: str) -> Response:
        return requests.get(self.base_url + path, headers=self.headers, timeout=10, verify=self.verify)

