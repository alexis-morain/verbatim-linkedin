// Tests for scripts/VerbatimConfig.swift, compiled against that exact source
// so there is no second copy of the logic to drift.
//
//   swiftc -o /tmp/t scripts/VerbatimConfig.swift scripts/config-test.swift && /tmp/t
//
// What is worth testing here is one thing: this code edits a file that holds
// somebody's API key and that they may have written by hand. It must change
// the four lines it owns and nothing else, ever.

import Foundation

var failures = 0

func check(_ what: String, _ passed: Bool, _ detail: String = "") {
    if passed {
        print("  ok   \(what)")
    } else {
        failures += 1
        print("  FAIL \(what)\(detail.isEmpty ? "" : ": \(detail)")")
    }
}

func scratch() -> URL {
    let dir = URL(fileURLWithPath: NSTemporaryDirectory())
        .appendingPathComponent("verbatim-config-\(UUID().uuidString)")
    return dir.appendingPathComponent("env")
}

func body(_ url: URL) -> String {
    (try? String(contentsOf: url, encoding: .utf8)) ?? "<unreadable>"
}

@main
struct ConfigTests {
    static func main() throws {
        print("a file that does not exist yet")
        do {
            let file = scratch()
            try writeConfig(["VERBATIM_PROVIDER": "anthropic",
                             "VERBATIM_MODEL": "claude-opus-5",
                             "VERBATIM_BASE_URL": "https://api.anthropic.com",
                             "VERBATIM_API_KEY": "sk-test-value"], at: file)
            let back = readConfig(at: file)
            check("the four names round trip",
                  back["VERBATIM_PROVIDER"] == "anthropic"
                  && back["VERBATIM_MODEL"] == "claude-opus-5"
                  && back["VERBATIM_BASE_URL"] == "https://api.anthropic.com"
                  && back["VERBATIM_API_KEY"] == "sk-test-value", body(file))

            let mode = try FileManager.default.attributesOfItem(atPath: file.path)[.posixPermissions] as? NSNumber
            check("the file is readable by its owner alone", mode?.int16Value == 0o600,
                  String(mode?.int16Value ?? -1, radix: 8))
        }

        print("a file somebody wrote by hand")
        do {
            let file = scratch()
            try FileManager.default.createDirectory(at: file.deletingLastPathComponent(),
                                                    withIntermediateDirectories: true)
            let handwritten = """
                # my notes, which are mine
                VERBATIM_PROVIDER=openai
                export VERBATIM_MODEL=gpt-4o
                SOMETHING_ELSE=keep me
                # a trailing comment
                """
            try handwritten.write(to: file, atomically: true, encoding: .utf8)

            try writeConfig(["VERBATIM_PROVIDER": "anthropic",
                             "VERBATIM_MODEL": "claude-opus-5"], at: file)
            let text = body(file)
            check("an unrelated line survives", text.contains("SOMETHING_ELSE=keep me"), text)
            check("a comment survives", text.contains("# my notes, which are mine"), text)
            check("the trailing comment survives", text.contains("# a trailing comment"), text)
            check("the provider is replaced, not duplicated",
                  text.components(separatedBy: "VERBATIM_PROVIDER=").count == 2, text)
            check("the export form is recognised and replaced",
                  !text.contains("gpt-4o") && text.contains("VERBATIM_MODEL=claude-opus-5"), text)
            check("nothing was appended twice",
                  text.components(separatedBy: "VERBATIM_MODEL").count == 2, text)
        }

        print("values that need care")
        do {
            let file = scratch()
            try FileManager.default.createDirectory(at: file.deletingLastPathComponent(),
                                                    withIntermediateDirectories: true)
            try "VERBATIM_MODEL=\"quoted value\"\nVERBATIM_API_KEY=sk-old\n"
                .write(to: file, atomically: true, encoding: .utf8)
            check("a quoted value is read without its quotes",
                  readConfig(at: file)["VERBATIM_MODEL"] == "quoted value")

            // An empty field means "I removed this", not "write me an empty line".
            try writeConfig(["VERBATIM_API_KEY": ""], at: file)
            check("an emptied value stops being set", readConfig(at: file)["VERBATIM_API_KEY"] == nil,
                  body(file))
            check("and the old value is gone from the file", !body(file).contains("sk-old"), body(file))
        }

        print("the key a person had under the provider's own name")
        do {
            let file = scratch()
            try FileManager.default.createDirectory(at: file.deletingLastPathComponent(),
                                                    withIntermediateDirectories: true)
            try "ANTHROPIC_API_KEY=sk-theirs\n".write(to: file, atomically: true, encoding: .utf8)
            try writeConfig(["VERBATIM_API_KEY": "sk-ours"], at: file)
            let text = body(file)
            // Deliberate: their line is not ours to delete. providers.py reads
            // VERBATIM_API_KEY first, so the one the sheet wrote is the one that runs.
            check("their line is left alone", text.contains("ANTHROPIC_API_KEY=sk-theirs"), text)
            check("ours is written beside it", text.contains("VERBATIM_API_KEY=sk-ours"), text)
        }

        print("a file that is only whitespace")
        do {
            let file = scratch()
            try FileManager.default.createDirectory(at: file.deletingLastPathComponent(),
                                                    withIntermediateDirectories: true)
            try "\n\n  \n".write(to: file, atomically: true, encoding: .utf8)
            try writeConfig(["VERBATIM_PROVIDER": "openai"], at: file)
            check("it is filled rather than corrupted",
                  readConfig(at: file)["VERBATIM_PROVIDER"] == "openai", body(file))
        }

        print("")
        if failures == 0 {
            print("config: all green")
            exit(0)
        } else {
            print("config: \(failures) failing")
            exit(1)
        }
    }
}
