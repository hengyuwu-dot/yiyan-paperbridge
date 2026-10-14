import AppKit

let output = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
let icon = NSImage(size: NSSize(width: 1024, height: 1024))
icon.lockFocus()
NSColor.clear.setFill(); NSRect(x: 0, y: 0, width: 1024, height: 1024).fill()
let base = NSBezierPath(roundedRect: NSRect(x: 65, y: 65, width: 894, height: 894), xRadius: 205, yRadius: 205)
NSGradient(starting: NSColor(calibratedRed: 0.31, green: 0.47, blue: 0.39, alpha: 1),
           ending: NSColor(calibratedRed: 0.15, green: 0.29, blue: 0.24, alpha: 1))!.draw(in: base, angle: -70)
let page = NSBezierPath(roundedRect: NSRect(x: 585, y: 228, width: 194, height: 542), xRadius: 34, yRadius: 34)
NSColor(calibratedWhite: 1, alpha: 0.12).setFill(); page.fill()
let attributes: [NSAttributedString.Key: Any] = [.font: NSFont(name: "Songti SC", size: 510) ?? NSFont.systemFont(ofSize: 510),
    .foregroundColor: NSColor(calibratedRed: 0.96, green: 0.97, blue: 0.91, alpha: 1)]
("译" as NSString).draw(at: NSPoint(x: 219, y: 222), withAttributes: attributes)
NSColor(calibratedRed: 0.83, green: 0.88, blue: 0.75, alpha: 0.65).setStroke()
let line = NSBezierPath(); line.move(to: NSPoint(x: 285, y: 207)); line.line(to: NSPoint(x: 739, y: 207)); line.lineWidth = 10; line.lineCapStyle = .round; line.stroke()
icon.unlockFocus()
for size in [16, 32, 128, 256, 512] {
    for scale in [1, 2] {
        let pixels = size * scale
        let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels, bitsPerSample: 8,
                                  samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
                                  bytesPerRow: 0, bitsPerPixel: 0)!
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
        icon.draw(in: NSRect(x: 0, y: 0, width: pixels, height: pixels))
        NSGraphicsContext.restoreGraphicsState()
        let name = "icon_\(size)x\(size)\(scale == 2 ? "@2x" : "").png"
        try rep.representation(using: .png, properties: [:])!.write(to: output.appendingPathComponent(name))
    }
}
