import { useEffect, useRef } from "react";
import type { ChatMessage, Stream } from "../chatState";
import { SUGGESTIONS } from "../config";
import { Message, StreamingMessage } from "./Message";

type Props = {
  messages: ChatMessage[];
  stream: Stream | null;
  onSuggest: (text: string) => void;
  onEscalate: (id: number) => void;
};

function EmptyState({ onSuggest }: { onSuggest: (text: string) => void }) {
  return (
    <div className="empty">
      <div className="empty-icon">🎓</div>
      <h2>Canvas AI Agent</h2>
      <p>Your AI assistant for Canvas. Ask about your courses, assignments, grades, or files.</p>
      <div className="suggestions">
        {SUGGESTIONS.map((text) => (
          <button key={text} className="suggestion" type="button" onClick={() => onSuggest(text)}>
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}

export function MessageList({ messages, stream, onSuggest, onEscalate }: Props) {
  const el = useRef<HTMLDivElement>(null);

  // Follow the conversation as it grows, streamed text included
  useEffect(() => {
    if (el.current) el.current.scrollTop = el.current.scrollHeight;
  }, [messages, stream]);

  return (
    <div className="messages" ref={el}>
      {messages.length === 0 && !stream ? (
        <EmptyState onSuggest={onSuggest} />
      ) : (
        <>
          {messages.map((m) => (
            <Message key={m.id} message={m} onEscalate={onEscalate} />
          ))}
          {stream && <StreamingMessage stream={stream} />}
        </>
      )}
    </div>
  );
}
