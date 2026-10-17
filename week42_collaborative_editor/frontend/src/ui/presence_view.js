/**
 * Active participants presence bar and avatar pill renderer.
 */

export class PresenceView {
  constructor(containerElement) {
    this.container = containerElement;
    this.participants = new Map(); // sid -> participant
  }

  setParticipants(participantsList) {
    this.participants.clear();
    for (const p of participantsList) {
      this.participants.set(p.sid, p);
    }
    this.render();
  }

  addOrUpdateParticipant(participant) {
    this.participants.set(participant.sid, {
      ...this.participants.get(participant.sid),
      ...participant,
    });
    this.render();
  }

  removeParticipant(sid) {
    this.participants.delete(sid);
    this.render();
  }

  setTyping(sid, isTyping) {
    const p = this.participants.get(sid);
    if (p) {
      p.is_typing = isTyping;
      this.render();
    }
  }

  render() {
    if (!this.container) return;
    this.container.innerHTML = "";

    const count = this.participants.size;
    const badge = document.createElement("span");
    badge.className = "presence-count";
    badge.textContent = `${count} online`;
    this.container.appendChild(badge);

    for (const [sid, p] of this.participants.entries()) {
      const avatar = document.createElement("div");
      avatar.className = "participant-avatar";
      avatar.style.backgroundColor = p.color || "#3b82f6";
      avatar.title = p.user_name || "Anonymous";

      const initials = (p.user_name || "A")
        .split(" ")
        .map((n) => n[0])
        .slice(0, 2)
        .join("")
        .toUpperCase();
      avatar.textContent = initials;

      if (p.is_typing) {
        avatar.classList.add("typing");
        const typingDot = document.createElement("span");
        typingDot.className = "typing-pulse-dot";
        avatar.appendChild(typingDot);
      }

      this.container.appendChild(avatar);
    }
  }
}
