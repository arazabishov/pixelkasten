import cliProgress from "cli-progress";

export function progressBar(format) {
  const bar = new cliProgress.SingleBar(
    {
      format,
      hideCursor: true,
    },
    cliProgress.Presets.shades_classic
  );

  return {
    start: (...args) => {
      bar.start(...args);
    },
    increment: (...args) => {
      bar.increment(...args);
    },
    stop: (...args) => {
      bar.stop(...args);
    },
  };
}
