import AppKit
import Darwin
signal(SIGPIPE,SIG_IGN)
if CommandLine.arguments.contains("--check-update") {
    do {let release=try latestRelease(allowBundled:false);let data=try JSONEncoder().encode(release);print(String(data:data,encoding:.utf8)!);exit(0)}
    catch {fputs(error.localizedDescription+"\n",stderr);exit(1)}
}
final class InstallerDelegate:NSObject,NSApplicationDelegate {
    var controller:MacInstallerWindow?
    func applicationDidFinishLaunching(_ notification:Notification) {controller=MacInstallerWindow()}
    func applicationShouldTerminateAfterLastWindowClosed(_ application:NSApplication)->Bool {true}
    func applicationShouldTerminate(_ sender:NSApplication)->NSApplication.TerminateReply {if controller?.working == true {controller?.window.makeKeyAndOrderFront(nil);_ = controller?.windowShouldClose(controller!.window);return .terminateCancel};return .terminateNow}
}
let app=NSApplication.shared
app.setActivationPolicy(.regular)
let delegate=InstallerDelegate();app.delegate=delegate
app.run()
