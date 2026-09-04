// The native window around the local web app. Compiled by
// scripts/macos-app.sh into Verbatim.app's executable.
//
// It owns the machine, and the engine owns the instance. That line decides
// everything in this file. The Python package never writes outside the
// directory it was handed and never reads a key from it, so the two things
// that live on a machine rather than in an instance are here instead: which
// folder to serve, and the environment file holding the model and the key.
//
// The lifecycle: resolve an instance (ask, the first time), run
// Resources/start.sh with it, show the progress it reports, then show the
// app in a WKWebView and stop the server on quit. Every screen it displays
// is served by the engine; the only pixels this file owns are the starting
// state, the settings sheet and the failure alert.

// On language: every sentence in this file is English, and that is an
// exemption rather than an oversight. Interface strings live in locales/,
// but this shell runs before the engine is installed and cannot read them;
// what it says is the handful of lines between a double click and the first
// served screen. Anything a person reads after that is the engine's, and
// the engine speaks their language.

import Cocoa
import WebKit

let port = (Bundle.main.object(forInfoDictionaryKey: "VerbatimPort") as? String) ?? "8748"
let home = URL(string: "http://127.0.0.1:\(port)/")!
let supportDir = FileManager.default.urls(for: .applicationSupportDirectory,
                                          in: .userDomainMask)[0]
    .appendingPathComponent("Verbatim")
let instanceFile = supportDir.appendingPathComponent("instance")

// The model and the key live in scripts/VerbatimConfig.swift, never in the
// instance: providers.py refuses to start when it finds a credential in one.

let startingHTML = """
<!doctype html><meta charset="utf-8">
<body style="margin:0;height:100vh;display:grid;place-items:center;
             background:#10151C;font:16px ui-sans-serif,system-ui">
  <div style="text-align:center">
    <div style="display:inline-block;background:#F2E85C;color:#10151C;
                padding:0.4rem 1.2rem;transform:rotate(-3deg);
                font-family:'Iowan Old Style',Palatino,Georgia,serif;
                font-size:2.2rem">&#8220;&nbsp;Verbatim</div>
    <p id="status" style="color:#98A3B3;margin-top:1.6rem">starting the engine&#8230;</p>
  </div>
</body>
"""

final class SettingsSheet {
    let providerButton = NSPopUpButton(frame: NSRect(x: 120, y: 108, width: 300, height: 26))
    let modelField = NSTextField(frame: NSRect(x: 120, y: 76, width: 300, height: 22))
    let endpointField = NSTextField(frame: NSRect(x: 120, y: 44, width: 300, height: 22))
    let keyField = NSSecureTextField(frame: NSRect(x: 120, y: 12, width: 300, height: 22))

    private func label(_ text: String, _ y: CGFloat) -> NSTextField {
        let field = NSTextField(labelWithString: text)
        field.frame = NSRect(x: 0, y: y, width: 112, height: 18)
        field.alignment = .right
        return field
    }

    /// Returns true when the person saved.
    func run() -> Bool {
        let current = readConfig()
        providerButton.addItems(withTitles: PROVIDERS)
        let provider = current["VERBATIM_PROVIDER"] ?? "anthropic"
        if PROVIDERS.contains(provider) { providerButton.selectItem(withTitle: provider) }

        modelField.stringValue = current["VERBATIM_MODEL"] ?? ""
        modelField.placeholderString = DEFAULT_MODEL[provider] ?? "the model, as the provider spells it"
        endpointField.stringValue = current["VERBATIM_BASE_URL"] ?? ""
        endpointField.placeholderString = DEFAULT_BASE_URL[provider] ?? ""
        keyField.stringValue = current["VERBATIM_API_KEY"]
            ?? current["ANTHROPIC_API_KEY"] ?? current["OPENAI_API_KEY"] ?? ""

        let view = NSView(frame: NSRect(x: 0, y: 0, width: 430, height: 140))
        view.addSubview(label("Provider", 112))
        view.addSubview(label("Model", 78))
        view.addSubview(label("Endpoint", 46))
        view.addSubview(label("API key", 14))
        view.addSubview(providerButton)
        view.addSubview(modelField)
        view.addSubview(endpointField)
        view.addSubview(keyField)

        let alert = NSAlert()
        alert.messageText = "Verbatim settings"
        alert.informativeText = """
            The model that runs your interviews. This is written to \
            ~/.config/verbatim/env, readable by you alone, and never to the \
            folder holding your profile.

            Leave the endpoint empty for the provider's own. A local endpoint \
            on 127.0.0.1 needs no key.
            """
        alert.accessoryView = view
        alert.addButton(withTitle: "Save")
        alert.addButton(withTitle: "Cancel")
        guard alert.runModal() == .alertFirstButtonReturn else { return false }

        let chosen = providerButton.titleOfSelectedItem ?? "anthropic"
        let model = modelField.stringValue.trimmingCharacters(in: .whitespaces)
        let endpoint = endpointField.stringValue.trimmingCharacters(in: .whitespaces)
        do {
            try writeConfig([
                "VERBATIM_PROVIDER": chosen,
                "VERBATIM_MODEL": model.isEmpty ? (DEFAULT_MODEL[chosen] ?? "") : model,
                "VERBATIM_BASE_URL": endpoint.isEmpty ? (DEFAULT_BASE_URL[chosen] ?? "") : endpoint,
                "VERBATIM_API_KEY": keyField.stringValue,
            ])
        } catch {
            let failed = NSAlert()
            failed.messageText = "Verbatim"
            failed.informativeText = "Could not write ~/.config/verbatim/env: \(error.localizedDescription)"
            failed.runModal()
            return false
        }
        return true
    }
}

// ------------------------------------------------------------------ skills
// Copying the bundle into ~/.claude/skills is an operation on the machine,
// so it belongs to the launcher. Copy rather than link: the tool environment
// is replaced whole on every version bump and a link into it would break at
// the first one.
let skillsTarget = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent(".claude/skills/verbatim")
let skillsMarker = ".installed-by-verbatim-app"

func bundleInsideInstalledEngine() -> URL? {
    let tools = supportDir.appendingPathComponent("tools/verbatim-linkedin/lib")
    guard let pythons = try? FileManager.default.contentsOfDirectory(
        at: tools, includingPropertiesForKeys: nil) else { return nil }
    for python in pythons {
        let candidate = python.appendingPathComponent("site-packages/verbatim_app/_bundle")
        if FileManager.default.fileExists(atPath: candidate.appendingPathComponent("SKILL.md").path) {
            return candidate
        }
    }
    return nil
}

func installSkills() {
    let alert = NSAlert()
    alert.messageText = "Verbatim"

    guard let source = bundleInsideInstalledEngine() else {
        alert.informativeText = "The engine is not installed yet. Open Verbatim once, let it finish starting, then try again."
        alert.runModal()
        return
    }
    let manager = FileManager.default
    // The plan asked what happens with no Claude Code installed, and answered
    // "probably nothing, and say so". Creating ~/.claude for somebody who has
    // never had it would be answering the other way.
    let claudeHome = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".claude")
    guard manager.fileExists(atPath: claudeHome.path) else {
        alert.informativeText = """
            There is no ~/.claude on this machine, so Claude Code is not \
            installed and nothing has been created. The skills are for it; \
            install it first, then come back to this menu.
            """
        alert.runModal()
        return
    }
    if manager.fileExists(atPath: skillsTarget.path) {
        let ours = manager.fileExists(atPath: skillsTarget.appendingPathComponent(skillsMarker).path)
        if !ours {
            // A clone somebody symlinked by hand, most likely. Overwriting
            // somebody's working checkout would be the worst bug in here.
            alert.informativeText = """
                Something is already installed at ~/.claude/skills/verbatim and \
                it was not put there by this app, so nothing has been touched.

                If that is a clone of the repository, it is already the bundle \
                and there is nothing to do.
                """
            alert.runModal()
            return
        }
    }

    // Copy beside the target and move it into place, rather than copying
    // onto it. A copy that dies halfway would otherwise leave a tree with no
    // marker in it, and every retry after that would answer "this was not
    // put there by this app", which is the one thing that is not true.
    let staging = skillsTarget.deletingLastPathComponent()
        .appendingPathComponent(".verbatim-installing")
    do {
        try manager.createDirectory(at: skillsTarget.deletingLastPathComponent(),
                                    withIntermediateDirectories: true)
        try? manager.removeItem(at: staging)
        try manager.copyItem(at: source, to: staging)
        try Data().write(to: staging.appendingPathComponent(skillsMarker))
        if manager.fileExists(atPath: skillsTarget.path) {
            try manager.removeItem(at: skillsTarget)
        }
        try manager.moveItem(at: staging, to: skillsTarget)
        alert.informativeText = """
            The skill bundle is installed at ~/.claude/skills/verbatim.

            Open Claude Code and say you want to write a LinkedIn post, or that \
            you want to set up your profile.
            """
    } catch {
        try? manager.removeItem(at: staging)
        alert.informativeText = "Could not install the skills: \(error.localizedDescription)"
    }
    alert.runModal()
}

// ------------------------------------------------------------------- shell
final class Delegate: NSObject, NSApplicationDelegate, NSWindowDelegate,
                      WKNavigationDelegate, WKUIDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var instance: URL?
    private var failure: String?
    private var pending = ""

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

        // The instance has to be settled before start.sh runs, since it is
        // what start.sh is given. No folder, no app: there is nothing to show.
        guard let chosen = resolveInstance() else {
            NSApp.terminate(nil)
            return
        }
        instance = chosen

        // No model configured means no interview, and the interview is the
        // product. A missing file is only one way to have no model: a file
        // somebody wrote by hand holding a key and nothing else is the other,
        // and it is exactly the case this sheet exists to spare them.
        // Whether a model that IS named is usable stays the engine's
        // judgement: it has problems() and this file will not reimplement it.
        if (readConfig()["VERBATIM_MODEL"] ?? "").isEmpty {
            _ = SettingsSheet().run()
        }

        start()
    }

    /// The remembered folder, or a panel. A folder that has since moved asks
    /// again instead of failing.
    func resolveInstance() -> URL? {
        if let path = try? String(contentsOf: instanceFile, encoding: .utf8) {
            let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
            var isDirectory: ObjCBool = false
            if !trimmed.isEmpty,
               FileManager.default.fileExists(atPath: trimmed, isDirectory: &isDirectory),
               isDirectory.boolValue {
                return URL(fileURLWithPath: trimmed)
            }
        }
        return askForInstance()
    }

    func askForInstance() -> URL? {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.canCreateDirectories = true
        panel.prompt = "Use this folder"
        panel.message = """
            Choose the folder holding your Verbatim profile. An empty folder is \
            fine: Verbatim will show you what is missing and how to fill it.
            """
        guard panel.runModal() == .OK, let url = panel.url else { return nil }
        try? FileManager.default.createDirectory(at: supportDir, withIntermediateDirectories: true)
        try? url.path.write(to: instanceFile, atomically: true, encoding: .utf8)
        return url
    }

    func show(_ message: String) {
        guard let encoded = try? JSONEncoder().encode(message),
              let literal = String(data: encoded, encoding: .utf8) else { return }
        webView.evaluateJavaScript(
            "document.getElementById('status').textContent = \(literal)")
    }

    func start() {
        guard let script = Bundle.main.path(forResource: "start", ofType: "sh") else {
            fail("The app bundle has no start.sh. Rebuild it with scripts/macos-app.sh.")
            return
        }
        guard let instance = instance else { return }
        failure = nil
        pending = ""

        let run = Process()
        run.executableURL = URL(fileURLWithPath: "/bin/zsh")
        run.arguments = [script, instance.path]
        let pipe = Pipe()
        run.standardOutput = pipe

        // start.sh talks while it works: the first launch installs a Python
        // runtime and a fixed splash for two minutes is indistinguishable
        // from a hang.
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let chunk = handle.availableData
            guard !chunk.isEmpty, let text = String(data: chunk, encoding: .utf8) else { return }
            DispatchQueue.main.async { self?.consume(text) }
        }

        DispatchQueue.global().async {
            do {
                try run.run()
                run.waitUntilExit()
            } catch {
                DispatchQueue.main.async {
                    self.fail("start.sh could not be run: \(error.localizedDescription)")
                }
                return
            }
            // Drain what is left before deciding. The handler hands its
            // chunks to the main queue, so a FAIL line still in the pipe here
            // would land after the verdict and be replaced by the generic
            // message it was written to avoid.
            pipe.fileHandleForReading.readabilityHandler = nil
            let rest = pipe.fileHandleForReading.readDataToEndOfFile()
            let tail = String(data: rest, encoding: .utf8) ?? ""
            DispatchQueue.main.async {
                if !tail.isEmpty { self.consume(tail) }
                if run.terminationStatus == 0 {
                    // start.sh only exits 0 once the port answers.
                    self.webView.load(URLRequest(url: home))
                } else {
                    self.fail(self.failure
                        ?? "The engine did not start. Details are in ~/Library/Logs/verbatim.log")
                }
            }
        }
    }

    /// STATUS lines reach the window, FAIL lines are kept for the alert,
    /// everything else is the log's business.
    private func consume(_ text: String) {
        pending += text
        while let cut = pending.firstIndex(of: "\n") {
            let line = String(pending[pending.startIndex..<cut])
            pending = String(pending[pending.index(after: cut)...])
            if line.hasPrefix("STATUS ") { show(String(line.dropFirst(7))) }
            if line.hasPrefix("FAIL ") { failure = String(line.dropFirst(5)) }
        }
    }

    func fail(_ message: String) {
        let alert = NSAlert()
        alert.messageText = "Verbatim"
        alert.informativeText = message
        alert.runModal()
    }

    // ------------------------------------------------------------ the menu
    @objc func openSettings(_ sender: Any?) {
        if SettingsSheet().run() { restart() }
    }

    @objc func chooseInstance(_ sender: Any?) {
        guard let picked = askForInstance() else { return }
        instance = picked
        restart()
    }

    @objc func installSkillBundle(_ sender: Any?) { installSkills() }

    /// The engine reads its environment once, at start. Anything the sheet
    /// changed only counts after a restart, so the restart is not optional.
    private func restart() {
        stopServer()
        webView.loadHTMLString(startingHTML, baseURL: nil)
        start()
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

    private func stopServer() {
        let pidFile = supportDir.appendingPathComponent("server.pid")
        guard let raw = try? String(contentsOf: pidFile, encoding: .utf8),
              let pid = Int32(raw.trimmingCharacters(in: .whitespacesAndNewlines))
        else { return }
        kill(pid, SIGTERM)
        try? FileManager.default.removeItem(at: pidFile)
    }

    // The window owns the server: quitting the app stops it, so nothing is
    // left listening behind a closed window.
    func applicationWillTerminate(_ note: Notification) { stopServer() }
}

let app = NSApplication.shared
app.setActivationPolicy(.regular)
let delegate = Delegate()

let mainMenu = NSMenu()
let appItem = NSMenuItem()
mainMenu.addItem(appItem)
let appMenu = NSMenu()
let settingsItem = NSMenuItem(title: "Settings\u{2026}",
                              action: #selector(Delegate.openSettings(_:)), keyEquivalent: ",")
settingsItem.target = delegate
appMenu.addItem(settingsItem)
let instanceItem = NSMenuItem(title: "Choose Instance Folder\u{2026}",
                              action: #selector(Delegate.chooseInstance(_:)), keyEquivalent: "o")
instanceItem.target = delegate
appMenu.addItem(instanceItem)
let skillsItem = NSMenuItem(title: "Install Skills for Claude Code\u{2026}",
                            action: #selector(Delegate.installSkillBundle(_:)), keyEquivalent: "")
skillsItem.target = delegate
appMenu.addItem(skillsItem)
appMenu.addItem(NSMenuItem.separator())
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

app.delegate = delegate
app.run()
