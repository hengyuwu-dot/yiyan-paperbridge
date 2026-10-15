using System.Diagnostics;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

internal static class Program
{
    [STAThread]
    static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new PaperWindow(args.Contains("--smoke-test")));
    }
}

internal sealed class PaperWindow : Form
{
    readonly WebView2 view = new() { Dock = DockStyle.Fill };
    readonly Label loading = new() { Text = "正在准备论文工作室…", Dock = DockStyle.Fill,
        TextAlign = ContentAlignment.MiddleCenter, Font = new Font("Microsoft YaHei UI", 16) };
    readonly string data = Environment.GetEnvironmentVariable("PAPERBRIDGE_HOME") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "PaperBridge");
    readonly HttpClient http = new(new HttpClientHandler { UseProxy = false }) { Timeout = TimeSpan.FromSeconds(3) };
    readonly StringBuilder log = new();
    readonly bool smoke;
    Process? server;
    string stateFile = "";
    string origin = "";
    bool closing;

    public PaperWindow(bool smokeTest)
    {
        smoke = smokeTest;
        Text = "译研 · SCI 论文翻译";
        Size = new Size(1380, 920);
        MinimumSize = new Size(960, 680);
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.FromArgb(248, 249, 245);
        var icon = System.Drawing.Icon.ExtractAssociatedIcon(Environment.ProcessPath!);
        if (icon != null) Icon = icon;
        Controls.Add(view); Controls.Add(loading);
        Shown += async (_, _) => await StartStudio();
        FormClosing += async (_, e) => {
            if (closing) return;
            e.Cancel = true;
            bool busy = false;
            try { var s = JsonDocument.Parse(await http.GetStringAsync(origin + "/api/desktop/status")); busy = s.RootElement.GetProperty("busy").GetBoolean(); }
            catch { }
            if (busy && MessageBox.Show("论文正在处理，退出会停止当前任务，已完成的内容会保留。现在退出吗？", "退出译研", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
            closing = true; StopServer(); Close();
        };
        FormClosed += (_, _) => { StopServer(); http.Dispose(); };
    }

    async Task StartStudio()
    {
        try
        {
            string root = AppContext.BaseDirectory;
            string? browserFolder = File.Exists(Path.Combine(root, "Runtime", "WebView2", "msedgewebview2.exe")) ? Path.Combine(root, "Runtime", "WebView2") : null;
            _ = CoreWebView2Environment.GetAvailableBrowserVersionString(browserFolder);
            Directory.CreateDirectory(data);
            stateFile = Path.Combine(data, "tmp", "desktop-" + Guid.NewGuid().ToString("N") + ".json");
            Directory.CreateDirectory(Path.GetDirectoryName(stateFile)!);
            var start = new ProcessStartInfo(Path.Combine(root, "Runtime", "Python", "python.exe")) {
                WorkingDirectory = Path.Combine(root, "Engine"), UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardOutput = true, RedirectStandardError = true, StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8 };
            foreach (string arg in new[] { "-X", "utf8", "-m", "paperbridge.windows_bootstrap", "--parent-pid", Environment.ProcessId.ToString(), "--state-file", stateFile }) start.ArgumentList.Add(arg);
            start.Environment["PAPERBRIDGE_HOME"] = data;
            start.Environment["PAPERBRIDGE_LLAMA_DIR"] = Path.Combine(root, "Runtime", "llama");
            start.Environment["PAPERBRIDGE_WINDOWS_BUNDLE"] = root;
            start.Environment["PYTHONUTF8"] = "1";
            server = new Process { StartInfo = start };
            server.OutputDataReceived += (_, e) => { if (e.Data != null) lock (log) log.AppendLine(e.Data); };
            server.ErrorDataReceived += (_, e) => { if (e.Data != null) lock (log) log.AppendLine(e.Data); };
            server.Start(); server.BeginOutputReadLine(); server.BeginErrorReadLine();
            DateTime deadline = DateTime.UtcNow.AddMinutes(4);
            while (DateTime.UtcNow < deadline)
            {
                if (server.HasExited) throw new Exception("本地服务启动失败。" + log.ToString()[..Math.Min(log.Length, 1500)]);
                try
                {
                    if (File.Exists(stateFile)) {
                        var state = JsonDocument.Parse(await File.ReadAllTextAsync(stateFile));
                        int port = state.RootElement.GetProperty("port").GetInt32();
                        if (port < 8765 || port > 8775) throw new Exception("本机服务端口无效");
                        string candidate = "http://127.0.0.1:" + port;
                        var probe = JsonDocument.Parse(await http.GetStringAsync(candidate + "/api/desktop/status"));
                        if (probe.RootElement.GetProperty("pid").GetInt32() == server.Id &&
                            probe.RootElement.GetProperty("instance_id").GetString() == state.RootElement.GetProperty("instance_id").GetString()) { origin = candidate; break; }
                    }
                }
                catch (HttpRequestException) { }
                catch (JsonException) { }
                catch (IOException) { }
                await Task.Delay(200);
            }
            if (origin.Length == 0) throw new Exception("启动等待超时，请关闭后重新打开译研。");
            var environment = await CoreWebView2Environment.CreateAsync(browserExecutableFolder: browserFolder, userDataFolder: Path.Combine(data, "WebView2"));
            await view.EnsureCoreWebView2Async(environment);
            view.CoreWebView2.Settings.UserAgent += " PaperBridgeDesktop/1.5 Windows";
            view.CoreWebView2.Settings.AreDevToolsEnabled = false;
            view.CoreWebView2.NavigationStarting += (_, e) => {
                if (Uri.TryCreate(e.Uri, UriKind.Absolute, out var uri) && uri.GetLeftPart(UriPartial.Authority) == origin) return;
                e.Cancel = true;
            };
            view.CoreWebView2.NewWindowRequested += (_, e) => {
                e.Handled = true;
                if (Uri.TryCreate(e.Uri, UriKind.Absolute, out var uri) && uri.GetLeftPart(UriPartial.Authority) == origin) view.CoreWebView2.Navigate(e.Uri);
            };
            view.CoreWebView2.DownloadStarting += (_, e) => {
                using var picker = new SaveFileDialog { FileName = Path.GetFileName(e.ResultFilePath), Filter = "所有文件|*.*", OverwritePrompt = true };
                if (picker.ShowDialog(this) == DialogResult.OK) e.ResultFilePath = picker.FileName;
                else e.Cancel = true;
                e.Handled = true;
            };
            view.CoreWebView2.NavigationCompleted += async (_, e) => {
                if (!e.IsSuccess) return;
                loading.Visible = false;
                if (smoke) {
                    await Task.Delay(1500);
                    using var capture = File.Create(Path.Combine(data, "windows-ui-smoke.png"));
                    await view.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, capture);
                    await view.CoreWebView2.ExecuteScriptAsync("document.getElementById('modelBadge').click()");
                    await Task.Delay(800);
                    using var modelCapture = File.Create(Path.Combine(data, "windows-models-smoke.png"));
                    await view.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, modelCapture);
                    var status = JsonDocument.Parse(await http.GetStringAsync(origin + "/api/status"));
                    await File.WriteAllTextAsync(Path.Combine(data, "windows-ui-smoke.json"), JsonSerializer.Serialize(new { loaded = true, engine = "WebView2", bundled_browser = browserFolder != null, origin, status = status.RootElement.Clone() }));
                    closing = true; StopServer(); Close();
                }
            };
            view.CoreWebView2.Navigate(origin);
        }
        catch (WebView2RuntimeNotFoundException)
        {
            MessageBox.Show("请先安装 Microsoft Edge WebView2 Runtime，再打开译研。下载地址已写在 Windows 安装教程中。", "准备 Windows 阅读组件", MessageBoxButtons.OK, MessageBoxIcon.Information);
            StopServer(); Environment.ExitCode = 1; closing = true; Close();
        }
        catch (Exception e)
        {
            Directory.CreateDirectory(data);
            await File.WriteAllTextAsync(Path.Combine(data, "desktop-error.log"), e + "\n" + log);
            MessageBox.Show(e.Message, "译研启动提示", MessageBoxButtons.OK, MessageBoxIcon.Error);
            StopServer(); Environment.ExitCode = 1; closing = true; Close();
        }
    }

    void StopServer()
    {
        try { if (server is { HasExited: false }) { server.Kill(entireProcessTree: true); server.WaitForExit(5000); } }
        catch (InvalidOperationException) { }
        catch (System.ComponentModel.Win32Exception) { }
        try { if (stateFile.Length > 0) File.Delete(stateFile); } catch (IOException) { }
    }
}
