export type DocsSectionLink = {
  groupLabel: string;
  sectionId: string;
  sectionTitle: string;
};

export type DocsSectionButtonIndex = Map<string, HTMLButtonElement[]>;

export type DocsSectionElementLink = DocsSectionLink & {
  element: HTMLElement;
};
