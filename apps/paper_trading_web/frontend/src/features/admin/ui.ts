export function setHtml(target: HTMLElement, className: string, html: string): void {
  target.className = className;
  target.innerHTML = html;
}


export function setOutput(
  target: HTMLElement,
  state: "empty" | "error" | "success",
  message: string,
  asHtml: boolean = false,
): void {
  target.className = state;
  if (asHtml) {
    target.innerHTML = message;
  } else {
    target.textContent = message;
  }
}
