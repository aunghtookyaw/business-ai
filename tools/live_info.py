import re
from html.parser import HTMLParser

import requests

try:
    import config
except ImportError:
    config = None


DEFAULT_PRICE_URLS = (
    "https://checkraka.app/price/vegetable-today/makro/",
    "https://checkraka.app/price/vegetable-today/simummuang/",
)

DEFAULT_MYANMAR_PRICE_URLS = (
    "https://www.selinawamucii.com/insights/prices/myanmar/lettuce/",
    "https://www.selinawamucii.com/insights/prices/myanmar/vegetables/",
)

DEFAULT_MYANMAR_RETAIL_PRICE_URLS = (
    "https://www.makropro.com.mm/en/c/fruit-vegetables/vegetables",
    "https://www.citymall.com.mm/citymall/my/%E1%80%95%E1%80%85%E1%80%B9%E1%80%85%E1%80%8A%E1%80%BA%E1%80%B8%E1%80%A1%E1%80%99%E1%80%BB%E1%80%AD%E1%80%AF%E1%80%B8%E1%80%A1%E1%80%85%E1%80%AC%E1%80%B8%E1%80%99%E1%80%BB%E1%80%AC%E1%80%B8/Brands/City-Farm/c/C0392",
)

VEGETABLE_ALIASES = {
    "tomato": "มะเขือเทศ",
    "cabbage": "กะหล่ำปลี",
    "green cabbage": "กะหล่ำปลี",
    "chinese cabbage": "ผักกาดขาว",
    "lettuce": "ผักกาดหอม",
    "green oak": "กรีนโอ๊ค",
    "red oak": "เรดโอ๊ค",
    "cos": "คอส",
    "romaine": "คอส",
    "butterhead": "บัตเตอร์เฮด",
    "carrot": "แครอท",
    "cucumber": "แตงกวา",
    "potato": "มันฝรั่ง",
    "garlic": "กระเทียมจีน",
    "onion": "หัวหอมใหญ่",
    "shallot": "หอมแดง",
    "broccoli": "บล็อคโคลี่",
    "chili": "พริก",
    "red chili": "พริกแดง",
    "green chili": "พริกเขียว",
    "mushroom": "เห็ด",
    "celery": "คื่นช่าย",
}

RETAIL_VEGETABLE_ALIASES = {
    "tomato": ("tomato", "ခရမ်းချဉ်", "မะเขือเทศ"),
    "cabbage": ("cabbage", "ဂေါ်ဖီ", "กะหล่ำปลี"),
    "green cabbage": ("cabbage", "ဂေါ်ဖီ", "กะหล่ำปลี"),
    "chinese cabbage": ("chinese cabbage", "ผักกาดขาว"),
    "lettuce": ("lettuce", "ဆလပ်", "ผักกาดหอม"),
    "green oak": ("green oak", "ဂရင်းအုပ်", "กรีนโอ๊ค"),
    "red oak": ("red oak", "เรดโอ๊ค"),
    "cos": ("cos", "romaine", "คอส"),
    "romaine": ("romaine", "cos", "คอส"),
    "butterhead": ("butterhead", "butter head", "บัตเตอร์เฮด"),
    "carrot": ("carrot", "မုန်လာဥနီ", "แครอท"),
    "cucumber": ("cucumber", "သခွား", "แตงกวา"),
    "potato": ("potato", "အာလူး", "มันฝรั่ง"),
    "garlic": ("garlic", "ကြက်သွန်ဖြူ", "กระเทียม"),
    "onion": ("onion", "ကြက်သွန်နီ", "หัวหอม"),
    "shallot": ("shallot", "ကြက်သွန်နီ", "หอมแดง"),
    "broccoli": ("broccoli", "ဘရိုကိုလီ", "บล็อคโคลี่"),
    "chili": ("chili", "chilli", "ငရုတ်", "พริก"),
    "mushroom": ("mushroom", "မှို", "เห็ด"),
    "celery": ("celery", "ကင်ချိုင်း", "คื่นช่าย"),
}

WEATHER_WORDS = ("weather", "forecast", "မိုးလေဝသ", "ရာသီဥတု", "temperature", "rain", "မိုး")
PRICE_WORDS = ("vegetable", "veggie", "price", "စျေး", "ဈေး", "ผัก")
NEGOTIATION_WORDS = (
    "makro",
    "citymart",
    "city mart",
    "citymall",
    "city mall",
    "negotiation",
    "negotiate",
    "deal",
    "retail",
    "seller",
    "saler",
    "reduce",
    "discount",
    "ceiling",
    "walk away",
    "အရောင်း",
    "လျှော့",
)


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth:
            return
        text = " ".join(data.split())
        if text:
            self._parts.append(text)

    def text(self):
        return "\n".join(self._parts)


def _setting(name, default=None):
    value = getattr(config, name, None) if config is not None else None
    return value if value not in (None, "") else default


def _normalize(text):
    return " ".join((text or "").lower().split())


def _looks_like_weather(question):
    text = _normalize(question)
    return any(word in text for word in WEATHER_WORDS)


def _looks_like_price(question):
    text = _normalize(question)
    return any(word in text for word in PRICE_WORDS) and (
        "thai" in text
        or "thailand" in text
        or "myanmar" in text
        or "makro" in text
        or "citymart" in text
        or "city mart" in text
        or "citymall" in text
        or "city mall" in text
        or "lettuce" in text
        or "ထိုင်း" in text
        or "ผัก" in text
        or "vegetable" in text
        or "veggie" in text
    )


def _looks_like_negotiation(question):
    text = _normalize(question)
    return any(word in text for word in NEGOTIATION_WORDS) and (
        any(word in text for word in PRICE_WORDS)
        or "lettuce" in text
        or "vegetables" in text
        or "market" in text
    )


def _html_to_text(html):
    parser = _TextParser()
    parser.feed(html)
    return parser.text()


def _weather_code_description(code):
    descriptions = {
        0: "clear sky",
        1: "mainly clear",
        2: "partly cloudy",
        3: "overcast",
        45: "fog",
        48: "depositing rime fog",
        51: "light drizzle",
        53: "moderate drizzle",
        55: "dense drizzle",
        61: "slight rain",
        63: "moderate rain",
        65: "heavy rain",
        80: "slight rain showers",
        81: "moderate rain showers",
        82: "violent rain showers",
        95: "thunderstorm",
    }
    return descriptions.get(code, f"weather code {code}")


def _forecast_days(question):
    text = _normalize(question)
    if "tomorrow" in text or "မနက်ဖြန်" in text:
        return 2

    match = re.search(r"\b(\d{1,2})\s*(?:day|days)\b", text)
    if match:
        return max(1, min(int(match.group(1)), 16))

    if "week" in text or "weekly" in text or "တစ်ပတ်" in text:
        return 7

    return 1


def _extract_location(question):
    text = question or ""
    text = re.sub(r"\b\d{1,2}\s*(?:day|days)\b", "", text, flags=re.IGNORECASE)
    patterns = (
        r"\b([A-Za-z][A-Za-z\s,.-]{2,40})\s+(?:weather|forecast|temperature|rain)\b",
        r"\b(?:weather|forecast|temperature|rain)\s+(?:in|for)?\s*([A-Za-z][A-Za-z\s,.-]{2,40})",
        r"\b(?:in|for)\s+([A-Za-z][A-Za-z\s,.-]{2,40})\s+(?:weather|forecast|temperature|rain)\b",
    )
    stop_locations = {"day", "days", "today", "tomorrow", "now", "this week", "this month"}
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            location = match.group(1).strip(" .,")
            location = re.sub(r"\b(today|tomorrow|now)\b", "", location, flags=re.IGNORECASE).strip(" .,")
            if location and location.lower() not in stop_locations:
                return location
    return _setting("FAMILY_DEFAULT_WEATHER_LOCATION", "Yangon")


def _daily_value(daily, key, index):
    values = daily.get(key) or []
    if index >= len(values):
        return "?"
    return values[index]


def get_weather_answer(question, timeout=15):
    context = get_weather_context(question, timeout=timeout)
    return format_weather_answer(context)


def get_weather_context(question, timeout=15):
    location = _extract_location(question)
    forecast_days = _forecast_days(question)
    geo_response = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": location, "count": 1, "language": "en", "format": "json"},
        timeout=timeout,
    )
    geo_response.raise_for_status()
    geo_data = geo_response.json()
    results = geo_data.get("results") or []
    if not results:
        return {
            "type": "weather",
            "question": question,
            "error": f"Weather: no location found for {location}.",
        }

    place = results[0]
    forecast_response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "auto",
            "forecast_days": forecast_days,
        },
        timeout=timeout,
    )
    forecast_response.raise_for_status()
    data = forecast_response.json()
    current = data.get("current") or {}
    daily = data.get("daily") or {}
    place_name = ", ".join(
        item for item in [place.get("name"), place.get("admin1"), place.get("country")] if item
    )

    start_index = 1 if "tomorrow" in _normalize(question) or "မနက်ဖြန်" in question else 0
    available_days = len(daily.get("time") or [])
    end_index = min(forecast_days, start_index + 7, available_days)
    days = []
    for index in range(start_index, end_index):
        daily_code = int(_daily_value(daily, "weather_code", index) or 0)
        days.append({
            "date": _daily_value(daily, "time", index),
            "condition": _weather_code_description(daily_code),
            "max_c": _daily_value(daily, "temperature_2m_max", index),
            "min_c": _daily_value(daily, "temperature_2m_min", index),
            "rain_probability_percent": _daily_value(daily, "precipitation_probability_max", index),
        })

    return {
        "type": "weather",
        "question": question,
        "place": place_name,
        "forecast_days": forecast_days,
        "current": {
            "condition": _weather_code_description(int(current.get("weather_code") or 0)),
            "temperature_c": current.get("temperature_2m"),
            "humidity_percent": current.get("relative_humidity_2m"),
            "rain_now_mm": current.get("precipitation"),
        },
        "days": days,
        "source": "Open-Meteo",
    }


def format_weather_answer(context):
    if context.get("error"):
        return context["error"]

    if context.get("forecast_days") == 1:
        day = (context.get("days") or [{}])[0]
        current = context.get("current") or {}
        return (
            f"Weather for {context['place']}\n"
            f"Condition: {current.get('condition')}\n"
            f"Temperature: {current.get('temperature_c')} C\n"
            f"Humidity: {current.get('humidity_percent')}%\n"
            f"Rain now: {current.get('rain_now_mm')} mm\n"
            f"Today max/min: {day.get('max_c')} / {day.get('min_c')} C\n"
            f"Rain probability: {day.get('rain_probability_percent')}%\n"
            f"Source: {context['source']}"
        )

    lines = [f"Weather forecast for {context['place']}"]
    for day in context.get("days") or []:
        lines.append(
            f"- {day['date']}: {day['condition']}, "
            f"{day['max_c']} / {day['min_c']} C, "
            f"rain chance {day['rain_probability_percent']}%"
        )
    lines.append("Source: Open-Meteo")
    return "\n".join(lines)


def get_thb_mmk_rate(timeout=15):
    response = requests.get("https://open.er-api.com/v6/latest/THB", timeout=timeout)
    response.raise_for_status()
    data = response.json()
    rate = (data.get("rates") or {}).get("MMK")
    if not rate:
        raise RuntimeError("THB to MMK rate was not available.")
    return float(rate), data.get("time_last_update_utc") or data.get("time_last_update_unix")


def _price_source_urls():
    configured = _setting("THAILAND_VEGETABLE_PRICE_URLS")
    if configured:
        return [url.strip() for url in configured.split(",") if url.strip()]
    return list(DEFAULT_PRICE_URLS)


def _myanmar_price_source_urls():
    configured = _setting("MYANMAR_VEGETABLE_PRICE_URLS")
    if configured:
        return [url.strip() for url in configured.split(",") if url.strip()]
    return list(DEFAULT_MYANMAR_PRICE_URLS)


def _myanmar_retail_price_source_urls():
    configured = _setting("MYANMAR_RETAIL_VEGETABLE_PRICE_URLS")
    if configured:
        return [url.strip() for url in configured.split(",") if url.strip()]
    return list(DEFAULT_MYANMAR_RETAIL_PRICE_URLS)


def _wanted_vegetable(question):
    text = _normalize(question)
    for alias, thai_name in VEGETABLE_ALIASES.items():
        if alias in text or thai_name in question:
            return thai_name
    return None


def _wanted_retail_terms(question):
    text = _normalize(question)
    for alias, terms in RETAIL_VEGETABLE_ALIASES.items():
        if alias in text or any(term.lower() in text for term in terms):
            return terms
    return None


def _parse_price_rows(text, source_url):
    rows = []
    pattern = re.compile(
        r"([A-Za-zก-๙][A-Za-zก-๙\s()/-]{1,40})\s+(\d+(?:\.\d+)?)\s*บาท\s*/\s*กก",
        re.IGNORECASE,
    )
    for name, price in pattern.findall(text):
        clean_name = " ".join(name.split()).strip(" -|")
        bad_terms = ("ราคา", "าคา", "ถูกที่สุด", "ถึง", "makro", "วันนี้")
        if len(clean_name) < 2 or any(term in clean_name.lower() for term in bad_terms):
            continue
        rows.append({
            "name": clean_name,
            "price_thb": float(price),
            "unit": "kg",
            "source": source_url,
        })
    return rows


def _source_market_name(source_url):
    if "makropro.com.mm" in source_url:
        return "Makro PRO Myanmar"
    if "citymall.com.mm" in source_url:
        return "City Mart / City Mall"
    return source_url


def _normalize_retail_unit(quantity):
    text = " ".join((quantity or "").split())
    lower = text.lower()
    unit = text or "unit"
    multiplier = None

    number_match = re.search(r"(\d+(?:\.\d+)?)", lower)
    value = float(number_match.group(1)) if number_match else None
    if value is not None:
        if "kilo" in lower or "kg" in lower:
            unit = "kg" if value == 1 else f"{value:g} kg"
            multiplier = 1 / value if value else None
        elif "gram" in lower or re.search(r"\d\s*g\b", lower) or re.search(r"\d+g\b", lower):
            unit = "g" if value == 1 else f"{value:g} g"
            multiplier = 1000 / value if value else None
        elif "viss" in lower:
            unit = "viss" if value == 1 else f"{value:g} viss"
            multiplier = 1 / (value * 1.63293) if value else None
        elif "pc" in lower or "pcs" in lower:
            unit = "pc" if value == 1 else f"{value:g} pcs"

    return unit, multiplier


def _retail_row(name, quantity, price_mmk, source_url):
    unit, per_kg_multiplier = _normalize_retail_unit(quantity)
    row = {
        "market": _source_market_name(source_url),
        "name": " ".join(name.split()).strip(" -|"),
        "quantity": " ".join((quantity or "").split()),
        "price_mmk": float(price_mmk),
        "unit": unit,
        "source": source_url,
    }
    if per_kg_multiplier:
        row["price_mmk_per_kg"] = row["price_mmk"] * per_kg_multiplier
    return row


def _parse_citymall_retail_rows(text, source_url):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    rows = []
    for index, line in enumerate(lines):
        if not re.match(r"^[\d,]+(?:\.\d+)?\s*Ks$", line):
            continue

        price = float(line.split()[0].replace(",", ""))
        quantity = ""
        name = ""
        for back_index in range(index - 1, max(-1, index - 8), -1):
            candidate = lines[back_index]
            if re.search(r"\b(?:Gram|Kilo|KG|G|Viss|PCS?|ထုပ်|လုံး)\b", candidate, re.IGNORECASE):
                quantity = candidate
                continue
            if candidate.startswith("Image:") or "ရောင်းချသူ" in candidate or candidate.startswith("Sold by"):
                continue
            if not name and not re.match(r"^[\d,]+(?:\.\d+)?\s*Ks$", candidate):
                name = candidate
                break

        if not name or "seed" in name.lower() or "မျိုးစေ့" in name:
            continue
        rows.append(_retail_row(name, quantity, price, source_url))
    return rows


def _parse_makro_retail_rows(text, source_url):
    rows = _parse_makro_retail_json_rows(text, source_url)
    if rows:
        return rows

    compact = " ".join(text.split())
    pattern = re.compile(
        r"([A-Za-z0-9#/().,&'\-\s]{2,80}?)\s+((?:\d+(?:\.\d+)?\s*)?(?:kg|g|pc|pcs|pack|unit\(s\)|viss)[A-Za-z0-9()/.\-\s]*)\s*(?:MAKRO|GO GREEN|ARO|UNITED MUSHROOM|BURMA BUTCHER)\s+Ks\s*([\d,]+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    rows = []
    for name, quantity, price in pattern.findall(compact):
        clean_name = " ".join(name.split()).strip(" -|")
        if len(clean_name) < 2 or clean_name.lower().startswith(("showing products", "sort by", "product list")):
            continue
        rows.append(_retail_row(clean_name, quantity, float(price.replace(",", "")), source_url))
    return rows


def _makro_quantity_from_name(name, unit_size):
    text = name or ""
    patterns = (
        r"(\d+(?:\.\d+)?\s*(?:kg|g|viss|pc|pcs))\b",
        r"(\d+(?:\.\d+)?\s*(?:KG|G|VISS|PC|PCS))\b",
        r"\b(KG)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return "1 kg" if match.group(1).lower() == "kg" else match.group(1)
    return unit_size or "1 unit(s)"


def _parse_makro_retail_json_rows(html, source_url):
    rows = []
    pattern = re.compile(
        r'"displayPrice"\s*:\s*([\d.]+).*?'
        r'"priceUnit"\s*:\s*"MMK".*?'
        r'"seller"\s*:\s*"([^"]+)".*?'
        r'"title"\s*:\s*"([^"]*)"\s*,\s*"titleEn"\s*:\s*"([^"]+)".*?'
        r'"unitSize"\s*:\s*"([^"]*)"',
        re.DOTALL,
    )
    seen = set()
    for price, seller, title, title_en, unit_size in pattern.findall(html):
        name = title_en or title
        if "seed" in name.lower() or "မျိုးစေ့" in title:
            continue
        key = (name, price)
        if key in seen:
            continue
        seen.add(key)
        quantity = _makro_quantity_from_name(name, unit_size)
        rows.append(_retail_row(name, quantity, float(price), source_url))
        rows[-1]["seller"] = seller
    return rows


def _parse_retail_myanmar_price_rows(text, source_url):
    if "makropro.com.mm" in source_url:
        return _parse_makro_retail_rows(text, source_url)
    if "makro.pro" in source_url:
        return _parse_makro_retail_rows(text, source_url)
    if "citymall.com.mm" in source_url:
        return _parse_citymall_retail_rows(text, source_url)
    return _parse_citymall_retail_rows(text, source_url) + _parse_makro_retail_rows(text, source_url)


def _fetch_retail_myanmar_price_rows(timeout=20):
    rows = []
    errors = []
    for url in _myanmar_retail_price_source_urls():
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "BigShot-Guy-Bot/1.0"},
                timeout=timeout,
            )
            response.raise_for_status()
            source_text = response.text if "makro" in url else _html_to_text(response.text)
            rows.extend(_parse_retail_myanmar_price_rows(source_text, url))
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    return rows, errors


def _parse_myanmar_price_rows(text, source_url):
    rows = []
    compact = " ".join(text.split())
    title_match = re.search(r"Myanmar\s+([A-Za-z\s-]{2,40}?)\s+(?:Market|Price)", compact)
    name = " ".join((title_match.group(1) if title_match else "Vegetables").split())
    pattern = re.compile(
        r"between\s+MMK\s*([\d,]+(?:\.\d+)?)\s+and\s+MMK\s*([\d,]+(?:\.\d+)?)\s+per\s+kilogram",
        re.IGNORECASE,
    )
    seen = set()
    for low, high in pattern.findall(compact):
        low_value = float(low.replace(",", ""))
        high_value = float(high.replace(",", ""))
        key = (name.lower(), low_value, high_value)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "name": name,
            "price_mmk_min": low_value,
            "price_mmk_max": high_value,
            "unit": "kg",
            "source": source_url,
        })
    return rows


def _fetch_myanmar_price_rows(timeout=20):
    rows = []
    errors = []
    for url in _myanmar_price_source_urls():
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "BigShot-Guy-Bot/1.0"},
                timeout=timeout,
            )
            response.raise_for_status()
            rows.extend(_parse_myanmar_price_rows(_html_to_text(response.text), url))
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    return rows, errors


def _fetch_price_rows(timeout=20):
    rows = []
    errors = []
    for url in _price_source_urls():
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "BigShot-Guy-Bot/1.0"},
                timeout=timeout,
            )
            response.raise_for_status()
            rows.extend(_parse_price_rows(_html_to_text(response.text), url))
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    return rows, errors


def _filter_thai_rows_for_question(rows, question):
    wanted = _wanted_vegetable(question)
    if wanted:
        matched = [row for row in rows if wanted in row["name"]]
        return matched, wanted
    return rows, None


def _filter_retail_rows_for_question(rows, question):
    terms = _wanted_retail_terms(question)
    if not terms:
        return rows, None
    matched = [
        row for row in rows
        if any(term.lower() in row["name"].lower() for term in terms)
    ]
    if not matched:
        return matched, terms

    matched_markets = {row["market"] for row in matched}
    supplemental = []
    for row in rows:
        if row["market"] in matched_markets:
            continue
        supplemental.append(row)
        matched_markets.add(row["market"])
    return matched + supplemental, terms


def get_vegetable_price_answer(question, timeout=20):
    context = get_vegetable_price_context(question, timeout=timeout)
    return format_vegetable_price_answer(context)


def get_vegetable_price_context(question, timeout=20):
    rows, errors = _fetch_price_rows(timeout=timeout)
    if not rows:
        error_text = "\n".join(errors[:2]) if errors else "No rows parsed."
        return {
            "type": "vegetable_price",
            "question": question,
            "error": f"Thailand vegetable prices: no updated data found.\n{error_text}",
        }

    rows, wanted = _filter_thai_rows_for_question(rows, question)
    if wanted:
        if not rows:
            return {
                "type": "vegetable_price",
                "question": question,
                "error": f"Thailand vegetable prices: no matching price found for {wanted}.",
            }

    rate, rate_date = get_thb_mmk_rate(timeout=timeout)
    rows = rows[:12]
    priced_rows = []
    for row in rows:
        priced_row = dict(row)
        priced_row["price_mmk"] = row["price_thb"] * rate
        priced_rows.append(priced_row)

    sources = []
    for row in priced_rows:
        if row["source"] not in sources:
            sources.append(row["source"])

    return {
        "type": "vegetable_price",
        "question": question,
        "exchange_rate": {
            "base": "THB",
            "quote": "MMK",
            "rate": rate,
            "date": rate_date,
        },
        "rows": priced_rows,
        "sources": sources,
    }


def get_market_negotiation_context(question, timeout=20):
    thai_rows, thai_errors = _fetch_price_rows(timeout=timeout)
    matched_thai_rows, wanted = _filter_thai_rows_for_question(thai_rows, question)
    selected_thai_rows = matched_thai_rows or thai_rows

    myanmar_rows, myanmar_errors = _fetch_myanmar_price_rows(timeout=timeout)
    retail_rows, retail_errors = _fetch_retail_myanmar_price_rows(timeout=timeout)
    matched_retail_rows, wanted_retail_terms = _filter_retail_rows_for_question(retail_rows, question)
    selected_retail_rows = matched_retail_rows or retail_rows

    if not selected_thai_rows and not myanmar_rows and not selected_retail_rows:
        error_text = "\n".join((thai_errors + myanmar_errors + retail_errors)[:6]) or "No rows parsed."
        return {
            "type": "market_negotiation",
            "question": question,
            "error": f"Market negotiation prices: no updated data found.\n{error_text}",
        }

    rate, rate_date = get_thb_mmk_rate(timeout=timeout)
    priced_thai_rows = []
    for row in selected_thai_rows[:16]:
        priced_row = dict(row)
        priced_row["price_mmk"] = row["price_thb"] * rate
        priced_thai_rows.append(priced_row)

    thai_sources = []
    for row in priced_thai_rows:
        if row["source"] not in thai_sources:
            thai_sources.append(row["source"])

    myanmar_sources = []
    for row in myanmar_rows:
        if row["source"] not in myanmar_sources:
            myanmar_sources.append(row["source"])

    retail_sources = []
    for row in selected_retail_rows:
        if row["source"] not in retail_sources:
            retail_sources.append(row["source"])

    notes = [
        "Use these rows as negotiation signals, not a guaranteed contract price.",
        "For Makro or City Mart retail seller negotiation, compare their quote against Myanmar retail rows, Thai market rows converted to MMK, and Myanmar Kyat/kg ranges.",
        "Do not reduce quality or committed quantity unless the quoted price is above the market signal or the grade/spec is weaker than agreed.",
    ]
    if wanted and not matched_thai_rows:
        notes.append(f"No exact Thailand match was parsed for {wanted}; showing available vegetable rows instead.")
    if wanted_retail_terms and not matched_retail_rows:
        notes.append("No exact Makro/City Mart retail match was parsed for " + ", ".join(wanted_retail_terms[:3]) + "; showing available retail vegetable rows instead.")
    if wanted_retail_terms and matched_retail_rows and len(selected_retail_rows) > len(matched_retail_rows):
        exact_markets = sorted({row["market"] for row in matched_retail_rows})
        notes.append(
            "Exact retail match was parsed from "
            + ", ".join(exact_markets)
            + "; extra rows from other retail sources are comparison signals only."
        )
    if myanmar_errors:
        notes.append("Some Myanmar price sources could not be read: " + "; ".join(myanmar_errors[:2]))
    if retail_errors:
        notes.append("Some Makro/City Mart retail sources could not be read: " + "; ".join(retail_errors[:2]))

    return {
        "type": "market_negotiation",
        "question": question,
        "wanted_thai_name": wanted,
        "wanted_retail_terms": wanted_retail_terms,
        "exchange_rate": {
            "base": "THB",
            "quote": "MMK",
            "rate": rate,
            "date": rate_date,
        },
        "thailand_rows": priced_thai_rows,
        "myanmar_retail_rows": selected_retail_rows[:18],
        "myanmar_rows": myanmar_rows[:12],
        "sources": {
            "thailand": thai_sources,
            "myanmar_retail": retail_sources,
            "myanmar": myanmar_sources,
        },
        "source_errors": {
            "thailand": thai_errors,
            "myanmar_retail": retail_errors,
            "myanmar": myanmar_errors,
        },
        "notes": notes,
    }


def format_market_negotiation_answer(context):
    if context.get("error"):
        return context["error"]

    rate = context["exchange_rate"]["rate"]
    lines = [
        "Retail price negotiation signal",
        f"Exchange rate: 1 THB = {rate:,.2f} MMK",
        f"Rate date: {context['exchange_rate']['date']}",
        "Makro / City Mart Myanmar retail rows:",
    ]
    for row in context.get("myanmar_retail_rows") or []:
        price_detail = f"{row['price_mmk']:,.0f} MMK"
        if row.get("price_mmk_per_kg"):
            price_detail += f" ~= {row['price_mmk_per_kg']:,.0f} MMK/kg"
        lines.append(
            f"- {row['market']} - {row['name']}: {price_detail}"
            f" ({row.get('quantity') or row.get('unit')})"
        )
    if not context.get("myanmar_retail_rows"):
        lines.append("- No Makro/City Mart retail rows parsed.")

    lines.extend([
        "Thailand market rows:",
    ])
    for row in context.get("thailand_rows") or []:
        lines.append(
            f"- {row['name']}: {row['price_thb']:,.2f} THB/{row['unit']} "
            f"~= {row['price_mmk']:,.0f} MMK/{row['unit']}"
        )

    lines.append("Myanmar market signal rows:")
    for row in context.get("myanmar_rows") or []:
        lines.append(
            f"- {row['name']}: {row['price_mmk_min']:,.0f}-{row['price_mmk_max']:,.0f} "
            f"MMK/{row['unit']}"
        )
    if not context.get("myanmar_rows"):
        lines.append("- No Myanmar rows parsed. Set MYANMAR_VEGETABLE_PRICE_URLS for your preferred local source.")

    lines.append("Negotiation use:")
    for note in context.get("notes") or []:
        lines.append(f"- {note}")
    lines.append("- Ask Makro/City Mart for product, grade, packing, delivery place, payment term, and rejection rule before agreeing price.")
    lines.append("- Do not reduce supplied product/quality unless the quote is above the market signal or the specification changed.")
    lines.append("Sources: " + str(context.get("sources") or {}))
    return "\n".join(lines)


def format_vegetable_price_answer(context):
    if context.get("error"):
        return context["error"]

    rate = context["exchange_rate"]["rate"]
    lines = [
        "Thailand vegetable prices converted to MMK",
        f"Exchange rate: 1 THB = {rate:,.2f} MMK",
        f"Rate date: {context['exchange_rate']['date']}",
    ]
    for row in context.get("rows") or []:
        lines.append(
            f"- {row['name']}: {row['price_thb']:,.2f} THB/{row['unit']} "
            f"~= {row['price_mmk']:,.0f} MMK/{row['unit']}"
        )

    lines.append("Sources: " + ", ".join(context.get("sources") or []))
    return "\n".join(lines)


def live_info_context(question):
    try:
        if _looks_like_negotiation(question):
            return get_market_negotiation_context(question)
        if _looks_like_weather(question):
            return get_weather_context(question)
        if _looks_like_price(question):
            return get_vegetable_price_context(question)
    except Exception as exc:
        return {
            "type": "live_info_error",
            "question": question,
            "error": f"Live data could not be fetched now: {exc}",
        }
    return None


def format_live_info_answer(context):
    if not context:
        return None
    if context.get("type") == "weather":
        return format_weather_answer(context)
    if context.get("type") == "vegetable_price":
        return format_vegetable_price_answer(context)
    if context.get("type") == "market_negotiation":
        return format_market_negotiation_answer(context)
    return context.get("error")


def answer_live_info(question):
    return format_live_info_answer(live_info_context(question))
