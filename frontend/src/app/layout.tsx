import { headers } from "next/headers";
import type { Metadata } from "next";
import { Shell } from "@/components/shell";
import "./globals.css";
import "./dashboard.css";
export const metadata: Metadata = {
  title: "SpecHelper",
  description: "From business needs to implementation-ready tickets.",
};
export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const nonce = (await headers()).get("x-nonce") || undefined;
  return (
    <html lang="fr" data-theme="dark" suppressHydrationWarning>
      <head>
        <script nonce={nonce}
          dangerouslySetInnerHTML={{
            __html: `(function(){var t="dark";try{var v=localStorage.getItem("spechelper-theme");if(v==="light"||v==="dark"||v==="system")t=v}catch(e){}document.documentElement.dataset.theme=t==="system"?(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"):t})()`,
          }}
        />
      </head>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
