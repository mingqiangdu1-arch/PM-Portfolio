import { beforeEach, describe, expect, it, vi } from "vitest";

const client = vi.hoisted(() => ({
  abortFileUpload: vi.fn(),
  completeFileUpload: vi.fn(),
  createProject: vi.fn(),
  getApiHealth: vi.fn(),
  getFile: vi.fn(),
  getProject: vi.fn(),
  getProjectVersion: vi.fn(),
  getSession: vi.fn(),
  initFileUpload: vi.fn(),
  listProjects: vi.fn(),
  listProjectVersions: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  refreshAccessToken: vi.fn(),
  register: vi.fn(),
  setWorkingProjectVersion: vi.fn(),
}));

vi.mock("./generated/client", () => client);

import { __resetRealAdapterForTests, realApi } from "./real-adapter";
import { PortError } from "./ports";

const success = <T,>(data: T) => ({ status: 200, data: { code: "OK", message: "ok", trace_id: "trace-ok", data }, headers: new Headers() }) as never;
const failure = (code: string, status: number, details: unknown[] = [{ field: "x", message: "bad" }]) => ({ status, data: { code, message: `error:${code}`, trace_id: "trace-error", details }, headers: new Headers() }) as never;
const refreshed = () => success({ access_token: "rotated-token", expires_in: 900, token_type: "Bearer" });
const emptyProjects = () => success({ items: [], has_more: false, next_cursor: null });
const emptyVersions = () => success({ items: [], has_more: false, next_cursor: null });
const session = () => success({ session_id: "session-1", expires_at: "2026-08-03T01:00:00Z", system_roles: [], user: { id: "user-1", display_name: "User", email: "user@example.com", status: "active", system_roles: [] } });
const authToken = (access_token: string) => success({ access_token, expires_in: 900, token_type: "Bearer", user: { id: "user-1", display_name: "User", email: "user@example.com", status: "active", system_roles: [] } });
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (reason?: unknown) => void; const promise = new Promise<T>((resolvePromise, rejectPromise) => { resolve = resolvePromise; reject = rejectPromise; }); return { promise, resolve, reject }; }

class SuccessfulUploadRequest {
  status = 200;
  upload: { onprogress?: (event: ProgressEvent<EventTarget>) => void } = {};
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  open = vi.fn();
  setRequestHeader = vi.fn();
  getResponseHeader = vi.fn(() => "etag-1");
  send = vi.fn(() => this.onload?.());
}

describe("realApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    __resetRealAdapterForTests();
    vi.stubGlobal("XMLHttpRequest", SuccessfulUploadRequest);
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "test-key"), subtle: { digest: vi.fn(async () => new Uint8Array(32).buffer) } });
  });

  it("refreshes once after a 401 and retries the original protected request", async () => {
    client.listProjects.mockResolvedValueOnce(failure("AUTH_REQUIRED", 401)).mockResolvedValueOnce(emptyProjects());
    client.refreshAccessToken.mockResolvedValue(refreshed());

    await expect(realApi.projects.list()).resolves.toEqual([]);

    expect(client.refreshAccessToken).toHaveBeenCalledTimes(1);
    expect(client.listProjects).toHaveBeenCalledTimes(2);
    expect(client.listProjects.mock.calls[1][1].headers).toEqual({ Authorization: "Bearer rotated-token" });
  });

  it("uses a single refresh rotation for concurrent 401 responses", async () => {
    client.listProjects.mockResolvedValueOnce(failure("AUTH_REQUIRED", 401)).mockResolvedValueOnce(emptyProjects());
    client.listProjectVersions.mockResolvedValueOnce(failure("UNAUTHORIZED", 401)).mockResolvedValueOnce(emptyVersions());
    client.refreshAccessToken.mockResolvedValue(refreshed());

    await expect(Promise.all([realApi.projects.list(), realApi.projects.versions("project-1")])).resolves.toEqual([[], []]);

    expect(client.refreshAccessToken).toHaveBeenCalledTimes(1);
  });

  it("does not recurse when refresh fails and preserves the refresh business error", async () => {
    const recover = vi.fn();
    window.addEventListener("aipdv:session-recovery", recover);
    client.listProjects.mockResolvedValue(failure("AUTH_REQUIRED", 401));
    client.refreshAccessToken.mockResolvedValue(failure("TOKEN_REUSE_DETECTED", 401));

    await expect(realApi.projects.list()).rejects.toMatchObject({ category: "UNAUTHENTICATED", apiCode: "TOKEN_REUSE_DETECTED", status: 401, traceId: "trace-error" });

    expect(client.refreshAccessToken).toHaveBeenCalledTimes(1);
    expect(client.listProjects).toHaveBeenCalledTimes(1);
    expect(recover).toHaveBeenCalledTimes(1);
    window.removeEventListener("aipdv:session-recovery", recover);
  });

  it("clears the current token and emits one recovery event when the retried request is still unauthorized", async () => {
    const recover = vi.fn();
    window.addEventListener("aipdv:session-recovery", recover);
    client.listProjects.mockResolvedValueOnce(failure("AUTH_REQUIRED", 401)).mockResolvedValueOnce(failure("UNAUTHORIZED", 401)).mockResolvedValueOnce(emptyProjects());
    client.refreshAccessToken.mockResolvedValue(refreshed());

    await expect(realApi.projects.list()).rejects.toMatchObject({ category: "UNAUTHENTICATED", apiCode: "UNAUTHORIZED" });
    await expect(realApi.projects.list()).resolves.toEqual([]);

    expect(client.refreshAccessToken).toHaveBeenCalledTimes(1);
    expect(recover).toHaveBeenCalledTimes(1);
    expect(client.listProjects.mock.calls[1][1].headers).toEqual({ Authorization: "Bearer rotated-token" });
    expect(client.listProjects.mock.calls[2][1].headers).toBeUndefined();
    window.removeEventListener("aipdv:session-recovery", recover);
  });

  it("does not allow a refresh started before logout to restore authorization", async () => {
    const pendingRefresh = deferred<ReturnType<typeof refreshed>>();
    client.refreshAccessToken.mockReturnValue(pendingRefresh.promise);
    client.getSession.mockResolvedValue(session());
    client.logout.mockResolvedValue(success({}));
    const refresh = realApi.identity.refresh();
    await Promise.resolve();
    const signedOut = realApi.identity.logout();
    await Promise.resolve();

    expect(client.logout).not.toHaveBeenCalled();

    pendingRefresh.resolve(refreshed());
    await Promise.all([refresh, signedOut]);
    expect(client.logout).toHaveBeenCalledTimes(1);
    expect(client.logout.mock.calls[0][1]).toMatchObject({ credentials: "include" });
    expect(client.logout.mock.calls[0][1].headers).toBeUndefined();
    client.listProjects.mockResolvedValue(emptyProjects());
    await realApi.projects.list();

    expect(client.listProjects.mock.calls[0][1].headers).toBeUndefined();
  });

  it("does not start a replacement refresh when an old protected request receives 401 after logout", async () => {
    const delayedResponse = deferred<ReturnType<typeof emptyProjects>>();
    client.listProjects.mockReturnValueOnce(delayedResponse.promise);
    client.logout.mockResolvedValue(success({}));
    const oldRequest = realApi.projects.list();
    await Promise.resolve();
    await realApi.identity.logout();

    delayedResponse.resolve(failure("AUTH_REQUIRED", 401));
    await expect(oldRequest).rejects.toMatchObject({ category: "UNAUTHENTICATED", apiCode: "AUTH_REQUIRED" });

    expect(client.refreshAccessToken).not.toHaveBeenCalled();
  });

  it("does not allow an old refresh to overwrite a newer login or registration", async () => {
    const firstRefresh = deferred<ReturnType<typeof refreshed>>();
    client.refreshAccessToken.mockReturnValueOnce(firstRefresh.promise);
    client.getSession.mockResolvedValue(session());
    client.login.mockResolvedValue(authToken("login-token"));
    const staleRefresh = realApi.identity.refresh();
    await Promise.resolve();
    const login = realApi.identity.login({ email: "user@example.com", password: "password" });
    await Promise.resolve();
    expect(client.login).not.toHaveBeenCalled();
    firstRefresh.resolve(refreshed());
    await login;
    await staleRefresh;
    client.listProjects.mockResolvedValue(emptyProjects());
    await realApi.projects.list();
    expect(client.listProjects.mock.calls[0][1].headers).toEqual({ Authorization: "Bearer login-token" });

    const secondRefresh = deferred<ReturnType<typeof refreshed>>();
    client.refreshAccessToken.mockReturnValueOnce(secondRefresh.promise);
    const staleRefreshAfterLogin = realApi.identity.refresh();
    await Promise.resolve();
    client.register.mockResolvedValue(authToken("register-token"));
    const register = realApi.identity.register({ displayName: "User", email: "user@example.com", password: "password" });
    await Promise.resolve();
    expect(client.register).not.toHaveBeenCalled();
    secondRefresh.resolve(refreshed());
    await register;
    await staleRefreshAfterLogin;
    client.listProjects.mockResolvedValue(emptyProjects());
    await realApi.projects.list();
    expect(client.listProjects.mock.calls[1][1].headers).toEqual({ Authorization: "Bearer register-token" });
  });

  it("preserves generated business code, category, status, details and trace", async () => {
    client.listProjects.mockResolvedValueOnce(failure("VERSION_CONFLICT", 409, [{ field: "version", message: "stale" }]));

    await expect(realApi.projects.list()).rejects.toMatchObject({
      category: "CONFLICT",
      apiCode: "VERSION_CONFLICT",
      status: 409,
      traceId: "trace-error",
      details: [{ field: "version", message: "stale" }],
    });

    client.listProjects.mockResolvedValueOnce(failure("RATE_LIMITED", 429));
    try { await realApi.projects.list(); } catch (error) {
      expect(error).toBeInstanceOf(PortError);
      expect((error as PortError).category).toBe("RATE_LIMITED");
      expect((error as PortError).apiCode).toBe("RATE_LIMITED");
    }
  });

  it("retries an ambiguous complete response with the same idempotency key without reinitializing", async () => {
    client.initFileUpload.mockResolvedValue(success({ upload_id: "upload-1", stored_file_id: "file-1", pending_file_version_id: "pending-1", upload_url: "https://storage.example/upload", http_method: "PUT", required_headers: {}, expires_at: "2026-08-03T00:00:00Z", max_size_bytes: 1024 }));
    client.completeFileUpload.mockRejectedValueOnce(new TypeError("response lost")).mockResolvedValueOnce(success({ file: { id: "file-1", logical_name: "brief.txt", current_version_id: "version-1", status: "available", version: 1 }, current_version: { id: "version-1", storage_status: "available" }, relations: [] }));
    const file = { name: "brief.txt", type: "text/plain", size: 5, arrayBuffer: async () => new TextEncoder().encode("brief").buffer } as File;

    const result = await realApi.files.upload("project-1", file);

    expect(result.status).toBe("uploaded");
    expect(client.initFileUpload).toHaveBeenCalledTimes(1);
    expect(client.completeFileUpload).toHaveBeenCalledTimes(2);
    expect(client.completeFileUpload.mock.calls[0][2]["Idempotency-Key"]).toBe(client.completeFileUpload.mock.calls[1][2]["Idempotency-Key"]);
    expect(client.abortFileUpload).not.toHaveBeenCalled();
  });
});
