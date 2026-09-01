import { resolveConfig } from "./config.mjs";
import { registerPdf2zhTools } from "./tools.mjs";

export const name = "dsh-pdf2zh";
export const inject = ["tools"];

export function apply(ctx, input = {}) {
  const config = resolveConfig(input);
  registerPdf2zhTools(ctx, config);
  ctx.logger?.info("[dsh-pdf2zh] tools registered (python=%s repo=%s)", config.python, config.repo);
}
