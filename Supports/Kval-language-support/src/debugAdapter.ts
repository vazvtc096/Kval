import * as cp from "child_process";
import * as path from "path";
import {
  DebugSession,
  InitializedEvent,
  OutputEvent,
  TerminatedEvent,
  ThreadEvent,
} from "@vscode/debugadapter";
import type { DebugProtocol } from "@vscode/debugprotocol";

class KvalDebugSession extends DebugSession {
  private child: cp.ChildProcess | undefined;

  public constructor() {
    super(false, true);
  }

  protected initializeRequest(response: DebugProtocol.InitializeResponse): void {
    this.sendResponse(response);
    this.sendEvent(new InitializedEvent());
  }

  protected launchRequest(
    response: DebugProtocol.LaunchResponse,
    args: DebugProtocol.LaunchRequestArguments
  ): void {
    const a = args as Record<string, unknown>;
    const program = String(a.program ?? "");
    const pythonPath = String(a.pythonPath ?? "python");
    const pythonSysPathRoot = String(a.pythonSysPathRoot ?? "");
    if (!program) {
      this.sendErrorResponse(response, 0, "未设置 program（.kval 文件路径）");
      return;
    }
    this.sendResponse(response);
    this.sendEvent(new ThreadEvent("started", 1));

    this.child = cp.spawn(pythonPath, ["-m", "Kval", "run", program], {
      cwd: path.dirname(program) || process.cwd(),
      env: { ...process.env, PYTHONPATH: pythonSysPathRoot || process.env.PYTHONPATH || "" },
      windowsHide: false,
    });

    this.child.stdout?.on("data", (b) => {
      this.sendEvent(new OutputEvent(b.toString(), "stdout"));
    });
    this.child.stderr?.on("data", (b) => {
      this.sendEvent(new OutputEvent(b.toString(), "stderr"));
    });
    this.child.on("close", (code) => {
      this.sendEvent(new OutputEvent(`\n[Kval] 进程结束，退出码 ${code ?? 0}\n`, "console"));
      this.sendEvent(new TerminatedEvent());
    });
    this.child.on("error", (err) => {
      this.sendEvent(new OutputEvent(String(err), "stderr"));
      this.sendEvent(new TerminatedEvent());
    });
  }

  protected disconnectRequest(
    response: DebugProtocol.DisconnectResponse,
    args: DebugProtocol.DisconnectArguments,
    request?: DebugProtocol.Request
  ): void {
    this.child?.kill();
    super.disconnectRequest(response, args, request);
  }

  protected threadsRequest(response: DebugProtocol.ThreadsResponse): void {
    response.body = { threads: [{ id: 1, name: "Kval" }] };
    this.sendResponse(response);
  }
}

DebugSession.run(KvalDebugSession);
