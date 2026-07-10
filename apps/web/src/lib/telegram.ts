declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        initData: string;
        ready: () => void;
        expand: () => void;
        colorScheme: "light" | "dark";
        themeParams: Record<string, string>;
        MainButton?: { show: () => void; hide: () => void };
        BackButton?: { show: () => void; hide: () => void };
        onEvent: (event: string, cb: () => void) => void;
        offEvent: (event: string, cb: () => void) => void;
      };
    };
  }
}

export function getTelegramInitData(): string | null {
  if (typeof window === "undefined") return null;
  const tg = window.Telegram?.WebApp;
  if (!tg) return null;
  return tg.initData || null;
}

export function initTelegramWebApp(): void {
  const tg = window.Telegram?.WebApp;
  if (!tg) return;
  try {
    tg.ready();
    tg.expand();
  } catch {
    // ignore
  }
}

export function isInsideTelegram(): boolean {
  return typeof window !== "undefined" && Boolean(window.Telegram?.WebApp);
}
