"""Whole-House Customization standalone quotation application."""
import os,sys,json,argparse,socket,http.client
sys.dont_write_bytecode=True
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from core.config import DATA_DIR
from server import api

def main():
    p=argparse.ArgumentParser(description="Whole-House Customization 报价系统")
    p.add_argument("--port",type=int,default=8878)
    p.add_argument("--no-browser",action="store_true")
    args=p.parse_args()
    args.no_browser=args.no_browser or os.environ.get("WHOLE_HOUSE_CUSTOMIZATION_NO_BROWSER")=="1"
    if not args.no_browser:
        try:
            saved=json.load(open(os.path.join(DATA_DIR,"server.json")))
            url="http://127.0.0.1:%d/"%saved["port"]
            conn=http.client.HTTPConnection("127.0.0.1",saved["port"],timeout=1)
            conn.request("GET","/api/identity");response=conn.getresponse()
            data=json.loads(response.read());conn.close()
            if data.get("application")=="whole-house-customization-independent-v3":
                api._open_app_window(url); return
        except Exception: pass
    for port in range(args.port,args.port+50):
        with socket.socket() as sock:
            try: sock.bind(("127.0.0.1",port))
            except OSError: continue
        api.serve(port,open_browser=not args.no_browser)
        return
    raise RuntimeError("No available local port / 没有可用本机端口")

if __name__=="__main__":
    try: main()
    except Exception:
        import traceback
        text=traceback.format_exc()
        with open(os.path.join(DATA_DIR,"startup-error.log"),"w",encoding="utf-8") as f:f.write(text)
        if sys.executable.lower().endswith("pythonw.exe"):
            import ctypes
            ctypes.windll.user32.MessageBoxW(0,"Startup failed / 启动失败\n"+text,"Whole-House Customization",16)
        else: raise
