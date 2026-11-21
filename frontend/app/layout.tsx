import type { Metadata } from "next";
import { AuthProvider } from "@/components/AuthContext";
import ErrorReporter from "@/components/ErrorReporter";
import Sidebar from "@/components/Sidebar";
import "./globals.css";

export const metadata: Metadata = {
  title: "降 AI 味改写平台",
  description: "保持原意与段落结构的中文改写工具",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>
        <AuthProvider>
          <ErrorReporter />
          <div className="min-h-screen md:flex">
            <Sidebar />
            <main className="min-w-0 flex-1 px-3 py-5 sm:px-5 sm:py-6">
              <div className="mx-auto max-w-6xl">{children}</div>
            </main>
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}
