# Where should AmpCharge build its next EV chargers in NSW?

An independent data project that ranks existing Ampol service stations in NSW
by how good a candidate each is for an AmpCharge fast charger, using only
public data.

**Independent project. Not affiliated with or endorsed by Ampol or AmpCharge.
Built from public data only.**

**[View the live interactive map »](https://ankur794.github.io/ampcharge-nsw/outputs/ampcharge_map.html)**

## The idea

Ampol already owns hundreds of NSW sites that have power, parking and often a
Foodary store. Adding a charger to an existing site is cheaper than building a
new one, so the real question is *which sites first*. This project scores every
Ampol site on EV demand nearby, how short the area is on fast chargers, and the
site's own strengths (Foodary, major road), then ranks them.

## Results

Using live public data: **539 Ampol sites**, the official NSW register of
**~3,400 charger locations**, and **160,000+ EVs** across 128 council areas
(LGAs).

**The validation.** Rather than trust the ranking, I tested whether EV demand
predicts where the whole charging industry actually built its fast chargers.
Across 128 LGAs, with a proper held-out cross-validation:

- correlation (EVs vs fast chargers): **0.70**
- cross-validated R²: **0.45**

So EV demand explains about 45% of where chargers were really built, on data
the model never saw. The demand signal is real.

**The opportunity.** The under-served areas that fall out of this are
established, high-EV suburbs that the fast-charging network hasn't kept up with:
The Hills, Ku-ring-gai, Ryde, Parramatta, Cumberland. Top Ampol sites in those
areas with no fast charger within 2 km include **EG Ampol Kellyville Ridge**,
**Ampol Foodary St Ives North**, **EG Ampol West Ryde** and
**Ampol Foodary Wentworthville**. Full list in `outputs/opportunity_sites.csv`.

## What makes it more than a ranking

1. **Demand validation** (above): does EV demand predict real-world charger
   placement, cross-validated. See `scripts/validate_demand.py`.
2. **Sensitivity test:** the scoring weights are jiggled 500 times at random to
   see which picks hold up under any weighting. See `weight_stability()` in
   `src/ampcharge/scoring.py`.
3. **Tested engine:** the scoring logic is proven on synthetic data with a known
   answer before it touches real data. See `tests/`.

## Honest limitations

- Both EV counts and charger counts partly scale with LGA size/population; the
  next step is to control for population and model EVs-per-charger directly.
- EV counts are at LGA resolution, coarser than a true drive-time catchment.
- No grid-capacity, site-cost or land data (not public), so this finds
  *candidates*, not final build decisions.

## Run it

```bash
pip install -r requirements.txt

# prove the engine on synthetic data with a known answer:
PYTHONPATH=src python -m pytest tests/ -q
PYTHONPATH=src python scripts/run_demo.py

# with the real data files in data/raw/ (see Data sources):
PYTHONPATH=src python scripts/validate_demand.py   # the validation + opportunity list
PYTHONPATH=src python scripts/build_map.py          # the interactive map
```

## Data sources

- Ampol site locations: [NSW FuelCheck](https://api.nsw.gov.au/) (via my fuel-price project)
- EV charger locations: [NSW Transport – EV Charging Locations](https://data.nsw.gov.au/data/dataset/2-ev-charging-locations)
- EV registrations by LGA: NSW vehicle registration data (Peclet open data)
- Postcode / LGA lookup: [matthewproctor/australianpostcodes](https://github.com/matthewproctor/australianpostcodes)

## Layout

```
src/ampcharge/   config, features, scoring  (the model)
scripts/         fetch, validate, map and run scripts
tests/           synthetic ground-truth tests
data/raw/        downloaded public CSVs (gitignored)
outputs/         the map, the scored sites, the opportunity list
```
