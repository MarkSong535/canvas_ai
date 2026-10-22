import { memo, useMemo } from "react";
import type { ChatMessage, Stream } from "../chatState";
import { renderRich } from "../render/richText";
import type { Renders } from "../protocol";

function Bubble({ who, children }: { who: "user" | "ai"; children: React.ReactNode }) {
  return (
    <div className={`msg ${who}`}>
      <div className="msg-avatar">{who === "user" ? "you" : "ai"}</div>
      <div className="msg-body">
        <div className="msg-role">{who === "user" ? "you" : "canvas ai"}</div>
        {children}
      </div>
    </div>
  );
}

function RichText({ text, renders, cursor = false }: { text: string; renders: Renders | null; cursor?: boolean }) {
  const html = useMemo(() => renderRich(text, renders, { cursor }), [text, renders, cursor]);
  return <div className="msg-text md" dangerouslySetInnerHTML={{ __html: html }} />;
}

const TypingDots = () => (
  <div className="typing-dots">
    <span />
    <span />
    <span />
  </div>
);

type Props = { message: ChatMessage; onEscalate: (id: number) => void };

export const Message = memo(function Message({ message, onEscalate }: Props) {
  switch (message.role) {
    case "user":
      return (
        <Bubble who="user">
          <div className="msg-text">{message.text}</div>
        </Bubble>
      );
    case "ai":
      return (
        <Bubble who="ai">
          <RichText text={message.text} renders={message.renders} />
          {/* The server never escalates on its own; when an answer struggled it offers a retry and the user decides */}
          {message.canEscalate && (
            <button className="escalate-btn" type="button" onClick={() => onEscalate(message.id)}>
              Try again with deeper reasoning
            </button>
          )}
        </Bubble>
      );
    case "error":
      return (
        <Bubble who="ai">
          <div className="msg-text">
            Error: {message.text}
            {message.count > 1 && ` (x${message.count})`}
          </div>
        </Bubble>
      );
    case "note":
      return <div className="msg-note">{message.text}</div>;
  }
});

// The reply being streamed: typing dots, then text that fills in with a cursor; tool activity shows above it
export function StreamingMessage({ stream }: { stream: Stream }) {
  return (
    <Bubble who="ai">
      {stream.status && <div className="msg-status">{stream.status}</div>}
      {stream.text ? (
        <RichText text={stream.text} renders={null} cursor />
      ) : (
        <div className="msg-text">
          <TypingDots />
        </div>
      )}
    </Bubble>
  );
}
