"""Local dimension extraction. Never invent cabinet/material/height information."""
import base64, io, os, re, subprocess, tempfile
from pathlib import Path

def candidates(text):
    text=re.sub(r'(?i)\bm\s+m\b','mm',text)
    text=re.sub(r'(?i)\bc\s+m\b','cm',text)
    out=[]
    pattern=r'(\d{2,5}(?:\.\d+)?)\s*[xX×*]\s*(\d{2,5}(?:\.\d+)?)(?:\s*[xX×*]\s*(\d{2,5}(?:\.\d+)?))?\s*(mm|cm|ft|inch|m)?'
    for m in re.finditer(pattern,text):
        factor={'mm':1,'cm':10,'m':1000,'ft':304.8,'inch':25.4}.get(m[4],1)
        vals=[float(m[i])*factor if m[i] else 0 for i in (1,2,3)]
        if all(v==0 or 50<=v<=20000 for v in vals):
            d={'length_mm':vals[0],'height_mm':vals[1] if vals[2] else 0,'depth_mm':vals[2] or vals[1],
               'source':m[0],'view':'3d' if vals[2] else 'plan','confirmed':False}
            if d not in out:out.append(d)
    return out

def windows_ocr(path):
    # Windows PowerShell invokes the installed Windows OCR engine without Python WinRT packages.
    ps=r'''param([string]$ImagePath)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null
$asTask=([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {$_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'})[0]
function Await($op,[Type]$type){$task=$asTask.MakeGenericMethod($type).Invoke($null,@($op));$task.Wait();$task.Result}
$file=Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($ImagePath)) ([Windows.Storage.StorageFile])
$stream=Await ($file.OpenReadAsync()) ([Windows.Storage.Streams.IRandomAccessStreamWithContentType])
$decoder=Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap=Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if($null -eq $engine){throw 'Windows OCR language pack not installed / 未安装Windows OCR语言包'}
$result=Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
$result.Text
'''
    with tempfile.TemporaryDirectory(prefix='whole_house_customization_ocr_') as temp:
        script=Path(temp)/'ocr.ps1';script.write_text(ps,encoding='utf-8-sig')
        exe=os.path.join(os.environ.get('SystemRoot',r'C:\Windows'),'System32','WindowsPowerShell','v1.0','powershell.exe')
        result=subprocess.run([exe,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),str(path)],capture_output=True,timeout=70,creationflags=0x08000000)
        if result.returncode:raise RuntimeError(result.stderr.decode('utf-8',errors='replace')[-600:])
        return result.stdout.decode('utf-8-sig',errors='replace')

def recognize(body):
    name=body.get('name','drawing.png');suffix=Path(name).suffix.lower()
    if body.get('text') is not None:
        text=str(body['text']);return {'text':text,'candidates':candidates(text),'numbers':re.findall(r'\b\d{3,5}\b',text),'engine':'Text / 文字'}
    data=base64.b64decode(body.get('data','').split(',')[-1],validate=True)
    if len(data)>20_000_000:raise ValueError('File limit 20 MB / 图纸限20MB')
    text='';preview='';engine=''
    with tempfile.TemporaryDirectory(prefix='whole_house_customization_drawing_') as tmp:
        if suffix=='.dxf':
            raw=data.decode('utf-8',errors='replace').splitlines();values=[]
            for i in range(0,len(raw)-1,2):
                if raw[i].strip() in ('1','3','42'):values.append(raw[i+1].strip())
            text='\n'.join(values);engine='DXF text & dimension entities / DXF文字与尺寸实体'
        else:
            from PIL import Image,ImageOps
            if suffix=='.pdf':
                import pypdfium2 as pdfium
                pdf=pdfium.PdfDocument(data);page=pdf[min(int(body.get('page',0)),len(pdf)-1)]
                text=page.get_textpage().get_text_range();im=page.render(scale=1.8).to_pil()
                engine='PDF text / PDF文字'
            else:im=Image.open(io.BytesIO(data));engine='Windows OCR / Windows离线识别'
            im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((2600,2600))
            display=io.BytesIO();im.save(display,format='JPEG',quality=82)
            preview='data:image/jpeg;base64,'+base64.b64encode(display.getvalue()).decode()
            if not text.strip():
                path=Path(tmp)/'drawing.png';ImageOps.autocontrast(im.convert('L')).save(path)
                text=windows_ocr(path);engine='Windows OCR / Windows离线识别'
    return {'text':text,'preview':preview,'engine':engine,'candidates':candidates(text),
            'numbers':list(dict.fromkeys(re.findall(r'\b\d{3,5}\b',text)))[:150]}
