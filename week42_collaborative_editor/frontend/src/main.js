/**
 * PulsePad frontend main entry point.
 */
document.addEventListener("DOMContentLoaded", () => {
  const editor = document.getElementById("primary-editor");
  const docTitle = document.getElementById("doc-title-input");
  const timelineBtn = document.getElementById("toggle-timeline-btn");
  const timelineDrawer = document.getElementById("timeline-drawer");
  const closeTimelineBtn = document.getElementById("close-timeline-btn");

  if (timelineBtn && timelineDrawer) {
    timelineBtn.addEventListener("click", () => {
      timelineDrawer.classList.toggle("hidden");
    });
  }

  if (closeTimelineBtn && timelineDrawer) {
    closeTimelineBtn.addEventListener("click", () => {
      timelineDrawer.classList.add("hidden");
    });
  }
});
