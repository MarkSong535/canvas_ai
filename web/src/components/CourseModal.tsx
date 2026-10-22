import { useEffect, useState } from "react";
import type { Course } from "../protocol";

type Props = {
  courses: Course[];
  canDownload: boolean;
  onDownload: (courses: Course[]) => void;
  onClose: () => void;
};

export function CourseModal({ courses, canDownload, onDownload, onClose }: Props) {
  const [selected, setSelected] = useState<string[]>([]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const toggle = (id: string, checked: boolean) =>
    setSelected((ids) => (checked ? [...ids, id] : ids.filter((other) => other !== id)));

  return (
    <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="courseModalTitle">
        <div className="modal-head">
          <div>
            <div className="modal-title" id="courseModalTitle">
              Select Courses for Download
            </div>
            <div className="modal-copy">Choose one or more courses, then start the same download flow used in the original page.</div>
          </div>
          <button className="close-btn" type="button" onClick={onClose} aria-label="Close course selector">
            ×
          </button>
        </div>
        <div className="modal-body">
          {courses.length ? (
            <div className="course-list">
              {courses.map((course, idx) => {
                const id = String(course.id);
                return (
                  <label key={id} className="course-option">
                    <input type="checkbox" checked={selected.includes(id)} onChange={(e) => toggle(id, e.target.checked)} />
                    <div>
                      <div className="course-name">{course.name || "Untitled course"}</div>
                      <div className="course-meta">
                        Index: {course.index ?? idx + 1} • ID: {id}
                      </div>
                    </div>
                  </label>
                );
              })}
            </div>
          ) : (
            <div className="course-empty">No courses are available yet. Try reconnecting in a moment.</div>
          )}
        </div>
        <div className="modal-actions">
          <button className="modal-btn muted" type="button" onClick={onClose}>
            Cancel
          </button>
          <button
            className="modal-btn primary"
            type="button"
            disabled={!canDownload || selected.length === 0}
            onClick={() => onDownload(courses.filter((c) => selected.includes(String(c.id))))}
          >
            Start Download
          </button>
        </div>
      </div>
    </div>
  );
}
