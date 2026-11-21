"use client";

import { useEffect } from "react";

function report(message: string, detail: string) {
  try {
    void fetch("/api/errors", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        detail,
        path: window.location.pathname,
      }),
      keepalive: true,
    });
  } catch {
    // ignore reporting failures
  }
}

export default function ErrorReporter() {
  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      report(event.message || "前端运行时错误", String(event.error?.stack ?? ""));
    };
    const onRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason;
      report(
        `未处理的 Promise 拒绝：${reason instanceof Error ? reason.message : String(reason)}`,
        reason instanceof Error ? String(reason.stack ?? "") : ""
      );
    };
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, []);

  return null;
}
