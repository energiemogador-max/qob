# QOB

Storefront for QOB Atelier — Moroccan heritage streetwear, Casablanca.
Static site, no framework, no build step. Deployed on Cloudflare Pages.

Architecture is derived from `energiemogador-max/novastyle`; none of its
content, copy or theme carries over.

## Locked build parameters

| | |
|---|---|
| Domain | qob.co |
| Firebase | new project (not shared with novastyle) |
| Locales | FR + AR + EN |
| Transacting market | Morocco only — MAD, cash on delivery |
| Lockup | QOB Atelier |

`/fr/` and `/en/` exist as content locales with `transacts: false` and
`price_eur: null`. They rank and inform; they do not take orders yet.

## The data layer

`products-index.json` is the single source of truth. Pages are generated
from it; nothing generates it from pages. There is no second product store.

Stock lives on variants, never on products. A product is orderable only
when at least one variant has stock — that is derived at render time, never
written into the file.

Validate before generating anything:

```
python scripts/validate_index.py            # structural checks
python scripts/validate_index.py --strict    # launch gate: refuses dummy
                                             # data and TODO: placeholder copy
```

## Design system

`assets/tokens.css` holds every colour, typeface and type size in the
system. Nothing downstream may introduce its own. The whole brand changes
from that one file.

## Preview

```
python -m http.server 8765
```

`http://127.0.0.1:8765/ma/qob-coat/qob-coat-mlifa/`

## Phase state

- [x] Phase 0 — discovery of novastyle
- [x] Phase 1 — products-index.json v2 schema + validator
- [ ] Phase 1 — novastyle to v2 migration script
- [x] Phase 3 — one working PDP with variants (`/ma/qob-coat/qob-coat-mlifa/`)
- [ ] Category and heritage pages
- [ ] Admin panel adapted for variant stock
- [ ] SEO layer, sitemap, redirects, 404
- [ ] Blog scaffolding

The three products in `products-index.json` are dummy data, marked
`"_dummy": true`. They are not a line sheet. `--strict` refuses to pass
while any remain.
