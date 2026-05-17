declare module "node:fs" {
  export function readFileSync(path: URL | string, encoding: string): string;
}
