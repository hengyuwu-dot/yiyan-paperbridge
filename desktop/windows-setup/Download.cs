using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace PaperBridgeSetup;

public sealed record Asset(string Name, long Bytes, string Sha256, string Url);
public sealed record Edition(string Profile, string Label, long DiskBudget, long InstalledBudget,
    string ModelFile, long ModelBytes, string ModelSha256, Asset[] Files)
{
    public long TotalBytes => Files.Sum(f => f.Bytes);
}

public static class Packages
{
    public static Edition[] Load()
    {
        using var stream = typeof(Packages).Assembly.GetManifestResourceStream("PaperBridgeSetup.packages.json")!;
        var editions = JsonSerializer.Deserialize<Edition[]>(stream, new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;
        Validate(editions);
        return editions;
    }

    public static void Validate(Edition[] editions)
    {
        if (editions.Length != 2 || !editions.Select(e => e.Profile).Order().SequenceEqual(new[] { "precision", "standard" }))
            throw new InvalidDataException("安装目录清单不完整");
        foreach (var e in editions)
        {
            var label = e.Profile == "precision" ? "14B" : "4B";
            var prefix = $"Yiyan-1.6.0-Windows-x64-Offline-{label}-Setup";
            int count = e.Profile == "precision" ? 6 : 3;
            var names = Enumerable.Range(1, count).Select(i => prefix + $"-{i}.bin").Append(prefix + ".exe").Order();
            if (!e.Files.Select(f => f.Name).Order().SequenceEqual(names)) throw new InvalidDataException("安装文件清单异常");
            foreach (var f in e.Files)
            {
                string expected = $"https://github.com/hengyuwu-dot/yiyan-paperbridge/releases/download/v1.6.0-windows-{label.ToLowerInvariant()}-offline/{f.Name}";
                if (f.Url != expected || f.Name != Path.GetFileName(f.Name) || f.Bytes <= 0 || !Regex.IsMatch(f.Sha256, "^[a-f0-9]{64}$"))
                    throw new InvalidDataException("安装文件校验信息异常");
            }
        }
    }
}

public readonly record struct Transfer(long Bytes, string Stage);

public sealed class Downloader(HttpClient http, Func<int, CancellationToken, Task>? retryDelay = null,
    Func<Asset,int,string>? chooseUrl = null, TimeSpan? networkTimeout = null)
{
    public static async Task<string> HashAsync(string path, CancellationToken token = default)
    {
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        await HashPrefix(path, hash, token);
        return Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant();
    }

    static async Task HashPrefix(string path, IncrementalHash hash, CancellationToken token)
    {
        await using var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 4 * 1024 * 1024, FileOptions.Asynchronous | FileOptions.SequentialScan);
        var buffer = new byte[4 * 1024 * 1024];
        int read;
        while ((read = await input.ReadAsync(buffer, token)) > 0) hash.AppendData(buffer, 0, read);
    }

    public async Task DownloadAsync(Asset asset, string folder, Action<Transfer>? progress, CancellationToken token)
    {
        Directory.CreateDirectory(folder);
        if (asset.Name != Path.GetFileName(asset.Name)) throw new InvalidDataException("安装文件名异常");
        string target = Path.Combine(folder, asset.Name), partial = target + ".partial";
        if (File.Exists(target))
        {
            progress?.Invoke(new(0, "正在校验已下载的文件"));
            if (new FileInfo(target).Length == asset.Bytes && await HashAsync(target, token) == asset.Sha256)
            { progress?.Invoke(new(asset.Bytes, "文件已校验")); return; }
            File.Delete(target);
        }
        for (int attempt = 0; ; attempt++)
        {
            token.ThrowIfCancellationRequested();
            try
            {
                long offset = File.Exists(partial) ? new FileInfo(partial).Length : 0;
                if (offset > asset.Bytes) { File.Delete(partial); offset = 0; }
                using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
                if (offset > 0)
                {
                    progress?.Invoke(new(offset, "正在准备断点续传"));
                    await HashPrefix(partial, hash, token);
                }
                if (offset < asset.Bytes)
                {
                    using var request = new HttpRequestMessage(HttpMethod.Get, chooseUrl?.Invoke(asset,attempt) ?? asset.Url);
                    if (offset > 0) request.Headers.Range = new RangeHeaderValue(offset, null);
                    using var headerTimeout=CancellationTokenSource.CreateLinkedTokenSource(token);headerTimeout.CancelAfter(networkTimeout??TimeSpan.FromSeconds(90));
                    using var response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, headerTimeout.Token);
                    headerTimeout.CancelAfter(Timeout.InfiniteTimeSpan);
                    response.EnsureSuccessStatusCode();
                    if (response.StatusCode == HttpStatusCode.PartialContent)
                    {
                        var range = response.Content.Headers.ContentRange;
                        if (range?.From != offset || range.To != asset.Bytes - 1 || range.Length != asset.Bytes)
                            throw new InvalidDataException("下载续传范围异常，请重试");
                    }
                    else if (response.StatusCode == HttpStatusCode.OK)
                    {
                        offset = 0; hash.GetHashAndReset(); // Server ignored Range; replace the partial instead of appending.
                    }
                    else throw new InvalidDataException("下载响应异常");
                    if (response.Content.Headers.ContentLength is long length && length != asset.Bytes - offset)
                        throw new InvalidDataException("下载文件大小与安装清单不符");
                    await using var input = await response.Content.ReadAsStreamAsync(token);
                    await using var output = new FileStream(partial, offset > 0 ? FileMode.Append : FileMode.Create,
                        FileAccess.Write, FileShare.None, 1024 * 1024, FileOptions.Asynchronous | FileOptions.SequentialScan);
                    var buffer = new byte[1024 * 1024];
                    using var idle = CancellationTokenSource.CreateLinkedTokenSource(token);
                    long received = offset;
                    while (true)
                    {
                        idle.CancelAfter(networkTimeout??TimeSpan.FromSeconds(90));
                        int read = await input.ReadAsync(buffer, idle.Token);
                        if (read == 0) break;
                        if (received + read > asset.Bytes) throw new InvalidDataException("下载文件超出清单大小");
                        await output.WriteAsync(buffer.AsMemory(0, read), token);
                        hash.AppendData(buffer, 0, read); received += read;
                        progress?.Invoke(new(received, "正在下载"));
                    }
                    await output.FlushAsync(token);
                    if (received != asset.Bytes) throw new IOException("连接中断，文件尚未下载完整");
                }
                if (Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant() != asset.Sha256)
                    throw new InvalidDataException("安装文件完整性校验失败");
                File.Move(partial, target, true);
                progress?.Invoke(new(asset.Bytes, "文件已校验"));
                return;
            }
            catch (OperationCanceledException) when (token.IsCancellationRequested) { throw; }
            catch (Exception error) when (error is HttpRequestException || error is IOException || error is InvalidDataException || error is OperationCanceledException)
            {
                if (error is InvalidDataException) { if (File.Exists(partial)) File.Delete(partial); }
                if (attempt >= 3) throw new IOException("下载暂未完成。请检查网络后点击继续，已下载的内容会保留。", error);
                progress?.Invoke(new(File.Exists(partial) ? new FileInfo(partial).Length : 0, "连接中断，正在自动重试"));
                if (retryDelay is not null) await retryDelay(attempt, token);
                else await Task.Delay(TimeSpan.FromSeconds(2 * (attempt + 1)), token);
            }
        }
    }
}

public static class InstallPaths
{
    public static string ValidateDestination(string value)
    {
        if (!Path.IsPathFullyQualified(value) || value.StartsWith(@"\\") || value.Any(c => c == '"'))
            throw new IOException("请选择本机磁盘上的安装文件夹");
        string path = Path.GetFullPath(value).TrimEnd(Path.DirectorySeparatorChar);
        if (string.Equals(path, Path.GetPathRoot(path)?.TrimEnd(Path.DirectorySeparatorChar), StringComparison.OrdinalIgnoreCase))
            throw new IOException("请选择磁盘内的文件夹，例如 D:\\译研");
        return path;
    }

    public static void CheckSpace(Edition edition, string cache, string destination)
    {
        long cached = edition.Files.Sum(f => new[] { Path.Combine(cache, f.Name), Path.Combine(cache, f.Name + ".partial") }
            .Where(File.Exists).Select(p => Math.Min(new FileInfo(p).Length, f.Bytes)).DefaultIfEmpty(0).Max());
        var cacheDrive = new DriveInfo(Path.GetPathRoot(cache)!);
        var appDrive = new DriveInfo(Path.GetPathRoot(destination)!);
        long remaining = Math.Max(0, edition.TotalBytes - cached);
        if (string.Equals(cacheDrive.Name, appDrive.Name, StringComparison.OrdinalIgnoreCase))
        {
            if (cacheDrive.AvailableFreeSpace < Math.Max(remaining + edition.InstalledBudget, edition.DiskBudget - cached))
                throw new IOException($"所选磁盘空间不足，请预留约 {edition.DiskBudget / 1e9:0} GB 后继续");
        }
        else if (cacheDrive.AvailableFreeSpace < remaining + 1_000_000_000 || appDrive.AvailableFreeSpace < edition.InstalledBudget)
            throw new IOException("下载缓存所在磁盘或安装磁盘空间不足，请整理空间后继续");
    }
}
