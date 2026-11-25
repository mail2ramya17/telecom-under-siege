// Minimal Node.js globals used by the CLI, so the project builds without @types/node.
declare const process: {
  argv: string[];
  exitCode?: number;
  exit(code?: number): never;
};
