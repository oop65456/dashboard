"""FRED (St. Louis Fed): macro series such as the dollar index and Treasury yields."""
from .. import env, net

URL = "https://api.stlouisfed.org/fred/series/observations"
COLUMNS = ["time", "value"]


def series(series_id, start_date):
    """Observations from start_date ("YYYY-MM-DD"). FRED marks missing days with "." - those are skipped."""
    d = net.get_json(URL, params={"series_id": series_id, "observation_start": start_date,
                                  "file_type": "json", "api_key": env.get("FRED_API_KEY")})
    return [{"time": o["date"] + "T00:00:00Z", "value": o["value"]}
            for o in d.get("observations", []) if o["value"] not in (".", "")]
