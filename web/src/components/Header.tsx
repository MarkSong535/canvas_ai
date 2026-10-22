import { GITHUB_URL } from "../config";

type Props = { connected: boolean; badge: string; canStartNew: boolean; onNewChat: () => void };

export function Header({ connected, badge, canStartNew, onNewChat }: Props) {
  // The dot stays neutral until the first connection attempt settles
  const dot = connected ? "ready" : badge === "disconnected" || badge === "verification unavailable" ? "error" : "";
  return (
    <header>
      <div className="logo">
        <div>
          <div className="logo-text">Canvas AI Agent</div>
          <a className="logo-sub" href={GITHUB_URL} target="_blank" rel="noopener noreferrer">
            <img src={`${import.meta.env.BASE_URL}github-mark.svg`} alt="" />
            <span>GitHub</span>
          </a>
        </div>
      </div>
      <div className="header-actions">
        <button className="new-chat-btn" type="button" disabled={!canStartNew} onClick={onNewChat}>
          New chat
        </button>
        <span className="session-badge">{badge}</span>
        <div className={`status-dot ${dot}`} />
      </div>
    </header>
  );
}
