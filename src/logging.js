import { consola } from "consola";

export function canShowProgress() {
  return consola.level < 4;
}
