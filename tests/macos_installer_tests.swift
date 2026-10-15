import Foundation
import CryptoKit

final class TransportFixture: URLProtocol {
    static var body=Data((0..<2097152).map{UInt8($0%251)})
    static var requests:[Int]=[]
    static var mode="resume"
    override class func canInit(with request:URLRequest)->Bool {true}
    override class func canonicalRequest(for request:URLRequest)->URLRequest {request}
    override func startLoading() {
        let header=request.value(forHTTPHeaderField:"Range") ?? "bytes=0-"
        let start=Int(header.replacingOccurrences(of:"bytes=",with:"").replacingOccurrences(of:"-",with:""))!
        Self.requests.append(start)
        let call=Self.requests.count
        let ignore=Self.mode=="ignore"
        let beginning=ignore ? 0:start
        let range="bytes \(beginning)-\(Self.body.count-1)/\(Self.body.count)"
        let fields=["Content-Length":String(Self.body.count-beginning),"Content-Range":range]
        let response=HTTPURLResponse(url:request.url!,statusCode:!ignore && start>0 ? 206:200,httpVersion:"HTTP/1.1",headerFields:fields)!
        client?.urlProtocol(self,didReceive:response,cacheStoragePolicy:.notAllowed)
        if Self.mode=="interrupt" && call==1 {
            client?.urlProtocol(self,didLoad:Self.body.prefix(160))
            client?.urlProtocolDidFinishLoading(self);return
        }
        if Self.mode=="pause" && call==1 {
            client?.urlProtocol(self,didLoad:Self.body.prefix(160));return
        }
        var content=Self.body.subdata(in:beginning..<Self.body.count)
        if Self.mode=="badHash" && call==1 {content[0]^=1}
        client?.urlProtocol(self,didLoad:content);client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
func fixtureConfiguration()->URLSessionConfiguration {let c=URLSessionConfiguration.ephemeral;c.protocolClasses=[TransportFixture.self];return c}
func check(_ condition:@autoclosure()->Bool,_ message:String) {if !condition(){fatalError(message)}}
func testDirectory(_ name:String)throws->URL {let p=URL(fileURLWithPath:NSTemporaryDirectory()).appendingPathComponent("yiyan-installer-tests-"+UUID().uuidString+"/"+name);try FileManager.default.createDirectory(at:p,withIntermediateDirectories:true);return p}
func asset()->RemoteAsset {let h=SHA256.hash(data:TransportFixture.body).map{String(format:"%02x",$0)}.joined();return RemoteAsset(name:"sample.bin",url:repositoryPrefix+"test/sample.bin",sha256:h,bytes:Int64(TransportFixture.body.count))}
func reset(_ mode:String) {TransportFixture.requests=[];TransportFixture.mode=mode}
@main struct Tests {
    static func main()throws {
        setbuf(stdout,nil)
        let sample=asset()
        try sample.validate()
        for invalid in [RemoteAsset(name:"../outside",url:sample.url,sha256:sample.sha256,bytes:sample.bytes),RemoteAsset(name:"sample.bin",url:"https://example.com/sample.bin",sha256:sample.sha256,bytes:sample.bytes)] {do{try invalid.validate();fatalError("Unsafe manifest accepted")}catch{}}
        print("PASS manifest rejects foreign host and unsafe paths")
        do {
            reset("resume");let dir=try testDirectory("resume");defer{try? FileManager.default.removeItem(at:dir.deletingLastPathComponent())}
            try TransportFixture.body.prefix(160).write(to:dir.appendingPathComponent("sample.bin.partial"))
            let result=try ResumableTransfer().download(sample,into:dir){_ in}
            check(TransportFixture.requests==[160],"resume did not request saved offset");check(try! Data(contentsOf:result)==TransportFixture.body,"resume changed bytes")
            print("PASS SHA-verified HTTP 206 continuation")
        }
        do {
            reset("ignore");let dir=try testDirectory("ignore");defer{try? FileManager.default.removeItem(at:dir.deletingLastPathComponent())}
            try TransportFixture.body.prefix(160).write(to:dir.appendingPathComponent("sample.bin.partial"))
            let result=try ResumableTransfer().download(sample,into:dir){_ in};check(try! Data(contentsOf:result)==TransportFixture.body,"HTTP 200 was appended to partial")
            print("PASS HTTP 200 replaces a partial instead of appending")
        }
        do {
            reset("interrupt");let dir=try testDirectory("interrupt");defer{try? FileManager.default.removeItem(at:dir.deletingLastPathComponent())}
            let result=try ResumableTransfer().download(sample,into:dir){_ in};check(TransportFixture.requests==[0,160],"short response offsets: \(TransportFixture.requests)");check(try! Data(contentsOf:result)==TransportFixture.body,"retry corrupted file")
            print("PASS interrupted transfer resumes actual saved bytes")
        }
        do {
            reset("badHash");let dir=try testDirectory("hash");defer{try? FileManager.default.removeItem(at:dir.deletingLastPathComponent())}
            let result=try ResumableTransfer().download(sample,into:dir){_ in};check(TransportFixture.requests==[0,0],"bad checksum did not restart");check(try! Data(contentsOf:result)==TransportFixture.body,"bad checksum activated")
            print("PASS checksum failure cannot activate corrupt content")
        }
        do {
            reset("resume");let dir=try testDirectory("cache");defer{try? FileManager.default.removeItem(at:dir.deletingLastPathComponent())}
            try TransportFixture.body.write(to:dir.appendingPathComponent("sample.bin"))
            _=try ResumableTransfer().download(sample,into:dir){_ in};check(TransportFixture.requests.isEmpty,"valid cache downloaded again")
            try Data(repeating:0,count:TransportFixture.body.count).write(to:dir.appendingPathComponent("sample.bin"))
            _=try ResumableTransfer().download(sample,into:dir){_ in};check(TransportFixture.requests==[0],"invalid cache was reused")
            print("PASS cached file reused only after SHA256 verification")
        }
        do {
            reset("pause");let dir=try testDirectory("pause");defer{try? FileManager.default.removeItem(at:dir.deletingLastPathComponent())}
            try TransportFixture.body.prefix(160).write(to:dir.appendingPathComponent("sample.bin.partial"))
            let transfer=ResumableTransfer()
            DispatchQueue.global().asyncAfter(deadline:.now()+0.2){transfer.pause()}
            do{_=try transfer.download(sample,into:dir){_ in};fatalError("pause not propagated")}catch SetupFailure.paused{}
            check(fileBytes(dir.appendingPathComponent("sample.bin.partial"))==160,"pause discarded progress")
            let result=try ResumableTransfer().download(sample,into:dir){_ in};check(try! Data(contentsOf:result)==TransportFixture.body,"paused transfer did not resume")
            print("PASS pause preserves partial and a new transfer resumes")
        }
        check(versionIsNewer("1.10.0","1.9.0"),"numeric version comparison failed")
        check(!versionIsNewer("1.8.0","1.8.0"),"same version counted as update")
        print("PASS semantic version order")
        print("8 installer checks passed")
    }
}
