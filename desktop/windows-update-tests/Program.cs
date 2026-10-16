using System.IO.Compression;
using System.Net;
using System.Net.Http.Headers;
using System.Text.Json;
using PaperBridgeSetup;
using PaperBridgeUpdate;

internal static class Program
{
    static void Check(bool value,string message){if(!value)throw new Exception(message);}
    static async Task Reject<T>(Func<Task> operation)where T:Exception{try{await operation();}catch(T){return;}throw new Exception("Expected "+typeof(T).Name);}
    static void Seed(string target){
        foreach(string p in new[]{"Runtime/Python","Models/qwen3-4b","Models/qwen3-14b","data/jobs","Engine/.cache/babeldoc","Engine/release-assets/vendor-sources"})Directory.CreateDirectory(Path.Combine(target,p));
        foreach(var item in new Dictionary<string,string>{{"Yiyan.exe","old launcher"},{"Runtime/Python/python.exe","unchanged runtime"},{"Engine/old.py","old code"},{"Models/qwen3-4b/test.gguf","GGUF four protected"},{"Models/qwen3-14b/test.gguf","GGUF fourteen protected"},{"data/jobs/original.pdf","protected source"},{"data/jobs/translated.pdf","protected translation"},{"settings.json","protected settings"},{"Engine/.cache/babeldoc/ready.json","pinned layout"},{"Engine/release-assets/vendor-sources/license.tar.gz","corresponding runtime source"},{"BUILD-REPORT.json","{\"version\":\"1.6.0\",\"edition\":\"precision\"}"}})File.WriteAllText(Path.Combine(target,item.Key),item.Value);
    }
    static async Task<(AppRelease release,string archive)> Package(string folder,Dictionary<string,string>? extras=null,string reportVersion="1.9.0"){
        var files=new Dictionary<string,string>{{"Yiyan/Engine/new.py","new application code"},{"Yiyan/Updater/Yiyan-Updater.exe","new updater"},{"Yiyan/Yiyan.exe","new launcher"},{"Yiyan/BUILD-REPORT.json",JsonSerializer.Serialize(new{version=reportVersion})}};
        if(extras!=null)foreach(var item in extras)files.Add(item.Key,item.Value);
        string archive=Path.Combine(folder,"package.zip");using(var zip=ZipFile.Open(archive,ZipArchiveMode.Create))foreach(var item in files){using var writer=new StreamWriter(zip.CreateEntry(item.Key).Open());writer.Write(item.Value);}
        using var z=ZipFile.OpenRead(archive);long expanded=z.Entries.Sum(e=>e.Length);string name="Yiyan-1.9.0-Windows-x64-App.zip";
        return(new(1,"1.9.0","windows-x64",new(name,new FileInfo(archive).Length,await Downloader.HashAsync(archive),"https://github.com/hengyuwu-dot/yiyan-paperbridge/releases/download/v1.9.0-windows-update/"+name),["Engine","Updater","Yiyan.exe","BUILD-REPORT.json"],expanded,"1.5.0",false),archive);
    }
    static void Preserved(string p){
        Check(File.ReadAllText(Path.Combine(p,"Models/qwen3-4b/test.gguf"))=="GGUF four protected","4B modified");
        Check(File.ReadAllText(Path.Combine(p,"Models/qwen3-14b/test.gguf"))=="GGUF fourteen protected","14B modified");
        Check(File.ReadAllText(Path.Combine(p,"data/jobs/original.pdf"))=="protected source","Original changed");
        Check(File.ReadAllText(Path.Combine(p,"data/jobs/translated.pdf"))=="protected translation","Translation changed");
        Check(File.ReadAllText(Path.Combine(p,"settings.json"))=="protected settings","Settings changed");
        Check(File.ReadAllText(Path.Combine(p,"Runtime/Python/python.exe"))=="unchanged runtime","Runtime changed");
    }
    static async Task Main(){
        string root=Path.Combine(Path.GetTempPath(),"paperbridge-update-tests-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(root);int count=0;
        async Task Run(string title,Func<string,Task> test){string p=Path.Combine(root,(++count).ToString());Directory.CreateDirectory(p);await test(p);Console.WriteLine("PASS "+title);}
        try{
            await Run("Only versioned app archives from the correct repository are accepted",async p=>{var x=await Package(p);x.release.Validate();await Reject<InvalidDataException>(()=>{(x.release with{Archive=x.release.Archive with{Url="https://example.com/update.zip"}}).Validate();return Task.CompletedTask;});});
            await Run("Model and user-data roots cannot enter an application update",async p=>{var x=await Package(p);foreach(string c in new[]{"Models","data","settings.json","../Engine"})await Reject<InvalidDataException>(()=>{(x.release with{Components=x.release.Components.Append(c).ToArray()}).Validate();return Task.CompletedTask;});});
            await Run("Update preserves both model folders, documents, settings and runtime",async p=>{string app=Path.Combine(p,"app");Seed(app);var x=await Package(p);await UpdateTransaction.Apply(x.release,x.archive,app);Preserved(app);Check(File.ReadAllText(Path.Combine(app,"Yiyan.exe"))=="new launcher","Launcher not updated");using var report=JsonDocument.Parse(File.ReadAllText(Path.Combine(app,"BUILD-REPORT.json")));Check(report.RootElement.GetProperty("edition").GetString()=="precision","14B default lost");Check(File.Exists(Path.Combine(app,"Engine/.cache/babeldoc/ready.json")),"Layout lost");Check(File.Exists(Path.Combine(app,"Engine/release-assets/vendor-sources/license.tar.gz")),"Runtime sources lost");});
            await Run("A failed replacement restores the original application",async p=>{string app=Path.Combine(p,"app");Seed(app);var x=await Package(p);await Reject<IOException>(()=>UpdateTransaction.Apply(x.release,x.archive,app,beforeCommit:i=>{if(i==1)throw new IOException("injected file lock");}));Preserved(app);Check(File.ReadAllText(Path.Combine(app,"Yiyan.exe"))=="old launcher"&&File.Exists(Path.Combine(app,"Engine/old.py")),"Rollback incomplete");});
            foreach(var bad in new[]{"Yiyan/Engine/../../Models/evil.txt","Yiyan/Engine/a:stream","Yiyan/Engine/CON.txt","Yiyan/Engine/new.py.","Yiyan/Engine/weights.gguf","Yiyan/Engine/model.safetensors","Yiyan/engine/NEW.py"})await Run("Reject unsafe archive path "+bad,async p=>{string app=Path.Combine(p,"app");Seed(app);var x=await Package(p,new(){{bad,"untrusted bytes"}});await Reject<InvalidDataException>(()=>UpdateTransaction.Apply(x.release,x.archive,app));Preserved(app);Check(File.ReadAllText(Path.Combine(app,"Yiyan.exe"))=="old launcher","Unsafe update committed");});
            await Run("Wrong archive digest cannot replace application files",async p=>{string app=Path.Combine(p,"app");Seed(app);var x=await Package(p);await Reject<InvalidDataException>(()=>UpdateTransaction.Apply(x.release with{Archive=x.release.Archive with{Sha256=new string('0',64)}},x.archive,app));Preserved(app);});
            await Run("Unexpected expanded bytes are rejected before commit",async p=>{string app=Path.Combine(p,"app");Seed(app);var x=await Package(p);await Reject<InvalidDataException>(()=>UpdateTransaction.Apply(x.release with{ExpandedBytes=x.release.ExpandedBytes+1},x.archive,app));Preserved(app);});
            await Run("Staged application version must match the published manifest",async p=>{string app=Path.Combine(p,"app");Seed(app);var x=await Package(p,reportVersion:"1.8.0");await Reject<InvalidDataException>(()=>UpdateTransaction.Apply(x.release,x.archive,app));Preserved(app);});
            await Run("A newer installed version cannot be downgraded",async p=>{string app=Path.Combine(p,"app");Seed(app);File.WriteAllText(Path.Combine(app,"BUILD-REPORT.json"),"{\"version\":\"2.0.0\"}");var x=await Package(p);await Reject<IOException>(()=>UpdateTransaction.Apply(x.release,x.archive,app));Preserved(app);});
            await Run("Cancellation keeps the old application usable",async p=>{string app=Path.Combine(p,"app");Seed(app);var x=await Package(p);using var stop=new CancellationTokenSource();stop.Cancel();await Reject<OperationCanceledException>(()=>UpdateTransaction.Apply(x.release,x.archive,app,stop.Token));Preserved(app);});
            await Run("Runtime replacement requires explicit manifest permission",async p=>{var x=await Package(p);await Reject<InvalidDataException>(()=>{(x.release with{Components=x.release.Components.Append("Runtime").ToArray()}).Validate();return Task.CompletedTask;});});
            Console.WriteLine(count+" update transaction checks passed");
        }finally{Directory.Delete(root,true);}
    }
}
