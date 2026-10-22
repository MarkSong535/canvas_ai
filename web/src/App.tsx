import { useCallback, useEffect, useRef, useState } from "react";
import { Composer, type ComposerHandle } from "./components/Composer";
import { CourseModal } from "./components/CourseModal";
import { Header } from "./components/Header";
import { MessageList } from "./components/MessageList";
import { Turnstile, type TurnstileHandle } from "./components/Turnstile";
import { TURNSTILE_ACTION, TURNSTILE_SITEKEY, WS_ENDPOINT } from "./config";
import type { Course } from "./protocol";
import { useCanvasSocket } from "./useCanvasSocket";

const RETRY_VERIFICATION_MS = 3000;

// A short-lived message shown in place of the course status, e.g. after requesting a download
function useTransientText() {
  const [text, setText] = useState("");
  const timer = useRef<number | undefined>(undefined);
  const show = useCallback((value: string, durationMs?: number) => {
    window.clearTimeout(timer.current);
    setText(value);
    if (durationMs) timer.current = window.setTimeout(() => setText(""), durationMs);
  }, []);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  return [text, show] as const;
}

export default function App() {
  const turnstile = useRef<TurnstileHandle>(null);
  const composer = useRef<ComposerHandle>(null);
  const retryTimer = useRef<number | undefined>(undefined);
  const connectedRef = useRef(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [courseNote, showCourseNote] = useTransientText();

  // After a disconnect, ask Turnstile for a fresh token; its callback reconnects
  const retryVerification = useCallback(() => {
    window.clearTimeout(retryTimer.current);
    retryTimer.current = window.setTimeout(() => {
      if (connectedRef.current) return;
      setBadge("verifying…");
      turnstile.current?.reset();
    }, RETRY_VERIFICATION_MS);
  }, []);

  const { state, connect, sendChat, escalate, newChat, downloadCourses, setBadge } = useCanvasSocket({
    endpoint: WS_ENDPOINT,
    onClosed: retryVerification,
  });
  connectedRef.current = state.connected;
  const { connected, pending, courses, coursesLoaded } = state;

  useEffect(() => {
    if (!connected) {
      setModalOpen(false);
      showCourseNote("");
    }
  }, [connected, showCourseNote]);
  useEffect(() => () => window.clearTimeout(retryTimer.current), []);

  let courseStatus = courseNote;
  if (!courseStatus) {
    if (!connected) courseStatus = "Reconnect to load courses";
    else if (state.courseError) courseStatus = "Course initialization failed. See error above.";
    else if (!coursesLoaded) courseStatus = "Loading courses…";
    else if (courses.length === 0) courseStatus = "No courses available";
    else courseStatus = `${courses.length} course${courses.length === 1 ? "" : "s"} ready`;
  }

  // Messages are memoized; keep the escalate handler's identity stable across renders
  const escalateRef = useRef(escalate);
  escalateRef.current = escalate;
  const onEscalate = useCallback((id: number) => escalateRef.current(id), []);

  const onDownload = (selected: Course[]) => {
    if (selected.length === 0) {
      showCourseNote("Please select at least one course.", 2500);
      return;
    }
    downloadCourses(selected);
    setModalOpen(false);
    showCourseNote(`Requested download for ${selected.length} course${selected.length === 1 ? "" : "s"}.`, 3000);
  };

  const closeModal = useCallback(() => setModalOpen(false), []);

  return (
    <>
      <div className="app">
        <Header
          connected={connected}
          badge={state.badge}
          canStartNew={connected && !pending}
          onNewChat={() => {
            newChat();
            composer.current?.focus();
          }}
        />
        {/* Stays mounted while connected so the widget can be reset for a fresh token after a disconnect */}
        <div className="verification-overlay" hidden={connected}>
          <Turnstile
            ref={turnstile}
            sitekey={TURNSTILE_SITEKEY}
            action={TURNSTILE_ACTION}
            onToken={connect}
            onExpired={() => {
              if (!connectedRef.current) retryVerification();
            }}
            onError={() => {
              if (!connectedRef.current) setBadge("verification unavailable");
            }}
          />
        </div>
        <MessageList
          messages={state.messages}
          stream={state.stream}
          onSuggest={(text) => {
            if (!sendChat(text)) composer.current?.fill(text);
          }}
          onEscalate={onEscalate}
        />
        <Composer
          ref={composer}
          canSend={connected && !pending}
          onSend={sendChat}
          coursesEnabled={connected && !pending && coursesLoaded && courses.length > 0}
          courseStatus={courseStatus}
          onOpenCourses={() => setModalOpen(true)}
        />
      </div>
      {modalOpen && (
        <CourseModal courses={courses} canDownload={connected && !pending} onDownload={onDownload} onClose={closeModal} />
      )}
    </>
  );
}
