"""
ca_gazetteer.py -- California proper-name supplement for the OCR-correction dictionary.

Purpose: real CA proper names (counties, cities, geographic features, legislators)
are NOT in general English dictionaries, so they get false-flagged as "bad" and can
be mis-"corrected" (e.g. Karnette -> a common word). Adding the canonical forms to the
known-dictionary (a) stops false-flagging -> honest residual, (b) protects the names
from Pass C correction / de-merge shredding.

Caveat: this helps CORRECTLY-OCR'd names. A garbled name (Karnetto, kaloogian) still
won't match and stays in the residual for the image/context pass -- which is correct.

COUNTIES are complete + authoritative (CA has exactly 58). CITIES / FEATURES /
LEGISLATORS are a high-value curated SEED (the high-frequency + known-mangled ones),
not exhaustive -- extend as needed.

Exports CA_NAME_TOKENS: a set of lowercase individual word-tokens (multi-word names
are split, since the corpus tokenizer splits on whitespace). Tokens < 3 chars dropped.
"""

# --- 58 California counties (complete, authoritative) ---
COUNTIES = [
    "Alameda","Alpine","Amador","Butte","Calaveras","Colusa","Contra Costa","Del Norte",
    "El Dorado","Fresno","Glenn","Humboldt","Imperial","Inyo","Kern","Kings","Lake",
    "Lassen","Los Angeles","Madera","Marin","Mariposa","Mendocino","Merced","Modoc",
    "Mono","Monterey","Napa","Nevada","Orange","Placer","Plumas","Riverside","Sacramento",
    "San Benito","San Bernardino","San Diego","San Francisco","San Joaquin",
    "San Luis Obispo","San Mateo","Santa Barbara","Santa Clara","Santa Cruz","Shasta",
    "Sierra","Siskiyou","Solano","Sonoma","Stanislaus","Sutter","Tehama","Trinity",
    "Tulare","Tuolumne","Ventura","Yolo","Yuba",
]

# --- Cities / towns (curated, high-frequency in statutes + seen in residual) ---
CITIES = [
    "Alhambra","Anaheim","Antioch","Arcadia","Azusa","Bakersfield","Belmont","Benicia",
    "Berkeley","Beverly Hills","Brea","Buena Park","Burbank","Burlingame","Calexico",
    "Carlsbad","Carmel","Chico","Chula Vista","Claremont","Clovis","Coalinga","Compton",
    "Concord","Corona","Coronado","Costa Mesa","Covina","Culver City","Cupertino",
    "Daly City","Davis","Downey","Drytown","El Cajon","El Centro","El Monte","Emeryville",
    "Escondido","Eureka","Fairfield","Folsom","Fontana","Fremont","Fullerton","Gardena",
    "Gilroy","Glendale","Glendora","Hanford","Hawthorne","Hayward","Hemet","Hollister",
    "Inglewood","Irvine","Lakewood","Lancaster","Livermore","Lodi","Lompoc","Long Beach",
    "Lynwood","Madera","Manhattan Beach","Manteca","Marysville","Martinez","Maywood",
    "Menlo Park","Merced","Millbrae","Milpitas","Modesto","Monrovia","Montebello",
    "Monterey","Monterey Park","Napa","National City","Needles","Newark","Norwalk",
    "Novato","Oakland","Oceanside","Ojai","Ontario","Orange","Oroville","Oxnard",
    "Pacifica","Palmdale","Palo Alto","Pasadena","Paso Robles","Petaluma","Piedmont",
    "Pittsburg","Placerville","Pomona","Porterville","Rancho Cordova","Redding",
    "Redlands","Redondo Beach","Redwood City","Reedley","Richmond","Ridgecrest",
    "Riverside","Roseville","Sacramento","Salinas","San Bruno","San Gabriel","San Jose",
    "San Leandro","San Marcos","San Mateo","San Pedro","San Rafael","San Ysidro",
    "Sanger","Santa Ana","Santa Maria","Santa Monica","Santa Paula","Santa Rosa",
    "Saratoga","Sausalito","Selma","Simi Valley","Sonora","South Gate","Stockton",
    "Sunnyvale","Susanville","Taft","Tehachapi","Torrance","Tracy","Tulare","Turlock",
    "Tustin","Ukiah","Upland","Vacaville","Vallejo","Ventura","Visalia","Vista",
    "Watsonville","Weed","Whittier","Willows","Woodland","Yreka","Yuba City",
]

# --- Geographic features / regions (curated) ---
FEATURES = [
    "Sierra Nevada","Mojave","Tahoe","Yosemite","Shasta","Lassen","Whitney","Diablo",
    "Tamalpais","Palomar","Cuyamaca","Klamath","Trinity","Feather","Yuba","American",
    "Cosumnes","Mokelumne","Tuolumne","Merced","Kings","Kern","Salinas","Pajaro",
    "Russian","Eel","Mad","Smith","Owens","Truckee","Carson","Walker","Carquinez",
    "Suisun","Tehachapi","Cascade","Cleveland","Tahquitz","Islais","Mono","Pyramid",
    "Cachuma","Berryessa","Oroville","Folsom","Almanor","Havasu","Goose","Clear",
    "Honey","Coachella","Imperial","Antelope","Owens Valley","Central Valley",
    "San Joaquin","Sacramento","Coastal","Channel Islands","Farallon","Catalina",
]

# --- CA legislators (curated SEED -- includes the ones we saw mangled in the residual;
#     distinctive surnames only, to avoid colliding with common words) ---
LEGISLATORS = [
    # seen mangled in the residual
    "Karnette","Kaloogian","Poochigian","Frusetta","Migden","Escutia","Ducheny",
    "Bronshvag","Setencich","Aroner",
    # other distinctive CA legislator surnames
    "Vasconcellos","Brulte","Polanco","Areias","Hertzberg","Cedillo","Firebaugh",
    "Torlakson","Maldonado","Vuich","Boatwright","Quackenbush","Seastrand","Takasugi",
    "Honda","Shimizu","Matsui","Wieckowski","Galgiani","Oropeza","Negrete","Solorio",
    "Hueso","Pavley","Kehoe","Roberti","Lockyer","Vasconcelos","Calderon","Padilla",
    "Alquist","Vuong","Nakanishi","Canciamilla","Wesson","Cardenas","Bustamante",
    "Cogdill","Ashburn","Florez","Machado","Dutton","Runner","Margett","Strickland",
]

def _tokens(names):
    out = set()
    for name in names:
        for part in name.replace("-", " ").split():
            p = part.lower().strip()
            if len(p) >= 3 and p.isalpha():
                out.add(p)
    return out

CA_NAME_TOKENS = _tokens(COUNTIES) | _tokens(CITIES) | _tokens(FEATURES) | _tokens(LEGISLATORS)

if __name__ == "__main__":
    print(f"counties={len(COUNTIES)} cities={len(CITIES)} features={len(FEATURES)} "
          f"legislators={len(LEGISLATORS)} -> {len(CA_NAME_TOKENS)} unique name-tokens")
