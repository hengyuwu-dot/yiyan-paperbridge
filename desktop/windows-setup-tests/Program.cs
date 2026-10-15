using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text.Json;
using PaperBridgeSetup;

static class Tests
{
    static readonly byte[] Data = Enumerable.Range(0, 8192).Select(i => (byte)(i % 251)).ToArray();
    static Asset File(byte[]? data = null) => new("sample.bin", (data ?? Data).Length, Convert.ToHexString(SHA256.HashData(data ?? Data)).ToLowerInvariant(), "https://github.com/example/file");
    static void Check(bool value, string message) { if (!value) throw new Exception(message); }
    static HttpResponseMessage Response(byte[] data, long? start = null, long? total = null)
    {
        var r = new HttpResponseMessage(start.HasValue ? HttpStatusCode.PartialContent : HttpStatusCode.OK) { Content = new ByteArrayContent(data) };
        if (start.HasValue) r.Content.Headers.ContentRange = new ContentRangeHeaderValue(start.Value, start.Value + data.Length - 1, total ?? Data.Length);
        return r;
    }
    static async Task Throws<T>(Func<Task> action) where T : Exception
    { try { await action(); } catch (T) { return; } throw new Exception("Expected " + typeof(T).Name); }
    static Downloader Download(Func<HttpRequestMessage, HttpResponseMessage> f) => new(new HttpClient(new Handler(f)), (_, _) => Task.CompletedTask);

    static async Task Main(string[] args)
    {
        if (args.Length == 3 && args[0] == "--verify-installed")
        {
            var e = Packages.Load().Single(e => e.Profile == args[2]);
            string model = Path.Combine(args[1], "Models", e.Profile == "precision" ? "qwen3-14b" : "qwen3-4b", e.ModelFile);
            Check(new FileInfo(model).Length == e.ModelBytes, "Installed model size");
            Check(await Downloader.HashAsync(model) == e.ModelSha256, "Installed model SHA256");
            Console.WriteLine(JsonSerializer.Serialize(new { model_sha256_verified = true, profile = e.Profile })); return;
        }
        string root = Path.Combine(Path.GetTempPath(), "PaperBridge-setup-tests-" + Guid.NewGuid().ToString("N")); Directory.CreateDirectory(root);
        int count = 0;
        async Task Run(string name, Func<string, Task> test)
        { string path = Path.Combine(root, (++count).ToString()); Directory.CreateDirectory(path); await test(path); Console.WriteLine("PASS " + name); }
        try
        {
            await Run("Pinned manifest rejects missing volumes and foreign URLs", _ => {
                var editions = Packages.Load(); Check(editions[0].Files.Length + editions[1].Files.Length == 11, "Manifest volume count");
                var copy = editions.ToArray(); copy[0] = copy[0] with { Files = copy[0].Files.Select((f, i) => i == 0 ? f with { Url = "https://example.com/file.exe" } : f).ToArray() };
                return Throws<InvalidDataException>(() => { Packages.Validate(copy); return Task.CompletedTask; });
            });
            await Run("Resume preserves and hashes the prefix", async p => {
                System.IO.File.WriteAllBytes(Path.Combine(p, "sample.bin.partial"), Data[..37]);
                var d = Download(r => { Check(r.Headers.Range?.Ranges.Single().From == 37, "Range missing"); return Response(Data[37..], 37, Data.Length); });
                await d.DownloadAsync(File(), p, null, default);
                Check(System.IO.File.ReadAllBytes(Path.Combine(p, "sample.bin")).SequenceEqual(Data), "Resume changed bytes");
            });
            await Run("Server ignoring Range replaces instead of appending", async p => {
                System.IO.File.WriteAllBytes(Path.Combine(p, "sample.bin.partial"), Data[..100]);
                await Download(_ => Response(Data)).DownloadAsync(File(), p, null, default);
                Check(new FileInfo(Path.Combine(p, "sample.bin")).Length == Data.Length, "Ignored Range appended");
            });
            await Run("Wrong range never activates a file", async p => {
                System.IO.File.WriteAllBytes(Path.Combine(p, "sample.bin.partial"), Data[..10]);
                await Throws<IOException>(() => Download(_ => Response(Data[10..], 11, Data.Length + 1)).DownloadAsync(File(), p, null, default));
                Check(!System.IO.File.Exists(Path.Combine(p, "sample.bin")), "Wrong range activated");
            });
            await Run("Checksum mismatch removes corrupt partial files", async p => {
                await Throws<IOException>(() => Download(_ => Response(Data)).DownloadAsync(File() with { Sha256 = new string('0', 64) }, p, null, default));
                Check(!System.IO.File.Exists(Path.Combine(p, "sample.bin")) && !System.IO.File.Exists(Path.Combine(p, "sample.bin.partial")), "Corrupt file retained");
            });
            await Run("Interrupted body retries from the actual saved length", async p => {
                int calls = 0;
                var d = Download(r => {
                    if (++calls == 1) { var response = Response(Data[..100]); response.Content.Headers.ContentLength = Data.Length; return response; }
                    Check(r.Headers.Range?.Ranges.Single().From == 100, "Retry lost prefix"); return Response(Data[100..], 100, Data.Length);
                });
                await d.DownloadAsync(File(), p, null, default); Check(calls == 2, "Unexpected retries");
            });
            await Run("Only checksum-valid cached files skip the network", async p => {
                System.IO.File.WriteAllBytes(Path.Combine(p, "sample.bin"), new byte[Data.Length]); int calls = 0;
                var d = Download(_ => { calls++; return Response(Data); });
                await d.DownloadAsync(File(), p, null, default); await d.DownloadAsync(File(), p, null, default);
                Check(calls == 1, "Corrupt cache accepted or valid cache downloaded twice");
            });
            await Run("Pause leaves a resumable prefix and resume verifies the whole file", async p => {
                byte[] data = Enumerable.Range(0, 1024 * 1024 + 128).Select(i => (byte)(i % 251)).ToArray();
                using var cancellation = new CancellationTokenSource();
                await Throws<OperationCanceledException>(() => Download(_ => Response(data)).DownloadAsync(File(data), p, t => { if (t.Bytes > 0) cancellation.Cancel(); }, cancellation.Token));
                long length = new FileInfo(Path.Combine(p, "sample.bin.partial")).Length;
                Check(length > 0 && length < data.Length, "Pause failed to preserve a prefix");
                await Download(r => { Check(r.Headers.Range?.Ranges.Single().From == length, "Paused prefix not resumed"); return Response(data[(int)length..], length, data.Length); }).DownloadAsync(File(data), p, null, default);
                Check(await Downloader.HashAsync(Path.Combine(p, "sample.bin")) == File(data).Sha256, "Resumed hash mismatch");
            });
            await Run("Manifest filenames cannot escape the cache directory", async p => {
                await Throws<InvalidDataException>(() => Download(_ => Response(Data)).DownloadAsync(File() with { Name = "../outside.exe" }, p, null, default));
            });
            Console.WriteLine($"{count} downloader checks passed");
        }
        finally { Directory.Delete(root, true); }
    }
    sealed class Handler(Func<HttpRequestMessage, HttpResponseMessage> response) : HttpMessageHandler
    { protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) => Task.FromResult(response(request)); }
}
