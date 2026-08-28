// The native window around the local web app. Compiled by
// scripts/macos-app.sh into Verbatim.app's executable.
//
// It owns the lifecycle and nothing else: run Resources/start.sh (which
// updates the clone and brings the server up on loopback), show the app in
// a WKWebView, and stop the server on quit. Every screen it displays is
// served by the engine; the only pixels this file owns are the starting
// state and the failure alert.

import Cocoa
import WebKit

let port = (Bundle.main.object(forInfoDictionaryKey: "VerbatimPort") as? String) ?? "8748"
let home = URL(string: "http://127.0.0.1:\(port)/")!
let supportDir = FileManager.default.urls(for: .applicationSupportDirectory,
                                          in: .userDomainMask)[0]
    .appendingPathComponent("Verbatim")

let startingHTML = """
<!doctype html><meta charset="utf-8">
<body style="margin:0;height:100vh;display:grid;place-items:center;
             background:#10151C;font:16px ui-sans-serif,system-ui">
  <div style="text-align:center">
    <div style="display:inline-block;background:#F2E85C;color:#10151C;
                padding:0.4rem 1.2rem;transform:rotate(-3deg);
                font-family:'Iowan Old Style',Palatino,Georgia,serif;
                font-size:2.2rem">&#8220;&nbsp;Verbatim</div>
    <p style="color:#98A3B3;margin-top:1.6rem">starting the engine&#8230;</p>
  </div>
</body>
"""

final class Delegate: NSObject, NSApplicationDelegate, NSWindowDelegate,
                      WKNavigationDelegate, WKUIDelegate {
    var window: NSWindow!
    var webView: WKWebView!

    func applicationDidFinishLaunching(_ note: Notification) {
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1180, height: 820),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered, defer: false)
        window.title = "Verbatim"
        window.minSize = NSSize(width: 640, height: 480)
        window.setFrameAutosaveName("VerbatimWindow")
        window.delegate = self

        webView = WKWebView(frame: window.contentView!.bounds,
                            configuration: WKWebViewConfiguration())
        webView.autoresizingMask = [.width, .height]
        webView.navigationDelegate = self
        webView.uiDelegate = self
        window.contentView!.addSubview(webView)
        webView.loadHTMLString(startingHTML, baseURL: nil)

        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        start()
    }

    func start() {
        guard let script = Bundle.main.path(forResource: "start", ofType: "sh") else {
            fail("The app bundle has no start.sh. Rebuild it with scripts/macos-app.sh.")
            return
        }
        DispatchQueue.global().async {
            let run = Process()
            run.executableURL = URL(fileURLWithPath: "/bin/zsh")
            run.arguments = [script]
            do {
                try run.run()
                run.waitUntilExit()
            } catch {
                DispatchQueue.main.async {
                    self.fail("start.sh could not be run: \(error.localizedDescription)")
                }
                return
            }
            DispatchQueue.main.async {
                if run.terminationStatus == 0 {
                    // start.sh only exits 0 once the port answers.
                    self.webView.load(URLRequest(url: home))
                } else {
                    // Its own dialog already said what went wrong.
                    self.fail("The engine did not start. Details are in ~/Library/Logs/verbatim.log")
                }
            }
        }
    }

    func fail(_ message: String) {
        let alert = NSAlert()
        alert.messageText = "Verbatim"
        alert.informativeText = message
        alert.runModal()
    }

    // A link that leaves the machine opens in the default browser. This
    // window is the local app, nothing else.
    func webView(_ webView: WKWebView,
                 decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let url = action.request.url, let host = url.host,
           host != "127.0.0.1", host != "localhost" {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }

    // target=_blank stays in this window when local, in the browser when not.
    func webView(_ webView: WKWebView,
                 createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction,
                 windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url {
            if let host = url.host, host == "127.0.0.1" || host == "localhost" {
                webView.load(URLRequest(url: url))
            } else {
                NSWorkspace.shared.open(url)
            }
        }
        return nil
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool {
        true
    }

    // The window owns the server: quitting the app stops it, so nothing is
    // left listening behind a closed window.
    func applicationWillTerminate(_ note: Notification) {
        let pidFile = supportDir.appendingPathComponent("server.pid")
        guard let raw = try? String(contentsOf: pidFile, encoding: .utf8),
              let pid = Int32(raw.trimmingCharacters(in: .whitespacesAndNewlines))
        else { return }
        kill(pid, SIGTERM)
        try? FileManager.default.removeItem(at: pidFile)
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.regular)

let mainMenu = NSMenu()
let appItem = NSMenuItem()
mainMenu.addItem(appItem)
let appMenu = NSMenu()
appMenu.addItem(withTitle: "Hide Verbatim",
                action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
appMenu.addItem(NSMenuItem.separator())
appMenu.addItem(withTitle: "Quit Verbatim",
                action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
appItem.submenu = appMenu

// Without an Edit menu there is no copy and paste, and this app is a place
// where somebody types the material of their post.
let editItem = NSMenuItem()
mainMenu.addItem(editItem)
let editMenu = NSMenu(title: "Edit")
editMenu.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
editMenu.addItem(withTitle: "Redo", action: Selector(("redo:")), keyEquivalent: "Z")
editMenu.addItem(NSMenuItem.separator())
editMenu.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
editMenu.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
editMenu.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
editMenu.addItem(withTitle: "Select All",
                 action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
editItem.submenu = editMenu
app.mainMenu = mainMenu

let delegate = Delegate()
app.delegate = delegate
app.run()
