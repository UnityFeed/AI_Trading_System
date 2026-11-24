# Archived one-time scripts

These scripts did a job once and are kept for reference. They are not part
of the daily workflow. Do not rerun them without a clear reason.

| Script | What it did |
|---|---|
| `import_historical_data.py` | One-time import of the Kraken CSV history. **Done; never run it again** (see CLAUDE.md). |
| `import_bitstamp_data.py` | First full download of Bitstamp hourly candles (2013 on). |
| `import_coinbase_data.py` | First full download of Coinbase hourly candles (2015 on). |
| `final_recent_data_pull.py` | One-off pull of the last 720 hours from all exchanges. |
| `check_coinbase_source_candle.py` | Checked one suspicious Coinbase candle against the API (2017-04-15). |
| `inspect_kraken_source_candle.py` | Checked suspicious Kraken candles against the original CSV. |
| `inspect_return_extremes.py` | Looked at the largest hourly returns around known anomalies. |
| `report_hourly_analysis.py` | Early hourly SMA + returns report on Kraken only (replaced by `report_indicators`). |
| `report_hourly_returns.py` | Early hourly returns report on Kraken only (replaced by `report_indicators`). |

Run one only if needed, from the project folder:
`python -m scripts.archive.<name>`

For the daily routine use the app (`start_app.bat`) or `python -m scripts.daily_run`.
