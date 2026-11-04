"use client";

import { useEffect, useState } from "react";

export function browserTicketUrl(value: string | undefined, browserHostname: string): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || /[\\\s\x00-\x1f\x7f]/.test(value)) return null;
    // Docker's host alias is for connectors, not for the local browser. Keep
    // the recorded URL intact and preserve its scheme, port and ticket route.
    if (url.hostname === "host.docker.internal") {
      if (!/^(localhost|127\.0\.0\.1|\[::1\])$/.test(browserHostname) && !browserHostname.endsWith(".localhost")) return null;
      url.hostname = browserHostname;
    }
    return url.href;
  } catch {
    return null;
  }
}

export function useTicketUrlResolver() {
  const [hostname, setHostname] = useState("");
  useEffect(() => { setHostname(window.location.hostname); }, []);
  return (value?: string) => browserTicketUrl(value, hostname);
}
