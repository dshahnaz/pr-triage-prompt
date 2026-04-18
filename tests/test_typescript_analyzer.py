from pathlib import Path

from pr_triage_prompt.analyzers.typescript import TypeScriptAnalyzer


def _analyze(filename: str, patch: str, status: str = "modified"):
    return TypeScriptAnalyzer().analyze(Path(filename), patch, status)


def test_added_class_and_methods() -> None:
    patch = (
        "@@ -0,0 +1,7 @@\n"
        "+export class UserStore {\n"
        "+    constructor(private api: Api) {}\n"
        "+    async load(id: string) {\n"
        "+        return this.api.get(id);\n"
        "+    }\n"
        "+    clear() { this.cache = {}; }\n"
        "+}\n"
    )
    summary = _analyze("store.ts", patch, status="added")
    assert "UserStore" in summary.classes_changed
    assert "UserStore.load" in summary.functions_changed


def test_arrow_function_and_interface() -> None:
    patch = (
        "@@ -0,0 +1,4 @@\n"
        "+export interface Config { debug: boolean }\n"
        "+export const makeClient = (cfg: Config) => new Client(cfg);\n"
        "+export function boot() { return makeClient({ debug: false }); }\n"
        "+const helper = async (x: number) => x + 1;\n"
    )
    summary = _analyze("client.ts", patch, status="added")
    assert "Config" in summary.classes_changed
    assert "makeClient" in summary.functions_changed
    assert "boot" in summary.functions_changed
    assert "helper" in summary.functions_changed


def test_tsx_extension_routes_to_analyzer() -> None:
    patch = (
        "@@ -0,0 +1,3 @@\n"
        "+export function Button() { return <button/>; }\n"
    )
    summary = _analyze("Button.tsx", patch, status="added")
    assert "Button" in summary.functions_changed


def test_counts_additions_deletions() -> None:
    patch = (
        "@@ -1,2 +1,3 @@\n"
        " const a = 1;\n"
        "+const b = 2;\n"
        "-const c = 3;\n"
        "+const c = 4;\n"
    )
    summary = _analyze("x.ts", patch)
    assert summary.additions == 2
    assert summary.deletions == 1
