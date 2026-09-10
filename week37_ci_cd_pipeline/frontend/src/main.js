/**
 * Project 52 - Week 37: CI/CD Pipeline Setup
 * Frontend Application Entry Point
 */

import { initTheme } from './utils/theme.js';
import { DashboardPage } from './pages/dashboardPage.js';

document.addEventListener('DOMContentLoaded', () => {
  // 1. Initialize Theme (dark/light mode)
  initTheme();

  // 2. Mount Dashboard Controller
  const appContainer = document.getElementById('app');
  if (appContainer) {
    const dashboard = new DashboardPage(appContainer);
    dashboard.init();
  }
});
