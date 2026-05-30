import * as path from "path";
import * as fs from "fs";
import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  TransportKind,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;

function shellQuoteSingle(s: string): string {
  return `'${s.replace(/'/g, "''")}'`;
}

function shellQuoteDouble(s: string): string {
  return `"${s.replace(/"/g, '\\"')}"`;
}

function buildRunCommand(py: string, filePath: string, mode: "run" | "compile"): string {
  const shell = (vscode.env.shell ?? "").toLowerCase();
  const sub = mode === "run" ? "run" : "compile";

  // PowerShell requires call operator for quoted executable path.
  if (shell.includes("powershell") || shell.includes("pwsh")) {
    return `& ${shellQuoteSingle(py)} -m Kval ${sub} ${shellQuoteSingle(filePath)}`;
  }
  // cmd/bash/zsh/fish: regular quoted invocation works.
  return `${shellQuoteDouble(py)} -m Kval ${sub} ${shellQuoteDouble(filePath)}`;
}

function resolvePythonSysPathRoot(workspaceFolder: string | undefined, configured: string): string {
  if (configured.trim()) return configured.trim();
  if (!workspaceFolder) return "";
  const base = workspaceFolder;
  const parserProbe = path.join(base, "Core", "Parser", "Parser.py");
  if (path.basename(base) === "Kval" && fs.existsSync(parserProbe)) {
    return path.dirname(base);
  }
  return base;
}

function kvalSettings() {
  const cfg = vscode.workspace.getConfiguration("kval");
  const wf = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  const configuredRoot = cfg.get<string>("workspaceRoot") ?? "";
  return {
    pythonPath: (cfg.get<string>("pythonPath") ?? "python").trim(),
    workspaceRoot: wf ?? "",
    pythonSysPathRoot: resolvePythonSysPathRoot(wf, configuredRoot),
    diagnosticsEnabled: cfg.get<boolean>("diagnosticsEnabled") ?? true,
    diagnosticsDelayMs: cfg.get<number>("diagnosticsDelayMs") ?? 400,
  };
}

export function activate(context: vscode.ExtensionContext): void {
  const serverModule = context.asAbsolutePath(path.join("out", "server.js"));
  const serverOptions: ServerOptions = {
    run: { module: serverModule, transport: TransportKind.ipc },
    debug: {
      module: serverModule,
      transport: TransportKind.ipc,
      options: { execArgv: ["--nolazy", "--inspect=6009"] },
    },
  };

  const clientOptions: LanguageClientOptions = {
    documentSelector: [
      { scheme: "file", language: "kval" },
      { scheme: "file", language: "kvi" },
    ],
    synchronize: {
      fileEvents: vscode.workspace.createFileSystemWatcher("**/*.{kval,kvi}"),
    },
    initializationOptions: {
      extensionRoot: context.extensionPath,
      ...kvalSettings(),
    } satisfies Record<string, unknown>,
    middleware: {},
  };

  client = new LanguageClient(
    "kvalLanguageServer",
    "Kval Language Server",
    serverOptions,
    clientOptions
  );

  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (!e.affectsConfiguration("kval")) return;
      void client?.sendNotification("kval/settings", {
        extensionRoot: context.extensionPath,
        ...kvalSettings(),
      });
    })
  );

  const run = (mode: "run" | "compile") => {
    const ed = vscode.window.activeTextEditor;
    if (!ed || ed.document.languageId !== "kval") {
      vscode.window.showWarningMessage("当前不是 .kval 文件。");
      return;
    }
    const doc = ed.document;
    if (doc.isUntitled) {
      vscode.window.showWarningMessage("请先保存文件。");
      return;
    }
    const cfg = vscode.workspace.getConfiguration("kval");
    const py = (cfg.get<string>("pythonPath") ?? "python").trim();
    const wf = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? "";
    const sysRoot = resolvePythonSysPathRoot(wf, cfg.get<string>("workspaceRoot") ?? "");
    const term = vscode.window.createTerminal({
      name: "Kval",
      cwd: wf || path.dirname(doc.uri.fsPath),
      env: { ...process.env, PYTHONPATH: sysRoot },
    });
    term.show();
    const q = doc.uri.fsPath;
    term.sendText(buildRunCommand(py, q, mode));
  };

  context.subscriptions.push(
    vscode.commands.registerCommand("kval.runFile", () => run("run")),
    vscode.commands.registerCommand("kval.compileFile", () => run("compile")),
    vscode.commands.registerCommand("kval.showOutput", () => {
      client?.outputChannel.show(true);
    })
  );

  void client.start();
  context.subscriptions.push(
    new vscode.Disposable(() => {
      void client?.stop();
    })
  );

  const fillKvalDebugConfig = (
    folder: vscode.WorkspaceFolder | undefined,
    config: vscode.DebugConfiguration
  ): vscode.DebugConfiguration => {
    const wf = folder?.uri.fsPath ?? vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    const cfg = vscode.workspace.getConfiguration("kval");
    const py =
      (config.pythonPath as string | undefined)?.trim() ||
      cfg.get<string>("pythonPath") ||
      "python";
    const sysRoot =
      (config.pythonSysPathRoot as string | undefined)?.trim() ||
      resolvePythonSysPathRoot(wf, cfg.get<string>("workspaceRoot") ?? "");
    return { ...config, pythonPath: py, pythonSysPathRoot: sysRoot };
  };

  context.subscriptions.push(
    vscode.debug.registerDebugConfigurationProvider(
      "kval",
      {
        resolveDebugConfiguration(_folder, config) {
          if (config.type !== "kval") return config;
          return config;
        },
      },
      vscode.DebugConfigurationProviderTriggerKind.Initial
    ),
    vscode.debug.registerDebugConfigurationProvider(
      "kval",
      {
        resolveDebugConfigurationWithSubstitutedVariables(folder, config) {
          if (config.type !== "kval") return config;
          const c = fillKvalDebugConfig(folder ?? undefined, config);
          const p = String(c.program ?? "").trim();
          if (!p) {
            void vscode.window.showErrorMessage(
              "Kval 调试：请在 launch.json 中设置 program（例如 ${file}）。"
            );
            return undefined;
          }
          return c;
        },
      },
      vscode.DebugConfigurationProviderTriggerKind.Dynamic
    )
  );

  context.subscriptions.push(
    vscode.debug.registerDebugAdapterDescriptorFactory("kval", {
      createDebugAdapterDescriptor() {
        return new vscode.DebugAdapterExecutable(process.execPath, [
          context.asAbsolutePath(path.join("out", "debugAdapter.js")),
        ]);
      },
    })
  );
}

export function deactivate(): Thenable<void> | undefined {
  return client?.stop();
}
