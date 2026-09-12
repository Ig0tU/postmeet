import { execFile } from "child_process";

/** All workers converge on Python's canonical renderer; never render in TS. */
export function finalizePublication(result: unknown, request: Record<string, unknown>): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const child = execFile("python3", ["-m", "postmeet.publication"], {
      env: { ...process.env, PYTHONPATH: process.cwd() },
      timeout: 45000,
      maxBuffer: 32 * 1024 * 1024,
    }, (error, stdout) => {
      if (error) {
        reject(new Error("Publication failed: canonical YouTube metadata/rendering unavailable. " + error.message));
        return;
      }
      try { resolve(JSON.parse(stdout)); } catch { reject(new Error("Invalid publication output")); }
    });
    child.stdin?.on("error", () => { /* reported by execFile callback */ });
    child.stdin?.end(JSON.stringify({ result, request }));
  });
}
