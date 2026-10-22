// Cloudflare Turnstile challenge; its token is the WebSocket's admission ticket (redeemed once by the server).
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";

type TurnstileApi = {
  render: (el: HTMLElement, options: Record<string, unknown>) => string;
  reset: (widgetId: string) => void;
  remove: (widgetId: string) => void;
};

declare global {
  interface Window {
    turnstile?: TurnstileApi;
    onCanvasTurnstileLoad?: () => void;
  }
}

const SCRIPT_SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js?onload=onCanvasTurnstileLoad&render=explicit";

let scriptLoaded: Promise<TurnstileApi> | null = null;
function loadTurnstile(): Promise<TurnstileApi> {
  scriptLoaded ??= new Promise((resolve) => {
    window.onCanvasTurnstileLoad = () => resolve(window.turnstile!);
    const script = document.createElement("script");
    script.src = SCRIPT_SRC;
    script.async = true;
    script.defer = true;
    document.head.appendChild(script);
  });
  return scriptLoaded;
}

export type TurnstileHandle = { reset: () => void };

type Props = {
  sitekey: string;
  action: string;
  onToken: (token: string) => void;
  onExpired: () => void;
  onError: () => void;
};

export const Turnstile = forwardRef<TurnstileHandle, Props>(function Turnstile(props, ref) {
  const el = useRef<HTMLDivElement>(null);
  const widgetId = useRef<string | null>(null);
  const callbacks = useRef(props);
  callbacks.current = props;

  useEffect(() => {
    // Dev builds only: skip the challenge (e.g. against a local mock); ws_server.py rejects the placeholder token
    if (import.meta.env.DEV && import.meta.env.VITE_SKIP_TURNSTILE === "1") {
      callbacks.current.onToken("dev-skip");
      return;
    }
    let cancelled = false;
    loadTurnstile().then((turnstile) => {
      if (cancelled || !el.current) return;
      widgetId.current = turnstile.render(el.current, {
        sitekey: props.sitekey,
        action: props.action,
        callback: (token: string) => callbacks.current.onToken(token),
        "expired-callback": () => callbacks.current.onExpired(),
        "error-callback": () => callbacks.current.onError(),
      });
    });
    return () => {
      cancelled = true;
      if (widgetId.current !== null) window.turnstile?.remove(widgetId.current);
      widgetId.current = null;
    };
  }, [props.sitekey, props.action]);

  useImperativeHandle(ref, () => ({
    reset: () => {
      if (import.meta.env.DEV && import.meta.env.VITE_SKIP_TURNSTILE === "1") return callbacks.current.onToken("dev-skip");
      if (window.turnstile && widgetId.current !== null) window.turnstile.reset(widgetId.current);
    },
  }));

  return <div ref={el} />;
});
