# Where should AmpCharge build its next EV chargers in NSW?

An independent data project looking at where Ampol's existing NSW service
stations could take an AmpCharge fast charger, and what actually drives where
the charging industry builds. Public data only.

**Independent project. Not affiliated with or endorsed by Ampol or AmpCharge.**

**[View the live interactive map »](https://ankur794.github.io/ampcharge-nsw/outputs/ampcharge_map.html)**

## The short version

The charging market clusters. New fast chargers are going in next to existing
ones and close to the city, not where EV owners are short of charging. That
leaves established high-EV suburbs, like The Hills and Ku-ring-gai, with fewer
fast chargers than their EV numbers would suggest, and Ampol already has sites
in those areas.

This project is a **first-pass filter**: it narrows 539 Ampol sites down to a
shortlist worth a closer look. It is not a final build list, because the things
that really decide a site (grid capacity, lease terms, land cost) aren't public.

## The data

- **539 Ampol sites** in NSW (FuelCheck)
- **~3,400 charger records** from the official NSW EV charging register,
  including **94 planned fast chargers** not yet built
- **160,000+ battery EVs** across 128 council areas (LGAs), with 12-month growth

## What I tested, and what came out

I ran three tests and report all of them, including the ones that didn't go
the model's way.

**1. Does EV demand explain where fast chargers exist today?**
Across 128 LGAs, EV numbers line up with charger numbers (correlation 0.70,
cross-validated R² 0.45). But most of that is size: LGA size alone gives
R² 0.42, and EV demand adds only +0.07 on top. Per head, there's no clear link
(correlation -0.01). So bigger areas have more EVs and more chargers, but
demand alone doesn't explain placement.

**2. Are the planned chargers going into the gaps?**
No. Under-served LGAs are getting 43% of planned fast chargers, below the 52%
you'd expect from their EV numbers. The top-ranked Ampol opportunity sites
have a planned charger nearby 12% of the time, against 16% for other Ampol sites.

**3. So what does predict where the planned chargers go?**
I modelled it across all 539 Ampol sites (cross-validated AUC):

| What the model used | AUC |
| --- | --- |
| Distance to existing chargers and to the CBD | **0.74** |
| EV demand in the area | 0.66 |
| Site features (major road, Foodary) | 0.58 |

The plain-English version:

| Nearest existing fast charger | Ampol sites | Planned charger within 2 km |
| --- | --- | --- |
| under 1 km | 165 | **24%** |
| 1 to 3 km | 150 | 20% |
| 3 to 10 km | 93 | 9% |
| over 10 km | 131 | 4% |

A site next to an existing charger is about six times more likely to get a new
one nearby than a site more than 10 km away. Part of this is simply that busy
urban areas attract everything, but the clustering is clear.

## What it means

Two readings, and public data can't settle which is right:

1. The gaps exist for reasons we can't see from outside (grid capacity, land,
   leases), and operators are avoiding them for good reason.
2. The gaps are real and the market is leaving them open, which would be an
   opening for a company that already owns sites there.

Either way, the shortlist below is where it's worth asking that question.

## The shortlist

Ampol sites in LGAs with fewer fast chargers than their EV numbers suggest, and
no fast charger within 2 km. Top of the list:

- EG Ampol Kellyville Ridge (The Hills)
- Ampol Rouse Hill (The Hills)
- Ampol Foodary St Ives North (Ku-ring-gai)
- EG Ampol West Ryde (Ryde)
- Ampol Foodary Wentworthville (Cumberland)

Full list: `outputs/opportunity_sites.csv`. All 25 are on the map.

## Limitations

- EV numbers are only available by LGA, so anything finer is an estimate.
- Planned chargers have no LGA in the source file, so each was given the LGA of
  its nearest existing charger.
- 94 planned chargers is a small sample; treat test 2 as a signal, not proof.
- No grid, land or cost data, so this finds candidates, not decisions.

## Run it

```bash
pip install -r requirements.txt

# check the scoring engine on synthetic data with a known answer
PYTHONPATH=src python -m pytest tests/ -q

# with the public data files in data/raw/
PYTHONPATH=src python scripts/validate_demand.py        # test 1 + shortlist
PYTHONPATH=src python scripts/backtest_upcoming.py      # test 2
PYTHONPATH=src python scripts/what_drives_placement.py  # test 3
PYTHONPATH=src python scripts/build_map.py              # the map
```

## Data sources

- Ampol sites: NSW FuelCheck (from my fuel-price project)
- Charger locations: [NSW EV Charging Locations](https://data.nsw.gov.au/data/dataset/2-ev-charging-locations)
- EV registrations by LGA: NSW vehicle registration data (Peclet open data portal)
- Postcode and LGA lookup: [australianpostcodes](https://github.com/matthewproctor/australianpostcodes)

## Layout

```
src/ampcharge/   scoring engine (features, scoring, sensitivity test)
scripts/         fetch, test and map scripts
tests/           synthetic ground-truth tests
data/raw/        downloaded public data (not committed)
outputs/         map, shortlist and test results
```
