"""The quotation studio owns its local data, exports and instance identity."""
import os,shutil
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ID = "vouguer-next-v4"
APP_VERSION = "1.1.0"
DEFAULT_PORT = 8978
DATA_DIR = os.path.abspath(os.environ.get("VOUGUER_NEXT_DATA_DIR") or os.path.join(BASE_DIR,"workspace-data"))
WEB_DIR = os.path.join(BASE_DIR,"web")
EXPORT_DIR = os.path.abspath(os.environ.get("VOUGUER_NEXT_EXPORT_DIR") or os.path.join(BASE_DIR,"exports"))
DB_PATH = os.path.join(DATA_DIR,"app.db")
PRICING_PATH = os.path.join(DATA_DIR,"pricing.json")
UPLOAD_DIR = os.path.join(DATA_DIR,"uploads")
DEFAULT_SETTINGS = {"currency":"RM","discount":"1.0","deposit_rate":"0.5"}
for p in (DATA_DIR,EXPORT_DIR,UPLOAD_DIR): os.makedirs(p,exist_ok=True)
if not os.path.exists(PRICING_PATH):
    shutil.copy2(os.path.join(BASE_DIR,"data","factory-pricing.json"),PRICING_PATH)
