"""Launch the real app with disposable data and exercise its HTTP workflow."""
from pathlib import Path
import json, os, socket, subprocess, sys, tempfile, time, unittest, urllib.request

ROOT=Path(__file__).resolve().parents[1]

class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='quotation-http-',dir=os.environ.get('TEMP'))
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        cls.base='http://127.0.0.1:%d'%port
        env=dict(os.environ,VOUGUER_NEXT_DATA_DIR=str(Path(cls.tmp.name)/'data'),
                 VOUGUER_NEXT_EXPORT_DIR=str(Path(cls.tmp.name)/'exports'),
                 VOUGUER_NEXT_NO_BROWSER='1',PYTHONIOENCODING='utf-8')
        cls.log=open(Path(cls.tmp.name)/'server.log','w+',encoding='utf-8')
        cls.proc=subprocess.Popen([sys.executable,str(ROOT/'app.py'),'--no-browser','--port',str(port)],
                                  cwd=ROOT,env=env,stdout=cls.log,stderr=cls.log,
                                  creationflags=0x08000000 if os.name=='nt' else 0)
        try:
            for _ in range(100):
                if cls.proc.poll() is not None:
                    cls.log.seek(0); raise RuntimeError(cls.log.read())
                try:
                    with urllib.request.urlopen(cls.base+'/api/identity',timeout=.5) as response:
                        if response.status==200: return
                except OSError: time.sleep(.1)
            raise RuntimeError('Application startup timed out')
        except BaseException:
            cls.tearDownClass(); raise

    @classmethod
    def tearDownClass(cls):
        if getattr(cls,'proc',None) and cls.proc.poll() is None:
            cls.proc.terminate(); cls.proc.wait(timeout=10)
        if getattr(cls,'log',None): cls.log.close()
        if getattr(cls,'tmp',None): cls.tmp.cleanup()

    def request_json(self,path,data=None,method=None):
        request=urllib.request.Request(self.base+path,
            data=json.dumps(data).encode('utf-8') if data is not None else None,
            headers={'Content-Type':'application/json'},method=method)
        with urllib.request.urlopen(request,timeout=15) as response: return json.load(response)

    def test_identity_health_and_customer_page(self):
        identity=self.request_json('/api/identity')
        self.assertEqual(identity['version'],'1.1.0')
        self.assertEqual(Path(identity['data_directory']),Path(self.tmp.name)/'data')
        self.assertTrue(self.request_json('/api/health')['ok'])
        with urllib.request.urlopen(self.base+'/',timeout=5) as response:
            html=response.read().decode('utf-8')
        self.assertIn('Whole-House Quotation Studio 1.1',html)
        self.assertIn('categorySelect',html)

    def test_clean_bootstrap_and_zero_rate_quote(self):
        bootstrap=self.request_json('/api/bootstrap')
        self.assertTrue(bootstrap['categories'])
        cat=next(c for c in bootstrap['categories'] if c['key']=='custom_cabinet')
        material=next(m['key'] for m in cat['materials'])
        self.assertTrue(all(float(m['price'])==0 for c in bootstrap['categories'] for m in c['materials']))
        quote=self.request_json('/api/quotes',{'customer':'Sample customer','project':'Sample project',
            'items':[{'room':'Sample Room','floor':'GF','cat':cat['key'],'material':material,'door':'',
                     'cab_name':'Sample Cabinet','length_mm':1800,'height_mm':2400,'depth_mm':600,
                     'qty':1,'extras':{}}]},method='POST')
        self.assertEqual(quote['computed']['summary']['total'],0)
        listed=self.request_json('/api/quotes')
        self.assertEqual(len(listed['quotes']),1)

if __name__=='__main__': unittest.main(verbosity=2)
