"""Paths owned exclusively by this standalone application."""
import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.abspath(os.environ.get("WHOLE_HOUSE_CUSTOMIZATION_DATA_DIR", os.path.join(BASE_DIR,"data")))
WEB_DIR = os.path.join(BASE_DIR,"web")
EXPORT_DIR = os.path.abspath(os.environ.get("WHOLE_HOUSE_CUSTOMIZATION_EXPORT_DIR", os.path.join(BASE_DIR,"exports")))
DB_PATH = os.path.join(DATA_DIR,"app.db")
PRICING_PATH = os.path.join(DATA_DIR,"pricing.json")
UPLOAD_DIR = os.path.join(DATA_DIR,"uploads")
DEFAULT_SETTINGS = {"currency":"RM","discount":"1.0","deposit_rate":"0.5"}
for p in (DATA_DIR,EXPORT_DIR,UPLOAD_DIR): os.makedirs(p,exist_ok=True)
if not os.path.exists(PRICING_PATH):
    import shutil
    shutil.copy2(os.path.join(BASE_DIR,"data","factory-pricing.json"),PRICING_PATH)
