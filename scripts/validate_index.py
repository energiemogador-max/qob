#!/usr/bin/env python3
"""Validate products-index.json before anything is generated from it.

Why this exists
---------------
Nova Style shipped two catalogue files that drifted apart in silence:
catalog.json said `miroirs-sdb` where products-index.json said `sdb-premium`,
49 products disagreed, and nothing ever noticed because nothing ever checked.
QOB has one catalogue file, and this script is the reason it can stay one.

Every reference in the file must resolve, every SKU must be unique, and stock
must live on variants only. A product that violates any of these cannot be
turned into a page.

Usage:
    python scripts/validate_index.py                # structural checks
    python scripts/validate_index.py --strict       # also refuse dummy data
                                                    # and untranslated TODO:
                                                    # strings. Use before launch.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "products-index.json")

errors = []
warnings = []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def walk_strings(node, path=""):
    """Yield (path, string) for every string in the tree."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk_strings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_strings(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def main():
    strict = "--strict" in sys.argv

    with open(INDEX, encoding="utf-8") as fh:
        idx = json.load(fh)

    locales = idx["locales"]
    categories = {c["id"]: c for c in idx["categories"]}
    guides = idx["size_guides"]
    colours = idx["colours"]
    glossary = idx["glossary"]
    care_terms = idx["care_terms"]
    products = idx["products"]

    # ── categories ────────────────────────────────────────────────────────
    for cid, c in categories.items():
        if c["branch"] not in ("heritage", "street"):
            err(f"category {cid}: branch must be 'heritage' or 'street'")
        if c["cross_link"] not in categories:
            err(f"category {cid}: cross_link '{c['cross_link']}' does not exist")
        if c["cross_link"] == cid:
            err(f"category {cid}: cross_link points at itself")
        if categories[c["cross_link"]]["branch"] == c["branch"]:
            warn(f"category {cid}: cross-links to the same branch — the "
                 f"heritage/street mechanism only works across branches")
        if c["size_guide_id"] not in guides:
            err(f"category {cid}: unknown size_guide_id '{c['size_guide_id']}'")
        for loc in locales:
            if loc not in c["name"]:
                err(f"category {cid}: name missing locale '{loc}'")

    # ── size guides ───────────────────────────────────────────────────────
    for gid, g in guides.items():
        if g.get("measured") != "garment_flat":
            err(f"size guide {gid}: measurements must be garment_flat, not body")
        if g.get("unit") != "cm":
            err(f"size guide {gid}: unit must be cm")
        for size, row in g["rows"].items():
            for point in g["points"]:
                if point not in row:
                    err(f"size guide {gid}: size {size} missing '{point}'")

    # ── products ──────────────────────────────────────────────────────────
    all_skus = {}
    for p in products:
        pid = p["id"]

        if p["id"] != p["slug"]:
            err(f"{pid}: id and slug must be identical")
        if p["category"] not in categories:
            err(f"{pid}: unknown category '{p['category']}'")
        elif categories[p["category"]]["branch"] != p["branch"]:
            err(f"{pid}: branch '{p['branch']}' disagrees with its category")
        if p["size_guide_id"] not in guides:
            err(f"{pid}: unknown size_guide_id '{p['size_guide_id']}'")
        if p["heritage_term"] not in glossary and p["heritage_term"] not in categories:
            warn(f"{pid}: heritage_term '{p['heritage_term']}' is in neither the "
                 f"glossary nor the category tree")

        for loc in locales:
            for field in ("name", "description"):
                if loc not in p[field]:
                    err(f"{pid}: {field} missing locale '{loc}'")

        if p.get("price_mad") is None:
            err(f"{pid}: price_mad is required — /ma/ is the transacting market")

        for t in p["construction"]:
            if t not in glossary:
                err(f"{pid}: construction term '{t}' is not in the glossary")
        for c in p["care"]:
            if c not in care_terms:
                err(f"{pid}: care term '{c}' is not in care_terms")

        for cw in p["colourways"]:
            if cw not in colours:
                err(f"{pid}: colourway '{cw}' is not a defined colour")

        guide_sizes = set(guides[p["size_guide_id"]]["rows"]) if p["size_guide_id"] in guides else set()
        for s in p["sizes"]:
            if guide_sizes and s not in guide_sizes:
                err(f"{pid}: size '{s}' has no row in size guide "
                    f"'{p['size_guide_id']}' — the guide modal would show a gap")

        # ── variants: the whole point ─────────────────────────────────────
        if "stock" in p:
            err(f"{pid}: stock is on the product. It belongs on variants only.")

        seen_combo = set()
        for v in p["variants"]:
            sku = v["sku"]
            if sku in all_skus:
                err(f"{pid}: SKU '{sku}' is already used by {all_skus[sku]}")
            all_skus[sku] = pid

            if v["colourway"] not in p["colourways"]:
                err(f"{pid}/{sku}: colourway '{v['colourway']}' is not offered "
                    f"on this product")
            if v["size"] not in p["sizes"]:
                err(f"{pid}/{sku}: size '{v['size']}' is not offered on this product")

            combo = (v["colourway"], v["size"])
            if combo in seen_combo:
                err(f"{pid}: two variants for {combo}")
            seen_combo.add(combo)

            if not isinstance(v.get("stock"), int) or v["stock"] < 0:
                err(f"{pid}/{sku}: stock must be a non-negative integer")
            if v.get("price_override") is not None and v["price_override"] <= 0:
                err(f"{pid}/{sku}: price_override must be positive or null")

        # Orderability is derived, never stored.
        orderable = any(v["stock"] > 0 for v in p["variants"])
        if p.get("active") and not orderable:
            warn(f"{pid}: active but no variant has stock — the page will render "
                 f"with every option disabled and a sold-out button")

        # A combination absent from variants[] renders as 'never made'. That is
        # legal and deliberate, but flag a product where it is the whole grid.
        offered = len(p["colourways"]) * len(p["sizes"])
        if len(p["variants"]) < offered / 2:
            warn(f"{pid}: only {len(p['variants'])} of {offered} colour x size "
                 f"combinations exist — check this is intended")

    # ── launch gate ───────────────────────────────────────────────────────
    if strict:
        for p in products:
            if p.get("_dummy"):
                err(f"{p['id']}: dummy product must be removed before launch")
        for path, s in walk_strings(idx):
            if s.startswith("TODO"):
                err(f"placeholder copy still present at {path}")
        for gid, g in guides.items():
            if g.get("_placeholder"):
                err(f"size guide {gid}: measurements not taken from a physical sample")

    # ── report ────────────────────────────────────────────────────────────
    for w in warnings:
        print("warning:", w)
    for e in errors:
        print("error  :", e)

    print()
    print(f"{len(products)} products, {len(all_skus)} variants, "
          f"{len(categories)} categories, {len(locales)} locales")
    print(f"{len(errors)} errors, {len(warnings)} warnings"
          + (" [strict]" if strict else ""))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
