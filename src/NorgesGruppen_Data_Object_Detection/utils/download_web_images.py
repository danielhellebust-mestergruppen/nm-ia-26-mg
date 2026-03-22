import os
import requests
import time
from pathlib import Path
from duckduckgo_search import DDGS

# List of categories to process
category_lines = """
COTW_BREAKFAST_BLEND_KAFFEKAPSEL_10STK: 9
EGG_L_10STK_TOTEN: 9
FRIELE_FROKOST_HEL_500G: 9
MEIERISMØR_250G_BORDPK_TINE: 9
MELANGE_MARGARIN_250G: 9
BRUSCHETTE_FINE_CHEESE_MARETTI: 8
MÜSLI_BLÅBÆR_630G_AXA: 8
MÜSLI_ENERGI_650G_AXA: 8
SJOKOFLAK_FROKOSTBLANDING_375G_ELDORADO: 8
SMØREMYK_600G_ELDORADO: 8
SOFT_FLORA_ORIGINAL_230G: 8
STEKEMARGARIN_500G_FIRST_PRICE: 8
DELICATE_CRACKERS_SEA_SALT_180G_WASA: 7
MELANGE_FLYTENDE_500ML: 7
NIGHT_TE_20POS_PUKKA: 7
SANDWICH_BRUNOST_36G_WASA: 7
SANDWICH_PIZZA_37G_WASA: 7
CAPPUCCINO_8KAPSLER_DOLCE_GUSTO: 6
FEEL_NEW_URTETE_ØKOLOGISK_20POS_PUKKA: 6
FROKOSTRINGER_FRUKTSMAK_350G_ELDORADO: 6
Galåvolden_Store_Gårdsegg_6stk: 6
Gårdsegg_fra_Fana_10stk: 6
LADY_GREY_TE_200G_TWININGS: 6
SVARTHAVREGRYN_LETTKOKTE_900G_DEN_SORTE: 6
COTW_DARK_ROAST_KAFFEKAPSEL_10STK: 5
EXCELSO_COLOMBIA_FILTERMALT_200G_JACOBS: 5
KNEKKEBRØD_GODT_FOR_DEG_OST_190G_SIGDAL: 5
KRUTONGER_CHEESE_GARLIC_142G_CHATHAM: 5
NESCAFE_BRASERO_REFILL_180G: 5
SJOKOLADEDRIKK_512G_RETT_I_KOPPEN: 5
Tørresvik_Gårdsegg_6stk: 5
ZOEGAS_KAFFE_SKÅNEROST_450G: 5
BAKEKAKAO_250G_REGIA: 4
COTW_LUNGO_KOFFEINFRI_KAFFEKAPSEL_10STK: 4
ENGLISH_BREAKFAST_TEA_200G_TWININGS: 4
ESPRESSO_INTENSO_16KAPSLER_DOLCE_GUSTO: 4
ESPRESSO_ITALIAN_HELE_BØNNER_500G_JACOBS: 4
FLOTT_MATFETT_500G: 4
Galåvolden_Store_Gårdsegg_10stk: 4
KNEKKEBRØD_GL_FRI_150G_BRISK: 4
O_BOY_MINDRE_SUKKER_500G_POSE_FREIA: 4
ROOIBOS_TE_ØKOLOGISK_20PS: 4
SIDAMO_ETIOPIA_HELE_BØNNER_340G_COTW: 4
SJOKOLADEDRIKK_10X32G_RETT_I_KOPPEN: 4
COTW_COLOMBIA_EXCELSO_KAFFEKAPSEL_10STK: 3
COTW_LUNGO_ØKOLOGISK_KAFFEKAPSEL_10STK: 3
GIFFLAR_KANEL_300G_PÅGEN: 3
GRANDE_INTENSO_16KAPSLER_DOLCE_GUSTO: 3
HAVRERINGER_250G_SYNNØVE_FINDEN: 3
KAMILLE_TE_20POS_LIPTON: 3
LIPTON_ICETEA_PEACH_PULVER_50G: 3
MELANGE_FLYTENDE_MARGARIN_M_SMØR_500ML: 3
SANDWICH_SOUR_CREAM_ONION_33G_WASA: 3
SMØR_USALTET_250G_TINE: 3
SOFT_FLORA_STEKE_BAKE_500G: 3
Sunnmørsegg_10stk: 3
EARL_GREY_TEA_ØKOLOGISK_15POS_JACOBS: 2
EVERGOOD_ESPRESSO_HELE_BØNNER_500G: 2
FRIELE_INSTANT_GULL_100G_REFILL: 2
GIFFLAR_BRINGEBÆR_VANILJE_260G_PÅGEN: 2
GRANOLA_PEKAN_GL_FRI_325G_SYNNØVE_FINDEN: 2
HVITLØK_100G_PK: 2
KNEKKEBRØD_URTER_HAVSALT_GL_FRI_190G: 2
KNEKKS_KJEKS_HAVRE_190G_RØROS: 2
Leka_Egg_10stk: 2
MÜSLI_PAPAYA_GLUTENFRI_350G_AXA: 2
NUTELLA_BISCUITS_193G: 2
SMØREMYK_MELKEFRI_400G_BERIT: 2
TOM_JERRY_KJEKS_175G_SÆTRE: 2
BLÅ_JAVA_HELE_BØNNER_340G_COTW: 1
BRUSCHETTA_LIGURISK_130G_OLIVINO: 1
CLEAN_MATCHA_GREEN_TE_ØKOL_20POS_PUKKA: 1
DAVE_JON_S_DADLER_SOUR_COLA_125G: 1
EGG_M_L_ØKOLOGISKE_10STK_VILJE: 1
EXCELSO_COLOMBIA_HELE_BØNNER_500G_JACOBS: 1
FLAT_WHITE_16KAPSLER_DOLCE_GUSTO: 1
FRIELE_FROKOST_KOFFEINFRI_FILTERMALT_250G: 1
GRANOLA_RASPBERRY__500G_START_: 1
GREEN_CEYLON_TE_ØKOLOGISK_24POS_CONFECTA: 1
GRØNN_TE_CHAI_25POS_TWININGS: 1
GÅRDSEGG_EKSTRA_STORE_6STK_EK: 1
HAVREGRYN_STORE_GLUTENFRI_1KG_AXA: 1
JARLSBERG_27__SKIVET_120G_TINE: 1
KAFFEFILTER_PRESSKANNE_25STK_EVERGOOD: 1
KNEKKEBRØD_NATURELL_GL_FRI_240G_WASA: 1
KNEKKEBRØD_SESAM_HAVSALT_GL_FRI_240G: 1
KRYDDERMIKS_SHISH_KEBAB_10G_POS_HINDU: 1
LANO_SÅPE_2X125G: 1
LIPTON_ICETEA_LEMON_PULVER_50G: 1
LIPTON_ICETEA_MANGO_PULVER_50G: 1
MORENEPOTETER_GULE_650G_BJERTNÆS_HOEL: 1
OB_PROCOMFORT_NORMAL_16ST: 1
PANNEKAKER_6STK_ELDORADO: 1
PANNEKAKER_GROVE_STEKTE_480G_ÅMLI: 1
POTETCHIPS_SORT_TRØFFEL_125G_TORRES: 1
POWERKNEKKEBRØD_GL_FRI_225G_SCHÄR: 1
PREMIUM_DARK_ORANGE_100G_FREIA: 1
SANDWICH_CHEESE_GRESSLØK_37G_WASA: 1
SANDWICH_PESTO_37G_WASA: 1
STORFE_ENTRECOTE_180G_FIRST_PRICE: 1
STORFE_SHORT_RIBS_GREATER_OMAHA_LV: 1
SURDEIGKJEKS_100G_SÆTRES_BESTE: 1
TASSIMO_GEVALIA_LATTE_MACCHIATO_KARAMELL: 1
TROPISK_AROMA_FILTERMALT_200G_JACOBS: 1
VESTLANDSLEFSA_TØRRE_10STK_360G: 1
BJØRN_HAVREMEL_1KG_AXA: 0
BOG_390G_GILDE: 0
EXTRA_SWEET_FRUIT_14G: 0
FROKOSTBLANDING_LION_350G_NESTLE: 0
GRANOLA_CRAZELNUT_500G_START_: 0
ASPARGES_GRØNN: 0
"""

def clean_query(cat_name):
    """Make the category name more readable for a search engine."""
    return cat_name.replace("_", " ").replace("  ", " ")

def download_image(url, save_path):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        with open(save_path, 'wb') as f:
            f.write(response.content)
        return True
    except Exception as e:
        return False

def main():
    base_dir = Path(r"src\NorgesGruppen_Data_Object_Detection\datasets\web_images")
    base_dir.mkdir(parents=True, exist_ok=True)
    
    categories = []
    for line in category_lines.strip().split("\n"):
        if ":" in line:
            cat = line.split(":")[0].strip()
            categories.append(cat)
            
    print(f"Found {len(categories)} categories to process.")
    
    ddgs = DDGS()

    # Limit to e.g. 5 images per category to save time and space
    images_per_category = 5

    for idx, category in enumerate(categories, 1):
        print(f"\n[{idx}/{len(categories)}] Searching for: {category}")
        cat_dir = base_dir / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        
        # If folder already has enough images, skip (for resume capability)
        existing = len([f for f in cat_dir.iterdir() if f.is_file()])
        if existing >= images_per_category:
            print(f"  -> Already has {existing} images. Skipping.")
            continue
            
        query = clean_query(category)
        
        try:
            # Search DDG for images
            results = list(ddgs.images(query, max_results=10))
            
            downloaded = existing
            for r in results:
                if downloaded >= images_per_category:
                    break
                
                img_url = r.get('image')
                if img_url:
                    ext = img_url.split(".")[-1].split("?")[0]
                    if len(ext) > 4:
                        ext = "jpg"
                    
                    filename = cat_dir / f"web_{downloaded+1}.{ext}"
                    success = download_image(img_url, filename)
                    if success:
                        print(f"  -> Downloaded {filename.name}")
                        downloaded += 1
                        
            if downloaded == existing:
                 print("  -> Could not download any new images.")
                 
        except Exception as e:
            print(f"  -> Error searching/downloading for {category}: {e}")
            
        time.sleep(1) # Be nice to DDG

    print(f"\nDone! Images are saved in {base_dir}")

if __name__ == "__main__":
    main()