import cliProgress from "cli-progress";
import { logger } from "../logger.js";

export function progressBar(format) {
  const bar = !logger.verbose
    ? new cliProgress.SingleBar(
        {
          format,
          hideCursor: true,
        },
        cliProgress.Presets.shades_classic
      )
    : null;

  return {
    start: (...args) => {
      bar?.start(...args);
    },
    update: (...args) => {
      bar?.update(...args);
    },
    stop: (...args) => {
      bar?.stop(...args);
    },
  };
}
