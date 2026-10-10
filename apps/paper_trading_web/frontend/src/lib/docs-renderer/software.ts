import softwareData from "../../assets/software.json";
import { esc } from "./shared";
import type { SoftwareLang, SoftwarePackage, SoftwareProject } from "./types";

const SOFTWARE_PACKAGE_GROUP_ORDER = [
  "Data & Market Access",
  "Analysis & Modeling",
  "Visualization",
  "Backend & Validation",
  "Developer Tooling",
];

function buildPackagesSection(packages: SoftwarePackage[]): string {
  const grouped: Record<string, SoftwarePackage[]> = {};
  for (const softwarePackage of packages) {
    (grouped[softwarePackage.group] ??= []).push(softwarePackage);
  }

  const orderedGroups = [
    ...SOFTWARE_PACKAGE_GROUP_ORDER.filter((group) => grouped[group]),
    ...Object.keys(grouped)
      .filter((group) => !SOFTWARE_PACKAGE_GROUP_ORDER.includes(group))
      .sort(),
  ];

  const parts = orderedGroups.map((group) => {
    const rows = grouped[group]
      .map((softwarePackage) => `          <tr><td>${esc(softwarePackage.name)}</td><td>${esc(softwarePackage.purpose)}</td></tr>`)
      .join("\n");
    return `      <p class="ref-subsection-label">${esc(group)}</p>
      <table class="ref-table ref-table--software">
        <thead><tr><th>Package</th><th>Purpose</th></tr></thead>
        <tbody>
${rows}
        </tbody>
      </table>`;
  });

  return `    <div class="ref-section">
      <h3>Key Python Packages</h3>
${parts.join("\n\n")}
    </div>`;
}

export function buildSoftwareCard(): string {
  const projects = softwareData.projects as SoftwareProject[];
  const langs = softwareData.languages_frameworks as SoftwareLang[];
  const packages = softwareData.packages as SoftwarePackage[];

  const projectRows = projects
    .map((project) => `          <tr><td>${esc(project.name)}</td><td>${esc(project.description)}</td></tr>`)
    .join("\n");

  const langRows = langs
    .map((lang) => `          <tr><td>${esc(lang.name)}</td><td>${esc(lang.usage)}</td></tr>`)
    .join("\n");

  return `  <section class="card ref-card">
    <div class="ref-card-head">
      <h2>Software</h2>
      <button type="button" class="ref-card-toggle-all" data-ref-card-toggle-all aria-label="Expand all" data-tooltip="Expand all">+</button>
    </div>

    <div class="ref-section">
      <h3>Projects in This Repository</h3>
      <table class="ref-table ref-table--software">
        <thead><tr><th>Project</th><th>Description</th></tr></thead>
        <tbody>
${projectRows}
        </tbody>
      </table>
    </div>

    <div class="ref-section">
      <h3>Languages and Frameworks</h3>
      <table class="ref-table ref-table--software">
        <thead><tr><th>Language / Framework</th><th>Usage</th></tr></thead>
        <tbody>
${langRows}
        </tbody>
      </table>
    </div>

${buildPackagesSection(packages)}
  </section>`;
}
