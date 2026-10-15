import AppKit
import Darwin
signal(SIGPIPE,SIG_IGN)
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
