import re

STRAIN_DATABASE = {
    "granddaddy purple": "indica", "gdp": "indica", "purple kush": "indica", "northern lights": "indica", "afghani": "indica", "blueberry": "indica", "bubba kush": "indica", "master kush": "indica", "og kush": "indica", "skywalker og": "indica", "kosher kush": "indica", "la confidential": "indica", "purple punch": "indica", "ice cream cake": "indica", "wedding cake": "indica", "do si dos": "indica", "dosidos": "indica", "zkittlez": "indica", "gelato": "indica", "sherbet": "indica", "sunset sherbet": "indica", "purple urkle": "indica", "grape ape": "indica", "blackberry kush": "indica", "death star": "indica", "romulan": "indica", "critical kush": "indica", "chocolate og": "indica", "motorbreath": "indica", "slurricane": "indica", "sundae driver": "indica", "candy rain": "indica", "cherry pie": "indica",
    "sour diesel": "sativa", "jack herer": "sativa", "durban poison": "sativa", "green crack": "sativa", "super lemon haze": "sativa", "tangie": "sativa", "strawberry cough": "sativa", "trainwreck": "sativa", "maui wowie": "sativa", "acapulco gold": "sativa", "panama red": "sativa", "super silver haze": "sativa", "amnesia haze": "sativa", "ghost train haze": "sativa", "candyland": "sativa", "lemon skunk": "sativa", "chemdog": "sativa", "chem dawg": "sativa", "cherry ak": "sativa", "j1": "sativa", "lamb's bread": "sativa", "red congolese": "sativa", "thai": "sativa", "colombian gold": "sativa", "malawi": "sativa", "super sour diesel": "sativa", "clementine": "sativa",
    "blue dream": "hybrid", "girl scout cookies": "hybrid", "gsc": "hybrid", "gorilla glue": "hybrid", "gg4": "hybrid", "white widow": "hybrid", "pineapple express": "hybrid", "ak-47": "hybrid", "sour og": "hybrid", "golden goat": "hybrid", "headband": "hybrid", "chernobyl": "hybrid", "bruce banner": "hybrid", "fire og": "hybrid", "gmo cookies": "hybrid", "mac": "hybrid", "miracle alien cookies": "hybrid", "wedding crasher": "hybrid", "mimosa": "hybrid", "runtz": "hybrid", "biscotti": "hybrid", "cookies and cream": "hybrid", "animal cookies": "hybrid", "platinum cookies": "hybrid", "thin mint": "hybrid", "thin mint cookies": "hybrid", "scooby snacks": "hybrid", "london pound cake": "hybrid", "apples and bananas": "hybrid", "cereal milk": "hybrid", "rainbow belts": "hybrid", "jealousy": "hybrid", "grape gasoline": "hybrid", "oreoz": "hybrid", "gary payton": "hybrid", "obama kush": "hybrid", "tahoe og": "hybrid", "sfv og": "hybrid", "larry og": "hybrid", "triple og": "hybrid", "wifi og": "hybrid",
    "kush": "indica", "haze": "sativa", "cookies": "hybrid", "diesel": "sativa", "skunk": "sativa", "cheese": "hybrid", "punch": "indica", "cake": "indica", "pie": "indica", "breath": "hybrid", "sherb": "indica",
}
SIZE_PATTERN = re.compile(r'\b\d+\.?\d*\s*(g|mg|oz|ml|ct|count|pk|pack)\b')
PRODUCT_TYPE_PATTERN = re.compile(r'\b(flower|pre[-\s]?roll|joint|blunt|eighth|quarter|half|ounce)\b')
SORTED_STRAIN_NAMES = sorted(STRAIN_DATABASE.keys(), key=len, reverse=True)
STRAIN_PATTERNS = {strain: re.compile(r'\b' + re.escape(strain) + r'\b') for strain in STRAIN_DATABASE.keys()}
strain_lookup_cache = {}

def free_strain_lookup(product_name, category):
    if not product_name:
        return "unspecified"
    cache_key = f"{product_name.lower().strip()}|{category.lower().strip()}"
    if cache_key in strain_lookup_cache:
        return strain_lookup_cache[cache_key]
    name_lower = product_name.lower().strip()
    clean_name = SIZE_PATTERN.sub('', name_lower)
    clean_name = PRODUCT_TYPE_PATTERN.sub('', clean_name).strip()
    if clean_name in STRAIN_DATABASE:
        result = STRAIN_DATABASE[clean_name]
        strain_lookup_cache[cache_key] = result
        return result
    for strain_name in SORTED_STRAIN_NAMES:
        if STRAIN_PATTERNS[strain_name].search(clean_name):
            result = STRAIN_DATABASE[strain_name]
            strain_lookup_cache[cache_key] = result
            return result
    strain_lookup_cache[cache_key] = "unspecified"
    return "unspecified"

def ai_lookup_strain_type(product_name, category):
    return free_strain_lookup(product_name, category)


def get_strain_database_size() -> int:
    return len(STRAIN_DATABASE)


def get_strain_lookup_cache_size() -> int:
    return len(strain_lookup_cache)


def clear_strain_lookup_cache() -> None:
    strain_lookup_cache.clear()
