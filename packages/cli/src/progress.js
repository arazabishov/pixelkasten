import cliProgress from "cli-progress";

export function progressBar() {
  const bar = new cliProgress.SingleBar(
    {
      format: "⧗ {bar} {percentage}% | {value}/{total}",
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
