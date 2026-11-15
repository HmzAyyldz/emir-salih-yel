"""Plain-language cargo cards: free-text cargo → closest NASA specimen, one-sentence summary, colour tone.

Colour is a reading aid only, never a safety rating. Every card also says it in words.
"""
import html

import streamlit as st

from src.i18n import t

# Everyday words → the NASA reference specimen they are closest to (never "the same material").
KEYWORDS = {
    "pamuklu kumaş": ["cotton", "pamuk", "fabric", "kumaş", "textile", "tekstil", "towel", "havlu", "clothing", "giysi",
                      "kıyafet", "sibal", "curtain", "perde"],
    "kablo kılıfı": ["cable", "kablo", "wire", "tel", "insulation", "yalıtım", "cord"],
    "kauçuk": ["rubber", "kauçuk", "silicone", "silikon", "elastomer", "gasket", "conta", "seal"],
    "kağıt": ["paper", "kağıt", "kâğıt", "cellulose", "selüloz", "notebook", "defter", "napkin", "peçete", "tissue"],
}

# Extra NASA specimens from a separate verified table (data/additional_specimens.json); checked first.
EXTRA_KEYWORDS = {
    "jersey_extra": ["t-shirt", "tshirt", "tişört", "tisort", "jersey", "shirt", "gömlek"],
    "pmma_extra": ["acrylic", "akrilik", "pmma", "plexiglass", "pleksi", "plexi", "window", "pencere"],
    "hdpe_extra": ["bottle", "şişe", "container", "hdpe", "plastic box", "plastik kutu", "plastik kap", "food box", "saklama kabı"],
    "delrin_extra": ["delrin", "acetal", "asetal", "gear", "dişli", "knob", "düğme"],
    "nomex_extra": ["nomex", "flight suit", "uçuş tulumu", "tulum", "coverall"],
}

SUGGESTIONS = [("Cotton T-shirt", "Pamuklu tişört"), ("Bath towel", "Banyo havlusu"), ("Headphone cable", "Kulaklık kablosu"),
               ("Silicone gasket", "Silikon conta"), ("Notebook", "Defter"), ("Acrylic window", "Akrilik pencere"),
               ("Plastic water bottle (HDPE)", "Plastik su şişesi (HDPE)"), ("Delrin gear", "Delrin dişli"),
               ("Nomex flight suit", "Nomex uçuş tulumu"), ("Laptop", "Dizüstü bilgisayar")]


def suggestions() -> list:
    return [tr if _tr() else en for en, tr in SUGGESTIONS]


def extras() -> dict:
    import json as _json
    from src.evidence import ROOT
    data = _json.loads((ROOT / "data" / "additional_specimens.json").read_text(encoding="utf-8"))
    return {s["key"]: s for s in data["specimens"]}


def extra_name(key: str) -> str:
    s = extras()[key]
    return s["name_tr"] if _tr() else s["name_en"]

DEFAULT_ASSUMPTIONS = {
    "ISS": {"oxygen": 21.0, "pressure": 101.325, "default": True,
            "note_en": "default: about 21% O₂ and 1 atm, the cabin air of the WIF tests",
            "note_tr": "varsayılan: WIF testlerindeki kabin havası gibi yaklaşık %21 O₂ ve 1 atm"},
    "Moon Base": {"oxygen": 34.0, "pressure": 56.5, "default": True,
                  "note_en": "default: NASA's planned FM² test atmosphere, 34% O₂ at 8.2 psia (poster 20240015307, p. 1)",
                  "note_tr": "varsayılan: NASA'nın planlanan FM² test atmosferi, 8,2 psia'da %34 O₂ (poster 20240015307, s. 1)"},
    "Earth Lab": {"oxygen": 21.0, "pressure": 101.325, "default": True,
                  "note_en": "default: normal air at 1 atm", "note_tr": "varsayılan: 1 atm'de normal hava"},
}


def _tr() -> bool:
    return st.session_state.get("fg_lang", "EN") == "TR"


def resolve(item: str, keys: list) -> str | None:
    """Known specimen key, or the closest specimen for a typed word, or None."""
    if item in keys:
        return item
    low = item.casefold()
    for key, words in EXTRA_KEYWORDS.items():
        if any(w in low for w in words):
            return key
    for key, words in KEYWORDS.items():
        if key in keys and any(w in low for w in words):
            return key
    return None


def _count(rows, column, value):
    return int(rows.loc[rows[column].eq(value), "test_count"].fillna(0).sum())


def card(user_word: str, key, rows, env: str, specimen_name: str) -> tuple:
    """HTML card with one plain sentence. rows = this specimen's compiled rows (unfiltered)."""
    tr = _tr()
    title = html.escape(user_word)
    if key in EXTRA_KEYWORDS:
        return extra_card(user_word, key, env)
    if key is None or rows.empty:
        if key is None:
            body = t("No NASA flight test in this collection matches this item. Missing data does not mean safe.")
        else:
            body = t("NASA study evidence exists for this specimen, but no compiled test count. Missing data does not mean safe.")
        from src.access import say_button
        return (f"<div class='plain-card tone-none'>{say_button(user_word + '. ' + body)}<div class='plain-title'>{title}</div>"
                f"<span class='plain-badge'>◌ {html.escape(t('No compiled test'))}</span>"
                f"<p>{html.escape(body)}</p></div>"), "none"
    n = int(rows.test_count.fillna(0).sum())
    ign = _count(rows, "ignition", "observed")
    local = _count(rows, "ignition", "local_gas_flame")
    disputed = _count(rows, "ignition", "disputed")
    spread = _count(rows, "propagation", "observed")
    no_spread = _count(rows, "propagation", "not_observed")
    sentences = [t("NASA tested this specimen in space once.") if n == 1 else t("NASA tested this specimen in space {n} times.", n=n)]
    if disputed:
        sentences.append(t("The report's ignition count is disputed, so no ignition ratio is shown."))
        tone = "none"
    elif local == n:
        sentences.append(t("Each time only a brief local flame appeared; it did not keep burning or spread."))
        tone = "low"
    else:
        sentences.append(t("It ignited in {k} of them.", k=ign))
        from src.stats import interval_text
        if n > 1:
            sentences.append(interval_text(ign, n, t))
        if spread:
            sentences.append(t("The flame spread in {s}.", s=spread))
            tone = "high"
        else:
            sentences.append(t("Flame spread was not reported as observed."))
            tone = "medium"
    if no_spread and not local == n and spread:
        sentences.append(t("In {m} the flame did not spread.", m=no_spread))
    gravity_note = ""
    if env != "ISS":
        tone = "none"
        gravity_note = (f"<span class='plain-badge warn'>⚠ {html.escape(t('These tests were in microgravity, not this environment.'))}</span>")
    tone_label = {"high": t("Flame spread observed"), "medium": t("Ignited; spread not observed"),
                  "low": t("Brief local flame only"), "none": t("No ratio shown")}[tone]
    from src.access import say_button
    return (f"<div class='plain-card tone-{tone}'>{say_button(user_word + '. ' + ' '.join(sentences))}<div class='plain-title'>{title}"
            + (f"<span class='plain-map'> → {html.escape(specimen_name)}</span>" if specimen_name != user_word else "") + "</div>"
            f"<div class='plain-sub'>{html.escape(t('Closest NASA-tested specimen, not your exact product.'))}</div>"
            f"<span class='plain-badge'>{html.escape(tone_label)}</span>{gravity_note}"
            f"<p>{html.escape(' '.join(sentences))}</p></div>"), tone


CSS = """<style>
.plain-card{background:var(--surface,#101a29);border:1px solid var(--line,#314156);border-left:5px solid #7d8a9c;border-radius:8px;
  padding:14px 18px;margin:8px 0}
.plain-card p{margin:8px 0 0;max-width:80ch}
.plain-title{font-size:18px;font-weight:600}.plain-map{color:var(--muted,#abbace);font-weight:400;font-size:15px}
.plain-sub{color:var(--muted,#abbace);font-size:13px;margin:2px 0 6px}
.plain-badge{display:inline-block;font-size:13px;border:1px solid var(--line,#314156);border-radius:4px;padding:3px 8px;margin-right:6px}
.plain-badge.warn{border-color:#ffb487;color:#ffb487}
.plain-card.tone-high{border-left-color:#e8704a;background:linear-gradient(135deg,rgba(232,110,72,.18),var(--surface,#101a29) 70%)}
.plain-card.tone-medium{border-left-color:#e0a53b;background:linear-gradient(135deg,rgba(224,165,59,.15),var(--surface,#101a29) 70%)}
.plain-card.tone-low{border-left-color:#5296dc;background:linear-gradient(135deg,rgba(82,150,220,.15),var(--surface,#101a29) 70%)}
.plain-card.tone-none{border-left-color:#7d8a9c;border-style:dashed solid dashed solid}
</style>"""


def legend() -> str:
    return t("Card colour is a reading aid, not a safety rating: orange = flame spread observed · amber = ignited, spread not "
             "observed · blue = only a brief local flame or no ignition · grey = no data, disputed count or different gravity. Blue does not mean safe.")


MOOD_CSS = """<style>
/* Theme shifts softly toward red-orange when the cargo list shows flame spread (a reading aid, not a safety rating). */
.stApp{transition:background 1.2s ease, box-shadow 1.2s ease}
.stApp.fg-mood-high{background:radial-gradient(1400px 700px at 70% -12%, rgba(232,96,64,.26) 0%, rgba(214,72,56,.10) 38%, #080d16 70%) fixed!important}
.stApp.fg-mood-medium{background:radial-gradient(1400px 700px at 70% -12%, rgba(232,150,64,.20) 0%, #080d16 65%) fixed!important}
.stApp.fg-mood-high [data-testid="stSidebar"]{transition:background 1.2s ease;background:linear-gradient(180deg,#2a1712 0%,#0d1623 55%)!important}
.stApp.fg-mood-high h1,.stApp.fg-mood-high h2,.stApp.fg-mood-high h3{transition:color 1.2s ease;color:#ffc2a6}
@media (prefers-reduced-motion: reduce){.stApp,.stApp [data-testid="stSidebar"]{transition:none}}
</style>"""


def page_mood(tones: list) -> None:
    """Set a soft page tint from the strongest tone in the list; clears it otherwise."""
    order = {"high": 2, "medium": 1}
    present = [x for x in tones if x in order]
    mood = max(present, key=order.get) if present else ""
    js = ("const a=window.parent.document.querySelector('.stApp');"
          "if(a){a.classList.remove('fg-mood-high','fg-mood-medium');" + (f"a.classList.add('fg-mood-{mood}');" if mood else "") + "}")
    st.markdown(MOOD_CSS, unsafe_allow_html=True)
    st.html(f"<script>try{{{js}}}catch(e){{}}</script>", unsafe_allow_javascript=True)


def _fmt_range(r, unit):
    if not r:
        return t("not reported")
    lo, hi = r
    return f"{lo:g} {unit}" if lo == hi else f"{lo:g}–{hi:g} {unit}"


def extra_card(user_word: str, key: str, env: str) -> tuple:
    s = extras()[key]
    nm = extra_name(key)
    n, k, no = s["tests"], s["ignited"], s["not_ignited"]
    sentences = [t("NASA tested this specimen in space once.") if n == 1 else t("NASA tested this specimen in space {n} times.", n=n)]
    if k == n:
        sentences.append(t("It ignited.") if n == 1 else t("It ignited in {k} of them.", k=k))
        tone = "medium"
    elif k == 0 and n == 1:
        sentences.append(t("It did not ignite."))
        tone = "low"
    elif k == 0:
        sentences.append(t("It did not ignite in any of them."))
        tone = "low"
    else:
        sentences.append(t("It ignited in {k} of them.", k=k))
        tone = "medium"
    from src.stats import interval_text
    if n > 1:
        sentences.append(interval_text(k, n, t))
    sentences.append(t("Test conditions: O₂ {o2}, pressure {p}.", o2=_fmt_range(s["oxygen_pct"], "%"), p=_fmt_range(s["pressure_kpa"], "kPa")))
    gravity_note = ""
    if env != "ISS":
        tone = "none"
        gravity_note = f"<span class='plain-badge warn'>⚠ {html.escape(t('These tests were in microgravity, not this environment.'))}</span>"
    links = " · ".join(f"<a href='{x['url']}' target='_blank'>{html.escape(x['short'])}, {t('p.')} {x['page']}</a>" for x in s["sources"])
    tone_label = {"medium": t("Ignited; spread not reported in this table"), "low": t("Did not ignite"), "none": t("No ratio shown")}[tone]
    map_part = f"<span class='plain-map'> → {html.escape(nm)}</span>" if nm != user_word else ""
    from src.access import say_button
    return (f"<div class='plain-card tone-{tone}'>{say_button(user_word + '. ' + ' '.join(sentences))}<div class='plain-title'>{html.escape(user_word)}{map_part}</div>"
            f"<div class='plain-sub'>{html.escape(t('Closest NASA-tested specimen, not your exact product.'))} "
            f"{html.escape(t('Separate verified table'))} · {', '.join(s['experiments'])}</div>"
            f"<span class='plain-badge'>{html.escape(tone_label)}</span>{gravity_note}"
            f"<p>{html.escape(' '.join(sentences))}</p><div class='plain-sub'>{links}</div></div>"), tone


# Everyday things made of a similar kind of material. Illustration only: NASA tested the specimen, not these products.
EVERYDAY = {
    "pamuklu kumaş": (["cotton towels", "bed sheets", "cotton work clothes", "curtains"],
                      ["pamuklu havlular", "çarşaflar", "pamuklu iş kıyafetleri", "perdeler"]),
    "kablo kılıfı": (["phone charger cables", "headphone cables", "laptop power cords", "extension cords"],
                     ["telefon şarj kabloları", "kulaklık kabloları", "laptop güç kabloları", "uzatma kabloları"]),
    "kauçuk": (["silicone door and window seals", "phone cases", "baking mats", "watch straps"],
               ["silikon kapı ve pencere contaları", "telefon kılıfları", "fırın matları", "saat kayışları"]),
    "kağıt": (["notebooks", "checklists and manuals", "paper towels", "cardboard labels"],
              ["defterler", "kontrol listeleri ve kılavuzlar", "kâğıt havlular", "karton etiketler"]),
    "plastik (pmma)": (["acrylic windows", "display and screen covers", "light covers", "aquarium panels"],
                       ["akrilik pencereler", "ekran ve vitrin kapakları", "lamba kapakları", "akvaryum camları"]),
    "pmma_extra": (["acrylic windows", "display and screen covers", "light covers", "aquarium panels"],
                   ["akrilik pencereler", "ekran ve vitrin kapakları", "lamba kapakları", "akvaryum camları"]),
    "delrin_extra": (["small gears", "zipper pulls", "knobs and buttons", "kitchen utensil handles"],
                     ["küçük dişliler", "fermuar uçları", "düğmeler ve topuzlar", "mutfak gereci sapları"]),
    "hdpe_extra": (["water and milk bottles", "food storage boxes", "cutting boards", "bottle caps"],
                   ["su ve süt şişeleri", "yiyecek saklama kapları", "kesme tahtaları", "şişe kapakları"]),
    "nomex_extra": (["firefighter suits", "flight suits", "racing driver gloves", "fire-resistant work wear"],
                    ["itfaiyeci kıyafetleri", "uçuş tulumları", "yarış pilotu eldivenleri", "yanmaz iş kıyafetleri"]),
    "jersey_extra": (["T-shirts", "sportswear", "pyjamas", "underwear"],
                     ["tişörtler", "spor giyim", "pijamalar", "iç çamaşırları"]),
}


def everyday_html(key: str) -> str:
    """Chips with everyday examples, plus the honest caveat."""
    pair = EVERYDAY.get(key)
    if not pair:
        return ""
    items = pair[1] if _tr() else pair[0]
    chips = "".join(f"<span class='plain-badge'>{html.escape(x)}</span>" for x in items)
    return (f"<div class='plain-card tone-none' style='border-style:solid'>"
            f"<div class='plain-title' style='font-size:16px'>🏠 {html.escape(t('Everyday examples'))}</div>"
            f"<div style='margin:6px 0'>{chips}</div>"
            f"<div class='plain-sub'>{html.escape(t('Things made of a similar kind of material. NASA tested the specimen above, not these products.'))}</div></div>")


def everyday_words(key: str) -> str:
    """Search text: everyday examples and typed keywords for a specimen, both languages."""
    en, tr = EVERYDAY.get(key, ([], []))
    words = KEYWORDS.get(key, []) + EXTRA_KEYWORDS.get(key, [])
    return " ".join([*en, *tr, *words]).casefold()


def matches(key: str, label: str, query: str) -> bool:
    """Search by specimen name, everyday examples or keywords; word by word, so 'su şişesi' finds 'şişe'."""
    q = query.casefold().strip()
    if not q:
        return True
    text = (key + " " + label).casefold() + " " + everyday_words(key)
    if q in text:
        return True
    tokens = [w for w in q.replace(",", " ").split() if len(w) >= 3]
    return any(w in text or w[:-2] in text for w in tokens if len(w[:-2]) >= 3) or any(w in text for w in tokens)
