/**
 * Toast notification component rendering transient alerts for user operations.
 * 
 * The controller appends and automatically dismisses notification elements.
 */

import { escapeHtml } from '../utils/helpers.js';

export class Toast {
  /**
   * Displays a temporary floating toast message on screen.
   */
  static show(message, type = 'info', duration = 3500) {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
      <span class="toast-icon">${type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'}</span>
      <span class="toast-text">${escapeHtml(message)}</span>
    `;

    container.appendChild(toast);

    // Fade out and remove element after duration
    setTimeout(() => {
      toast.classList.add('toast-hiding');
      setTimeout(() => {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 300);
    }, duration);
  }

  static success(msg) { Toast.show(msg, 'success'); }
  static error(msg) { Toast.show(msg, 'error'); }
  static info(msg) { Toast.show(msg, 'info'); }
}