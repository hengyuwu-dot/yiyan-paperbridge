import Foundation

// This affects only this app's URLSession. System proxy settings are never changed.
func installerNetworkConfiguration() -> URLSessionConfiguration {
    let config=URLSessionConfiguration.ephemeral
    config.connectionProxyDictionary=["HTTPEnable":0,"HTTPSEnable":0,"SOCKSEnable":0,"ProxyAutoConfigEnable":0,"ProxyAutoDiscoveryEnable":0]
    config.timeoutIntervalForRequest=15
    config.timeoutIntervalForResource=24*3600
    config.urlCache=nil
    return config
}

struct DownloadRoute {
    let name:String, prefix:String
    func url(_ original:String)->URL {URL(string:prefix+original)!}
}
func installerDownloadRoutes()->[DownloadRoute] {
    [DownloadRoute(name:"GitHub 直连",prefix:""),
     DownloadRoute(name:"备用加速线路 1",prefix:"https://ghfast.top/"),
     DownloadRoute(name:"备用加速线路 2",prefix:"https://gh-proxy.com/")]
}

let publishedMacManifest="https://raw.githubusercontent.com/hengyuwu-dot/yiyan-paperbridge/main/release-assets/macos-app.json"
func installerMetadataURLs(_ original:String)->[URL] {
    let base="https://raw.githubusercontent.com/hengyuwu-dot/yiyan-paperbridge/main/"
    guard original.hasPrefix(base) else {return [URL(string:original)!]}
    let path=String(original.dropFirst(base.count))
    return [URL(string:original)!,URL(string:"https://cdn.jsdelivr.net/gh/hengyuwu-dot/yiyan-paperbridge@main/"+path)!]
}

func downloadProgressText(bytes:Int64,total:Int64,speed:Double)->String {
    let head=String(format:"%.2f / %.2f GB · %.0f%%",Double(bytes)/1e9,Double(total)/1e9,100*Double(bytes)/Double(max(1,total)))
    guard speed>0 else{return head+" · 正在连接…"}
    let rate=speed>=1_000_000 ? String(format:"%.1f MB/s",speed/1e6):String(format:"%.0f KB/s",speed/1e3)
    let remaining=Double(max(0,total-bytes))/speed
    let eta=remaining>=3600 ? String(format:"约 %.1f 小时",remaining/3600):remaining>=60 ? "约 \(Int(ceil(remaining/60))) 分钟":"约 \(max(1,Int(ceil(remaining)))) 秒"
    return head+" · "+rate+" · 剩余"+eta
}
