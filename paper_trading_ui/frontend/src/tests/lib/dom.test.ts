// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";

import { find, findAll } from "../../lib/dom";

describe("find", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("returns the matching element when it exists", () => {
    document.body.innerHTML = `<div id="target"></div>`;
    const el = find<HTMLDivElement>("#target");
    expect(el).not.toBeNull();
    expect(el?.id).toBe("target");
  });

  it("returns null when no element matches", () => {
    document.body.innerHTML = `<div id="other"></div>`;
    const el = find("#missing");
    expect(el).toBeNull();
  });

  it("scopes search to a provided root element", () => {
    document.body.innerHTML = `
      <div id="scope"><span class="inner"></span></div>
      <span class="inner"></span>
    `;
    const scope = document.getElementById("scope")!;
    const el = find<HTMLSpanElement>(".inner", scope);
    expect(el).not.toBeNull();
    // Should find the one inside scope, not the second one — both match but
    // querySelector from scope returns the first child.
    expect(el?.parentElement?.id).toBe("scope");
  });
});

describe("findAll", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("returns all matching elements", () => {
    document.body.innerHTML = `<li class="item"></li><li class="item"></li><li class="item"></li>`;
    const items = findAll<HTMLLIElement>(".item");
    expect(items.length).toBe(3);
  });

  it("returns an empty NodeList when nothing matches", () => {
    document.body.innerHTML = `<div></div>`;
    const items = findAll(".missing");
    expect(items.length).toBe(0);
  });

  it("scopes search to a provided root element", () => {
    document.body.innerHTML = `
      <ul id="list"><li class="row"></li><li class="row"></li></ul>
      <li class="row"></li>
    `;
    const list = document.getElementById("list")!;
    const rows = findAll<HTMLLIElement>(".row", list);
    expect(rows.length).toBe(2);
  });
});
