export type FinanceTerm = {
  term: string;
  group: string;
  use: string;
  definition: string;
};

export type SoftwarePackage = {
  name: string;
  group: string;
  purpose: string;
};

export type SoftwareProject = {
  name: string;
  description: string;
};

export type SoftwareLang = {
  name: string;
  usage: string;
};

export type ApiBasic = {
  item: string;
  details: string;
};

export type ApiEndpoint = {
  method: string;
  path: string;
  group: string;
  description: string;
};
