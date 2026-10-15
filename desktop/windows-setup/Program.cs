using System.Diagnostics;
using System.Drawing.Text;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace PaperBridgeSetup;

internal static class Program
{
    [STAThread]
    static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        Application.SetCompatibleTextRenderingDefault(true);
        Application.Run(new SetupWindow(args));
    }
}

internal sealed class SetupWindow : Form
{
    readonly Edition[] editions = Packages.Load();
    readonly Color green = Color.FromArgb(40, 101, 80), ink = Color.FromArgb(28, 55, 47);
    readonly RadioButton standard = new() { Text = "4B 标准版", Checked = true, AutoSize = true };
    readonly RadioButton precision = new() { Text = "14B 精译版", AutoSize = true };
    readonly TextBox destination = new() { Dock = DockStyle.Fill };
    readonly CheckBox clearCache = new() { Text = "装好后清理下载缓存", Checked = true, AutoSize = true };
    readonly CheckBox openApp = new() { Text = "安装完成后打开译研", Checked = true, AutoSize = true };
    readonly Label status = new() { AutoSize = false, Dock = DockStyle.Top, Height = 29 };
    readonly Label detail = new() { AutoSize = false, Dock = DockStyle.Top, Height = 40 };
    readonly ProgressBar bar = new() { Dock = DockStyle.Bottom, Height = 11, Maximum = 1000 };
    readonly Button start = new() { Text = "下载并安装 4B", Width = 300, Height = 46 };
    readonly Button pause = new() { Text = "暂停下载", Width = 112, Height = 46, Enabled = false };
    readonly Button browse = new() { Text = "更改位置", Width = 90, Dock = DockStyle.Right };
    readonly PrivateFontCollection fonts = new();
    readonly HttpClient http = new(new HttpClientHandler { MaxConnectionsPerServer = 3 }) { Timeout = TimeSpan.FromMinutes(2) };
    readonly string cacheRoot = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "PaperBridge", "InstallerCache");
    readonly string? smokeProfile, evidence, preview;
    readonly Stopwatch elapsed = new();
    readonly object progressLock = new();
    readonly StringBuilder log = new();
    CancellationTokenSource? cancellation;
    long[] positions = [];
    long lastBytes;
    long lastUpdate;
    double speed;
    bool working, installing, installed, closeAfterPause;
    IntPtr fontMemory;
    FileStream? installationLock;

    Edition Selected => editions.Single(e => e.Profile == (precision.Checked ? "precision" : "standard"));
    string Cache => Path.Combine(cacheRoot, "1.6.0", Selected.Profile);

    public SetupWindow(string[] args)
    {
        string? Option(string name) { int i = Array.IndexOf(args, name); return i >= 0 && i + 1 < args.Length ? args[i + 1] : null; }
        smokeProfile = Option("--install-smoke"); evidence = Option("--evidence"); preview = Option("--preview-smoke");
        if (smokeProfile is not null && (evidence is null || Option("--destination") is null || Option("--cache") is null))
            throw new ArgumentException("Smoke mode needs explicit evidence, destination and cache directories");
        if (Option("--cache") is string customCache && smokeProfile is not null) cacheRoot = Path.GetFullPath(customCache);
        using var stream = typeof(SetupWindow).Assembly.GetManifestResourceStream("PaperBridgeSetup.UiFont.ttf")!;
        using var memory = new MemoryStream(); stream.CopyTo(memory); var bytes = memory.ToArray();
        fontMemory = Marshal.AllocCoTaskMem(bytes.Length); Marshal.Copy(bytes, 0, fontMemory, bytes.Length);
        fonts.AddMemoryFont(fontMemory, bytes.Length);
        Font = MakeFont(10.5f); ForeColor = ink; BackColor = Color.FromArgb(248, 250, 247);
        Text = "译研 · 一键下载安装"; ClientSize = new Size(820, 700); MinimumSize = new Size(800, 720);
        AutoScaleMode = AutoScaleMode.Dpi; StartPosition = FormStartPosition.CenterScreen;
        Icon = System.Drawing.Icon.ExtractAssociatedIcon(Environment.ProcessPath!);
        var root = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(26), RowCount = 8, ColumnCount = 1 };
        foreach (int h in new[] { 76, 132, 36, 66, 44, 98, 62, 34 }) root.RowStyles.Add(new RowStyle(SizeType.Absolute, h));
        Controls.Add(root);
        var header = new Panel { Dock = DockStyle.Fill };
        header.Controls.Add(new Label { Text = "选择模型，接下来交给译研。", Location = new Point(0, 43), AutoSize = true, ForeColor = Color.DimGray });
        header.Controls.Add(new Label { Text = "译研 · 一键安装", Font = MakeFont(23), ForeColor = green, AutoSize = true });
        root.Controls.Add(header, 0, 0);
        var choices = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 1 };
        choices.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50)); choices.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        choices.Controls.Add(Card(standard, "日常阅读，轻巧易用\n下载约 4.07 GB · 最低 16 GB 内存\nNVIDIA 加速：显存 6 GB 起"), 0, 0);
        choices.Controls.Add(Card(precision, "复杂长句与专业表达\n下载约 10.49 GB · 最低 24 GB 内存\nNVIDIA 加速：显存 12 GB 起"), 1, 0);
        root.Controls.Add(choices, 0, 1);
        root.Controls.Add(new Label { Text = "两版均支持 CPU。模型、字体与排版环境全部装好，之后直接离线用。", AutoSize = true, Padding = new Padding(0, 8, 0, 0), ForeColor = Color.DimGray }, 0, 2);
        var pathPanel = new Panel { Dock = DockStyle.Fill, Padding = new Padding(0, 25, 0, 9) };
        pathPanel.Controls.Add(new Label { Text = "安装位置", AutoSize = true, Location = new Point(0, 0) });
        destination.Text = Option("--destination") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Yiyan");
        pathPanel.Controls.Add(destination); pathPanel.Controls.Add(browse); root.Controls.Add(pathPanel, 0, 3);
        browse.Click += (_, _) => { using var picker = new FolderBrowserDialog { Description = "选择译研安装位置", UseDescriptionForTitle = true, SelectedPath = destination.Text }; if (picker.ShowDialog(this) == DialogResult.OK) destination.Text = picker.SelectedPath; };
        var options = new FlowLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(0, 7, 0, 0) };
        options.Controls.Add(clearCache); options.Controls.Add(openApp); root.Controls.Add(options, 0, 4);
        var progress = new Panel { Dock = DockStyle.Fill, Padding = new Padding(0, 4, 0, 8) };
        status.Text = "准备就绪"; status.Font = MakeFont(12); status.ForeColor = green;
        detail.Text = "首次安装需要联网。下载可暂停，重新打开后能接着下载。"; detail.ForeColor = Color.DimGray;
        progress.Controls.Add(bar); progress.Controls.Add(detail); progress.Controls.Add(status); root.Controls.Add(progress, 0, 5);
        var actions = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.RightToLeft, Padding = new Padding(0, 6, 0, 0) };
        start.BackColor = green; start.ForeColor = Color.White; start.FlatStyle = FlatStyle.Flat; start.FlatAppearance.BorderSize = 0;
        pause.FlatStyle = FlatStyle.Flat; pause.FlatAppearance.BorderColor = Color.FromArgb(200, 216, 202);
        actions.Controls.Add(start); actions.Controls.Add(pause); root.Controls.Add(actions, 0, 6);
        var footer = new Panel { Dock = DockStyle.Fill };
        footer.Controls.Add(new Label { Text = "译研 PaperBridge · 安装向导 1.7", AutoSize = true, ForeColor = Color.DimGray, Location = new Point(0, 5) });
        var license = new LinkLabel { Text = "开源许可", AutoSize = true, Dock = DockStyle.Right, LinkColor = green };
        license.LinkClicked += (_, _) => ShowLicenses(); footer.Controls.Add(license); root.Controls.Add(footer, 0, 7);
        standard.CheckedChanged += (_, _) => { if (standard.Checked && precision.Checked) precision.Checked = false; RefreshChoice(); };
        precision.CheckedChanged += (_, _) => { if (precision.Checked && standard.Checked) standard.Checked = false; RefreshChoice(); };
        // The cards have different parents; make them one explicit exclusive choice.
        start.Click += async (_, _) => { if (installed) LaunchApp(); else await Install(); };
        pause.Click += (_, _) => cancellation?.Cancel();
        FormClosing += (_, e) => { if (working) { e.Cancel = true; if (!installing) { closeAfterPause = true; cancellation?.Cancel(); } else detail.Text = "正在安装，请等待完成后关闭向导。"; } };
        FormClosed += (_, _) => { http.Dispose(); installationLock?.Dispose(); fonts.Dispose(); if (fontMemory != IntPtr.Zero) Marshal.FreeCoTaskMem(fontMemory); };
        Shown += async (_, _) => {
            if (preview is not null)
            {
                standard.Checked = true; await Task.Delay(300); Capture(preview, "windows-setup-4b.png");
                precision.Checked = true; await Task.Delay(300); Capture(preview, "windows-setup-14b.png"); Close();
            }
            else if (smokeProfile is not null)
            {
                precision.Checked = smokeProfile == "precision"; standard.Checked = !precision.Checked; openApp.Checked = false;
                await Task.Delay(300); Capture(evidence!, "setup-selected.png"); start.PerformClick();
            }
        };
    }

    Font MakeFont(float size) => new(fonts.Families[0], size, FontStyle.Regular, GraphicsUnit.Point);
    Panel Card(RadioButton choice, string description)
    {
        var card = new Panel { Dock = DockStyle.Fill, BackColor = Color.FromArgb(234, 241, 231), Padding = new Padding(17, 12, 10, 8), Margin = new Padding(0, 0, 10, 4) };
        choice.Font = MakeFont(14); choice.ForeColor = green; choice.Dock = DockStyle.Top; choice.Height = 31;
        var text = new Label { Text = description, Dock = DockStyle.Fill, Padding = new Padding(0, 6, 0, 0) };
        text.Click += (_, _) => choice.Checked = true; card.Click += (_, _) => choice.Checked = true;
        card.Controls.Add(text); card.Controls.Add(choice); return card;
    }

    void RefreshChoice() { if (!standard.Checked && !precision.Checked) return; installed = false; if (!working) start.Text = "下载并安装 " + (precision.Checked ? "14B" : "4B"); }
    void EnableChoices(bool enabled) { standard.Parent!.Enabled = precision.Parent!.Enabled = enabled; standard.Enabled = precision.Enabled = destination.Enabled = browse.Enabled = clearCache.Enabled = openApp.Enabled = enabled; }
    void Capture(string folder, string name) { Directory.CreateDirectory(folder); using var bitmap = new Bitmap(Width, Height); DrawToBitmap(bitmap, new Rectangle(0, 0, Width, Height)); bitmap.Save(Path.Combine(folder, name), System.Drawing.Imaging.ImageFormat.Png); }
    void WriteState(object state)
    {
        if (evidence is null) return;
        Directory.CreateDirectory(evidence);
        string path = Path.Combine(evidence, "setup-progress.json"), temp = path + ".tmp";
        File.WriteAllText(temp, JsonSerializer.Serialize(state)); File.Move(temp, path, true);
    }

    async Task Install()
    {
        if (working) return;
        working = true; installing = false; installed = false; EnableChoices(false); start.Enabled = false; pause.Enabled = true;
        cancellation = new CancellationTokenSource(); var token = cancellation.Token;
        var edition = Selected; string folder = Cache; int installerExit = -1;
        try
        {
            string target = InstallPaths.ValidateDestination(destination.Text); destination.Text = target;
            Directory.CreateDirectory(cacheRoot);
            try { installationLock = new FileStream(Path.Combine(cacheRoot, ".installer.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None); }
            catch (IOException) { throw new IOException("另一个安装向导正在工作，请先完成或关闭它再继续。"); }
            InstallPaths.CheckSpace(edition, folder, target);
            Directory.CreateDirectory(target);
            using (new FileStream(Path.Combine(target, ".paperbridge-write-test-" + Guid.NewGuid().ToString("N")), FileMode.CreateNew, FileAccess.Write, FileShare.None, 1, FileOptions.DeleteOnClose)) { }
            foreach (var process in Process.GetProcessesByName("Yiyan"))
            {
                using (process)
                {
                    string? path = null; try { path = process.MainModule?.FileName; } catch { }
                    if (path is not null && string.Equals(Path.GetFullPath(path), Path.Combine(target, "Yiyan.exe"), StringComparison.OrdinalIgnoreCase))
                        throw new IOException("请先退出正在运行的译研，再点击继续安装。");
                }
            }
            positions = new long[edition.Files.Length]; elapsed.Restart(); lastUpdate = 0; lastBytes = 0; speed = 0;
            var reporter = new Progress<(long bytes, string stage)>(p => {
                if (installing || !working) return;
                double fraction = (double)p.bytes / edition.TotalBytes; bar.Style = ProgressBarStyle.Continuous; bar.Value = Math.Clamp((int)(fraction * 1000), 0, 1000);
                status.Text = $"{p.stage} {edition.Label} · {fraction:P0}";
                detail.Text = $"{p.bytes / 1e9:0.00} / {edition.TotalBytes / 1e9:0.00} GB" + (speed > 0 ? $" · {speed / 1e6:0.0} MB/s" : "");
                WriteState(new { stage = "downloading", profile = edition.Profile, bytes = p.bytes, total_bytes = edition.TotalBytes, elapsed_seconds = elapsed.Elapsed.TotalSeconds });
            });
            var downloader = new Downloader(http);
            await Parallel.ForEachAsync(Enumerable.Range(0, edition.Files.Length), new ParallelOptions { MaxDegreeOfParallelism = 2, CancellationToken = token }, async (index, ct) => {
                await downloader.DownloadAsync(edition.Files[index], folder, update => {
                    Interlocked.Exchange(ref positions[index], update.Bytes);
                    lock (progressLock)
                    {
                        long now = elapsed.ElapsedMilliseconds;
                        if (now - lastUpdate < 250 && update.Bytes != edition.Files[index].Bytes) return;
                        long total = positions.Sum();
                        if (now > lastUpdate && total >= lastBytes) speed = (total - lastBytes) * 1000.0 / Math.Max(1, now - lastUpdate);
                        lastUpdate = now; lastBytes = total; ((IProgress<(long, string)>)reporter).Report((total, update.Stage));
                    }
                }, ct);
            });
            token.ThrowIfCancellationRequested();
            // Drain the queued progress callbacks before presenting installation state.
            await Task.Yield(); installing = true; pause.Enabled = false; status.Text = "下载与校验已完成，正在安装…";
            detail.Text = "正在写入模型、阅读组件与排版环境，请保持向导打开。"; bar.Style = ProgressBarStyle.Marquee;
            WriteState(new { stage = "installing", profile = edition.Profile, files_verified = edition.Files.Length });
            string setup = Path.Combine(folder, edition.Files.Single(f => f.Name.EndsWith(".exe")).Name);
            var info = new ProcessStartInfo(setup) { UseShellExecute = false, CreateNoWindow = true };
            foreach (string arg in new[] { "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RESTARTEXITCODE=3010", "/NOCLOSEAPPLICATIONS", "/NORESTARTAPPLICATIONS", "/SP-", "/DIR=" + target, "/LOG=" + Path.Combine(folder, "installation.log") }) info.ArgumentList.Add(arg);
            using (var process = Process.Start(info) ?? throw new IOException("安装程序未能启动，请重试。"))
            { await process.WaitForExitAsync(); installerExit = process.ExitCode; }
            if (installerExit is not (0 or 3010)) throw new IOException($"安装未完成（{installerExit}）。请检查安装位置后重试，已下载的文件会保留。");
            if (!File.Exists(Path.Combine(target, "Yiyan.exe"))) throw new IOException("安装文件尚未准备完成，请重试。");
            string model = Path.Combine(target, "Models", edition.Profile == "precision" ? "qwen3-14b" : "qwen3-4b", edition.ModelFile);
            if (!File.Exists(model) || new FileInfo(model).Length != edition.ModelBytes) throw new IOException("模型文件尚未安装完整，请点击继续重试。");
            ApplyEditionPreference(target);
            if (clearCache.Checked)
                foreach (var f in edition.Files) { try { File.Delete(Path.Combine(folder, f.Name)); File.Delete(Path.Combine(folder, f.Name + ".partial")); } catch (IOException) { } catch (UnauthorizedAccessException) { } }
            bool cleaned = edition.Files.All(f => !File.Exists(Path.Combine(folder, f.Name)));
            installed = true; bar.Style = ProgressBarStyle.Continuous; bar.Value = 1000; status.Text = "安装完成，可以直接离线翻译。";
            detail.Text = installerExit == 3010 ? "Windows 提示需要重启，请重启电脑后打开译研。" : "模型已就绪，打开译研，导入论文即可开始。";
            start.Text = "打开译研";
            start.Enabled = true;
            var report = new { status = "complete", profile = edition.Profile, installer_exit_code = installerExit, all_files_verified = true,
                files_verified = edition.Files.Length, download_bytes = edition.TotalBytes, automatic_install = true,
                cache_cleaned = cleaned, destination = target, elapsed_seconds = Math.Round(elapsed.Elapsed.TotalSeconds, 1) };
            WriteState(report);
            if (evidence is not null) { File.WriteAllText(Path.Combine(evidence, "SETUP-REPORT.json"), JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true })); Capture(evidence, "setup-complete.png"); }
            if (openApp.Checked && installerExit == 0) LaunchApp();
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { status.Text = "下载已暂停"; detail.Text = "进度已保存，点击继续即可接着下载。"; start.Text = "继续下载并安装"; WriteState(new { status = "paused", profile = edition.Profile }); }
        catch (Exception error)
        {
            status.Text = "暂时未能完成安装"; detail.Text = error is UnauthorizedAccessException ? "所选位置无法写入，请更换安装文件夹。" : error.Message;
            start.Text = "继续下载并安装"; log.AppendLine(error.ToString()); WriteState(new { status = "error", profile = edition.Profile, message = error.Message });
            if (evidence is not null) { Directory.CreateDirectory(evidence); File.WriteAllText(Path.Combine(evidence, "setup-error.log"), error.ToString()); Capture(evidence, "setup-error.png"); Environment.ExitCode = 1; }
        }
        finally
        {
            working = installing = false; EnableChoices(true); start.Enabled = true; pause.Enabled = false;
            installationLock?.Dispose(); installationLock = null; cancellation.Dispose(); cancellation = null;
            if (smokeProfile is not null || closeAfterPause) { await Task.Delay(500); Close(); }
        }
    }

    void LaunchApp() { try { Process.Start(new ProcessStartInfo(Path.Combine(destination.Text, "Yiyan.exe")) { UseShellExecute = true }); } catch (Exception e) { detail.Text = "请从桌面打开译研。"; log.AppendLine(e.ToString()); } }
    static void ApplyEditionPreference(string target)
    {
        // Match the known base source before adding the chosen-edition preference.
        var assembly = typeof(SetupWindow).Assembly;
        using var marker = assembly.GetManifestResourceStream("PaperBridgeSetup.base-module.json")!;
        using var metadata = JsonDocument.Parse(marker);
        string path = Path.Combine(target, "Engine", "paperbridge", "windows_models.py");
        string original = File.ReadAllText(path, Encoding.UTF8).Replace("\r\n", "\n");
        string digest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(original))).ToLowerInvariant();
        using var source = assembly.GetManifestResourceStream("PaperBridgeSetup.windows_models.py")!;
        using var reader = new StreamReader(source); string replacement = reader.ReadToEnd().Replace("\r\n", "\n");
        string replacementHash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(replacement))).ToLowerInvariant();
        if (digest != metadata.RootElement.GetProperty("before_sha256").GetString() && digest != replacementHash)
            throw new IOException("安装组件版本与校验清单不符，请重试。");
        File.WriteAllText(path + ".new", replacement, new UTF8Encoding(false)); File.Move(path + ".new", path, true);
    }
    void ShowLicenses()
    {
        using var stream = typeof(SetupWindow).Assembly.GetManifestResourceStream("PaperBridgeSetup.LICENSES.txt")!;
        using var reader = new StreamReader(stream);
        using var agpl = typeof(SetupWindow).Assembly.GetManifestResourceStream("PaperBridgeSetup.AGPl.txt")!;
        using var agplReader = new StreamReader(agpl);
        using var form = new Form { Text = "译研 · 开源许可", Size = new Size(780, 600), StartPosition = FormStartPosition.CenterParent };
        form.Controls.Add(new TextBox { Text = reader.ReadToEnd() + "\r\n\r\n" + agplReader.ReadToEnd(), Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Both, Dock = DockStyle.Fill, Font = new Font("Consolas", 10) }); form.ShowDialog(this);
    }
}
