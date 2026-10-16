using System.Diagnostics;
using System.Drawing.Text;
using System.Runtime.InteropServices;
using System.Text.Json;
using PaperBridgeSetup;
using PaperBridgeUpdate;

internal static class Program
{
    [STAThread] static void Main(string[] args){ApplicationConfiguration.Initialize();Application.SetCompatibleTextRenderingDefault(true);Application.Run(new UpdateWindow(args));}
}
internal sealed class UpdateWindow:Form
{
    readonly Label status=new(){AutoSize=false,Height=36,Dock=DockStyle.Top},detail=new(){AutoSize=false,Height=72,Dock=DockStyle.Top};
    readonly ProgressBar progress=new(){Dock=DockStyle.Top,Height=12,Maximum=1000};
    readonly Button start=new(){Text="检查并更新应用",Width=210,Height=42},pause=new(){Text="暂停",Width=90,Height=42,Enabled=false};
    readonly HttpClient http=UpdateNetwork.Client();readonly string target,data,cache;readonly string? evidence;readonly int parent;
    readonly bool automatic,smoke,launch;readonly PrivateFontCollection fonts=new();IntPtr memory;CancellationTokenSource? cancellation;
    bool working,committing,complete,closeAfter;AppRelease? release;
    public UpdateWindow(string[] args)
    {
        string? Option(string key){int n=Array.IndexOf(args,key);return n>=0&&n+1<args.Length?args[n+1]:null;}
        target=Option("--destination")??Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Programs","Yiyan");
        data=Option("--data")??Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"PaperBridge");
        cache=Option("--cache")??Path.Combine(data,"UpdateCache");evidence=Option("--evidence");int.TryParse(Option("--parent-pid"),out parent);
        smoke=args.Contains("--update-smoke");automatic=smoke||args.Contains("--auto");launch=!args.Contains("--no-launch")&&!smoke;
        if(smoke&&(evidence is null||Option("--destination") is null||Option("--data") is null))throw new ArgumentException("Smoke paths required");
        using var resource=typeof(UpdateWindow).Assembly.GetManifestResourceStream("PaperBridgeUpdate.UiFont.ttf")!;using var bytes=new MemoryStream();resource.CopyTo(bytes);
        byte[] font=bytes.ToArray();memory=Marshal.AllocCoTaskMem(font.Length);Marshal.Copy(font,0,memory,font.Length);fonts.AddMemoryFont(memory,font.Length);
        Font=new Font(fonts.Families[0],11);Text="译研 · 软件更新";ClientSize=new Size(700,370);StartPosition=FormStartPosition.CenterScreen;
        BackColor=Color.FromArgb(248,250,247);ForeColor=Color.FromArgb(28,55,47);Icon=Icon.ExtractAssociatedIcon(Environment.ProcessPath!);
        var content=new Panel(){Dock=DockStyle.Fill,Padding=new Padding(28)};Controls.Add(content);
        var license=new LinkLabel(){Text="开源许可",Dock=DockStyle.Bottom,Height=26,LinkColor=ForeColor};license.LinkClicked+=(_,_)=>ShowLicenses();content.Controls.Add(license);
        var actions=new FlowLayoutPanel(){Dock=DockStyle.Bottom,Height=52,FlowDirection=FlowDirection.RightToLeft};actions.Controls.Add(start);actions.Controls.Add(pause);content.Controls.Add(actions);
        var note=new Label(){Text="只更新应用；4B / 14B 模型、论文、译稿和设置继续保留。",Dock=DockStyle.Top,Height=58};
        content.Controls.Add(progress);content.Controls.Add(detail);content.Controls.Add(status);content.Controls.Add(note);
        content.Controls.Add(new Label(){Text="更新译研，保留本地模型。",Dock=DockStyle.Top,Height=58,Font=new Font(fonts.Families[0],22),ForeColor=Color.FromArgb(40,101,80)});
        status.Text="准备就绪";detail.Text="独立直连 · 自动切换备用下载线路";
        start.Click+=async(_,_)=>{if(complete)Open();else await RunUpdate();};pause.Click+=(_,_)=>cancellation?.Cancel();
        Shown+=async(_,_)=>{if(automatic){await Task.Delay(250);CaptureEvidence("update-ready.png");start.PerformClick();}};
        FormClosing+=(_,e)=>{if(working){e.Cancel=true;if(!committing){closeAfter=true;cancellation?.Cancel();}else detail.Text="正在更新，请等待完成。";}};
        FormClosed+=(_,_)=>{http.Dispose();fonts.Dispose();if(memory!=IntPtr.Zero)Marshal.FreeCoTaskMem(memory);};
    }
    async Task WaitForApp(CancellationToken token)
    {
        foreach(var p in Process.GetProcessesByName("Yiyan"))using(p){
            try {if(!string.Equals(Path.GetFullPath(p.MainModule!.FileName),Path.Combine(target,"Yiyan.exe"),StringComparison.OrdinalIgnoreCase))continue;}
            catch(System.ComponentModel.Win32Exception){throw new IOException("请先关闭正在运行的译研。");}
            if(parent!=p.Id)throw new IOException("请先退出正在运行的译研，再继续更新。");
            using var timeout=CancellationTokenSource.CreateLinkedTokenSource(token);timeout.CancelAfter(TimeSpan.FromSeconds(60));
            try{await p.WaitForExitAsync(timeout.Token);}catch(OperationCanceledException)when(!token.IsCancellationRequested){throw new IOException("译研尚未退出，请关闭后再继续更新。");}
        }
    }
    async Task RunUpdate()
    {
        if(working)return;Environment.ExitCode=0;working=true;start.Enabled=false;pause.Enabled=true;cancellation=new();var token=cancellation.Token;
        var clock=Stopwatch.StartNew();long last=0;double lastTime=0,rate=0;
        try {
            UpdateTransaction.Destination(target);Directory.CreateDirectory(data);Directory.CreateDirectory(cache);
            using var updateLock=new FileStream(Path.Combine(data,".application-update.lock"),FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None);
            status.Text="正在检查应用版本…";release=await UpdateNetwork.Latest(http,token,smoke?Environment.GetEnvironmentVariable("PAPERBRIDGE_WINDOWS_TEST_MANIFEST"):null);
            var downloader=new Downloader(http,chooseUrl:UpdateNetwork.BinaryUrl,networkTimeout:TimeSpan.FromSeconds(30));
            await downloader.DownloadAsync(release.Archive,cache,t=>{
                double now=clock.Elapsed.TotalSeconds;if(now-lastTime<0.3&&t.Bytes!=release.Archive.Bytes)return;
                if(lastTime>0&&t.Bytes>=last){double sample=(t.Bytes-last)/Math.Max(.01,now-lastTime);rate=rate==0?sample:.3*sample+.7*rate;}
                last=t.Bytes;lastTime=now;
                BeginInvoke(()=>{progress.Value=Math.Clamp((int)(t.Bytes*1000/release.Archive.Bytes),0,1000);status.Text="译研 "+release.Version+" · "+t.Stage;detail.Text=$"{t.Bytes/1e6:0} / {release.Archive.Bytes/1e6:0} MB"+(rate>0?$" · {rate/1e6:0.0} MB/s":"")+"\n模型无需下载，个人资料继续保留。";});
            },token);
            await WaitForApp(token);token.ThrowIfCancellationRequested();committing=true;pause.Enabled=false;status.Text="正在更新应用与界面…";
            await Task.Run(()=>UpdateTransaction.Apply(release,Path.Combine(cache,release.Archive.Name),target,token));
            try{File.Delete(Path.Combine(cache,release.Archive.Name));}catch(IOException){}
            complete=true;progress.Value=1000;status.Text="更新完成，模型与论文已保留。";detail.Text="译研 "+release.Version+" · 现在可以继续离线翻译。";start.Text="打开译研";
            Record(new{status="complete",version=release.Version,download_bytes=release.Archive.Bytes,downloaded_assets=new[]{release.Archive.Name},models_downloaded=false,models_preserved=true,data_preserved=true,runtime_reused=!release.RuntimeIncluded,elapsed_seconds=Math.Round(clock.Elapsed.TotalSeconds,1),destination=target});CaptureEvidence("update-complete.png");
            if(launch)Open();
        }catch(OperationCanceledException)when(token.IsCancellationRequested){status.Text="更新下载已暂停";detail.Text="进度已保存，点击继续即可续传。";start.Text="继续更新";Record(new{status="paused"});}
        catch(Exception e){Environment.ExitCode=1;status.Text="暂时未能完成更新";detail.Text=e.Message;start.Text="重试更新";Record(new{status="error",message=e.ToString()});CaptureEvidence("update-error.png");}
        finally{working=committing=false;start.Enabled=true;pause.Enabled=false;cancellation.Dispose();cancellation=null;if(smoke||closeAfter||automatic&&complete)Close();}
    }
    void Open(){try{var p=new ProcessStartInfo(Path.Combine(target,"Yiyan.exe")){UseShellExecute=false};p.Environment["PAPERBRIDGE_HOME"]=data;Process.Start(p);}catch(Exception e){detail.Text=e.Message;}}
    void ShowLicenses(){
        string Read(string name){using var stream=typeof(UpdateWindow).Assembly.GetManifestResourceStream("PaperBridgeUpdate."+name)!;using var reader=new StreamReader(stream);return reader.ReadToEnd();}
        using var form=new Form(){Text="译研 · 开源许可",Size=new Size(780,600),StartPosition=FormStartPosition.CenterParent};
        form.Controls.Add(new TextBox(){Text=Read("LICENSES.txt")+"\r\n\r\n"+Read("LICENSE.txt"),Multiline=true,ReadOnly=true,ScrollBars=ScrollBars.Both,Dock=DockStyle.Fill,Font=new Font("Consolas",10)});form.ShowDialog(this);
    }
    void Record(object value){if(evidence is null)return;Directory.CreateDirectory(evidence);File.WriteAllText(Path.Combine(evidence,"WINDOWS-UPDATE-REPORT.json"),JsonSerializer.Serialize(value,AppRelease.Json));}
    void CaptureEvidence(string file){if(evidence is null)return;Directory.CreateDirectory(evidence);using var bitmap=new Bitmap(Width,Height);DrawToBitmap(bitmap,new Rectangle(0,0,Width,Height));bitmap.Save(Path.Combine(evidence,file));}
}
