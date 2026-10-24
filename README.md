# Where should AmpCharge build its next EV chargers in NSW?

An independent data project that ranks existing Ampol service stations in NSW
by how good a candidate each is for an AmpCharge fast charger, using only
public data.

**Independent project. Not affiliated with or endorsed by Ampol or AmpCharge.
Built from public data only.**

## The idea

Ampol already owns hundreds of NSW sites that have power, parking and often a
Foodary store. Adding a charger to an existing site is cheaper than building a
new one, so the real question is *which sites first*. This project scores every
Ampol site on four things and ranks them:

- **Demand** – EVs registered nearby, how fast that is growing, and the share
  of apartments (people who can't charge at home).
- **Gap** – how few fast chargers already serve the area.
- **Traffic** – cars passing the site each day.
- **Site** – does it have a Foodary, is it open 24/7, is it on a highway.

## What makes it more than a ranking

The ranking is the easy part. Two steps make it trustworthy:

1. **Backtest.** We score every site using only data from before AmpCharge's
   current sites were built, then check whether those real sites land near the
   top. If the model agrees with Ampol's own decisions, it's believable. See
   `backtest()` in `src/ampcharge/scoring.py`.
2. **Sensitivity test.** We jiggle the four weights 500 times at random and
   count how often each site stays in the Top 20. Sites that stay no matter the
   weighting are strong picks; ones that drop out easily are labelled "maybe".
   See `weight_stability()`.

## Run it

```bash
pip install -r requirements.txt

# See the whole thing work on synthetic data (no downloads needed):
PYTHONPATH=src python scripts/run_demo.py

# Run the tests (they prove the engine on data with a known answer):
PYTHONPATH=src python -m pytest tests/ -q
```

## Use real data (run these on your own machine)

The data sites are blocked in some sandboxes, so fetch locally:

```bash
# 1. Ampol sites from your existing fuel database
python scripts/extract_ampol_sites.py --db $FUEL_DB_PATH
#    then open data/raw/ampol_sites_nsw.csv and set has_foodary / is_24_7 /
#    on_highway where you know them.

# 2. Every public charger in NSW
python scripts/fetch_chargers.py --key $OCM_API_KEY

# 3. EV registrations by postcode: download from TfNSW (see Data sources),
#    save as data/raw/ev_by_postcode.csv with columns
#    postcode, ev_count, ev_count_prev

# 4. Census by postcode from ABS DataPacks, saved as
#    data/raw/demographics.csv with columns
#    postcode, pc_lat, pc_lon, population, apartment_share
```

Then point `run_demo.py` (or a small `run_real.py`) at those CSVs instead of
the synthetic world.

## Data sources

- Ampol site locations: NSW FuelCheck API (via my fuel-price project)
- EV chargers: [Open Charge Map](https://openchargemap.org/site/develop/api)
- EV registrations: [TfNSW registration statistics](https://opendata.transport.nsw.gov.au/data/dataset/2342b8e4-d4fc-4549-82de-b36380ea46f2)
- Traffic: [TfNSW Traffic Volume Counts API](https://opendata.transport.nsw.gov.au/data/dataset/nsw-roads-traffic-volume-counts-api)
- Census: ABS 2021 Census DataPacks

## Honest limitations

- No grid-capacity data: some sites can't take a fast charger without an
  expensive upgrade, and that isn't public.
- No site costs, leases or land size.
- Traffic counters aren't outside every site, so some AADT figures come from the
  nearest counter (flagged in the data).
- EV counts are by postcode, coarser than a true drive-time catchment.

## Layout

```
src/ampcharge/   config, features, scoring  (the model)
scripts/         fetch + run scripts
tests/           synthetic ground-truth tests
data/raw/        your downloaded CSVs (gitignored)
outputs/         maps and site cards
```
