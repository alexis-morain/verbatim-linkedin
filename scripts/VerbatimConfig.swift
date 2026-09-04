// The environment file: ~/.config/verbatim/env, and the four names
// providers.py reads out of it.
//
// This is its own file because it is the only part of the shell that is
// logic rather than lifecycle, and because it edits a file holding somebody's
// API key. scripts/config-test.swift compiles against exactly this source,
// so what the tests prove is what the app runs. No second copy.

import Foundation

let configDir = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent(".config/verbatim")
let configFile = configDir.appendingPathComponent("env")

// The four names providers.py reads. The key is last because it is the only
// one that is a secret, and the only one that never reaches a screen.
let PROVIDERS = ["anthropic", "openai"]
let DEFAULT_BASE_URL = ["anthropic": "https://api.anthropic.com",
                        "openai": "https://api.openai.com/v1"]
let DEFAULT_MODEL = ["anthropic": "claude-opus-5"]

/// Read `KEY=VALUE` lines. Deliberately forgiving and deliberately dumb: it
/// is reading a file a person may have written by hand long before this
/// sheet existed.
func readConfig(at url: URL = configFile) -> [String: String] {
    guard let raw = try? String(contentsOf: url, encoding: .utf8) else { return [:] }
    var found: [String: String] = [:]
    for line in raw.split(separator: "\n", omittingEmptySubsequences: false) {
        var text = line.trimmingCharacters(in: .whitespaces)
        if text.hasPrefix("#") { continue }
        if text.hasPrefix("export ") { text = String(text.dropFirst(7)) }
        guard let cut = text.firstIndex(of: "=") else { continue }
        let name = String(text[text.startIndex..<cut]).trimmingCharacters(in: .whitespaces)
        var value = String(text[text.index(after: cut)...]).trimmingCharacters(in: .whitespaces)
        if value.count >= 2, value.hasPrefix("\""), value.hasSuffix("\"") {
            value = String(value.dropFirst().dropLast())
        }
        if !name.isEmpty { found[name] = value }
    }
    return found
}

/// Update the four names we own and leave every other line of the file
/// exactly as it was. Somebody's hand written file is not ours to rewrite.
func writeConfig(_ updates: [String: String], at url: URL = configFile) throws {
    try FileManager.default.createDirectory(at: url.deletingLastPathComponent(),
                                            withIntermediateDirectories: true,
                                            attributes: [.posixPermissions: 0o700])
    let existing = (try? String(contentsOf: url, encoding: .utf8)) ?? ""
    var lines = existing.isEmpty ? [] : existing.split(separator: "\n",
                                                       omittingEmptySubsequences: false).map(String.init)
    while lines.last?.trimmingCharacters(in: .whitespaces).isEmpty == true { lines.removeLast() }
    if lines.isEmpty {
        lines = ["# Written by Verbatim.app. The model and the key live here,",
                 "# never in an instance directory."]
    }
    for (name, value) in updates.sorted(by: { $0.key < $1.key }) {
        let line = value.isEmpty ? nil : "\(name)=\(value)"
        var replaced = false
        for (index, current) in lines.enumerated() {
            var text = current.trimmingCharacters(in: .whitespaces)
            if text.hasPrefix("export ") { text = String(text.dropFirst(7)) }
            guard text.hasPrefix("\(name)=") else { continue }
            if let line = line { lines[index] = line } else { lines[index] = "# \(name) unset" }
            replaced = true
            break
        }
        if !replaced, let line = line { lines.append(line) }
    }
    let body = lines.joined(separator: "\n") + "\n"
    try body.write(to: url, atomically: true, encoding: .utf8)
    // atomically: true replaces the file, so the mode is set after the write
    // rather than before it.
    try FileManager.default.setAttributes([.posixPermissions: 0o600],
                                          ofItemAtPath: url.path)
}
