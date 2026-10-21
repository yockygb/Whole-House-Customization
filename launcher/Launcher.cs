using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;
class Launcher {
 [STAThread] static void Main(){
  string root=AppDomain.CurrentDomain.BaseDirectory;
  string python=Path.Combine(root,".venv","Scripts","pythonw.exe");
  try {
   if(!File.Exists(python)) throw new FileNotFoundException("Run Setup.cmd first / 请先运行 Setup.cmd");
   Process.Start(new ProcessStartInfo {
    FileName=python, Arguments="\""+Path.Combine(root,"app.py")+"\"",
    WorkingDirectory=root, UseShellExecute=false, CreateNoWindow=true
   });
  } catch(Exception e){MessageBox.Show("Startup failed / 启动失败\n"+e.Message,"Whole-House Customization Quotation",MessageBoxButtons.OK,MessageBoxIcon.Error);}
 }
}
