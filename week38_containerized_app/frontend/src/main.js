/**
 * Project 52 - Week 38: Containerized App with Docker (Docker Pulse)
 * Frontend Application Entry Point
 * 
 * The initialization script mounts the dashboard and logs topological state.
 */

document.addEventListener('DOMContentLoaded', () => {
  // The system logs initialization confirmation to the console
  console.log('[Docker Pulse] Operations Hub initialized in vanilla JS module mode.');

  // The script attaches click telemetry to endpoint test buttons
  const testButtons = document.querySelectorAll('.btn-link');
  testButtons.forEach(button => {
    button.addEventListener('click', (event) => {
      const endpoint = button.getAttribute('href');
      console.log(`[Docker Pulse] Dispatching probe request to: ${endpoint}`);
    });
  });
});\n