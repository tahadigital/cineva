import type { Config, Context } from "@netlify/functions";
import { getDatabase } from "@netlify/database";
import { handleApiRequest } from "./cloud-core.mjs";

const db = getDatabase();

export default async (req: Request, context: Context) => {
  return handleApiRequest(req, {
    ip: context.ip || "0.0.0.0",
    db,
    env: (name: string) => Netlify.env.get(name) ?? "",
  });
};

export const config: Config = {
  path: "/api/v1/*",
};
