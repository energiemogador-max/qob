#!/usr/bin/env python3
"""Generate the QOB storefront from products-index.json.

products-index.json is the single source of truth. Every page this script
writes is derived from it — nothing here invents a product, a price or a
stock count, and nothing ever writes back into the data file.

Locales emitted
---------------
/ma/     French, MAD, cash on delivery   (the transacting market)
/ma/ar/  Arabic, MAD, cash on delivery   (same market, mirrored layout)

/fr/ and /en/ are declared in the data file but are NOT emitted yet: they
have no EUR prices and no translated copy, so publishing them would ship
thin duplicates of the Moroccan pages and invite exactly the duplicate
indexing that hurt novastyle.ma. They turn on here when the copy exists —
see EMIT_EU. Until then no hreflang points at them, so nothing dangles.

Usage:
    python scripts/validate_index.py && python scripts/build.py
"""
import html
import json
import os
import re
import shutil
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "products-index.json")
SITE = "https://qob.co"
# Path prefix the site is served under. "" for a domain root;
# "/qob" for GitHub project Pages. Override with QOB_BASE.
BASE = os.environ.get("QOB_BASE", "/qob").rstrip("/")
IS_PREVIEW = BASE != ""
NL = chr(10)

EMIT_EU = False   # flip on when /fr/ and /en/ have prices and real copy

# Locale -> (url prefix, html lang, dir)
LOCALES = {
    "fr": ("/ma", "fr", "ltr"),
    "ar": ("/ma/ar", "ar", "rtl"),
}

# ── UI strings ─────────────────────────────────────────────────────────────
UI = {
    "fr": {
        "home": "Accueil", "pieces": "Les pièces", "heritage": "Patrimoine",
        "street": "Collection", "journal": "Journal", "cart": "Panier",
        "atelier": "L'atelier", "contact": "Contact", "returns": "Retours et échanges",
        "shipping": "Livraison", "colour": "Coloris", "size": "Taille",
        "size_guide": "Guide des tailles", "add": "Ajouter au panier",
        "pick_size": "Choisir une taille", "sold_out": "Épuisé",
        "ref": "Référence", "fit": "Coupe", "fabric": "Tissu",
        "construction": "Construction", "care": "Entretien",
        "composition": "Composition", "weight": "Poids", "origin": "Origine",
        "made_in": "Confection", "casablanca": "Casablanca",
        "left": "Plus que {n} en stock",
        "model_wears": "Le mannequin mesure <b>{h}&nbsp;cm</b> et porte une <b>{s}</b>.",
        "fit_advice": "Prenez votre taille habituelle pour la coupe voulue. Une taille en dessous si vous préférez moins d'ampleur aux épaules.",
        "returns_line": "Échange de taille sous 30 jours, retour sous 14 jours.",
        "guide_note": "Vêtement mesuré à plat, en centimètres. Ce ne sont pas des mensurations de corps. Comparez avec une pièce que vous portez déjà.",
        "close": "Fermer", "photo": "Photo", "see_piece": "Voir la pièce",
        "see_pieces": "Voir les pièces", "read_journal": "Lire le journal",
        "derived": "Dérivé de", "breadcrumb": "Fil d'Ariane", "main_nav": "Principale",
        "ai": "Certains visuels sont créés avec l'IA.",
        "legal": "QOB Atelier · Casablanca · Prix en dirhams, paiement à la livraison.",
        "tag": "La capuche de la djellaba, coupée pour aujourd'hui.",
        "sub": "Laine du Moyen Atlas, sfifa appliquée à la main, boutons aqad noués un par un. Fabriqué à Casablanca.",
        "cross_h": "À voir aussi",
        "out_of": "épuisé", "unavailable": "non disponible dans ce coloris",
        "no_stock_note": "Cette pièce est épuisée dans toutes les tailles.",
        "sizes_label": "Tailles",
    },
    "ar": {
        "home": "الرئيسية", "pieces": "القطع", "heritage": "التراث",
        "street": "المجموعة", "journal": "المجلة", "cart": "السلة",
        "atelier": "الورشة", "contact": "اتصل بنا", "returns": "الإرجاع والتبديل",
        "shipping": "التوصيل", "colour": "اللون", "size": "المقاس",
        "size_guide": "دليل المقاسات", "add": "أضف إلى السلة",
        "pick_size": "اختر مقاساً", "sold_out": "نفدت الكمية",
        "ref": "المرجع", "fit": "القَص", "fabric": "القماش",
        "construction": "الصنعة", "care": "العناية",
        "composition": "التركيب", "weight": "الوزن", "origin": "المنشأ",
        "made_in": "الخياطة", "casablanca": "الدار البيضاء",
        "left": "بقي {n} فقط",
        "model_wears": "طول العارض <b>{h}&nbsp;سم</b> ويلبس مقاس <b>{s}</b>.",
        "fit_advice": "خذ مقاسك المعتاد للحصول على القَص المقصود، أو مقاساً أصغر إن كنت تفضّل سعة أقل عند الكتفين.",
        "returns_line": "تبديل المقاس خلال 30 يوماً، والإرجاع خلال 14 يوماً.",
        "guide_note": "قياسات الثوب مسطّحاً بالسنتيمتر، وليست قياسات الجسم. قارنها بقطعة تلبسها بالفعل.",
        "close": "إغلاق", "photo": "صورة", "see_piece": "عرض القطعة",
        "see_pieces": "عرض القطع", "read_journal": "اقرأ المجلة",
        "derived": "مشتق من", "breadcrumb": "مسار التصفح", "main_nav": "الرئيسية",
        "ai": "بعض الصور مُنشأة بالذكاء الاصطناعي.",
        "legal": "قب أتولييه · الدار البيضاء · الأسعار بالدرهم، الدفع عند التسليم.",
        "tag": "قلنسوة الجلابة، مقصوصة لليوم.",
        "sub": "صوف الأطلس المتوسط، سفيفة مطبَّقة يدوياً، وأزرار عقاد معقودة واحداً واحداً. صُنع في الدار البيضاء.",
        "cross_h": "شاهد أيضاً",
        "out_of": "نفدت", "unavailable": "غير متوفر بهذا اللون",
        "no_stock_note": "نفدت هذه القطعة بجميع المقاسات.",
        "sizes_label": "المقاسات",
    },
}

NAV = ["djellaba-homme", "caftan", "jabador", "qob-coat", "overshirt"]


# ── helpers ────────────────────────────────────────────────────────────────
def e(s):
    return html.escape(str(s), quote=True)


def t(node, loc, fallback=""):
    """Localised string. Placeholder copy never reaches a page."""
    if not isinstance(node, dict):
        return fallback
    v = node.get(loc) or node.get("fr") or ""
    if not v or v.startswith("TODO"):
        return fallback
    return v


def money(amount, loc):
    s = f"{int(amount):,}".replace(",", " ")   # narrow no-break space
    return f"{s} MAD" if loc == "fr" else f"{s} درهم"


def url(loc, *parts):
    """In-page URL, carrying the deploy prefix."""
    prefix = BASE + LOCALES[loc][0]
    path = "/".join(str(p).strip("/") for p in parts if p)
    return f"{prefix}/{path}/" if path else f"{prefix}/"


def canon(loc, *parts):
    """Production URL — never carries BASE, so canonicals and hreflang always
    point at the real origin even when previewing from a subpath."""
    prefix = LOCALES[loc][0]
    path = "/".join(str(p).strip("/") for p in parts if p)
    return f"{prefix}/{path}/" if path else f"{prefix}/"


def asset(path):
    return BASE + path


def write(path, content):
    full = os.path.join(ROOT, path.lstrip("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    return path


def alternates(paths_by_loc):
    """Full hreflang cluster. Every emitted locale, plus x-default."""
    out = []
    for loc, p in paths_by_loc.items():
        tag = "fr-MA" if loc == "fr" else "ar-MA"
        out.append(f'<link rel="alternate" hreflang="{tag}" href="{SITE}{p}">')
    out.append(f'<link rel="alternate" hreflang="x-default" href="{SITE}{paths_by_loc["fr"]}">')
    return "\n".join(out)


# ── shell ──────────────────────────────────────────────────────────────────
def shell(loc, *, title, desc, canonical, alts_map, body, jsonld=None, head_extra=""):
    alts = alternates(alts_map)
    lang, direction = LOCALES[loc][1], LOCALES[loc][2]
    u = UI[loc]
    ld = ""
    if jsonld:
        ld = ('<script type="application/ld+json">\n'
              + json.dumps(jsonld, ensure_ascii=False, indent=2)
              + "\n</script>")

    nav_items = "".join(
        f'<li><a href="{url(loc, c)}">{e(CAT_NAME[c][loc])}</a></li>' for c in NAV
    )
    other = "ar" if loc == "fr" else "fr"

    return f"""<!DOCTYPE html>
<html lang="{lang}" dir="{direction}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{SITE}{canonical}">
{'<meta name="robots" content="noindex,nofollow">' if IS_PREVIEW else ''}
{alts}
<meta property="og:type" content="website">
<meta property="og:title" content="{e(title)}">
<meta property="og:url" content="{SITE}{canonical}">
<meta property="og:site_name" content="QOB Atelier">
<link rel="icon" href="{asset("/assets/logo/qob-mark.svg")}" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Karla:wght@300;400;500;600;700&family=IBM+Plex+Sans+Arabic:wght@400;500;600&display=swap">
<link rel="stylesheet" href="{asset("/assets/qob.css")}">
{head_extra}
{ld}
</head>
<body>
<a class="vh" href="#main">{e(u['pieces'])}</a>

<header class="site-header">
  <a class="brand" href="{url(loc)}" aria-label="QOB Atelier">
    <img src="{asset("/assets/logo/qob-logo-rev.svg")}" alt="QOB" width="1096" height="982">
  </a>
  <nav class="site-nav" aria-label="{e(u['main_nav'])}">
    <ul>{nav_items}<li><a href="{url(loc, 'panier')}">{e(u['cart'])} (0)</a></li></ul>
  </nav>
</header>

<main id="main">
{body}
</main>

<footer class="site-footer">
  <div class="wrap footer-grid">
    <ul class="footer-links">
      <li><a href="{url(loc, 'retours-et-echanges')}">{e(u['returns'])}</a></li>
      <li><a href="{url(loc, 'livraison')}">{e(u['shipping'])}</a></li>
      <li><a href="{url(loc, 'journal')}">{e(u['journal'])}</a></li>
      <li><a href="{url(loc, 'atelier')}">{e(u['atelier'])}</a></li>
      <li><a href="{url(loc, 'contact')}">{e(u['contact'])}</a></li>
    </ul>
    <p class="locale-switch">
      <a href="{BASE + alts_map[other]}" lang="{LOCALES[other][1]}" dir="{LOCALES[other][2]}">{'العربية' if other == 'ar' else 'Français'}</a>
    </p>
  </div>
  <div class="wrap">
    <!-- EU AI Act Article 50 — visible wherever AI-generated visuals are
         reachable from the EU. -->
    <p class="legal">{e(u['ai'])}</p>
    <p class="legal">{e(u['legal'])}</p>
  </div>
</footer>
</body>
</html>
"""


# ── page builders ──────────────────────────────────────────────────────────
def slot(text, path):
    return (f'<p class="slot"><b>{e(text)}</b>'
            f'<bdi dir="ltr">{e(path)}</bdi></p>')


def spec_row(p, loc):
    """The facts a shopper actually decides on, in a fixed order."""
    u = UI[loc]
    sep = "، " if loc == "ar" else ", "
    cw = sep.join(t(COLOURS[c]["name"], loc, c) for c in p["colourways"])
    return (f'<dt>{e(u["fabric"])}</dt><dd>{e(t(p["fabric"]["composition"], loc, ""))} · '
            f'<bdi dir="ltr">{p["fabric"]["weight_gsm"]} g/m²</bdi></dd>'
            f'<dt>{e(u["colour"])}</dt><dd>{e(cw)}</dd>'
            f'<dt>{e(u["sizes_label"])}</dt><dd>{e(p["sizes"][0])}–{e(p["sizes"][-1])}</dd>')


def piece_row(p, loc, n):
    """One numbered row in the index. Not a card — the number carries the
    rhythm and the facts sit beside the plate rather than under it."""
    u = UI[loc]
    href = url(loc, p["category"], p["slug"])
    name = t(p["name"], loc, p["name"]["fr"])
    orderable = any(v["stock"] > 0 for v in p["variants"])
    price = money(p["price_mad"], loc)
    if not orderable:
        price += f' <small>— {e(u["out_of"])}</small>'
    kicker = (f'{u["derived"]} {t(GLOSS[p["heritage_term"]]["term"], loc, p["heritage_term"])}'
              if p["heritage_term"] in GLOSS else t(CATS[p["category"]]["name"], loc, ""))
    return f"""<article class="piece">
  <p class="piece__no num">{n:02d}</p>
  <div class="piece__plate">{slot(u['photo'], f"/images/{p['slug']}/main.webp")}</div>
  <div class="piece__body">
    <p class="kicker">{e(kicker)}</p>
    <h3 class="piece__title"><a href="{href}">{e(name)}</a></h3>
    <dl class="piece__spec">{spec_row(p, loc)}</dl>
    <p class="piece__price">{price}</p>
    <p class="piece__cta"><a class="btn btn--ghost" href="{href}">{e(u['see_piece'])}</a></p>
  </div>
</article>"""


def cross_band(loc, heading, copy, href, cta):
    return f"""
  <section class="band">
    <img class="band__mark" src="{asset("/assets/logo/qob-mark-rev.svg")}" alt="" aria-hidden="true"
         width="210" height="140" loading="lazy">
    <div class="wrap band__inner">
      <h2>{e(heading)}</h2>
      <p>{e(copy)}</p>
      <p><a class="btn btn--ghost" href="{href}">{e(cta)}</a></p>
    </div>
  </section>"""


def build_home(loc):
    u = UI[loc]
    items = [p for p in PRODUCTS if p.get("active")][:3]
    rows = NL.join(piece_row(p, loc, i + 1) for i, p in enumerate(items))
    canonical = canon(loc)
    alts = {l: canon(l) for l in LOCALES}
    tag = u["tag"]
    head, _, tail = tag.partition(",")

    body = f"""
  <section class="wrap field hero">
    <p class="selvedge">QOB Atelier · {e(u['casablanca'])}</p>
    <div class="hero__plate">
      <img src="{asset("/assets/logo/qob-logo-rev.svg")}" alt="QOB" width="1096" height="982">
    </div>
    <div class="hero__body">
      <p class="kicker reveal">{e(u['casablanca'])}</p>
      <h1 class="display reveal">{e(head)}{',' if tail else ''}<em>{e(tail)}</em></h1>
      <p class="lede reveal">{e(u['sub'])}</p>
      <p class="reveal" style="margin:0"><a class="btn" href="{url(loc, 'qob-coat')}">{e(u['see_pieces'])}</a></p>
    </div>
  </section>

  <div class="wrap"><div class="rule" aria-hidden="true"><i></i><i></i><i></i></div></div>

  <section class="wrap field">
    <p class="selvedge">{e(u['pieces'])}</p>
    <div class="index">
{rows}
    </div>
  </section>
{cross_band(loc, t(GLOSS['qob']['term'], loc, 'Qob'),
            t(GLOSS['qob']['definition'], loc, ''),
            url(loc, 'journal'), u['read_journal'])}
"""
    ld = {"@context": "https://schema.org", "@type": "Organization",
          "@id": f"{SITE}/#org", "name": "QOB", "alternateName": "QOB Atelier",
          "url": f"{SITE}{canonical}", "logo": f"{SITE}/assets/logo/qob-logo.svg",
          "address": {"@type": "PostalAddress", "addressLocality": "Casablanca",
                      "addressCountry": "MA"}}
    return write(canonical + "index.html", shell(
        loc, title="QOB Atelier — " + u["tag"], desc=u["sub"],
        canonical=canonical, alts_map=alts, body=body, jsonld=ld))


def build_category(cat, loc):
    u = UI[loc]
    cid = cat["id"]
    name = t(cat["name"], loc, cid)
    items = [p for p in PRODUCTS if p["category"] == cid and p.get("active")]
    canonical = canon(loc, cid)
    alts = {l: canon(l, cid) for l in LOCALES}
    cross = CATS[cat["cross_link"]]
    cross_name = t(cross["name"], loc, cross["id"])

    h1 = t(cat["seo"]["h1"], loc, name)
    intro = t(cat["seo"]["intro"], loc, "")
    if not intro:
        # Structural fallback so no page ever ships the word TODO. Real copy is
        # what ranks here, and validate_index.py --strict flags every one.
        seed = [g for g in (cid.split("-")[0], "sfifa") if g in GLOSS]
        intro = " ".join(t(GLOSS[g]["definition"], loc, "") for g in seed)

    rows = (NL.join(piece_row(p, loc, i + 1) for i, p in enumerate(items))
            if items else f'<p class="lede">{e(u["no_stock_note"])}</p>')

    cross_copy = t(cat["seo"]["cross_link_copy"], loc, "") or         f"{name} · {cross_name}"

    body = f"""
  <div class="wrap">
    <nav class="breadcrumb" aria-label="{e(u['breadcrumb'])}">
      <a href="{url(loc)}">{e(u['home'])}</a> / <span aria-current="page">{e(name)}</span>
    </nav>
  </div>

  <section class="wrap field">
    <p class="selvedge">{e(u['heritage'] if cat['branch'] == 'heritage' else u['street'])}</p>
    <header class="cat-head">
      <h1>{e(h1)}</h1>
      <div class="cat-head__body"><p>{e(intro)}</p></div>
    </header>
    <div class="index">
{rows}
    </div>
  </section>
{cross_band(loc, u['cross_h'], cross_copy, url(loc, cross['id']), cross_name)}
"""
    ld = {"@context": "https://schema.org", "@type": "BreadcrumbList",
          "itemListElement": [
              {"@type": "ListItem", "position": 1, "name": "QOB", "item": f"{SITE}{url(loc)}"},
              {"@type": "ListItem", "position": 2, "name": name}]}
    return write(canonical + "index.html", shell(
        loc, title=f"{h1} — QOB Atelier", desc=(intro[:158] or name),
        canonical=canonical, alts_map=alts, body=body, jsonld=ld))


VARIANT_JS = r"""
(function () {
  "use strict";
  var root = document.querySelector("[data-product]");
  if (!root) return;
  var data = JSON.parse(document.getElementById("qob-product-data").textContent);
  var swatchBox = root.querySelector("[data-swatches]");
  var sizeBox   = root.querySelector("[data-sizes]");
  var priceEl   = root.querySelector("[data-price]");
  var stockEl   = root.querySelector("[data-stock]");
  var skuEl     = root.querySelector("[data-sku]");
  var buyEl     = root.querySelector("[data-buy]");
  var colourLbl = root.querySelector("[data-colour-label]");
  var S = data.strings;
  var selected = { colourway: data.colourways[0].id, size: null };

  function fmt(n) {
    return new Intl.NumberFormat(data.numberLocale).format(n) + " " + S.currency;
  }
  function variantFor(c, s) {
    return data.variants.filter(function (v) { return v.colourway === c && v.size === s; })[0] || null;
  }
  /* available | out (exists, sold out) | unmade (never offered).
     None of the three is ever hidden. */
  function stateFor(c, s) {
    var v = variantFor(c, s);
    if (!v) return "unmade";
    return v.stock > 0 ? "available" : "out";
  }
  function renderSwatches() {
    swatchBox.innerHTML = "";
    data.colourways.forEach(function (c) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "swatch";
      b.style.setProperty("--swatch", c.hex);
      b.setAttribute("aria-pressed", String(c.id === selected.colourway));
      b.setAttribute("aria-label", S.colour + " " + c.name);
      b.addEventListener("click", function () {
        selected.colourway = c.id;
        if (selected.size && stateFor(c.id, selected.size) !== "available") selected.size = null;
        render();
      });
      swatchBox.appendChild(b);
    });
    var cur = data.colourways.filter(function (c) { return c.id === selected.colourway; })[0];
    colourLbl.textContent = cur ? cur.name : "";
  }
  function renderSizes() {
    sizeBox.innerHTML = "";
    data.sizes.forEach(function (size) {
      var state = stateFor(selected.colourway, size);
      var b = document.createElement("button");
      b.type = "button"; b.className = "size"; b.textContent = size;
      b.dataset.state = state;
      b.setAttribute("aria-pressed", String(selected.size === size));
      if (state === "available") {
        b.addEventListener("click", function () { selected.size = size; render(); });
      } else {
        b.disabled = true;
        b.setAttribute("aria-label", size + " — " + (state === "out" ? S.out : S.unavailable));
      }
      sizeBox.appendChild(b);
    });
  }
  function renderState() {
    var v = selected.size ? variantFor(selected.colourway, selected.size) : null;
    var price = v && v.price_override != null ? v.price_override : data.price;
    priceEl.textContent = fmt(price);
    skuEl.textContent = S.ref + " " + (v ? v.sku : "—");
    if (!data.orderable) { return; }
    if (!v) {
      stockEl.textContent = ""; stockEl.removeAttribute("data-low");
      buyEl.disabled = true; buyEl.textContent = S.pickSize;
      return;
    }
    var low = v.stock > 0 && v.stock <= 3;
    stockEl.textContent = low ? S.left.replace("{n}", v.stock) : "";
    stockEl.setAttribute("data-low", String(low));
    buyEl.disabled = false;
    buyEl.textContent = S.add + " — " + fmt(price);
  }
  function render() { renderSwatches(); renderSizes(); renderState(); }

  /* Orderable only when at least one variant has stock. Derived, never stored. */
  render();
  if (!data.orderable) { buyEl.disabled = true; buyEl.textContent = S.soldOut; }

  var guide = document.querySelector("[data-guide]");
  var open = document.querySelector("[data-open-guide]");
  if (guide && open) {
    open.addEventListener("click", function () { guide.showModal(); });
    guide.querySelector("[data-close-guide]").addEventListener("click", function () { guide.close(); });
    guide.addEventListener("click", function (ev) { if (ev.target === guide) guide.close(); });
  }
})();
"""


def build_product(p, loc):
    u = UI[loc]
    cat = CATS[p["category"]]
    name = t(p["name"], loc, p["name"]["fr"])
    canonical = canon(loc, p["category"], p["slug"])
    alts = {l: canon(l, p["category"], p["slug"]) for l in LOCALES}
    guide = GUIDES[p["size_guide_id"]]
    orderable = any(v["stock"] > 0 for v in p["variants"])

    desc = t(p["description"], loc, "")
    if not desc:
        desc = " ".join(t(GLOSS[c]["definition"], loc, "") for c in p["construction"][:2])

    # gallery — no photography exists, so no path is invented
    details = "\n".join(
        f'<figure class="shot">{slot(t(GLOSS[c]["term"], loc, c), f"/images/{p['"'"'slug'"'"']}/detail/{c}.webp")}</figure>'
        for c in p["construction"]
    ) if False else "\n".join(
        '<figure class="shot">' + slot(t(GLOSS[c]["term"], loc, c),
                                       "/images/" + p["slug"] + "/detail/" + c + ".webp") + '</figure>'
        for c in p["construction"]
    )

    terms = "\n".join(
        f'<div><dt>{e(t(GLOSS[c]["term"], loc, c))}</dt><dd>{e(t(GLOSS[c]["definition"], loc, ""))}</dd></div>'
        for c in p["construction"]
    )
    care = "\n".join(f"<li>{e(t(CARE[c], loc, c))}</li>" for c in p["care"])

    pts = list(guide["points"])
    head = "".join(f'<th scope="col">{e(t(guide["points"][k], loc, k))}</th>' for k in pts)
    rows = "".join(
        f'<tr><th scope="row">{e(s)}</th>'
        + "".join(f"<td>{guide['rows'][s][k]}</td>" for k in pts) + "</tr>"
        for s in p["sizes"] if s in guide["rows"]
    )

    heritage = p["heritage_term"]
    heritage_link = ""
    if heritage in GLOSS:
        target = next((c["id"] for c in CATEGORIES
                       if c["branch"] == "heritage" and c["id"].startswith(heritage)), None)
        label = t(GLOSS[heritage]["term"], loc, heritage)
        heritage_link = (f'{e(u["derived"])} <a href="{url(loc, target)}">{e(label)}</a>'
                         if target else e(label))

    payload = {
        "price": p["price_mad"],
        "orderable": orderable,
        "numberLocale": "fr-MA" if loc == "fr" else "ar-MA",
        "colourways": [{"id": c, "name": t(COLOURS[c]["name"], loc, c), "hex": COLOURS[c]["hex"]}
                       for c in p["colourways"]],
        "sizes": p["sizes"],
        "variants": [{"sku": v["sku"], "colourway": v["colourway"], "size": v["size"],
                      "stock": v["stock"], "price_override": v["price_override"]}
                     for v in p["variants"]],
        "strings": {
            "currency": "MAD" if loc == "fr" else "درهم",
            "colour": u["colour"], "ref": u["ref"], "add": u["add"],
            "pickSize": u["pick_size"], "soldOut": u["sold_out"],
            "left": u["left"], "out": u["out_of"], "unavailable": u["unavailable"],
        },
    }

    body = f"""
  <div class="wrap">
    <nav class="breadcrumb" aria-label="{e(u['breadcrumb'])}">
      <a href="{url(loc)}">{e(u['home'])}</a> /
      <a href="{url(loc, p['category'])}">{e(t(cat['name'], loc, p['category']))}</a> /
      <span aria-current="page">{e(name)}</span>
    </nav>

    <article class="pdp" data-product="{e(p['id'])}">
      <div class="gallery">
        <div class="gallery__lead">{slot(u['photo'], f"/images/{p['slug']}/main.webp")}</div>
        <div class="gallery__strip">
{details}
        </div>
      </div>

      <div class="info">
        <div class="info__head reveal">
          <p class="heritage-line">{heritage_link}</p>
          <h1 class="pdp__title">{e(name)}</h1>
        </div>

        <p class="price reveal" data-price>{money(p['price_mad'], loc)}</p>

        <div class="picker reveal">
          <div class="picker__head">
            <p class="label" id="lbl-colour">{e(u['colour'])}</p>
            <p class="picker__value" data-colour-label></p>
          </div>
          <fieldset class="swatches" aria-labelledby="lbl-colour" data-swatches></fieldset>
        </div>

        <div class="picker reveal">
          <div class="picker__head">
            <p class="label" id="lbl-size">{e(u['size'])}</p>
            <button type="button" class="linkish" data-open-guide>{e(u['size_guide'])}</button>
          </div>
          <fieldset class="sizes" aria-labelledby="lbl-size" data-sizes></fieldset>
          <p class="stock-note" data-stock role="status"></p>
        </div>

        <div class="reveal" style="display:grid;gap:var(--sp-3)">
          <button class="btn btn--block" type="button" data-buy disabled>{e(u['pick_size'])}</button>
          <p class="sku-line" data-sku>{e(u['ref'])} —</p>
        </div>

        <div class="fit">
          <p class="label">{e(u['fit'])}</p>
          <p>{u['model_wears'].format(h=p['fit']['model_height_cm'], s=e(p['fit']['size_worn']))}</p>
          <p>{e(u['fit_advice'])}</p>
        </div>

        <section class="spec">
          <h2>{e(u['fabric'])}</h2>
          <dl>
            <dt>{e(u['composition'])}</dt><dd>{e(t(p['fabric']['composition'], loc, ''))}</dd>
            <dt>{e(u['weight'])}</dt><dd><bdi dir="ltr">{p['fabric']['weight_gsm']} g/m²</bdi></dd>
            <dt>{e(u['origin'])}</dt><dd>{e(t(p['fabric']['origin'], loc, ''))}</dd>
            <dt>{e(u['made_in'])}</dt><dd>{e(u['casablanca'])}</dd>
          </dl>
        </section>

        <section class="spec">
          <h2>{e(u['construction'])}</h2>
          <dl class="terms">
{terms}
          </dl>
        </section>

        <section class="spec">
          <h2>{e(u['care'])}</h2>
          <ul class="care">
{care}
          </ul>
        </section>

        <p class="returns">
          <span>{e(u['returns_line'])}</span>
          <a href="{url(loc, 'retours-et-echanges')}">{e(u['returns'])}</a>
        </p>
      </div>
    </article>
  </div>

  <dialog class="guide" data-guide aria-labelledby="guide-title">
    <div class="guide__head">
      <h2 id="guide-title">{e(u['size_guide'])}</h2>
      <button type="button" class="guide__close" data-close-guide>{e(u['close'])}</button>
    </div>
    <div class="guide__body">
      <p class="guide__note">{e(u['guide_note'])}</p>
      <div class="scroll-x">
        <table class="measures">
          <thead><tr><th scope="col">{e(u['size'])}</th>{head}</tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </div>
  </dialog>

<script type="application/json" id="qob-product-data">
{json.dumps(payload, ensure_ascii=False)}
</script>
<script>{VARIANT_JS}</script>
"""

    variants_ld = []
    for v in p["variants"]:
        price = v["price_override"] if v["price_override"] is not None else p["price_mad"]
        variants_ld.append({
            "@type": "Product",
            "sku": v["sku"],
            "color": t(COLOURS[v["colourway"]]["name"], loc, v["colourway"]),
            "size": {"@type": "SizeSpecification", "name": v["size"],
                     "sizeSystem": "https://schema.org/WearableSizeSystemEU"},
            "offers": {"@type": "Offer", "price": str(price), "priceCurrency": "MAD",
                       "availability": "https://schema.org/InStock" if v["stock"] > 0
                       else "https://schema.org/OutOfStock",
                       "url": f"{SITE}{canonical}"},
        })

    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "QOB", "item": f"{SITE}{url(loc)}"},
            {"@type": "ListItem", "position": 2, "name": t(cat["name"], loc, p["category"]),
             "item": f"{SITE}{url(loc, p['category'])}"},
            {"@type": "ListItem", "position": 3, "name": name}]},
        {"@type": "ProductGroup",
         "name": name, "description": desc, "url": f"{SITE}{canonical}",
         "brand": {"@type": "Organization", "name": "QOB", "alternateName": "QOB Atelier"},
         "productGroupID": p["id"],
         "material": t(p["fabric"]["composition"], loc, ""),
         "variesBy": ["https://schema.org/size", "https://schema.org/color"],
         "hasVariant": variants_ld}]}

    return write(canonical + "index.html", shell(
        loc, title=f"{name} — QOB Atelier", desc=desc[:160],
        canonical=canonical, alts_map=alts, body=body, jsonld=ld))


def build_returns(loc):
    u = UI[loc]
    canonical = canon(loc, "retours-et-echanges")
    alts = {l: canon(l, "retours-et-echanges") for l in LOCALES}
    if loc == "fr":
        blocks = [
            ("Échanges", ["Un échange de taille est possible pendant 30 jours après réception. "
                          "La pièce doit être non portée, non lavée, étiquettes attachées.",
                          "L'échange est le cas le plus courant en prêt-à-porter. Écrivez-nous avec "
                          "votre numéro de commande et la taille souhaitée ; nous réservons la pièce "
                          "avant que vous renvoyiez la première."]),
            ("Retours", ["Un retour est possible pendant 14 jours après réception, dans les mêmes "
                         "conditions. Le remboursement se fait par le moyen utilisé à la commande.",
                         "Les frais de retour sont à votre charge sauf en cas de défaut ou d'erreur "
                         "de notre part."]),
            ("Défauts", ["La sfifa et l'aqad sont posés à la main : de légères irrégularités sont "
                         "normales et ne constituent pas un défaut. Une couture ouverte, un galon "
                         "décollé ou une pièce non conforme, oui — écrivez-nous."]),
        ]
    else:
        blocks = [
            ("التبديل", ["يمكن تبديل المقاس خلال 30 يوماً من الاستلام، بشرط ألا تكون القطعة قد لُبست أو غُسلت، مع بقاء البطاقات.",
                         "التبديل هو الحالة الأكثر شيوعاً في الملابس. راسلنا برقم الطلب والمقاس المطلوب، ونحجز لك القطعة قبل أن ترجع الأولى."]),
            ("الإرجاع", ["يمكن الإرجاع خلال 14 يوماً من الاستلام بالشروط نفسها، ويتم الاسترجاع بنفس وسيلة الدفع.",
                         "مصاريف الإرجاع على عاتقك إلا في حال وجود عيب أو خطأ من طرفنا."]),
            ("العيوب", ["السفيفة والعقاد يُركَّبان يدوياً، ولذلك فالتفاوت الطفيف أمر طبيعي وليس عيباً. أما الخياطة المفتوحة أو الشريط المنزوع أو قطعة غير مطابقة فراسلنا بشأنها."]),
        ]
    inner = "".join(f"<h2>{e(h)}</h2>" + "".join(f"<p>{e(x)}</p>" for x in ps) for h, ps in blocks)
    body = f"""
  <div class="wrap">
    <nav class="breadcrumb" aria-label="{e(u['breadcrumb'])}">
      <a href="{url(loc)}">{e(u['home'])}</a> / <span aria-current="page">{e(u['returns'])}</span>
    </nav>
    <header class="page-head"><h1>{e(u['returns'])}</h1></header>
    <div class="body-copy">{inner}</div>
  </div>
"""
    return write(canonical + "index.html", shell(
        loc, title=f"{u['returns']} — QOB Atelier",
        desc=u["returns_line"], canonical=canonical,
        alts_map=alts, body=body))


# ── static files ───────────────────────────────────────────────────────────
def build_root_redirect(pages):
    """Accept-Language routing with a visible switcher. Never traps anyone in
    a folder they did not choose, and works with JS off."""
    return write("index.html", f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QOB Atelier</title>
<link rel="canonical" href="{SITE}/ma/">
{alternates({l: url(l) for l in LOCALES})}
<link rel="stylesheet" href="{asset("/assets/qob.css")}">
<script>
  (function () {{
    var l = (navigator.language || "fr").toLowerCase();
    location.replace(l.indexOf("ar") === 0 ? "{BASE}/ma/ar/" : "{BASE}/ma/");
  }})();
</script>
</head>
<body>
<main id="main" class="hero">
  <img class="hero__logo" src="{asset("/assets/logo/qob-logo-rev.svg")}" alt="QOB" width="1096" height="982">
  <p class="hero__tag">QOB Atelier — Casablanca</p>
  <p class="locale-switch" style="justify-content:center;gap:var(--sp-5)">
    <a href="{BASE}/ma/">Français</a>
    <a href="{BASE}/ma/ar/" lang="ar" dir="rtl">العربية</a>
  </p>
</main>
</body>
</html>
""")


def build_404():
    return write("404.html", f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Page introuvable — QOB Atelier</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="{asset("/assets/qob.css")}">
</head>
<body>
<main id="main" class="hero">
  <img class="hero__logo" src="{asset("/assets/logo/qob-mark.svg")}" alt="" width="210" height="140" style="width:min(200px,40vw)">
  <p class="hero__tag">Cette page n'existe pas.</p>
  <p class="hero__sub">Le lien est peut-être ancien, ou la pièce n'est plus en ligne.</p>
  <p style="margin:0"><a class="btn" href="{BASE}/ma/">Retour à l'accueil</a></p>
</main>
</body>
</html>
""")


def build_sitemap(pages):
    """One entry per page per locale, with hreflang alternates on each."""
    today = date.today().isoformat()
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.w3.org/1999/sitemap/0.9"'.replace(
               "1999/sitemap", "1999/xhtml") if False else
           '<urlset xmlns="http://www.w3.org/1999/xhtml"'.replace(
               'xmlns="http://www.w3.org/1999/xhtml"',
               'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
               'xmlns:xhtml="http://www.w3.org/1999/xhtml"') + ">"]
    for group in pages:
        for loc, path in group.items():
            out.append("  <url>")
            out.append(f"    <loc>{SITE}{path}</loc>")
            for l2, p2 in group.items():
                tag = "fr-MA" if l2 == "fr" else "ar-MA"
                out.append(f'    <xhtml:link rel="alternate" hreflang="{tag}" href="{SITE}{p2}"/>')
            out.append(f'    <xhtml:link rel="alternate" hreflang="x-default" href="{SITE}{group["fr"]}"/>')
            out.append(f"    <lastmod>{today}</lastmod>")
            out.append("  </url>")
    out.append("</urlset>")
    return write("sitemap.xml", "\n".join(out) + "\n")


def build_robots():
    if IS_PREVIEW:
        # A subpath build is a preview host whose canonicals name qob.co.
        # Letting it be crawled invites the duplicate indexing this build
        # exists to avoid, so it is closed entirely.
        return write("robots.txt", "User-agent: *" + NL + "Disallow: /" + NL)
    return write("robots.txt",
                 "User-agent: *\n"
                 "Allow: /\n"
                 "Disallow: /admin.html\n"
                 "Disallow: /admin/\n\n"
                 f"Sitemap: {SITE}/sitemap.xml\n")


def build_redirects():
    """One canonical form per URL from day one. novastyle.ma collected 121
    canonical conflicts by retrofitting this; it is cheaper to be strict now."""
    return write("_redirects",
                 "# Force HTTPS and the apex host\n"
                 "http://qob.co/*            https://qob.co/:splat   301!\n"
                 "https://www.qob.co/*       https://qob.co/:splat   301!\n\n"
                 "# One trailing-slash convention: directories always end in /\n"
                 "/ma/:cat                   /ma/:cat/               301\n"
                 "/ma/ar/:cat                /ma/ar/:cat/            301\n\n"
                 "# Locale roots\n"
                 "/ar/*                      /ma/ar/:splat           301\n\n"
                 "# EU locales are declared in products-index.json but not built yet.\n"
                 "/fr/*                      /ma/:splat              302\n"
                 "/en/*                      /ma/:splat              302\n\n"
                 "/*                         /404.html               404\n")


# ── main ───────────────────────────────────────────────────────────────────
def main():
    global CATS, CATEGORIES, PRODUCTS, COLOURS, GLOSS, CARE, GUIDES, CAT_NAME

    with open(INDEX, encoding="utf-8") as fh:
        idx = json.load(fh)

    CATEGORIES = idx["categories"]
    CATS = {c["id"]: c for c in CATEGORIES}
    PRODUCTS = idx["products"]
    COLOURS = idx["colours"]
    GLOSS = idx["glossary"]
    CARE = idx["care_terms"]
    GUIDES = idx["size_guides"]
    CAT_NAME = {c["id"]: c["name"] for c in CATEGORIES}

    groups = []

    def pair(fn, *args):
        """Build one page in every locale and record the URL group, which is
        both the hreflang cluster and the sitemap entry."""
        g = {loc: fn(*args, loc).replace("index.html", "") for loc in LOCALES}
        groups.append(g)

    pair(build_home)
    for c in CATEGORIES:
        if c.get("active"):
            pair(build_category, c)
    for prod in PRODUCTS:
        if prod.get("active"):
            pair(build_product, prod)
    pair(build_returns)

    build_root_redirect(groups)
    build_404()
    build_sitemap(groups)
    build_robots()
    build_redirects()

    n_pages = sum(len(g) for g in groups)
    print(f"{n_pages} pages  ({len(groups)} in {len(LOCALES)} locales)")
    print(f"{len([p for p in PRODUCTS if p.get('active')])} products, "
          f"{len([c for c in CATEGORIES if c.get('active')])} categories")
    print("+ index.html, 404.html, sitemap.xml, robots.txt, _redirects")
    if not EMIT_EU:
        print("note: /fr/ and /en/ not emitted (no EUR prices, no copy) — "
              "no hreflang points at them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
