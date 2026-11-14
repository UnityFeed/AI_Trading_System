import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def main():

    params = {
        "start": "2017-04-15T23:00:00Z",
        "end": "2017-04-16T00:00:00Z",
        "granularity": 3600,
    }

    url = (
        "https://api.exchange.coinbase.com/"
        "products/BTC-USD/candles?"
        f"{urlencode(params)}"
    )

    request = Request(
        url,
        headers={"User-Agent": "AI-Trading-System/1.0"},
    )

    with urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

    print("Raw Coinbase response for the suspicious hour:")
    print(json.dumps(data, indent=2))
    print()
    print("Read-only check complete. Nothing was saved to the database.")


if __name__ == "__main__":
    main()