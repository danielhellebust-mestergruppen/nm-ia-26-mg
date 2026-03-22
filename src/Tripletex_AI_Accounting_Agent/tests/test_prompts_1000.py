"""
1000-prompt classification test suite for the Tripletex accounting agent.

Generates ~1000 classification tests from ~150 handcrafted base prompts across
all task types and all 7 languages (nb, nn, en, de, es, pt, fr).

Usage:
    python3 tests/test_prompts_1000.py                  # run classification (requires GOOGLE_API_KEY)
    python3 tests/test_prompts_1000.py --generate-only  # just generate prompts to JSON, no API calls
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

# Allow importing from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level="INFO", format="%(asctime)s %(name)s: %(message)s")
logger = logging.getLogger("test_1000")

# ---------------------------------------------------------------------------
# Name pools per language / culture
# ---------------------------------------------------------------------------
NAMES_NB = [
    ("Ola", "Nordmann"), ("Kari", "Hansen"), ("Erik", "Larsen"), ("Ingrid", "Bakke"),
    ("Magnus", "Haugen"), ("Hilde", "Johansen"), ("Tor", "Bakken"), ("Silje", "Ødegård"),
    ("Lars", "Berntsen"), ("Astrid", "Solberg"), ("Bjørn", "Sæther"), ("Ragnhild", "Østby"),
    ("Petter", "Aasen"), ("Marit", "Kvamme"), ("Svein", "Pedersen"), ("Åse", "Strand"),
]
NAMES_NN = [
    ("Eirik", "Viken"), ("Solveig", "Fjeld"), ("Håkon", "Brekke"), ("Gunnhild", "Aase"),
    ("Torbjørn", "Moen"), ("Randi", "Sætre"), ("Oddvar", "Lunde"), ("Ingunn", "Dale"),
]
NAMES_EN = [
    ("James", "Wilson"), ("Sarah", "Thompson"), ("Michael", "Roberts"), ("Emma", "Clark"),
    ("David", "Mitchell"), ("Olivia", "Parker"), ("Thomas", "Anderson"), ("Sophie", "Wright"),
]
NAMES_DE = [
    ("Hans", "Müller"), ("Anna", "Schmidt"), ("Klaus", "Weber"), ("Petra", "Schneider"),
    ("Friedrich", "Becker"), ("Ursula", "Hoffmann"), ("Wolfgang", "Schäfer"), ("Gisela", "König"),
]
NAMES_ES = [
    ("Carlos", "García"), ("María", "Rodríguez"), ("Pablo", "Martínez"), ("Isabel", "López"),
    ("Javier", "Hernández"), ("Lucía", "Fernández"), ("Alejandro", "Díaz"), ("Carmen", "Ruiz"),
]
NAMES_PT = [
    ("André", "Martins"), ("Beatriz", "Rodrigues"), ("Pedro", "Oliveira"), ("Catarina", "Silva"),
    ("João", "Ferreira"), ("Ana", "Sousa"), ("Miguel", "Santos"), ("Mariana", "Pereira"),
]
NAMES_FR = [
    ("Arthur", "Dubois"), ("Camille", "Moreau"), ("Louis", "Laurent"), ("Émilie", "Bernard"),
    ("Pierre", "Thomas"), ("Sophie", "Petit"), ("Antoine", "Robert"), ("Claire", "Richard"),
]

NAMES = {
    "nb": NAMES_NB, "nn": NAMES_NN, "en": NAMES_EN,
    "de": NAMES_DE, "es": NAMES_ES, "pt": NAMES_PT, "fr": NAMES_FR,
}

COMPANY_SUFFIXES = {
    "nb": ["AS", "ASA", "ANS"], "nn": ["AS", "ASA"],
    "en": ["Ltd", "Inc", "Plc"], "de": ["GmbH", "AG", "KG"],
    "es": ["SL", "SA"], "pt": ["Lda", "SA"],
    "fr": ["SARL", "SAS", "SA"],
}

COMPANY_WORDS_NB = [
    "Fjordkraft", "Havbris", "Nordlys", "Stormberg", "Bølgekraft", "Snøhetta",
    "Solstrand", "Trollfjord", "Ishavet", "Midnattssol", "Vikingskip",
]
COMPANY_WORDS_EN = [
    "Brightstone", "Ridgepoint", "Oakfield", "Clearwater", "Irongate", "Nordic Solutions",
]
COMPANY_WORDS_DE = [
    "Bergwerk", "Grünfeld", "Steinadler", "Lichtblick", "Schneekristall",
]
COMPANY_WORDS_ES = [
    "Sierra", "Dorada", "Luna", "Cumbre", "Montaña",
]
COMPANY_WORDS_PT = [
    "Cascata", "Floresta", "Oceano", "Tempestade", "Aurora",
]
COMPANY_WORDS_FR = [
    "Étoile", "Colline", "Océan", "Rivière", "Lumière",
]

COMPANY_WORDS = {
    "nb": COMPANY_WORDS_NB, "nn": COMPANY_WORDS_NB, "en": COMPANY_WORDS_EN,
    "de": COMPANY_WORDS_DE, "es": COMPANY_WORDS_ES, "pt": COMPANY_WORDS_PT,
    "fr": COMPANY_WORDS_FR,
}

STREETS_NO = [
    "Storgata", "Karl Johans gate", "Kirkegata", "Torggata", "Parkveien",
    "Solveien", "Fjordveien", "Kongens gate", "Dronningens gate", "Havnegata",
]
CITIES_NO = [
    ("0150", "Oslo"), ("5003", "Bergen"), ("7010", "Trondheim"),
    ("4611", "Kristiansand"), ("9008", "Tromsø"), ("3015", "Drammen"),
    ("1530", "Moss"), ("6004", "Ålesund"), ("4006", "Stavanger"),
]

PRODUCTS_NB = [
    "Konsulenttimer", "Programvarelisens", "Webdesign", "Systemutvikling",
    "Opplæring", "Vedlikehold", "Nettverkstjenester", "Driftsstøtte",
    "Databehandling", "Sikkerhetsrådgivning", "Prosjektledelse",
]
PRODUCTS_EN = [
    "Consulting hours", "Software license", "Web design", "System development",
    "Training", "Maintenance", "Network services", "Cloud storage",
    "Data processing", "Security consulting", "Project management",
]
PRODUCTS_DE = [
    "Beratungsstunden", "Softwarelizenz", "Webdesign", "Systementwicklung",
    "Schulung", "Wartung", "Netzwerkdienste", "Cloud-Speicher",
    "Datenberatung", "Sicherheitsberatung",
]
PRODUCTS_ES = [
    "Horas de consultoría", "Licencia de software", "Diseño web",
    "Desarrollo de sistemas", "Formación", "Mantenimiento", "Informe de análisis",
]
PRODUCTS_PT = [
    "Horas de consultoria", "Licença de software", "Design web",
    "Desenvolvimento de sistemas", "Formação", "Manutenção", "Serviço de rede",
]
PRODUCTS_FR = [
    "Heures de conseil", "Licence logicielle", "Conception web",
    "Développement système", "Formation", "Maintenance", "Services réseau",
]

PRODUCTS = {
    "nb": PRODUCTS_NB, "nn": PRODUCTS_NB, "en": PRODUCTS_EN,
    "de": PRODUCTS_DE, "es": PRODUCTS_ES, "pt": PRODUCTS_PT,
    "fr": PRODUCTS_FR,
}

PROJECT_NAMES = {
    "nb": ["Skymigrering", "Analyse Fjordkraft", "Digitaliseringsprosjekt", "IT-oppgradering", "Nettbutikk"],
    "nn": ["Systemoppgradering", "Datasikring", "Nettløysing"],
    "en": ["Cloud Migration", "Digital Transformation", "Security Audit", "ERP Integration"],
    "de": ["Systemintegration", "Digitalisierung", "Sicherheitsaudit"],
    "es": ["Implementación Dorada", "Migración Digital", "Auditoría de seguridad"],
    "pt": ["Migração para nuvem", "Transformação Digital", "Auditoria de segurança"],
    "fr": ["Migration Étoile", "Intégration CRM", "Audit sécurité", "Transformation digitale"],
}

ACTIVITIES = [
    "Utvikling", "Design", "Analyse", "Testing", "Prosjektledelse",
    "Rådgivning", "Implementering", "Dokumentasjon",
]

EXPENSE_ACCOUNTS = ["6300", "6340", "6500", "6590", "6860", "7140", "7350"]

# ---------------------------------------------------------------------------
# Helper to generate random values
# ---------------------------------------------------------------------------

def rand_org() -> str:
    return str(random.randint(800000000, 999999999))

def rand_product_number() -> str:
    return str(random.randint(1000, 9999))

def rand_amount(lo: int = 5000, hi: int = 80000) -> int:
    return random.randint(lo // 100, hi // 100) * 100

def rand_salary() -> int:
    return random.randint(280, 650) * 100

def rand_bonus() -> int:
    return random.randint(30, 200) * 100

def rand_name(lang: str) -> tuple[str, str]:
    pool = NAMES.get(lang, NAMES_NB)
    return random.choice(pool)

def rand_email(first: str, last: str) -> str:
    f = first.lower().replace("é", "e").replace("ü", "u").replace("ø", "o").replace("å", "a").replace("æ", "ae").replace("ã", "a").replace("ñ", "n").replace("í", "i").replace("ú", "u")
    l = last.lower().replace("é", "e").replace("ü", "u").replace("ø", "o").replace("å", "a").replace("æ", "ae").replace("ã", "a").replace("ñ", "n").replace("í", "i").replace("ú", "u")
    return f"{f}.{l}@example.org"

def rand_company(lang: str) -> str:
    word = random.choice(COMPANY_WORDS.get(lang, COMPANY_WORDS_NB))
    suffix = random.choice(COMPANY_SUFFIXES.get(lang, ["AS"]))
    return f"{word} {suffix}"

def rand_street() -> str:
    return f"{random.choice(STREETS_NO)} {random.randint(1, 200)}"

def rand_city() -> tuple[str, str]:
    return random.choice(CITIES_NO)

def rand_product(lang: str) -> str:
    return random.choice(PRODUCTS.get(lang, PRODUCTS_NB))

def rand_project(lang: str) -> str:
    return random.choice(PROJECT_NAMES.get(lang, PROJECT_NAMES["nb"]))

def rand_date_str() -> str:
    day = random.randint(1, 28)
    month = random.randint(1, 12)
    return f"{day}. {'January February March April May June July August September October November December'.split()[month-1]} 2026"


# ---------------------------------------------------------------------------
# BASE PROMPTS: ~150 handcrafted prompts across all task types and languages
# ---------------------------------------------------------------------------

PROMPTS: list[dict] = [
    # ========================================================================
    # create_employee (with admin, with details, multiple)
    # ========================================================================
    {"prompt": "Opprett en ny ansatt, Åse Ødegård, med e-post aase.odegard@example.org og gi henne administratorrolle i Tripletex.", "expected_type": "create_employee", "lang": "nb"},
    {"prompt": "Registrer ny medarbeider Erik Larsen (erik.larsen@example.org), født 12. mars 1988. Startdato 1. januar 2026.", "expected_type": "create_employee", "lang": "nb"},
    {"prompt": "Vi har tre nye ansatte som skal legges inn: Kari Hansen (kari.hansen@example.org), Lars Berntsen (lars.berntsen@example.org) og Ingrid Bakke (ingrid.bakke@example.org). Alle starter 1. februar 2026.", "expected_type": "create_employee", "lang": "nb"},
    {"prompt": "Opprett ein ny tilsett, Solveig Fjeld (solveig.fjeld@example.org), fødd 5. mai 1990. Ho skal vere administrator.", "expected_type": "create_employee", "lang": "nn"},
    {"prompt": "Registrer Eirik Viken som ny medarbeidar med e-post eirik.viken@example.org og startdato 15. mars 2026.", "expected_type": "create_employee", "lang": "nn"},
    {"prompt": "Create a new employee James Wilson (james.wilson@example.org), born 22 June 1985. Start date 1 March 2026. Give him administrator access.", "expected_type": "create_employee", "lang": "en"},
    {"prompt": "Register new employee Sarah Thompson with email sarah.thompson@example.org. She starts on 15 February 2026.", "expected_type": "create_employee", "lang": "en"},
    {"prompt": "Erstellen Sie einen neuen Mitarbeiter Hans Müller (hans.mueller@example.org), geboren am 3. April 1992. Startdatum: 1. März 2026. Er soll Administratorrechte erhalten.", "expected_type": "create_employee", "lang": "de"},
    {"prompt": "Neuen Mitarbeiter anlegen: Klaus Weber (klaus.weber@example.org), Geburtsdatum 18. September 1987.", "expected_type": "create_employee", "lang": "de"},
    {"prompt": "Tenemos un nuevo empleado llamado Carlos García, nacido el 14. March 1986. Créelo como empleado con el correo carlos.garcia@example.org y fecha de inicio 17. January 2026.", "expected_type": "create_employee", "lang": "es"},
    {"prompt": "Registre un nuevo empleado: Lucía Hernández (lucia.hernandez@example.org). Debe tener rol de administrador.", "expected_type": "create_employee", "lang": "es"},
    {"prompt": "Crie um novo funcionário André Martins (andre.martins@example.org), nascido em 20 de julho de 1991. Data de início: 1 de março de 2026.", "expected_type": "create_employee", "lang": "pt"},
    {"prompt": "Registar nova funcionária Beatriz Rodrigues com e-mail beatriz.rodrigues@example.org. Ela deve ser administradora.", "expected_type": "create_employee", "lang": "pt"},
    {"prompt": "Créez un nouvel employé Arthur Dubois (arthur.dubois@example.org), né le 8 novembre 1989. Date de début : 1er mars 2026. Il doit avoir les droits d'administrateur.", "expected_type": "create_employee", "lang": "fr"},
    {"prompt": "Enregistrez la nouvelle employée Camille Moreau (camille.moreau@example.org) avec une date de début le 15 février 2026.", "expected_type": "create_employee", "lang": "fr"},

    # ========================================================================
    # update_employee
    # ========================================================================
    {"prompt": "Oppdater kontaktinformasjonen til Kari Hansen: ny e-post er kari.ny@example.org og nytt telefonnummer er 98765432.", "expected_type": "update_employee", "lang": "nb"},
    {"prompt": "Endre adressen til Erik Larsen til Storgata 15, 0150 Oslo.", "expected_type": "update_employee", "lang": "nb"},
    {"prompt": "Oppdater Solveig Fjeld si e-postadresse til solveig.ny@example.org.", "expected_type": "update_employee", "lang": "nn"},
    {"prompt": "Update the phone number for James Wilson to +47 91234567.", "expected_type": "update_employee", "lang": "en"},
    {"prompt": "Change Sarah Thompson's email address to sarah.new@example.org.", "expected_type": "update_employee", "lang": "en"},
    {"prompt": "Aktualisieren Sie die Telefonnummer von Hans Müller auf +47 98765432.", "expected_type": "update_employee", "lang": "de"},
    {"prompt": "Actualice el correo electrónico de Carlos García a carlos.nuevo@example.org.", "expected_type": "update_employee", "lang": "es"},
    {"prompt": "Atualize o número de telefone de André Martins para +47 91234567.", "expected_type": "update_employee", "lang": "pt"},
    {"prompt": "Mettez à jour l'adresse e-mail d'Arthur Dubois à arthur.nouveau@example.org.", "expected_type": "update_employee", "lang": "fr"},

    # ========================================================================
    # create_customer (regular, supplier/leverandor, with address)
    # ========================================================================
    {"prompt": "Opprett kunden Nordlys AS med organisasjonsnummer 912345678 og e-post post@nordlys.no.", "expected_type": "create_customer", "lang": "nb"},
    {"prompt": "Legg inn Fjordkraft AS (org.nr 987654321) som ny kunde. Adresse: Storgata 10, 0150 Oslo. E-post: faktura@fjordkraft.no.", "expected_type": "create_customer", "lang": "nb"},
    {"prompt": "Registrer Havbris AS som leverandør med organisasjonsnummer 934567890.", "expected_type": "create_customer", "lang": "nb"},
    {"prompt": "Opprett Solstrand ANS (org.nr 956789012) som både kunde og leverandør.", "expected_type": "create_customer", "lang": "nb"},
    {"prompt": "Registrer ny kunde Bølgekraft AS med org.nr 827304212. Adresse: Kongens gate 44, 7010 Trondheim.", "expected_type": "create_customer", "lang": "nb"},
    {"prompt": "Opprett kunden Trollfjord ASA (org.nr 845123678) med e-post post@trollfjord.no.", "expected_type": "create_customer", "lang": "nn"},
    {"prompt": "Legg inn Midnattssol AS som leverandør med organisasjonsnummer 876543210.", "expected_type": "create_customer", "lang": "nn"},
    {"prompt": "Create the customer Brightstone Ltd with organization number 853284882. The address is Parkveien 61, 5003 Bergen. Email: post@brightstone.no.", "expected_type": "create_customer", "lang": "en"},
    {"prompt": "Register Ridgepoint Ltd (org no. 989339028) as a supplier.", "expected_type": "create_customer", "lang": "en"},
    {"prompt": "Create customer Oakfield Inc with org number 923456789 and email info@oakfield.com.", "expected_type": "create_customer", "lang": "en"},
    {"prompt": "Erstellen Sie den Kunden Bergwerk GmbH mit der Organisationsnummer 946768693. Die Adresse ist Solveien 5, 3015 Drammen. E-Mail: post@bergwerk.no.", "expected_type": "create_customer", "lang": "de"},
    {"prompt": "Registrieren Sie Grünfeld GmbH (Org.-Nr. 920238882) als Lieferant.", "expected_type": "create_customer", "lang": "de"},
    {"prompt": "Crea el cliente Luna SL con número de organización 975692981. La dirección es Torggata 50, 9008 Tromsø. Correo: post@luna.no.", "expected_type": "create_customer", "lang": "es"},
    {"prompt": "Registra Sierra SL como proveedor con número de organización 909007135.", "expected_type": "create_customer", "lang": "es"},
    {"prompt": "Crie o cliente Floresta Lda com número de organização 893475656. O endereço é Kirkegata 132, 7010 Trondheim. E-mail: post@floresta.no.", "expected_type": "create_customer", "lang": "pt"},
    {"prompt": "Registar Cascata Lda como fornecedor com número de organização 829637286.", "expected_type": "create_customer", "lang": "pt"},
    {"prompt": "Créez le client Colline SARL avec le numéro d'organisation 939137599. L'adresse est Kirkegata 77, 4611 Kristiansand. E-mail : post@colline.no.", "expected_type": "create_customer", "lang": "fr"},
    {"prompt": "Enregistrez Étoile SARL (nº org. 964531161) comme fournisseur.", "expected_type": "create_customer", "lang": "fr"},

    # ========================================================================
    # update_customer
    # ========================================================================
    {"prompt": "Oppdater e-postadressen til Nordlys AS til ny@nordlys.no.", "expected_type": "update_customer", "lang": "nb"},
    {"prompt": "Endre telefonnummeret til Fjordkraft AS til 22334455.", "expected_type": "update_customer", "lang": "nb"},
    {"prompt": "Update the email for Brightstone Ltd to new@brightstone.no.", "expected_type": "update_customer", "lang": "en"},
    {"prompt": "Aktualisieren Sie die E-Mail-Adresse von Bergwerk GmbH auf neu@bergwerk.no.", "expected_type": "update_customer", "lang": "de"},
    {"prompt": "Actualice el correo electrónico de Luna SL a nuevo@luna.no.", "expected_type": "update_customer", "lang": "es"},
    {"prompt": "Atualize o e-mail de Floresta Lda para novo@floresta.no.", "expected_type": "update_customer", "lang": "pt"},
    {"prompt": "Mettez à jour l'adresse e-mail de Colline SARL à nouveau@colline.no.", "expected_type": "update_customer", "lang": "fr"},

    # ========================================================================
    # create_product (single, multiple, different VAT rates)
    # ========================================================================
    {"prompt": "Opprett produktet \"Konsulenttimer\" med produktnummer 4449 og pris 1500 kr ekskl. MVA (25 %).", "expected_type": "create_product", "lang": "nb"},
    {"prompt": "Legg inn to nye produkter: \"Programvarelisens\" (nr 2584, 9300 kr, 25% MVA) og \"Opplæring\" (nr 3739, 16300 kr, 0% MVA).", "expected_type": "create_product", "lang": "nb"},
    {"prompt": "Opprett produkt \"Matlevering\" med nummer 5511, pris 450 kr ekskl. MVA med 15% MVA-sats (næringsmiddel).", "expected_type": "create_product", "lang": "nb"},
    {"prompt": "Legg inn produkt \"Hotellovernatting\" med nummer 6622, pris 1200 kr, 12% MVA (overnatting).", "expected_type": "create_product", "lang": "nb"},
    {"prompt": "Opprett produktet \"Eksporttjeneste\" med nummer 7733, pris 25000 kr, uten MVA (avgiftsfri).", "expected_type": "create_product", "lang": "nb"},
    {"prompt": "Create product \"Software license\" with number 8844, price 5000 NOK excl. VAT at 25%.", "expected_type": "create_product", "lang": "en"},
    {"prompt": "Create two products: \"Consulting\" (no. 1122, 2000 NOK, 25% VAT) and \"Training\" (no. 3344, 8000 NOK, 0% VAT exempt).", "expected_type": "create_product", "lang": "en"},
    {"prompt": "Erstellen Sie das Produkt \"Beratungsstunden\" mit Nummer 4455, Preis 3000 NOK ohne MwSt (25%).", "expected_type": "create_product", "lang": "de"},
    {"prompt": "Crea el producto \"Horas de consultoría\" con número 5566, precio 2500 NOK sin IVA (25%).", "expected_type": "create_product", "lang": "es"},
    {"prompt": "Crie o produto \"Consultoria\" com número 6677, preço 4000 NOK sem IVA (25%).", "expected_type": "create_product", "lang": "pt"},
    {"prompt": "Créez le produit \"Heures de conseil\" avec le numéro 7788, prix 3500 NOK HT (25% TVA).", "expected_type": "create_product", "lang": "fr"},

    # ========================================================================
    # update_product
    # ========================================================================
    {"prompt": "Oppdater prisen på \"Konsulenttimer\" til 1750 kr ekskl. MVA.", "expected_type": "update_product", "lang": "nb"},
    {"prompt": "Endre navnet på produktet \"Opplæring\" til \"Kurs og opplæring\".", "expected_type": "update_product", "lang": "nb"},
    {"prompt": "Update the price of \"Software license\" to 5500 NOK.", "expected_type": "update_product", "lang": "en"},
    {"prompt": "Aktualisieren Sie den Preis von \"Beratungsstunden\" auf 3500 NOK.", "expected_type": "update_product", "lang": "de"},
    {"prompt": "Actualice el precio de \"Horas de consultoría\" a 3000 NOK.", "expected_type": "update_product", "lang": "es"},

    # ========================================================================
    # create_department (single, multiple)
    # ========================================================================
    {"prompt": "Opprett avdelingen \"Utvikling\" med avdelingsnummer 200.", "expected_type": "create_department", "lang": "nb"},
    {"prompt": "Opprett tre avdelinger: \"HR\", \"Salg\" og \"Drift\".", "expected_type": "create_department", "lang": "nb"},
    {"prompt": "Opprett avdelinga \"Marknadsføring\" med avdelingsnummer 300.", "expected_type": "create_department", "lang": "nn"},
    {"prompt": "Create department \"Development\" with number 200.", "expected_type": "create_department", "lang": "en"},
    {"prompt": "Create two departments: \"Sales\" and \"Marketing\".", "expected_type": "create_department", "lang": "en"},
    {"prompt": "Erstellen Sie die Abteilung \"Entwicklung\" mit Nummer 200.", "expected_type": "create_department", "lang": "de"},
    {"prompt": "Crea el departamento \"Ventas\" con número 200.", "expected_type": "create_department", "lang": "es"},
    {"prompt": "Crie o departamento \"Vendas\" com número 200.", "expected_type": "create_department", "lang": "pt"},
    {"prompt": "Créez le département \"Ventes\" avec le numéro 200.", "expected_type": "create_department", "lang": "fr"},

    # ========================================================================
    # update_department
    # ========================================================================
    {"prompt": "Endre navnet på avdelingen \"Utvikling\" til \"Produktutvikling\".", "expected_type": "update_department", "lang": "nb"},
    {"prompt": "Rename department \"Development\" to \"Product Development\".", "expected_type": "update_department", "lang": "en"},
    {"prompt": "Benennen Sie die Abteilung \"Entwicklung\" in \"Produktentwicklung\" um.", "expected_type": "update_department", "lang": "de"},

    # ========================================================================
    # create_invoice (single line, multi-line, with payment, different VAT)
    # ========================================================================
    {"prompt": "Opprett og send en faktura til kunden Nordlys AS (org.nr 912345678) på 25000 kr ekskl. MVA. Fakturaen gjelder Konsulenttimer.", "expected_type": "create_invoice", "lang": "nb"},
    {"prompt": "Opprett ein faktura til kunden Bølgekraft AS (org.nr 827304212) med tre produktlinjer: Webdesign (6744) til 27000 kr med 25 % MVA, Programvarelisens (2584) til 9300 kr med 15 % MVA (næringsmiddel), og Opplæring (3739) til 16300 kr med 0 % MVA (avgiftsfri).", "expected_type": "create_invoice", "lang": "nn"},
    {"prompt": "Lag en faktura til Stormberg AS (org.nr 957353681) for Systemutvikling til 45000 kr ekskl. MVA. Registrer også full betaling.", "expected_type": "create_invoice", "lang": "nb"},
    {"prompt": "Erstellen Sie einen Auftrag für den Kunden Grünfeld GmbH (Org.-Nr. 920238882) mit den Produkten Datenberatung (5628) zu 23000 NOK und Cloud-Speicher (1573) zu 16550 NOK. Wandeln Sie den Auftrag in eine Rechnung um und registrieren Sie die vollständige Zahlung.", "expected_type": "create_invoice", "lang": "de"},
    {"prompt": "Create and send an invoice to Brightstone Ltd (org no. 853284882) for 20000 NOK excl. VAT. The invoice is for Consulting hours.", "expected_type": "create_invoice", "lang": "en"},
    {"prompt": "Create an invoice for Oakfield Inc (org no. 923456789) with two products: Web design (4411) at 15000 NOK with 25% VAT and Training (5522) at 8000 NOK with 0% VAT (exempt).", "expected_type": "create_invoice", "lang": "en"},
    {"prompt": "Crea una factura para el cliente Sierra SL (org. nº 909007135) con tres líneas de producto: Desarrollo de sistemas (8344) a 19250 NOK con 25 % IVA, Horas de consultoría (9563) a 10000 NOK con 15 % IVA (alimentos), y Informe de análisis (8060) a 15800 NOK con 0 % IVA (exento).", "expected_type": "create_invoice", "lang": "es"},
    {"prompt": "Crie e envie uma fatura para Floresta Lda (org. nº 893475656) de 30000 NOK sem IVA. A fatura refere-se a Serviço de rede.", "expected_type": "create_invoice", "lang": "pt"},
    {"prompt": "Créez et envoyez une facture au client Étoile SARL (nº org. 976414284) de 20000 NOK hors TVA. La facture concerne Heures de conseil.", "expected_type": "create_invoice", "lang": "fr"},
    {"prompt": "Créez une facture pour Colline SARL (nº org. 894562234) avec deux lignes : Licence logicielle (3344) à 12000 NOK avec 25% TVA et Formation (5566) à 9000 NOK avec 0% TVA (exonéré). Enregistrez le paiement complet.", "expected_type": "create_invoice", "lang": "fr"},

    # ========================================================================
    # register_payment
    # ========================================================================
    {"prompt": "Kunden Havbris AS (org.nr 831357983) har en utestående faktura på 5900 kr eksklusiv MVA for \"Konsulenttimer\". Registrer full betaling på denne fakturaen.", "expected_type": "register_payment", "lang": "nb"},
    {"prompt": "Registrer betaling fra Nordlys AS for faktura på 25000 kr.", "expected_type": "register_payment", "lang": "nb"},
    {"prompt": "Register full payment on the outstanding invoice for Brightstone Ltd for 20000 NOK.", "expected_type": "register_payment", "lang": "en"},
    {"prompt": "Registrieren Sie die vollständige Zahlung für die Rechnung von Bergwerk GmbH über 15000 NOK.", "expected_type": "register_payment", "lang": "de"},
    {"prompt": "Registre el pago completo de la factura de Luna SL por 18000 NOK.", "expected_type": "register_payment", "lang": "es"},
    {"prompt": "Registar o pagamento total da fatura de Cascata Lda de 22000 NOK.", "expected_type": "register_payment", "lang": "pt"},
    {"prompt": "Le client Océan SARL (nº org. 924390735) a une facture impayée de 39300 NOK hors TVA pour \"Maintenance\". Enregistrez le paiement intégral de cette facture.", "expected_type": "register_payment", "lang": "fr"},

    # ========================================================================
    # reverse_payment (returned by bank)
    # ========================================================================
    {"prompt": "Betalingen fra Fjordkraft AS på 15000 kr for \"Vedlikehold\" er blitt returnert av banken. Reverser betalingen.", "expected_type": "reverse_payment", "lang": "nb"},
    {"prompt": "The payment of 20000 NOK from Ridgepoint Ltd for \"Maintenance\" has been returned by the bank. Reverse the payment.", "expected_type": "reverse_payment", "lang": "en"},
    {"prompt": "Die Zahlung von 12000 NOK von Steinadler AG für \"Wartung\" wurde von der Bank zurückgebucht. Stornieren Sie die Zahlung.", "expected_type": "reverse_payment", "lang": "de"},
    {"prompt": "El pago de 18000 NOK de Dorada SL por \"Mantenimiento\" ha sido devolvido por el banco. Revierta el pago.", "expected_type": "reverse_payment", "lang": "es"},
    {"prompt": "O pagamento de 25000 NOK de Oceano SA referente a \"Manutenção\" foi devolvido pelo banco. Reverta o pagamento.", "expected_type": "reverse_payment", "lang": "pt"},
    {"prompt": "Le paiement de 30000 NOK de Rivière SAS pour \"Maintenance\" a été retourné par la banque. Annulez le paiement.", "expected_type": "reverse_payment", "lang": "fr"},

    # ========================================================================
    # create_credit_note
    # ========================================================================
    {"prompt": "Kunden Havbris AS (org.nr 995581094) har reklamert på fakturaen for \"Programvarelisens\" (34650 kr ekskl. MVA). Opprett en fullstendig kreditnota som reverserer hele fakturaen.", "expected_type": "create_credit_note", "lang": "nb"},
    {"prompt": "The customer Ridgepoint Ltd (org no. 989339028) has complained about the invoice for \"Maintenance\" (19650 NOK excl. VAT). Issue a full credit note that reverses the entire invoice.", "expected_type": "create_credit_note", "lang": "en"},
    {"prompt": "Der Kunde Grünfeld GmbH (Org.-Nr. 920238882) hat die Rechnung für \"Beratung\" (22000 NOK) reklamiert. Erstellen Sie eine vollständige Gutschrift.", "expected_type": "create_credit_note", "lang": "de"},
    {"prompt": "El cliente Luna SL (org. nº 975692981) ha reclamado sobre la factura de \"Consultoría\" (15000 NOK sin IVA). Emita una nota de crédito completa.", "expected_type": "create_credit_note", "lang": "es"},
    {"prompt": "O cliente Cascata Lda (org. nº 899582454) reclamou sobre a fatura referente a \"Serviço de rede\" (29150 NOK sem IVA). Emita uma nota de crédito completa que reverta toda a fatura.", "expected_type": "create_credit_note", "lang": "pt"},
    {"prompt": "Le client Étoile SARL (nº org. 964531161) a contesté la facture pour \"Conseil\" (18000 NOK HT). Émettez un avoir complet qui annule la facture.", "expected_type": "create_credit_note", "lang": "fr"},

    # ========================================================================
    # project_invoice (with hours, fixed price)
    # ========================================================================
    {"prompt": "Sett fastpris 178450 kr på prosjektet \"Skymigrering\" for Stormberg AS (org.nr 957353681). Prosjektleder er Magnus Haugen (magnus.haugen@example.org). Fakturer kunden for 50 % av fastprisen som en delbetaling.", "expected_type": "project_invoice", "lang": "nb"},
    {"prompt": "Prosjektet \"Analyse Fjordkraft\" for Fjordkraft AS (org.nr 944845712) har 13 timer registrert av Hilde Johansen (hilde.johansen@example.org) på aktiviteten Design. Fakturer kunden for timene.", "expected_type": "project_invoice", "lang": "nb"},
    {"prompt": "Defina um preço fixo de 362300 NOK no projeto \"Migração para nuvem\" para Cascata Lda (org. nº 829637286). O gestor de projeto é Beatriz Rodrigues (beatriz.rodrigues@example.org). Fature ao cliente 33 % do preço fixo como pagamento por etapa.", "expected_type": "project_invoice", "lang": "pt"},
    {"prompt": "Fixez un prix forfaitaire de 365350 NOK sur le projet \"Intégration CRM\" pour Colline SARL (nº org. 894562234). Le chef de projet est Adam Thomas (adam.thomas@example.org). Facturez au client 75 % du prix fixe comme paiement d'étape.", "expected_type": "project_invoice", "lang": "fr"},
    {"prompt": "Set a fixed price of 250000 NOK on project \"Cloud Migration\" for Oakfield Inc (org no. 923456789). Project manager is David Mitchell (david.mitchell@example.org). Invoice the client for 40% as a milestone payment.", "expected_type": "project_invoice", "lang": "en"},
    {"prompt": "Setzen Sie einen Festpreis von 280000 NOK für das Projekt \"Systemintegration\" für Steinadler AG (Org.-Nr. 912345678). Projektleiter ist Friedrich Becker (friedrich.becker@example.org). Fakturieren Sie 60% als Meilensteinzahlung.", "expected_type": "project_invoice", "lang": "de"},

    # ========================================================================
    # create_project (with customer, with manager)
    # ========================================================================
    {"prompt": "Opprett prosjektet \"Analyse Fjordkraft\" knyttet til kunden Fjordkraft AS (org.nr 944845712). Prosjektleder er Hilde Johansen (hilde.johansen@example.org).", "expected_type": "create_project", "lang": "nb"},
    {"prompt": "Opprett prosjektet \"Digitaliseringsprosjekt\" for Nordlys AS (org.nr 912345678) med startdato 1. mars 2026 og sluttdato 31. desember 2026.", "expected_type": "create_project", "lang": "nb"},
    {"prompt": "Create project \"Security Audit\" for Brightstone Ltd (org no. 853284882). Project manager is Michael Roberts (michael.roberts@example.org).", "expected_type": "create_project", "lang": "en"},
    {"prompt": "Crea el proyecto \"Implementación Dorada\" vinculado al cliente Dorada SL (org. nº 831075392). El director del proyecto es Isabel Rodríguez (isabel.rodriguez@example.org).", "expected_type": "create_project", "lang": "es"},
    {"prompt": "Créez le projet \"Migration Étoile\" lié au client Étoile SARL (nº org. 964531161). Le chef de projet est Arthur Dubois (arthur.dubois@example.org).", "expected_type": "create_project", "lang": "fr"},
    {"prompt": "Erstellen Sie das Projekt \"Digitalisierung\" für Bergwerk GmbH (Org.-Nr. 946768693). Projektleiter ist Wolfgang Schäfer (wolfgang.schaefer@example.org).", "expected_type": "create_project", "lang": "de"},
    {"prompt": "Crie o projeto \"Transformação Digital\" para Floresta Lda (org. nº 893475656). Gestor do projeto: Pedro Oliveira (pedro.oliveira@example.org).", "expected_type": "create_project", "lang": "pt"},

    # ========================================================================
    # update_project
    # ========================================================================
    {"prompt": "Oppdater sluttdatoen for prosjektet \"Skymigrering\" til 30. juni 2026.", "expected_type": "update_project", "lang": "nb"},
    {"prompt": "Avslutt prosjektet \"Analyse Fjordkraft\" — marker det som lukket.", "expected_type": "update_project", "lang": "nb"},
    {"prompt": "Update the end date for project \"Cloud Migration\" to 30 September 2026.", "expected_type": "update_project", "lang": "en"},
    {"prompt": "Mettez à jour la date de fin du projet \"Migration Étoile\" au 31 décembre 2026.", "expected_type": "update_project", "lang": "fr"},

    # ========================================================================
    # create_travel_expense (with per diem, with costs)
    # ========================================================================
    {"prompt": "Registrer en reiseregning for Kari Hansen for \"Kundemøte Bergen\". Reisen varte 3 dager med diett (800 kr/dag). Utgifter: flybillett 4500 kr og taxi 250 kr.", "expected_type": "create_travel_expense", "lang": "nb"},
    {"prompt": "Opprett reiseregning for Erik Larsen: \"Konferanse Stockholm\", 5 dager. Diett 800 kr/dag. Utgifter: fly 6200 kr, hotell 8500 kr, taxi 750 kr.", "expected_type": "create_travel_expense", "lang": "nb"},
    {"prompt": "Register a travel expense for James Wilson for \"Client visit Tromsø\". 2 days with per diem (800 NOK/day). Expenses: flight 3800 NOK and taxi 200 NOK.", "expected_type": "create_travel_expense", "lang": "en"},
    {"prompt": "Registe uma despesa de viagem para André Martins (andre.martins@example.org) referente a \"Visita cliente Trondheim\". A viagem durou 5 dias com ajudas de custo (taxa diária 800 NOK). Despesas: bilhete de avião 7600 NOK e táxi 350 NOK.", "expected_type": "create_travel_expense", "lang": "pt"},
    {"prompt": "Erstellen Sie eine Reisekostenabrechnung für Hans Müller für \"Kundentreffen Bergen\". 3 Tage mit Tagegeld (800 NOK/Tag). Ausgaben: Flug 5200 NOK und Taxi 300 NOK.", "expected_type": "create_travel_expense", "lang": "de"},
    {"prompt": "Registre un gasto de viaje para Carlos García por \"Visita cliente Bergen\". 4 días con viáticos (800 NOK/día). Gastos: vuelo 5800 NOK y taxi 400 NOK.", "expected_type": "create_travel_expense", "lang": "es"},
    {"prompt": "Enregistrez une note de frais de déplacement pour Camille Moreau pour \"Réunion client Oslo\". 3 jours avec indemnité journalière (800 NOK/jour). Frais : vol 4800 NOK et taxi 300 NOK.", "expected_type": "create_travel_expense", "lang": "fr"},

    # ========================================================================
    # update_travel_expense
    # ========================================================================
    {"prompt": "Oppdater reiseregningen \"Kundemøte Bergen\" for Kari Hansen — legg til en ekstra utgift: parkering 150 kr.", "expected_type": "update_travel_expense", "lang": "nb"},
    {"prompt": "Update the travel expense \"Client visit Tromsø\" for James Wilson — change the destination to Bodø.", "expected_type": "update_travel_expense", "lang": "en"},

    # ========================================================================
    # delete_travel_expense
    # ========================================================================
    {"prompt": "Slett reiseregningen \"Konferanse Stockholm\" for Erik Larsen.", "expected_type": "delete_travel_expense", "lang": "nb"},
    {"prompt": "Delete the travel expense \"Client visit Tromsø\" for James Wilson.", "expected_type": "delete_travel_expense", "lang": "en"},
    {"prompt": "Löschen Sie die Reisekostenabrechnung \"Kundentreffen Bergen\" für Hans Müller.", "expected_type": "delete_travel_expense", "lang": "de"},
    {"prompt": "Elimine el gasto de viaje \"Visita cliente Bergen\" de Carlos García.", "expected_type": "delete_travel_expense", "lang": "es"},
    {"prompt": "Supprimez la note de frais \"Réunion client Oslo\" de Camille Moreau.", "expected_type": "delete_travel_expense", "lang": "fr"},

    # ========================================================================
    # register_timesheet
    # ========================================================================
    {"prompt": "Registrer 7,5 timer for Hilde Johansen på prosjektet \"Analyse Fjordkraft\", aktivitet Design, dato 18. mars 2026.", "expected_type": "register_timesheet", "lang": "nb"},
    {"prompt": "Registrer 8 timer for Erik Larsen på prosjektet \"Skymigrering\", aktivitet Utvikling, i dag.", "expected_type": "register_timesheet", "lang": "nb"},
    {"prompt": "Register 6 hours for Michael Roberts on project \"Security Audit\", activity Testing, today.", "expected_type": "register_timesheet", "lang": "en"},
    {"prompt": "Registrieren Sie 7 Stunden für Friedrich Becker auf dem Projekt \"Systemintegration\", Aktivität Entwicklung.", "expected_type": "register_timesheet", "lang": "de"},
    {"prompt": "Registre 5 horas para Javier Hernández en el proyecto \"Implementación Dorada\", actividad Desarrollo.", "expected_type": "register_timesheet", "lang": "es"},
    {"prompt": "Registe 8 horas para Pedro Oliveira no projeto \"Transformação Digital\", atividade Implementação.", "expected_type": "register_timesheet", "lang": "pt"},
    {"prompt": "Enregistrez 6 heures pour Pierre Thomas sur le projet \"Migration Étoile\", activité Développement.", "expected_type": "register_timesheet", "lang": "fr"},

    # ========================================================================
    # run_payroll (with bonus)
    # ========================================================================
    {"prompt": "Kjør lønn for Erik Larsen (erik.larsen@example.org) for denne måneden. Grunnlønn er 49100 kr. Legg til en engangsbonus på 11200 kr i tillegg til grunnlønnen. Dersom lønns-API-et ikke fungerer, kan du bruke manuelle bilag på lønnskontoer (5000-serien) for å registrere lønnskostnaden.", "expected_type": "run_payroll", "lang": "nb"},
    {"prompt": "Kjør lønn for Tor Bakken (tor.bakken@example.org) for denne måneden. Grunnlønn er 34100 kr. Legg til en engangsbonus på 6550 kr.", "expected_type": "run_payroll", "lang": "nb"},
    {"prompt": "Run payroll for James Wilson (james.wilson@example.org) this month. Base salary 45000 NOK with a one-time bonus of 8000 NOK.", "expected_type": "run_payroll", "lang": "en"},
    {"prompt": "Führen Sie die Gehaltsabrechnung für Hans Müller (hans.mueller@example.org) durch. Grundgehalt 42000 NOK plus Einmalbonus 7500 NOK.", "expected_type": "run_payroll", "lang": "de"},
    {"prompt": "Ejecute la nómina para Carlos García (carlos.garcia@example.org) este mes. Salario base 38000 NOK con bono de 5000 NOK.", "expected_type": "run_payroll", "lang": "es"},
    {"prompt": "Execute a folha de pagamento para André Martins (andre.martins@example.org). Salário base 40000 NOK mais bónus de 6000 NOK.", "expected_type": "run_payroll", "lang": "pt"},
    {"prompt": "Exécutez la paie pour Arthur Dubois (arthur.dubois@example.org) ce mois-ci. Salaire de base 43000 NOK avec prime de 9000 NOK.", "expected_type": "run_payroll", "lang": "fr"},

    # ========================================================================
    # create_supplier_invoice (with details, with account number)
    # ========================================================================
    {"prompt": "Vi har mottatt en faktura fra leverandøren Havbris AS (org.nr 934567890) på 45000 kr inkl. MVA. Fakturanummer 2024-1234, konto 6300. Forfallsdato 15. april 2026.", "expected_type": "create_supplier_invoice", "lang": "nb"},
    {"prompt": "Registrer leverandørfaktura fra Solstrand ANS (org.nr 956789012): beløp 32000 kr inkl. MVA, fakturanr F-5678, konto 6590, forfallsdato 20. mars 2026.", "expected_type": "create_supplier_invoice", "lang": "nb"},
    {"prompt": "Register a supplier invoice from Irongate Ltd (org no. 945678901) for 28000 NOK incl. VAT. Invoice number INV-9012, account 6340, due date 10 April 2026.", "expected_type": "create_supplier_invoice", "lang": "en"},
    {"prompt": "Registrieren Sie eine Lieferantenrechnung von Lichtblick AG (Org.-Nr. 923456789) über 35000 NOK inkl. MwSt. Rechnungsnummer R-3456, Konto 6300.", "expected_type": "create_supplier_invoice", "lang": "de"},
    {"prompt": "Registre uma fatura de fornecedor de Aurora SA (org. nº 912345678) de 40000 NOK com IVA. Número da fatura F-7890, conta 6590.", "expected_type": "create_supplier_invoice", "lang": "pt"},
    {"prompt": "Enregistrez une facture fournisseur de Lumière SAS (nº org. 934567890) de 38000 NOK TTC. Numéro de facture F-1234, compte 6300.", "expected_type": "create_supplier_invoice", "lang": "fr"},

    # ========================================================================
    # create_voucher (receipt/kvittering, manual journal entry)
    # ========================================================================
    {"prompt": "Vi har en kvittering fra Clas Ohlson datert 15. mars 2026 for Oppbevaringsboks til 299 kr inkl. MVA. Bokfør utgiften på konto 6500 (kontorutstyr).", "expected_type": "create_voucher", "lang": "nb"},
    {"prompt": "Bokfør en forretningslunsj med kunde den 10. mars 2026 på restaurant Lofoten Fiskerestaurant for 1850 kr inkl. MVA. Konto 7350 (representasjon).", "expected_type": "create_voucher", "lang": "nb"},
    {"prompt": "Registrer manuelt bilag: debet konto 6860 (kontorkostnader) 5000 kr, kredit konto 1920 (bank) 5000 kr. Dato 18. mars 2026.", "expected_type": "create_voucher", "lang": "nb"},
    {"prompt": "Book a receipt from Elkjøp dated 12 March 2026 for a keyboard at 899 NOK incl. VAT. Account 6500 (office supplies).", "expected_type": "create_voucher", "lang": "en"},
    {"prompt": "Buchen Sie eine Quittung von IKEA vom 14. März 2026 für einen Bürostuhl zu 2499 NOK inkl. MwSt. Konto 6500.", "expected_type": "create_voucher", "lang": "de"},
    {"prompt": "Registre um recibo da papelaria datado de 11 de março de 2026 para material de escritório por 450 NOK com IVA. Conta 6590.", "expected_type": "create_voucher", "lang": "pt"},
    {"prompt": "Enregistrez un reçu de la librairie du 13 mars 2026 pour fournitures de bureau à 650 NOK TTC. Compte 6860.", "expected_type": "create_voucher", "lang": "fr"},

    # ========================================================================
    # delete_voucher
    # ========================================================================
    {"prompt": "Slett bilag nummer 42 fra 15. mars 2026.", "expected_type": "delete_voucher", "lang": "nb"},
    {"prompt": "Delete voucher number 42 from 15 March 2026.", "expected_type": "delete_voucher", "lang": "en"},
    {"prompt": "Löschen Sie den Beleg Nummer 42 vom 15. März 2026.", "expected_type": "delete_voucher", "lang": "de"},

    # ========================================================================
    # create_accounting_dimension (with voucher)
    # ========================================================================
    {"prompt": "Opprett en fri regnskapsdimensjon \"Prosjekttype\" med verdiene \"Forskning\" og \"Utvikling\". Bokfør deretter et bilag på konto 6590 for 10800 kr, knyttet til dimensjonsverdien \"Forskning\".", "expected_type": "create_accounting_dimension", "lang": "nb"},
    {"prompt": "Create a free accounting dimension \"Region\" with values \"North\", \"South\" and \"West\". Then post a voucher on account 7300 for 15000 NOK linked to dimension value \"North\".", "expected_type": "create_accounting_dimension", "lang": "en"},
    {"prompt": "Erstellen Sie eine freie Buchhaltungsdimension \"Kostenart\" mit den Werten \"Material\" und \"Personal\". Buchen Sie einen Beleg auf Konto 6300 für 20000 NOK mit Dimensionswert \"Material\".", "expected_type": "create_accounting_dimension", "lang": "de"},
    {"prompt": "Cree una dimensión contable libre \"Tipo de coste\" con valores \"Investigación\" y \"Desarrollo\". Registre un asiento en cuenta 6590 por 12000 NOK vinculado a \"Investigación\".", "expected_type": "create_accounting_dimension", "lang": "es"},
    {"prompt": "Crie uma dimensão contabilística livre \"Tipo de projeto\" com os valores \"Interno\" e \"Externo\". Registe um lançamento na conta 6300 por 18000 NOK ligado a \"Externo\".", "expected_type": "create_accounting_dimension", "lang": "pt"},
    {"prompt": "Créez une dimension comptable libre \"Centre de coût\" avec les valeurs \"Production\" et \"Administration\". Passez une écriture sur le compte 7300 pour 25000 NOK liée à \"Production\".", "expected_type": "create_accounting_dimension", "lang": "fr"},

    # ========================================================================
    # overdue_invoice (find overdue, post reminder fee, partial payment)
    # ========================================================================
    {"prompt": "Finn forfalte fakturaer og legg til et purregebyr på 50 kr. Bokfør gebyret på debet 1500, kredit 3400. Registrer deretter en delbetaling på 5000 kr.", "expected_type": "overdue_invoice", "lang": "nb"},
    {"prompt": "Søk etter forfalte fakturaer. Legg til purregebyr 75 kr og send påminnelse.", "expected_type": "overdue_invoice", "lang": "nb"},
    {"prompt": "Find overdue invoices and add a reminder fee of 50 NOK. Post the fee to debit 1500, credit 3400. Then register a partial payment of 8000 NOK.", "expected_type": "overdue_invoice", "lang": "en"},
    {"prompt": "Finden Sie überfällige Rechnungen und fügen Sie eine Mahngebühr von 65 NOK hinzu.", "expected_type": "overdue_invoice", "lang": "de"},
    {"prompt": "Busque facturas vencidas y agregue un cargo por recordatorio de 50 NOK.", "expected_type": "overdue_invoice", "lang": "es"},
    {"prompt": "Procure faturas vencidas e adicione uma taxa de lembrete de 50 NOK.", "expected_type": "overdue_invoice", "lang": "pt"},
    {"prompt": "Trouvez les factures impayées et ajoutez des frais de rappel de 60 NOK.", "expected_type": "overdue_invoice", "lang": "fr"},

    # ========================================================================
    # ledger_correction (find errors, fix them)
    # ========================================================================
    {"prompt": "Det er feil i hovedboka: et bilag på 15000 kr er ført på konto 6300 men skulle vært på konto 7140. Korriger feilen.", "expected_type": "ledger_correction", "lang": "nb"},
    {"prompt": "There is an error in the ledger: a voucher for 12000 NOK was posted to account 6300 but should be on 7140. Correct the error.", "expected_type": "ledger_correction", "lang": "en"},
    {"prompt": "Es gibt einen Fehler im Hauptbuch: Ein Beleg über 18000 NOK wurde auf Konto 6300 gebucht, sollte aber auf Konto 7140 stehen. Korrigieren Sie den Fehler.", "expected_type": "ledger_correction", "lang": "de"},
    {"prompt": "Hay un error en el libro mayor: un asiento de 14000 NOK se registró en la cuenta 6300 pero debería estar en la cuenta 7350. Corrija el error.", "expected_type": "ledger_correction", "lang": "es"},

    # ========================================================================
    # currency_payment (disagio/agio)
    # ========================================================================
    {"prompt": "Kunden Brightstone Ltd (org.nr 853284882) betalte en faktura på 4885 EUR. Opprinnelig kurs var 11.25, betalingskurs er 11.05. Registrer betalingen med valutadifferanse (disagio).", "expected_type": "currency_payment", "lang": "nb"},
    {"prompt": "Customer Oakfield Inc (org no. 923456789) paid an invoice of 5200 USD. Original rate was 10.50, payment rate is 10.75. Register payment with exchange rate difference (agio).", "expected_type": "currency_payment", "lang": "en"},
    {"prompt": "Der Kunde Steinadler AG (Org.-Nr. 912345678) hat eine Rechnung über 3800 EUR bezahlt. Originalkurs 11.30, Zahlungskurs 11.10. Registrieren Sie die Zahlung mit Wechselkursdifferenz (Disagio).", "expected_type": "currency_payment", "lang": "de"},
    {"prompt": "O cliente Aurora SA (org. nº 912345678) pagou uma fatura de 6000 EUR. Taxa original 11.20, taxa de pagamento 11.40. Registre o pagamento com diferença cambial (ágio).", "expected_type": "currency_payment", "lang": "pt"},
    {"prompt": "Le client Étoile SARL (nº org. 964531161) a payé une facture de 4500 EUR. Taux initial 11.15, taux de paiement 10.95. Enregistrez le paiement avec la différence de change (perte de change).", "expected_type": "currency_payment", "lang": "fr"},

    # ========================================================================
    # year_end_closing (annual, month-end)
    # ========================================================================
    {"prompt": "Utfør månedsslutt for mars 2026. Avskriv kontorutstyr (kostpris 120000 kr, 5 år, konto 1250) og IT-utstyr (kostpris 80000 kr, 3 år, konto 1210). Avskrivningskonto 6010. Avsett også 50000 kr i påløpt lønn (debet 5000, kredit 2900).", "expected_type": "year_end_closing", "lang": "nb"},
    {"prompt": "Perform year-end closing for 2025. Depreciate office equipment (cost 150000 NOK, 5 years, account 1250). Post closing entries for accrued salaries of 60000 NOK (debit 5000, credit 2900).", "expected_type": "year_end_closing", "lang": "en"},
    {"prompt": "Führen Sie den Monatsabschluss für Februar 2026 durch. Abschreibung Büromöbel (Anschaffungskosten 100000 NOK, 5 Jahre, Konto 1250), Abschreibungskonto 6010.", "expected_type": "year_end_closing", "lang": "de"},
    {"prompt": "Realize el cierre de fin de año 2025. Amortice el equipo informático (coste 200000 NOK, 3 años, cuenta 1210).", "expected_type": "year_end_closing", "lang": "es"},
    {"prompt": "Efectuez la clôture annuelle 2025. Amortissez le matériel informatique (coût 180000 NOK, 4 ans, compte 1210). Compte d'amortissement 6010.", "expected_type": "year_end_closing", "lang": "fr"},

    # ========================================================================
    # bank_reconciliation
    # ========================================================================
    {"prompt": "Utfør bankavstemming for mars 2026.", "expected_type": "bank_reconciliation", "lang": "nb"},
    {"prompt": "Perform bank reconciliation for March 2026.", "expected_type": "bank_reconciliation", "lang": "en"},
    {"prompt": "Führen Sie die Bankabstimmung für März 2026 durch.", "expected_type": "bank_reconciliation", "lang": "de"},

    # ========================================================================
    # full_project_cycle (complete lifecycle)
    # ========================================================================
    {"prompt": "Opprett prosjektet \"IT-oppgradering\" for Nordlys AS (org.nr 912345678) med budsjett 500000 kr. Prosjektleder er Magnus Haugen (magnus.haugen@example.org). Registrer 20 timer for Erik Larsen (erik.larsen@example.org) på Utvikling. Registrer leverandørkostnad fra Havbris AS (org.nr 934567890) på 45000 kr (konto 4300). Fakturer kunden 120000 kr og send fakturaen.", "expected_type": "full_project_cycle", "lang": "nb"},
    {"prompt": "Complete project cycle: Create project \"ERP Integration\" for Brightstone Ltd (org no. 853284882) with budget 400000 NOK. Manager: David Mitchell (david.mitchell@example.org). Register 15 hours for Sarah Thompson on Testing. Register supplier cost from Irongate Ltd of 35000 NOK (account 4300). Invoice client 100000 NOK.", "expected_type": "full_project_cycle", "lang": "en"},
    {"prompt": "Cycle complet du projet : Créez le projet \"Transformation digitale\" pour Colline SARL (nº org. 894562234) avec un budget de 600000 NOK. Chef de projet : Louis Laurent (louis.laurent@example.org). Enregistrez 25 heures pour Pierre Thomas sur Développement. Coût fournisseur de Lumière SAS : 50000 NOK (compte 4300). Facturez 150000 NOK au client.", "expected_type": "full_project_cycle", "lang": "fr"},

    # ========================================================================
    # cost_analysis (analyze ledger, create projects)
    # ========================================================================
    {"prompt": "Analyser hovedboka for januar-februar 2026. Finn de 3 kontiene med størst økning i kostnader. Opprett et prosjekt for hver konto for å spore fremtidige kostnader.", "expected_type": "cost_analysis", "lang": "nb"},
    {"prompt": "Analyze the ledger for Q1 2026. Find the top 3 expense accounts with the highest spending. Create a project for each to track costs.", "expected_type": "cost_analysis", "lang": "en"},
    {"prompt": "Analysieren Sie das Hauptbuch für Januar-März 2026. Finden Sie die 3 Konten mit den höchsten Kosten.", "expected_type": "cost_analysis", "lang": "de"},
    {"prompt": "Analysez le grand livre pour janvier-février 2026. Trouvez les 3 comptes avec les dépenses les plus élevées. Créez un projet pour chacun.", "expected_type": "cost_analysis", "lang": "fr"},

    # ========================================================================
    # enable_module
    # ========================================================================
    {"prompt": "Aktiver prosjektmodulen i Tripletex.", "expected_type": "enable_module", "lang": "nb"},
    {"prompt": "Enable the project module in Tripletex.", "expected_type": "enable_module", "lang": "en"},
    {"prompt": "Aktivieren Sie das Reisekostenmodul in Tripletex.", "expected_type": "enable_module", "lang": "de"},
    {"prompt": "Active el módulo de gastos de viaje en Tripletex.", "expected_type": "enable_module", "lang": "es"},
]


# ---------------------------------------------------------------------------
# Variation templates per task type
# Each template is a function that takes random params and returns a prompt dict
# ---------------------------------------------------------------------------

def _vary_create_employee(lang: str) -> dict:
    first, last = rand_name(lang)
    email = rand_email(first, last)
    is_admin = random.choice([True, False])
    templates = {
        "nb": [
            f"Opprett en ny ansatt, {first} {last}, med e-post {email}." + (" Gi vedkommende administratorrolle." if is_admin else ""),
            f"Registrer ny medarbeider {first} {last} ({email}). Startdato 1. mars 2026." + (" Administrator." if is_admin else ""),
        ],
        "nn": [
            f"Opprett ein ny tilsett, {first} {last} ({email})." + (" Vedkomande skal vere administrator." if is_admin else ""),
        ],
        "en": [
            f"Create a new employee {first} {last} ({email})." + (" Give them administrator access." if is_admin else ""),
            f"Register new employee {first} {last} with email {email}." + (" Admin role required." if is_admin else ""),
        ],
        "de": [
            f"Erstellen Sie einen neuen Mitarbeiter {first} {last} ({email})." + (" Administratorrechte erteilen." if is_admin else ""),
        ],
        "es": [
            f"Cree un nuevo empleado {first} {last} ({email})." + (" Con rol de administrador." if is_admin else ""),
        ],
        "pt": [
            f"Crie um novo funcionário {first} {last} ({email})." + (" Com acesso de administrador." if is_admin else ""),
        ],
        "fr": [
            f"Créez un nouvel employé {first} {last} ({email})." + (" Avec les droits d'administrateur." if is_admin else ""),
        ],
    }
    prompt = random.choice(templates.get(lang, templates["nb"]))
    return {"prompt": prompt, "expected_type": "create_employee", "lang": lang}


def _vary_update_employee(lang: str) -> dict:
    first, last = rand_name(lang)
    new_email = f"{first.lower()}.ny@example.org"
    phone = f"+47 9{random.randint(1000000, 9999999)}"
    templates = {
        "nb": [f"Oppdater e-posten til {first} {last} til {new_email}.", f"Endre telefonnummeret til {first} {last} til {phone}."],
        "nn": [f"Oppdater e-postadressa til {first} {last} til {new_email}."],
        "en": [f"Update the email for {first} {last} to {new_email}.", f"Change {first} {last}'s phone number to {phone}."],
        "de": [f"Aktualisieren Sie die E-Mail von {first} {last} auf {new_email}."],
        "es": [f"Actualice el correo de {first} {last} a {new_email}."],
        "pt": [f"Atualize o e-mail de {first} {last} para {new_email}."],
        "fr": [f"Mettez à jour l'e-mail de {first} {last} à {new_email}."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "update_employee", "lang": lang}


def _vary_create_customer(lang: str) -> dict:
    company = rand_company(lang)
    org = rand_org()
    street = rand_street()
    postal, city = rand_city()
    is_supplier = random.choice([False, False, True])  # 1/3 chance supplier
    email = f"post@{company.split()[0].lower().replace('é','e').replace('ü','u').replace('ø','o')}.no"
    templates = {
        "nb": [
            f"Opprett kunden {company} med organisasjonsnummer {org} og e-post {email}.",
            f"Legg inn {company} (org.nr {org}) som ny kunde. Adresse: {street}, {postal} {city}.",
            f"Registrer {company} som leverandør med organisasjonsnummer {org}." if is_supplier else f"Opprett {company} (org.nr {org}) som kunde med e-post {email}.",
        ],
        "nn": [f"Opprett kunden {company} med org.nr {org}. E-post: {email}."],
        "en": [
            f"Create the customer {company} with organization number {org}. Address: {street}, {postal} {city}. Email: {email}.",
            f"Register {company} (org no. {org}) as a supplier." if is_supplier else f"Create customer {company} with org number {org}.",
        ],
        "de": [
            f"Erstellen Sie den Kunden {company} mit Organisationsnummer {org}. Adresse: {street}, {postal} {city}. E-Mail: {email}.",
            f"Registrieren Sie {company} (Org.-Nr. {org}) als Lieferant." if is_supplier else f"Kunden {company} anlegen (Org.-Nr. {org}).",
        ],
        "es": [
            f"Crea el cliente {company} con número de organización {org}. Dirección: {street}, {postal} {city}. Correo: {email}.",
            f"Registra {company} como proveedor con org. nº {org}." if is_supplier else f"Crea el cliente {company} (org. nº {org}).",
        ],
        "pt": [
            f"Crie o cliente {company} com número de organização {org}. Endereço: {street}, {postal} {city}. E-mail: {email}.",
            f"Registar {company} como fornecedor com org. nº {org}." if is_supplier else f"Crie o cliente {company} (org. nº {org}).",
        ],
        "fr": [
            f"Créez le client {company} avec le numéro d'organisation {org}. Adresse : {street}, {postal} {city}. E-mail : {email}.",
            f"Enregistrez {company} (nº org. {org}) comme fournisseur." if is_supplier else f"Créez le client {company} (nº org. {org}).",
        ],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "create_customer", "lang": lang}


def _vary_update_customer(lang: str) -> dict:
    company = rand_company(lang)
    new_email = f"ny@{company.split()[0].lower().replace('é','e').replace('ü','u').replace('ø','o')}.no"
    templates = {
        "nb": [f"Oppdater e-postadressen til {company} til {new_email}."],
        "nn": [f"Oppdater e-postadressa til {company} til {new_email}."],
        "en": [f"Update the email for {company} to {new_email}."],
        "de": [f"Aktualisieren Sie die E-Mail von {company} auf {new_email}."],
        "es": [f"Actualice el correo de {company} a {new_email}."],
        "pt": [f"Atualize o e-mail de {company} para {new_email}."],
        "fr": [f"Mettez à jour l'e-mail de {company} à {new_email}."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "update_customer", "lang": lang}


def _vary_create_product(lang: str) -> dict:
    product = rand_product(lang)
    number = rand_product_number()
    price = rand_amount(500, 50000)
    vat_choice = random.choice([(25, "25%"), (15, "15%"), (12, "12%"), (0, "0%")])
    vat_pct, vat_label = vat_choice
    templates = {
        "nb": [
            f"Opprett produktet \"{product}\" med produktnummer {number} og pris {price} kr ekskl. MVA ({vat_label} MVA).",
            f"Legg inn produkt \"{product}\" (nr {number}, {price} kr, {vat_label} MVA).",
        ],
        "nn": [f"Opprett produktet \"{product}\" med nummer {number}, pris {price} kr ({vat_label} MVA)."],
        "en": [f"Create product \"{product}\" with number {number}, price {price} NOK excl. VAT ({vat_label} VAT)."],
        "de": [f"Erstellen Sie das Produkt \"{product}\" mit Nummer {number}, Preis {price} NOK ohne MwSt ({vat_label})."],
        "es": [f"Cree el producto \"{product}\" con número {number}, precio {price} NOK sin IVA ({vat_label})."],
        "pt": [f"Crie o produto \"{product}\" com número {number}, preço {price} NOK sem IVA ({vat_label})."],
        "fr": [f"Créez le produit \"{product}\" avec le numéro {number}, prix {price} NOK HT ({vat_label} TVA)."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "create_product", "lang": lang}


def _vary_update_product(lang: str) -> dict:
    product = rand_product(lang)
    new_price = rand_amount(500, 50000)
    templates = {
        "nb": [f"Oppdater prisen på \"{product}\" til {new_price} kr ekskl. MVA."],
        "en": [f"Update the price of \"{product}\" to {new_price} NOK."],
        "de": [f"Aktualisieren Sie den Preis von \"{product}\" auf {new_price} NOK."],
        "es": [f"Actualice el precio de \"{product}\" a {new_price} NOK."],
        "pt": [f"Atualize o preço de \"{product}\" para {new_price} NOK."],
        "fr": [f"Mettez à jour le prix de \"{product}\" à {new_price} NOK."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "update_product", "lang": lang}


def _vary_create_department(lang: str) -> dict:
    dept_names_pool = {
        "nb": ["Utvikling", "Drift", "HR", "Salg", "Markedsføring", "Økonomi", "Juridisk", "Kundeservice"],
        "en": ["Development", "Operations", "HR", "Sales", "Marketing", "Finance", "Legal"],
        "de": ["Entwicklung", "Betrieb", "Vertrieb", "Marketing", "Finanzen"],
        "es": ["Desarrollo", "Operaciones", "Ventas", "Marketing", "Finanzas"],
        "pt": ["Desenvolvimento", "Operações", "Vendas", "Marketing", "Finanças"],
        "fr": ["Développement", "Opérations", "Ventes", "Marketing", "Finances"],
    }
    pool = dept_names_pool.get(lang, dept_names_pool["nb"])
    dept = random.choice(pool)
    num = random.randint(100, 999)
    templates = {
        "nb": [f"Opprett avdelingen \"{dept}\" med avdelingsnummer {num}."],
        "nn": [f"Opprett avdelinga \"{dept}\" med avdelingsnummer {num}."],
        "en": [f"Create department \"{dept}\" with number {num}."],
        "de": [f"Erstellen Sie die Abteilung \"{dept}\" mit Nummer {num}."],
        "es": [f"Cree el departamento \"{dept}\" con número {num}."],
        "pt": [f"Crie o departamento \"{dept}\" com número {num}."],
        "fr": [f"Créez le département \"{dept}\" avec le numéro {num}."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "create_department", "lang": lang}


def _vary_update_department(lang: str) -> dict:
    dept_old = random.choice(["Utvikling", "Drift", "HR", "Salg"])
    dept_new = random.choice(["Produktutvikling", "IT-drift", "Personal", "Forretningsutvikling"])
    templates = {
        "nb": [f"Endre navnet på avdelingen \"{dept_old}\" til \"{dept_new}\"."],
        "en": [f"Rename department \"{dept_old}\" to \"{dept_new}\"."],
        "de": [f"Benennen Sie die Abteilung \"{dept_old}\" in \"{dept_new}\" um."],
        "es": [f"Cambie el nombre del departamento \"{dept_old}\" a \"{dept_new}\"."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "update_department", "lang": lang}


def _vary_create_invoice(lang: str) -> dict:
    company = rand_company(lang)
    org = rand_org()
    product = rand_product(lang)
    amount = rand_amount(5000, 80000)
    num = rand_product_number()
    register_pay = random.choice([True, False])
    templates = {
        "nb": [
            f"Opprett og send en faktura til kunden {company} (org.nr {org}) på {amount} kr ekskl. MVA. Fakturaen gjelder {product}." + (f" Registrer også full betaling." if register_pay else ""),
            f"Lag en faktura til {company} (org.nr {org}) for {product} ({num}) til {amount} kr med 25 % MVA." + (f" Registrer betaling." if register_pay else ""),
        ],
        "nn": [f"Opprett ein faktura til {company} (org.nr {org}) for {product} til {amount} kr."],
        "en": [
            f"Create and send an invoice to {company} (org no. {org}) for {amount} NOK excl. VAT. Invoice for {product}." + (" Register full payment." if register_pay else ""),
        ],
        "de": [
            f"Erstellen Sie eine Rechnung für {company} (Org.-Nr. {org}) über {amount} NOK für {product}." + (" Registrieren Sie die vollständige Zahlung." if register_pay else ""),
        ],
        "es": [
            f"Crea una factura para {company} (org. nº {org}) por {amount} NOK sin IVA. Factura por {product}." + (" Registre el pago completo." if register_pay else ""),
        ],
        "pt": [
            f"Crie e envie uma fatura para {company} (org. nº {org}) de {amount} NOK sem IVA. Fatura referente a {product}." + (" Registar pagamento." if register_pay else ""),
        ],
        "fr": [
            f"Créez une facture pour {company} (nº org. {org}) de {amount} NOK HT. Facture pour {product}." + (" Enregistrez le paiement." if register_pay else ""),
        ],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "create_invoice", "lang": lang}


def _vary_register_payment(lang: str) -> dict:
    company = rand_company(lang)
    org = rand_org()
    amount = rand_amount(5000, 60000)
    product = rand_product(lang)
    templates = {
        "nb": [
            f"Kunden {company} (org.nr {org}) har en utestående faktura på {amount} kr eksklusiv MVA for \"{product}\". Registrer full betaling.",
            f"Registrer betaling fra {company} for faktura på {amount} kr.",
        ],
        "nn": [f"Registrer betaling frå {company} (org.nr {org}) på {amount} kr for \"{product}\"."],
        "en": [f"Register full payment on the outstanding invoice for {company} (org no. {org}) for {amount} NOK. Invoice for \"{product}\"."],
        "de": [f"Registrieren Sie die vollständige Zahlung für die Rechnung von {company} (Org.-Nr. {org}) über {amount} NOK."],
        "es": [f"Registre el pago completo de la factura de {company} (org. nº {org}) por {amount} NOK."],
        "pt": [f"Registar o pagamento total da fatura de {company} (org. nº {org}) de {amount} NOK."],
        "fr": [f"Enregistrez le paiement intégral de la facture de {company} (nº org. {org}) de {amount} NOK HT pour \"{product}\"."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "register_payment", "lang": lang}


def _vary_reverse_payment(lang: str) -> dict:
    company = rand_company(lang)
    amount = rand_amount(5000, 50000)
    product = rand_product(lang)
    templates = {
        "nb": [f"Betalingen fra {company} på {amount} kr for \"{product}\" er blitt returnert av banken. Reverser betalingen."],
        "en": [f"The payment of {amount} NOK from {company} for \"{product}\" has been returned by the bank. Reverse the payment."],
        "de": [f"Die Zahlung von {amount} NOK von {company} für \"{product}\" wurde von der Bank zurückgebucht. Stornieren Sie die Zahlung."],
        "es": [f"El pago de {amount} NOK de {company} por \"{product}\" ha sido devolvido por el banco. Revierta el pago."],
        "pt": [f"O pagamento de {amount} NOK de {company} referente a \"{product}\" foi devolvido pelo banco. Reverta o pagamento."],
        "fr": [f"Le paiement de {amount} NOK de {company} pour \"{product}\" a été retourné par la banque. Annulez le paiement."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "reverse_payment", "lang": lang}


def _vary_create_credit_note(lang: str) -> dict:
    company = rand_company(lang)
    org = rand_org()
    amount = rand_amount(5000, 50000)
    product = rand_product(lang)
    templates = {
        "nb": [f"Kunden {company} (org.nr {org}) har reklamert på fakturaen for \"{product}\" ({amount} kr ekskl. MVA). Opprett en fullstendig kreditnota."],
        "en": [f"The customer {company} (org no. {org}) has complained about the invoice for \"{product}\" ({amount} NOK excl. VAT). Issue a full credit note."],
        "de": [f"Der Kunde {company} (Org.-Nr. {org}) hat die Rechnung für \"{product}\" ({amount} NOK) reklamiert. Erstellen Sie eine Gutschrift."],
        "es": [f"El cliente {company} (org. nº {org}) ha reclamado sobre la factura de \"{product}\" ({amount} NOK sin IVA). Emita una nota de crédito completa."],
        "pt": [f"O cliente {company} (org. nº {org}) reclamou sobre a fatura referente a \"{product}\" ({amount} NOK sem IVA). Emita uma nota de crédito completa."],
        "fr": [f"Le client {company} (nº org. {org}) a contesté la facture pour \"{product}\" ({amount} NOK HT). Émettez un avoir complet."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "create_credit_note", "lang": lang}


def _vary_project_invoice(lang: str) -> dict:
    company = rand_company(lang)
    org = rand_org()
    project = rand_project(lang)
    first, last = rand_name(lang)
    email = rand_email(first, last)
    fixed_price = random.choice([178450, 250000, 362300, 365350, 420000, 500000])
    pct = random.choice([25, 33, 40, 50, 60, 75])
    templates = {
        "nb": [f"Sett fastpris {fixed_price} kr på prosjektet \"{project}\" for {company} (org.nr {org}). Prosjektleder er {first} {last} ({email}). Fakturer kunden for {pct} % av fastprisen som en delbetaling."],
        "en": [f"Set a fixed price of {fixed_price} NOK on project \"{project}\" for {company} (org no. {org}). Project manager is {first} {last} ({email}). Invoice the client for {pct}% as a milestone payment."],
        "de": [f"Setzen Sie einen Festpreis von {fixed_price} NOK für Projekt \"{project}\" für {company} (Org.-Nr. {org}). Projektleiter: {first} {last} ({email}). Fakturieren Sie {pct}%."],
        "es": [f"Fije un precio fijo de {fixed_price} NOK en el proyecto \"{project}\" para {company} (org. nº {org}). Director: {first} {last} ({email}). Facture {pct}%."],
        "pt": [f"Defina um preço fixo de {fixed_price} NOK no projeto \"{project}\" para {company} (org. nº {org}). Gestor: {first} {last} ({email}). Fature {pct}%."],
        "fr": [f"Fixez un prix forfaitaire de {fixed_price} NOK sur le projet \"{project}\" pour {company} (nº org. {org}). Chef de projet : {first} {last} ({email}). Facturez {pct}%."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "project_invoice", "lang": lang}


def _vary_create_project(lang: str) -> dict:
    company = rand_company(lang)
    org = rand_org()
    project = rand_project(lang)
    first, last = rand_name(lang)
    email = rand_email(first, last)
    templates = {
        "nb": [f"Opprett prosjektet \"{project}\" knyttet til kunden {company} (org.nr {org}). Prosjektleder er {first} {last} ({email})."],
        "nn": [f"Opprett prosjektet \"{project}\" for {company} (org.nr {org}). Prosjektleiar: {first} {last} ({email})."],
        "en": [f"Create project \"{project}\" for {company} (org no. {org}). Project manager is {first} {last} ({email})."],
        "de": [f"Erstellen Sie das Projekt \"{project}\" für {company} (Org.-Nr. {org}). Projektleiter: {first} {last} ({email})."],
        "es": [f"Crea el proyecto \"{project}\" vinculado al cliente {company} (org. nº {org}). Director: {first} {last} ({email})."],
        "pt": [f"Crie o projeto \"{project}\" para {company} (org. nº {org}). Gestor: {first} {last} ({email})."],
        "fr": [f"Créez le projet \"{project}\" lié au client {company} (nº org. {org}). Chef de projet : {first} {last} ({email})."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "create_project", "lang": lang}


def _vary_update_project(lang: str) -> dict:
    project = rand_project(lang)
    templates = {
        "nb": [f"Oppdater sluttdatoen for prosjektet \"{project}\" til 30. juni 2026.", f"Avslutt prosjektet \"{project}\" — marker det som lukket."],
        "en": [f"Update the end date for project \"{project}\" to 30 September 2026.", f"Close project \"{project}\" — mark it as completed."],
        "de": [f"Aktualisieren Sie das Enddatum für Projekt \"{project}\" auf 30. Juni 2026."],
        "es": [f"Actualice la fecha de fin del proyecto \"{project}\" al 30 de junio de 2026."],
        "pt": [f"Atualize a data de fim do projeto \"{project}\" para 30 de junho de 2026."],
        "fr": [f"Mettez à jour la date de fin du projet \"{project}\" au 30 juin 2026."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "update_project", "lang": lang}


def _vary_create_travel_expense(lang: str) -> dict:
    first, last = rand_name(lang)
    email = rand_email(first, last)
    days = random.randint(2, 7)
    flight = rand_amount(2000, 9000)
    taxi = rand_amount(150, 800)
    destinations = ["Bergen", "Trondheim", "Tromsø", "Stavanger", "Oslo", "Stockholm", "København"]
    dest = random.choice(destinations)
    templates = {
        "nb": [f"Registrer en reiseregning for {first} {last} for \"Kundemøte {dest}\". Reisen varte {days} dager med diett (800 kr/dag). Utgifter: flybillett {flight} kr og taxi {taxi} kr."],
        "en": [f"Register a travel expense for {first} {last} ({email}) for \"Client visit {dest}\". {days} days with per diem (800 NOK/day). Expenses: flight {flight} NOK and taxi {taxi} NOK."],
        "de": [f"Erstellen Sie eine Reisekostenabrechnung für {first} {last} für \"Kundentreffen {dest}\". {days} Tage mit Tagegeld (800 NOK/Tag). Ausgaben: Flug {flight} NOK und Taxi {taxi} NOK."],
        "es": [f"Registre un gasto de viaje para {first} {last} por \"Visita cliente {dest}\". {days} días con viáticos (800 NOK/día). Gastos: vuelo {flight} NOK y taxi {taxi} NOK."],
        "pt": [f"Registe uma despesa de viagem para {first} {last} ({email}) referente a \"Visita cliente {dest}\". {days} dias com ajudas de custo (800 NOK/dia). Despesas: bilhete de avião {flight} NOK e táxi {taxi} NOK."],
        "fr": [f"Enregistrez une note de frais pour {first} {last} pour \"Réunion client {dest}\". {days} jours avec indemnité journalière (800 NOK/jour). Frais : vol {flight} NOK et taxi {taxi} NOK."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "create_travel_expense", "lang": lang}


def _vary_delete_travel_expense(lang: str) -> dict:
    first, last = rand_name(lang)
    dest = random.choice(["Bergen", "Trondheim", "Tromsø", "Oslo", "Stockholm"])
    templates = {
        "nb": [f"Slett reiseregningen \"Kundemøte {dest}\" for {first} {last}."],
        "en": [f"Delete the travel expense \"Client visit {dest}\" for {first} {last}."],
        "de": [f"Löschen Sie die Reisekostenabrechnung \"Kundentreffen {dest}\" für {first} {last}."],
        "es": [f"Elimine el gasto de viaje \"Visita {dest}\" de {first} {last}."],
        "pt": [f"Eliminar a despesa de viagem \"Visita {dest}\" de {first} {last}."],
        "fr": [f"Supprimez la note de frais \"Réunion {dest}\" de {first} {last}."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "delete_travel_expense", "lang": lang}


def _vary_register_timesheet(lang: str) -> dict:
    first, last = rand_name(lang)
    hours = random.choice([4, 5, 6, 7, 7.5, 8])
    project = rand_project(lang)
    activity = random.choice(ACTIVITIES)
    templates = {
        "nb": [f"Registrer {hours} timer for {first} {last} på prosjektet \"{project}\", aktivitet {activity}."],
        "en": [f"Register {hours} hours for {first} {last} on project \"{project}\", activity {activity}."],
        "de": [f"Registrieren Sie {hours} Stunden für {first} {last} auf Projekt \"{project}\", Aktivität {activity}."],
        "es": [f"Registre {hours} horas para {first} {last} en el proyecto \"{project}\", actividad {activity}."],
        "pt": [f"Registe {hours} horas para {first} {last} no projeto \"{project}\", atividade {activity}."],
        "fr": [f"Enregistrez {hours} heures pour {first} {last} sur le projet \"{project}\", activité {activity}."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "register_timesheet", "lang": lang}


def _vary_run_payroll(lang: str) -> dict:
    first, last = rand_name(lang)
    email = rand_email(first, last)
    salary = rand_salary()
    bonus = rand_bonus()
    templates = {
        "nb": [f"Kjør lønn for {first} {last} ({email}) for denne måneden. Grunnlønn er {salary} kr. Legg til en engangsbonus på {bonus} kr."],
        "en": [f"Run payroll for {first} {last} ({email}) this month. Base salary {salary} NOK with a one-time bonus of {bonus} NOK."],
        "de": [f"Führen Sie die Gehaltsabrechnung für {first} {last} ({email}) durch. Grundgehalt {salary} NOK plus Einmalbonus {bonus} NOK."],
        "es": [f"Ejecute la nómina para {first} {last} ({email}) este mes. Salario base {salary} NOK con bono de {bonus} NOK."],
        "pt": [f"Execute a folha de pagamento para {first} {last} ({email}). Salário base {salary} NOK mais bónus de {bonus} NOK."],
        "fr": [f"Exécutez la paie pour {first} {last} ({email}) ce mois-ci. Salaire de base {salary} NOK avec prime de {bonus} NOK."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "run_payroll", "lang": lang}


def _vary_create_supplier_invoice(lang: str) -> dict:
    company = rand_company(lang)
    org = rand_org()
    amount = rand_amount(10000, 80000)
    inv_no = f"F-{random.randint(1000, 9999)}"
    account = random.choice(EXPENSE_ACCOUNTS[:4])
    templates = {
        "nb": [f"Vi har mottatt en faktura fra leverandøren {company} (org.nr {org}) på {amount} kr inkl. MVA. Fakturanummer {inv_no}, konto {account}."],
        "en": [f"Register a supplier invoice from {company} (org no. {org}) for {amount} NOK incl. VAT. Invoice number {inv_no}, account {account}."],
        "de": [f"Registrieren Sie eine Lieferantenrechnung von {company} (Org.-Nr. {org}) über {amount} NOK inkl. MwSt. Rechnungsnummer {inv_no}, Konto {account}."],
        "es": [f"Registre una factura de proveedor de {company} (org. nº {org}) por {amount} NOK con IVA. Número de factura {inv_no}, cuenta {account}."],
        "pt": [f"Registar uma fatura de fornecedor de {company} (org. nº {org}) de {amount} NOK com IVA. Número da fatura {inv_no}, conta {account}."],
        "fr": [f"Enregistrez une facture fournisseur de {company} (nº org. {org}) de {amount} NOK TTC. Numéro de facture {inv_no}, compte {account}."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "create_supplier_invoice", "lang": lang}


def _vary_create_voucher(lang: str) -> dict:
    amount = rand_amount(200, 5000)
    account = random.choice(["6500", "6590", "6860", "7140", "7350"])
    desc_map = {
        "6500": {"nb": "kontorutstyr", "en": "office supplies", "de": "Büroausstattung", "es": "material de oficina", "pt": "material de escritório", "fr": "fournitures de bureau"},
        "6590": {"nb": "driftsmateriale", "en": "operating supplies", "de": "Betriebsmaterial", "es": "material operativo", "pt": "material operacional", "fr": "fournitures opérationnelles"},
        "6860": {"nb": "kontorkostnader", "en": "office expenses", "de": "Bürokosten", "es": "gastos de oficina", "pt": "custos de escritório", "fr": "frais de bureau"},
        "7140": {"nb": "reisekostnad", "en": "travel expense", "de": "Reisekosten", "es": "gastos de viaje", "pt": "custos de viagem", "fr": "frais de déplacement"},
        "7350": {"nb": "representasjon", "en": "representation", "de": "Bewirtung", "es": "representación", "pt": "representação", "fr": "représentation"},
    }
    desc = desc_map.get(account, desc_map["6500"]).get(lang, desc_map["6500"]["nb"])
    templates = {
        "nb": [
            f"Vi har en kvittering for {desc} på {amount} kr inkl. MVA. Bokfør utgiften på konto {account}.",
            f"Registrer manuelt bilag: debet konto {account} ({desc}), kredit konto 1920 (bank). Beløp {amount} kr.",
        ],
        "nn": [f"Vi har ein kvittering for {desc} på {amount} kr inkl. MVA. Bokfør på konto {account}."],
        "en": [f"Book a receipt for {desc} at {amount} NOK incl. VAT. Account {account}."],
        "de": [f"Buchen Sie eine Quittung für {desc} über {amount} NOK inkl. MwSt. Konto {account}."],
        "es": [f"Registre un recibo de {desc} por {amount} NOK con IVA. Cuenta {account}."],
        "pt": [f"Registe um recibo de {desc} por {amount} NOK com IVA. Conta {account}."],
        "fr": [f"Enregistrez un reçu pour {desc} de {amount} NOK TTC. Compte {account}."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "create_voucher", "lang": lang}


def _vary_delete_voucher(lang: str) -> dict:
    v_num = random.randint(10, 200)
    templates = {
        "nb": [f"Slett bilag nummer {v_num} fra mars 2026."],
        "en": [f"Delete voucher number {v_num} from March 2026."],
        "de": [f"Löschen Sie den Beleg Nummer {v_num} vom März 2026."],
        "es": [f"Elimine el comprobante número {v_num} de marzo 2026."],
        "pt": [f"Eliminar o voucher número {v_num} de março de 2026."],
        "fr": [f"Supprimez le justificatif numéro {v_num} de mars 2026."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "delete_voucher", "lang": lang}


def _vary_create_accounting_dimension(lang: str) -> dict:
    dim_name = random.choice(["Kostnadssted", "Prosjekttype", "Region", "Avdeling", "Segment"])
    val1 = random.choice(["Forskning", "Intern", "Nord", "Produksjon", "Material"])
    val2 = random.choice(["Utvikling", "Ekstern", "Sør", "Administrasjon", "Personal"])
    account = random.choice(["6300", "6590", "7300"])
    amount = rand_amount(5000, 30000)
    templates = {
        "nb": [f"Opprett en fri regnskapsdimensjon \"{dim_name}\" med verdiene \"{val1}\" og \"{val2}\". Bokfør et bilag på konto {account} for {amount} kr, knyttet til \"{val1}\"."],
        "en": [f"Create a free accounting dimension \"{dim_name}\" with values \"{val1}\" and \"{val2}\". Post a voucher on account {account} for {amount} NOK linked to \"{val1}\"."],
        "de": [f"Erstellen Sie eine freie Buchhaltungsdimension \"{dim_name}\" mit Werten \"{val1}\" und \"{val2}\". Buchen Sie auf Konto {account} für {amount} NOK mit Wert \"{val1}\"."],
        "es": [f"Cree una dimensión contable \"{dim_name}\" con valores \"{val1}\" y \"{val2}\". Registre un asiento en cuenta {account} por {amount} NOK vinculado a \"{val1}\"."],
        "pt": [f"Crie uma dimensão contabilística \"{dim_name}\" com valores \"{val1}\" e \"{val2}\". Registe na conta {account} por {amount} NOK ligado a \"{val1}\"."],
        "fr": [f"Créez une dimension comptable \"{dim_name}\" avec les valeurs \"{val1}\" et \"{val2}\". Écriture sur compte {account} pour {amount} NOK liée à \"{val1}\"."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "create_accounting_dimension", "lang": lang}


def _vary_overdue_invoice(lang: str) -> dict:
    fee = random.choice([50, 65, 75, 100])
    partial = rand_amount(2000, 15000)
    templates = {
        "nb": [
            f"Finn forfalte fakturaer og legg til et purregebyr på {fee} kr. Bokfør debet 1500, kredit 3400. Registrer delbetaling {partial} kr.",
            f"Søk etter forfalte fakturaer. Legg til purregebyr {fee} kr og send påminnelse.",
        ],
        "en": [f"Find overdue invoices and add a reminder fee of {fee} NOK. Register partial payment of {partial} NOK."],
        "de": [f"Finden Sie überfällige Rechnungen und fügen Sie eine Mahngebühr von {fee} NOK hinzu."],
        "es": [f"Busque facturas vencidas y agregue un cargo por recordatorio de {fee} NOK."],
        "pt": [f"Procure faturas vencidas e adicione uma taxa de lembrete de {fee} NOK."],
        "fr": [f"Trouvez les factures impayées et ajoutez des frais de rappel de {fee} NOK."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "overdue_invoice", "lang": lang}


def _vary_ledger_correction(lang: str) -> dict:
    amount = rand_amount(5000, 30000)
    wrong_acc = random.choice(["6300", "6500", "6590"])
    right_acc = random.choice(["7140", "7350", "6860"])
    templates = {
        "nb": [f"Det er feil i hovedboka: et bilag på {amount} kr er ført på konto {wrong_acc} men skulle vært på konto {right_acc}. Korriger feilen."],
        "en": [f"There is an error in the ledger: a voucher for {amount} NOK was posted to account {wrong_acc} but should be on {right_acc}. Correct it."],
        "de": [f"Fehler im Hauptbuch: Ein Beleg über {amount} NOK auf Konto {wrong_acc} sollte auf {right_acc} stehen. Korrigieren Sie."],
        "es": [f"Error en el libro mayor: un asiento de {amount} NOK en cuenta {wrong_acc} debería estar en {right_acc}. Corrija."],
        "pt": [f"Erro no razão: um lançamento de {amount} NOK na conta {wrong_acc} deveria estar na conta {right_acc}. Corrija."],
        "fr": [f"Erreur dans le grand livre : une écriture de {amount} NOK sur le compte {wrong_acc} devrait être sur {right_acc}. Corrigez."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "ledger_correction", "lang": lang}


def _vary_currency_payment(lang: str) -> dict:
    company = rand_company(lang)
    org = rand_org()
    foreign_amount = random.randint(2000, 8000)
    currency = random.choice(["EUR", "USD", "GBP"])
    orig_rate = round(random.uniform(10.0, 12.0), 2)
    pay_rate = round(orig_rate + random.uniform(-0.5, 0.5), 2)
    direction = "disagio" if pay_rate < orig_rate else "agio"
    templates = {
        "nb": [f"Kunden {company} (org.nr {org}) betalte en faktura på {foreign_amount} {currency}. Opprinnelig kurs {orig_rate}, betalingskurs {pay_rate}. Registrer med valutadifferanse ({direction})."],
        "en": [f"Customer {company} (org no. {org}) paid an invoice of {foreign_amount} {currency}. Original rate {orig_rate}, payment rate {pay_rate}. Register with exchange rate difference."],
        "de": [f"Kunde {company} (Org.-Nr. {org}) zahlte Rechnung über {foreign_amount} {currency}. Kurs bei Rechnungsstellung {orig_rate}, Zahlungskurs {pay_rate}. Wechselkursdifferenz buchen."],
        "pt": [f"O cliente {company} (org. nº {org}) pagou fatura de {foreign_amount} {currency}. Taxa original {orig_rate}, taxa de pagamento {pay_rate}. Diferença cambial."],
        "fr": [f"Le client {company} (nº org. {org}) a payé une facture de {foreign_amount} {currency}. Taux initial {orig_rate}, taux de paiement {pay_rate}. Différence de change."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "currency_payment", "lang": lang}


def _vary_year_end_closing(lang: str) -> dict:
    is_month_end = random.choice([True, False])
    month = random.choice(["januar", "februar", "mars", "april"])
    cost = random.choice([80000, 100000, 120000, 150000, 200000])
    years = random.choice([3, 5, 10])
    account = random.choice(["1200", "1210", "1250"])
    templates = {
        "nb": [
            f"Utfør månedsslutt for {month} 2026. Avskriv kontorutstyr (kostpris {cost} kr, {years} år, konto {account}). Avskrivningskonto 6010." if is_month_end
            else f"Utfør årsoppgjør for 2025. Avskriv utstyr (kostpris {cost} kr, {years} år, konto {account}). Avskrivningskonto 6010.",
        ],
        "en": [
            f"Perform month-end closing for March 2026. Depreciate equipment (cost {cost} NOK, {years} years, account {account})." if is_month_end
            else f"Perform year-end closing for 2025. Depreciate equipment (cost {cost} NOK, {years} years, account {account}).",
        ],
        "de": [
            f"Monatsabschluss Februar 2026. Abschreibung Ausstattung (Kosten {cost} NOK, {years} Jahre, Konto {account})." if is_month_end
            else f"Jahresabschluss 2025. Abschreibung (Kosten {cost} NOK, {years} Jahre, Konto {account}).",
        ],
        "es": [
            f"Cierre mensual marzo 2026. Amortice equipo (coste {cost} NOK, {years} años, cuenta {account})." if is_month_end
            else f"Cierre anual 2025. Amortice equipo (coste {cost} NOK, {years} años, cuenta {account}).",
        ],
        "fr": [
            f"Clôture mensuelle mars 2026. Amortissez équipement (coût {cost} NOK, {years} ans, compte {account})." if is_month_end
            else f"Clôture annuelle 2025. Amortissez équipement (coût {cost} NOK, {years} ans, compte {account}).",
        ],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "year_end_closing", "lang": lang}


def _vary_full_project_cycle(lang: str) -> dict:
    company = rand_company(lang)
    org = rand_org()
    project = rand_project(lang)
    mgr_first, mgr_last = rand_name(lang)
    mgr_email = rand_email(mgr_first, mgr_last)
    emp_first, emp_last = rand_name(lang)
    emp_email = rand_email(emp_first, emp_last)
    hours = random.randint(10, 40)
    budget = random.choice([300000, 400000, 500000, 600000])
    supplier = rand_company(lang)
    s_org = rand_org()
    s_cost = rand_amount(20000, 60000)
    inv_amount = rand_amount(80000, 200000)
    activity = random.choice(ACTIVITIES)
    templates = {
        "nb": [f"Opprett prosjektet \"{project}\" for {company} (org.nr {org}) med budsjett {budget} kr. Prosjektleder: {mgr_first} {mgr_last} ({mgr_email}). Registrer {hours} timer for {emp_first} {emp_last} ({emp_email}) på {activity}. Leverandørkostnad fra {supplier} (org.nr {s_org}) på {s_cost} kr (konto 4300). Fakturer kunden {inv_amount} kr."],
        "en": [f"Complete project cycle: Create project \"{project}\" for {company} (org no. {org}) with budget {budget} NOK. Manager: {mgr_first} {mgr_last} ({mgr_email}). Register {hours} hours for {emp_first} {emp_last} on {activity}. Supplier cost from {supplier}: {s_cost} NOK (account 4300). Invoice {inv_amount} NOK."],
        "fr": [f"Cycle complet : Créez le projet \"{project}\" pour {company} (nº org. {org}), budget {budget} NOK. Chef de projet : {mgr_first} {mgr_last} ({mgr_email}). {hours} heures pour {emp_first} {emp_last} sur {activity}. Coût fournisseur {supplier} : {s_cost} NOK (compte 4300). Facturez {inv_amount} NOK."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "full_project_cycle", "lang": lang}


def _vary_cost_analysis(lang: str) -> dict:
    period = random.choice(["januar-februar", "Q1", "januar-mars", "februar-mars"])
    n = random.choice([3, 5])
    templates = {
        "nb": [f"Analyser hovedboka for {period} 2026. Finn de {n} kontiene med størst økning i kostnader. Opprett et prosjekt for hver."],
        "en": [f"Analyze the ledger for {period} 2026. Find the top {n} expense accounts. Create a project for each."],
        "de": [f"Analysieren Sie das Hauptbuch für {period} 2026. Finden Sie die {n} Konten mit den höchsten Kosten."],
        "fr": [f"Analysez le grand livre pour {period} 2026. Trouvez les {n} comptes les plus coûteux. Créez un projet pour chacun."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "cost_analysis", "lang": lang}


def _vary_enable_module(lang: str) -> dict:
    modules = {
        "nb": ["prosjektmodulen", "reiseregningsmodulen", "lønnsmodulen", "faktureringsmodulen"],
        "en": ["the project module", "the travel expense module", "the payroll module"],
        "de": ["das Projektmodul", "das Reisekostenmodul", "das Gehaltsabrechnungsmodul"],
        "es": ["el módulo de proyectos", "el módulo de gastos de viaje"],
        "fr": ["le module projet", "le module notes de frais"],
    }
    mod_pool = modules.get(lang, modules["nb"])
    mod = random.choice(mod_pool)
    templates = {
        "nb": [f"Aktiver {mod} i Tripletex."],
        "en": [f"Enable {mod} in Tripletex."],
        "de": [f"Aktivieren Sie {mod} in Tripletex."],
        "es": [f"Active {mod} en Tripletex."],
        "fr": [f"Activez {mod} dans Tripletex."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "enable_module", "lang": lang}


def _vary_bank_reconciliation(lang: str) -> dict:
    month = random.choice(["januar", "februar", "mars", "april"])
    month_en = {"januar": "January", "februar": "February", "mars": "March", "april": "April"}[month]
    templates = {
        "nb": [f"Utfør bankavstemming for {month} 2026."],
        "en": [f"Perform bank reconciliation for {month_en} 2026."],
        "de": [f"Führen Sie die Bankabstimmung für {month_en} 2026 durch."],
        "fr": [f"Effectuez le rapprochement bancaire pour {month_en} 2026."],
    }
    return {"prompt": random.choice(templates.get(lang, templates["nb"])), "expected_type": "bank_reconciliation", "lang": lang}


# Map task type -> variation generator
VARIATION_GENERATORS = {
    "create_employee": _vary_create_employee,
    "update_employee": _vary_update_employee,
    "create_customer": _vary_create_customer,
    "update_customer": _vary_update_customer,
    "create_product": _vary_create_product,
    "update_product": _vary_update_product,
    "create_department": _vary_create_department,
    "update_department": _vary_update_department,
    "create_invoice": _vary_create_invoice,
    "register_payment": _vary_register_payment,
    "reverse_payment": _vary_reverse_payment,
    "create_credit_note": _vary_create_credit_note,
    "project_invoice": _vary_project_invoice,
    "create_project": _vary_create_project,
    "update_project": _vary_update_project,
    "create_travel_expense": _vary_create_travel_expense,
    "delete_travel_expense": _vary_delete_travel_expense,
    "register_timesheet": _vary_register_timesheet,
    "run_payroll": _vary_run_payroll,
    "create_supplier_invoice": _vary_create_supplier_invoice,
    "create_voucher": _vary_create_voucher,
    "delete_voucher": _vary_delete_voucher,
    "create_accounting_dimension": _vary_create_accounting_dimension,
    "overdue_invoice": _vary_overdue_invoice,
    "ledger_correction": _vary_ledger_correction,
    "currency_payment": _vary_currency_payment,
    "year_end_closing": _vary_year_end_closing,
    "full_project_cycle": _vary_full_project_cycle,
    "cost_analysis": _vary_cost_analysis,
    "enable_module": _vary_enable_module,
    "bank_reconciliation": _vary_bank_reconciliation,
    "update_travel_expense": None,  # no generator, only base prompts
}


# ---------------------------------------------------------------------------
# Generate ~1000 prompts from base + variations
# ---------------------------------------------------------------------------

def generate_variations(target: int = 1000, seed: int = 42) -> list[dict]:
    """Generate approximately `target` prompts by combining base prompts with variations."""
    random.seed(seed)
    all_prompts: list[dict] = []

    # Start with all base prompts
    for p in PROMPTS:
        all_prompts.append(dict(p))

    base_count = len(all_prompts)
    remaining = target - base_count
    if remaining <= 0:
        return all_prompts[:target]

    # Count how many base prompts per type
    type_counts = defaultdict(int)
    for p in PROMPTS:
        type_counts[p["expected_type"]] += 1

    # Get all task types that have generators
    gen_types = [t for t, g in VARIATION_GENERATORS.items() if g is not None]

    # Distribute remaining across types, weighted to balance coverage
    # Types with fewer base prompts get more variations
    max_base = max(type_counts.values()) if type_counts else 1
    weights = {}
    for t in gen_types:
        # Inverse weight: types with fewer base prompts get higher weight
        base = type_counts.get(t, 0)
        weights[t] = max(1, max_base - base + 3)

    total_weight = sum(weights.values())
    langs = ["nb", "nn", "en", "de", "es", "pt", "fr"]

    for t in gen_types:
        gen_fn = VARIATION_GENERATORS[t]
        # How many variations for this type
        n_variations = max(5, int(remaining * weights[t] / total_weight))
        for _ in range(n_variations):
            lang = random.choice(langs)
            try:
                p = gen_fn(lang)
                all_prompts.append(p)
            except Exception:
                pass  # skip if a template for this lang doesn't exist

    # Shuffle (keeping deterministic via seed)
    random.shuffle(all_prompts)

    # Trim to target if we overshoot
    return all_prompts[:target]


# ---------------------------------------------------------------------------
# Run classification tests
# ---------------------------------------------------------------------------

async def run_classification_test(prompts: list[dict]) -> dict:
    """Run each prompt through classify_and_extract_two_stage, compare results."""
    from llm.classifier import classify_and_extract_two_stage

    results = []
    correct = 0
    wrong = 0
    errors = 0
    type_stats: dict[str, dict] = defaultdict(lambda: {"total": 0, "correct": 0, "wrong": 0, "errors": 0})
    lang_stats: dict[str, dict] = defaultdict(lambda: {"total": 0, "correct": 0})

    total = len(prompts)
    start_time = time.time()

    for i, p in enumerate(prompts):
        prompt_text = p["prompt"]
        expected = p["expected_type"]
        lang = p.get("lang", "?")

        type_stats[expected]["total"] += 1
        lang_stats[lang]["total"] += 1

        try:
            plan = await classify_and_extract_two_stage(prompt_text)
            actual = plan.task_type.value

            is_match = actual == expected
            if is_match:
                correct += 1
                type_stats[expected]["correct"] += 1
                lang_stats[lang]["correct"] += 1
            else:
                wrong += 1
                type_stats[expected]["wrong"] += 1

            icon = "OK" if is_match else "FAIL"
            result = {
                "prompt": prompt_text,
                "lang": lang,
                "expected_type": expected,
                "actual_type": actual,
                "match": is_match,
            }
            results.append(result)

            if (i + 1) % 25 == 0 or not is_match:
                logger.info(
                    f"[{i+1}/{total}] {icon} | expected={expected}, got={actual} | lang={lang}"
                    + (f" | prompt={prompt_text[:80]}..." if not is_match else "")
                )

        except Exception as e:
            errors += 1
            type_stats[expected]["errors"] += 1
            results.append({
                "prompt": prompt_text,
                "lang": lang,
                "expected_type": expected,
                "actual_type": "ERROR",
                "match": False,
                "error": str(e),
            })
            logger.error(f"[{i+1}/{total}] ERROR | expected={expected} | {e}")

    elapsed = time.time() - start_time

    # Print summary
    print("\n" + "=" * 70)
    print(f"CLASSIFICATION TEST RESULTS ({total} prompts, {elapsed:.1f}s)")
    print("=" * 70)
    print(f"  Total:   {total}")
    print(f"  Correct: {correct}  ({100*correct/total:.1f}%)")
    print(f"  Wrong:   {wrong}  ({100*wrong/total:.1f}%)")
    print(f"  Errors:  {errors}")
    print()

    # Per task type
    print("PER TASK TYPE:")
    print(f"  {'Task Type':<35} {'Total':>6} {'Correct':>8} {'Accuracy':>10}")
    print(f"  {'-'*35} {'-'*6} {'-'*8} {'-'*10}")
    for t in sorted(type_stats.keys()):
        s = type_stats[t]
        acc = 100 * s["correct"] / s["total"] if s["total"] > 0 else 0
        marker = " <<<" if acc < 90 else ""
        print(f"  {t:<35} {s['total']:>6} {s['correct']:>8} {acc:>9.1f}%{marker}")
    print()

    # Per language
    print("PER LANGUAGE:")
    print(f"  {'Lang':<6} {'Total':>6} {'Correct':>8} {'Accuracy':>10}")
    print(f"  {'-'*6} {'-'*6} {'-'*8} {'-'*10}")
    for lang in sorted(lang_stats.keys()):
        s = lang_stats[lang]
        acc = 100 * s["correct"] / s["total"] if s["total"] > 0 else 0
        print(f"  {lang:<6} {s['total']:>6} {s['correct']:>8} {acc:>9.1f}%")
    print()

    # Misclassifications
    failures = [r for r in results if not r["match"] and "error" not in r]
    if failures:
        print(f"MISCLASSIFICATIONS ({len(failures)}):")
        for r in failures[:30]:
            print(f"  [{r['lang']}] expected={r['expected_type']}, got={r['actual_type']}")
            print(f"       {r['prompt'][:100]}")
    print()

    # Build output
    output = {
        "summary": {
            "total": total,
            "correct": correct,
            "wrong": wrong,
            "errors": errors,
            "accuracy_pct": round(100 * correct / total, 2) if total > 0 else 0,
            "elapsed_s": round(elapsed, 1),
        },
        "per_task_type": {
            t: {
                "total": s["total"],
                "correct": s["correct"],
                "wrong": s["wrong"],
                "errors": s["errors"],
                "accuracy_pct": round(100 * s["correct"] / s["total"], 2) if s["total"] > 0 else 0,
            }
            for t, s in type_stats.items()
        },
        "per_language": {
            lang: {
                "total": s["total"],
                "correct": s["correct"],
                "accuracy_pct": round(100 * s["correct"] / s["total"], 2) if s["total"] > 0 else 0,
            }
            for lang, s in lang_stats.items()
        },
        "results": results,
    }

    return output


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    generate_only = "--generate-only" in sys.argv

    logger.info("Generating ~1000 test prompts from base + variations...")
    prompts = generate_variations(target=1000)
    logger.info(f"Generated {len(prompts)} prompts")

    # Count per type
    type_counts = defaultdict(int)
    lang_counts = defaultdict(int)
    for p in prompts:
        type_counts[p["expected_type"]] += 1
        lang_counts[p.get("lang", "?")] += 1

    print(f"\nPrompt distribution ({len(prompts)} total):")
    print(f"  {'Task Type':<35} {'Count':>6}")
    print(f"  {'-'*35} {'-'*6}")
    for t in sorted(type_counts.keys()):
        print(f"  {t:<35} {type_counts[t]:>6}")
    print()
    print(f"  {'Language':<10} {'Count':>6}")
    print(f"  {'-'*10} {'-'*6}")
    for lang in sorted(lang_counts.keys()):
        print(f"  {lang:<10} {lang_counts[lang]:>6}")
    print()

    # Save prompts to JSON
    out_dir = Path(__file__).parent.parent / "logs"
    out_dir.mkdir(exist_ok=True)

    prompts_file = out_dir / "generated-1000-test-prompts.json"
    with open(prompts_file, "w") as f:
        json.dump(prompts, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved prompts to {prompts_file}")

    if generate_only:
        logger.info("--generate-only flag set. Exiting without running classification.")
        return

    # Run classification
    logger.info("Running classification tests (requires GOOGLE_API_KEY)...")
    output = await run_classification_test(prompts)

    # Save results
    results_file = out_dir / "classification-test-results.json"
    with open(results_file, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved results to {results_file}")


if __name__ == "__main__":
    asyncio.run(main())
