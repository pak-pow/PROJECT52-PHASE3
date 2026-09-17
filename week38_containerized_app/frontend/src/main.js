/**
 * Project 52 - Week 38: Containerized App with Docker (Docker Pulse)
 * Frontend Application Entry Point
 * 
 * The initialization script mounts the dashboard and initializes telemetry.
 */

import { DashboardPage } from './pages/dashboardPage.js';

document.addEventListener('DOMContentLoaded', () => {
  // The system logs initialization confirmation to the console
  console.log('[Docker Pulse] Operations Hub initialized in vanilla JS module mode.');

  const appContainer = document.getElementById('app');
  if (appContainer) {
    const dashboard = new DashboardPage(appContainer);
    dashboard.init();
  }
});