export function find<T extends Element>(selector: string, root: ParentNode = document): T | null {
  return root.querySelector<T>(selector);
}

export function findAll<T extends Element>(selector: string, root: ParentNode = document): NodeListOf<T> {
  return root.querySelectorAll<T>(selector);
}
