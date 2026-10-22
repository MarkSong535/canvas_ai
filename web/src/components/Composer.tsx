import { forwardRef, useImperativeHandle, useRef, useState } from "react";

type Props = {
  canSend: boolean;
  onSend: (text: string) => boolean;
  coursesEnabled: boolean;
  courseStatus: string;
  onOpenCourses: () => void;
};

export type ComposerHandle = { focus: () => void; fill: (text: string) => void };

const MAX_HEIGHT = 140;

export const Composer = forwardRef<ComposerHandle, Props>(function Composer(
  { canSend, onSend, coursesEnabled, courseStatus, onOpenCourses },
  ref,
) {
  const [text, setText] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);

  const resize = () => {
    const el = input.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, MAX_HEIGHT) + "px";
  };

  useImperativeHandle(ref, () => ({
    focus: () => input.current?.focus(),
    fill: (value: string) => {
      setText(value);
      requestAnimationFrame(resize);
    },
  }));

  const submit = () => {
    const value = text.trim();
    if (!value || !canSend || !onSend(value)) return;
    setText("");
    if (input.current) input.current.style.height = "auto";
  };

  return (
    <div className="input-bar">
      <div className="input-wrap">
        <textarea
          ref={input}
          value={text}
          placeholder="Ask about courses, assignments, grades, files…"
          rows={1}
          onChange={(e) => {
            setText(e.target.value);
            resize();
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button className="send-btn" type="button" aria-label="Send" disabled={!canSend || !text.trim()} onClick={submit}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="19" x2="12" y2="5" />
            <polyline points="5 12 12 5 19 12" />
          </svg>
        </button>
      </div>
      <div className="input-actions">
        <button className="secondary-btn" type="button" disabled={!coursesEnabled} onClick={onOpenCourses}>
          Select Courses for Download
        </button>
        <div className="course-status">{courseStatus}</div>
        <div className="input-hint">
          <kbd>Enter</kbd> to send · <kbd>Shift+Enter</kbd> for newline
        </div>
      </div>
    </div>
  );
});
