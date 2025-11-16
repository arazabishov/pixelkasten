export const logger = {
  verbose: false,

  debug(...args) {
    if (this.verbose) {
      console.log(...args);
    }
  },

  info(...args) {
    console.log(...args);
  },

  warn(...args) {
    console.warn(...args);
  },

  error(...args) {
    console.error(...args);
  },
};

export function canShowProgress() {
  return !logger.verbose;
}
