import type { AdminSection } from "./types";


export interface AdminSectionsController {
  initialize: () => void;
  wireActions: () => void;
}


export function createAdminSectionsController(): AdminSectionsController {
  let activeAdminSection: AdminSection = "jobs";

  function setActiveAdminSection(section: AdminSection): void {
    activeAdminSection = section;
    const buttons = Array.from(document.querySelectorAll<HTMLButtonElement>("[data-admin-section-target]"));
    const panels = Array.from(document.querySelectorAll<HTMLElement>("[data-admin-section-panel]"));
    for (const button of buttons) {
      button.classList.toggle("active", button.dataset.adminSectionTarget === section);
    }
    for (const panel of panels) {
      panel.hidden = panel.dataset.adminSectionPanel !== section;
    }
  }

  function wireActions(): void {
    const adminSectionButtons = Array.from(document.querySelectorAll<HTMLButtonElement>("[data-admin-section-target]"));
    for (const button of adminSectionButtons) {
      button.addEventListener("click", () => {
        const section = button.dataset.adminSectionTarget as AdminSection | undefined;
        if (!section) return;
        setActiveAdminSection(section);
      });
    }
  }

  function initialize(): void {
    setActiveAdminSection(activeAdminSection);
  }

  return {
    initialize,
    wireActions,
  };
}
