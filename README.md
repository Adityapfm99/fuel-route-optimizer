# Fuel Route Optimizer

A Django API that takes a start and finish location in the USA and returns:

- the driving route (GeoJSON, plus an interactive map),
- where to fuel up along the way, and how many gallons to buy at each stop, given a 500-mile range,
- the total fuel cost at 10 MPG, using the prices in `data/fuel_prices.csv`.

A request makes **one external API call** (the route). A repeated request makes none.

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                   # install dependencies
uv run python manage.py migrate           # create the SQLite database
uv run python manage.py load_stations     # load data/fuel_stations.csv (≈6.6k stations)
uv run python manage.py runserver
```

Run the tests with:

```bash
uv run pytest
```

`data/fuel_stations.csv` is already geocoded and committed. To rebuild it from the raw price file, run
`uv run python scripts/geocode_stations.py <us_cities.csv> data/fuel_prices.csv data/fuel_stations.csv`.

## Endpoints

### `GET /api/route/?start=…&finish=…`

Also available as `POST /api/route/` with a JSON body: `{"start": "...", "finish": "..."}`.

`start` and `finish` can be in any of these formats:

| Format | Example | External call? |
|---|---|---|
| `City, ST` | `Chicago, IL` | No. Looked up in the bundled US cities index. |
| `lat,lng` | `41.8781,-87.6298` | No |
| Free-text address | `1600 Pennsylvania Ave, Washington DC` | One Nominatim call, then cached |

```bash
curl "http://127.0.0.1:8000/api/route/?start=Chicago,%20IL&finish=Houston,%20TX"
```

```jsonc
{
  "start":  { "query": "Chicago, IL", "name": "Chicago, IL", "lat": 41.88585, "lng": -87.61812 },
  "finish": { "query": "Houston, TX", "name": "Houston, TX", "lat": 29.68068, "lng": -95.4122 },
  "vehicle": { "max_range_miles": 500.0, "miles_per_gallon": 10.0 },
  "route": {
    "distance_miles": 1094.1,
    "duration_hours": 20.06,
    "geometry": { "type": "LineString", "coordinates": [[-87.61811, 41.88551], "..."] }
  },
  "fuel_stops": [
    { "stop_number": 1, "opis_id": 72577, "name": "QUIKTRIP #7205", "address": "I-80, EXIT 161",
      "city": "Lansing", "state": "IL", "lat": 41.566045, "lng": -87.544634,
      "price_per_gallon": 3.079, "route_mile": 20.1, "detour_miles": 7.9, "gallons": 31.81, "cost": 97.94 },
    { "stop_number": 2, "name": "HUCKS FOOD & FUEL #379", "city": "Marion", "state": "IL",
      "price_per_gallon": 2.929, "route_mile": 318.1, "gallons": 47.8, "cost": 140.01, "...": "..." },
    { "stop_number": 3, "name": "Quiktrip #7900", "city": "Texarkana", "state": "TX",
      "price_per_gallon": 2.857, "route_mile": 796.1, "gallons": 29.8, "cost": 85.16, "...": "..." }
  ],
  "total_gallons": 109.41,
  "total_fuel_cost": 323.1,
  "meta": { "stations_considered": 179, "external_api_calls": 1, "cached": false, "elapsed_ms": 2092.6 },
  "map_url": "http://127.0.0.1:8000/api/route/map/?start=Chicago%2C+IL&finish=Houston%2C+TX"
}
```

Errors are returned as `{"error": "..."}`:

| Status | Cause |
|---|---|
| 400 | `start` or `finish` is missing |
| 404 | The location could not be found |
| 422 | The location is outside the USA, there is no drivable route, or a gap between stations is longer than 500 miles |
| 502 | The routing or geocoding service is unavailable |

### `GET /api/route/map/?start=…&finish=…`

Returns an HTML page with a Leaflet/OpenStreetMap map. It draws the route and numbered fuel stops, with a side panel listing each stop and the total cost. Every JSON response includes a link to this page in `map_url`. The page reuses the cached plan, so it makes no extra API calls.

### Postman

Import `postman/fuel-route.postman_collection.json`. Its `baseUrl` variable defaults to `http://127.0.0.1:8000`.

## How it works

```
start, finish ──► geocode (local index, no network)
              ──► OSRM route (the single external call)
              ──► stations within 10 mi of the route (numpy, in memory)
              ──► fuel plan (dynamic programming)
              ──► JSON / map (cached per start+finish)
```

| Module | Responsibility |
|---|---|
| `fuelroute/services/geocoding.py` | Turns `lat,lng`, `City, ST`, or free text into coordinates |
| `fuelroute/services/osrm.py` | The routing call (public OSRM server, full-resolution GeoJSON) |
| `fuelroute/services/station_index.py` | Loads all stations into numpy arrays once per process. For each station near the route, finds its route mile and detour distance. |
| `fuelroute/services/fuel_planner.py` | Chooses which stations to stop at and how much to buy at each one |
| `fuelroute/services/trip_planner.py` | Ties the steps together and caches the result |
| `fuelroute/views.py` | The JSON API and the map page |

### Choosing the fuel stops

This is the "gas station problem" on a fixed route. The cheapest possible plan follows a simple greedy rule, but it can be impractical. On New York → Los Angeles it made **18 stops**, some for about 1 gallon, because the next town was a cent cheaper.

The planner instead minimises **fuel cost + $10 for each stop**, using an exact dynamic program. The program relies on a structural result from Khuller, Malekian & Mestre, *To fill or not to fill* (2007). In some optimal plan, at each stop you either:

- buy just enough to reach the next stop, if that stop is at least as cheap, or
- fill the tank, if the next stop is more expensive.

Because of this, the fuel left on arrival at a stop can take only a few values, and the search takes about 70 ms for a cross-country route.

The $10 only influences which plan is chosen. `total_fuel_cost` is the money actually spent on fuel. The penalty is set by `FUELROUTE["STOP_PENALTY_USD"]` in `config/settings.py`; setting it to `0` gives the strictly cheapest plan.

| Route | Plan | Stops | Fuel cost |
|---|---|---|---|
| New York, NY → Los Angeles, CA (2,800.6 mi) | Strictly cheapest | 18 | $849.33 |
| | **Default** (penalty $10) | **7** | **$857.11** (+0.9%) |
| Chicago, IL → Houston, TX (1,094.1 mi) | Strictly cheapest | 8 | $321.00 |
| | **Default** (penalty $10) | **3** | **$323.10** |

### Performance

- **Station data is prepared ahead of time.** The 8k stations are geocoded offline, so a request never geocodes stations.
- **The station search runs in memory.** Finding stations near a route is a vectorised numpy distance computation over all stations, taking a few milliseconds.
- **Plans are cached.** Each plan is stored in Django's cache, keyed by start and finish. A repeated request or the map view responds in about 1 ms and makes 0 external calls.
- **Cold requests take about 2–3 s**, almost all of it waiting for the public OSRM server.

## Assumptions

- **Stations are placed at their city's centroid.** The price file has only city and state, not coordinates. 7,516 of 8,151 rows matched a US city and the rest are skipped. Stations listed more than once under the same OPIS id keep their cheapest price, which leaves about 6.6k stations.
- **A station within 10 miles of the route counts as "on" it.** This tolerance covers the error from city-centroid placement. A station's position on the route is the nearest route point.
- **The truck starts with an empty tank** and fuels up before leaving. Stations within 30 route miles of the start count as being at mile 0. As a result, `total_gallons` equals `distance / 10` and the cost covers every gallon used.
- **The truck arrives with an empty tank.** It doesn't buy fuel it won't use.
- **Fuel price is the CSV's `Retail Price`,** taken as current and constant.
- **Free services:**
  - Routing uses [OSRM](https://project-osrm.org/) (OpenStreetMap data). Set `OSRM_URL` to point at another server.
  - Free-text geocoding uses [Nominatim](https://nominatim.org/). Set `NOMINATIM_URL` to point at another server.
  - Map tiles come from OpenStreetMap.
- **The cache is in local memory,** which suits a single process. Use Redis or Memcached in production.
